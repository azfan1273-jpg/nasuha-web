"""Predict Today — hitung pelanggan yang prediksinya jatuh hari ini."""

import logging
from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median

from services.predict_today.config import (
    MATCH_DELTA_MAX, MATCH_DELTA_MIN,
    MAX_CYCLE_DAYS, MAX_RELATIVE_DEVIATION,
    MIN_CYCLE_DAYS, MIN_SERVICE_USAGE,
    MIN_TRANSACTIONS_FOR_PREDICTION,
)
from services.predict_today.scoring import calculate_score, get_confidence_level
from services.shared.customer_utils import get_customer_code, get_customer_name, get_phone
from services.shared.datetime_utils import (
    get_local_today, parse_datetime, resolve_timezone, to_local, utc_now,
)
from services.shared.order_utils import (
    build_service_stats, extract_services_from_order, get_order_price, is_cancelled_order,
)

logger = logging.getLogger(__name__)


def calculate_today_prediction(orders, timezone_str):
    """Return {predictions, top_services, metadata}."""
    today_local = get_local_today(timezone_str)
    now_utc = utc_now()
    now_local = to_local(now_utc, timezone_str)
    tz = resolve_timezone(timezone_str)
    skipped = []

    if not orders:
        return _empty_result(today_local, timezone_str, now_utc, now_local)

    historical = []
    for o in orders:
        if is_cancelled_order(o):
            continue
        dt = parse_datetime(o.get("created_at"))
        if not dt:
            continue
        d_local = dt.astimezone(tz).date()
        if d_local >= today_local:
            continue
        historical.append((o, d_local))

    service_stats = build_service_stats(orders)
    routine_services = {
        s for s, st in service_stats.items()
        if st["order_count"] >= MIN_SERVICE_USAGE
    }
    top_services_summary = _build_top_services(service_stats, routine_services)

    customer_dates = defaultdict(lambda: defaultdict(list))
    customer_meta = {}
    for o, d_local in historical:
        code = get_customer_code(o)
        if not code:
            continue
        customer_dates[code][d_local].append(o)
        if code not in customer_meta:
            customer_meta[code] = {
                "name": get_customer_name(o),
                "phone": get_phone(o),
            }

    predictions = []
    for code, dates_map in customer_dates.items():
        result = _analyze_customer(
            code, dates_map, customer_meta[code], today_local, skipped,
        )
        if result:
            predictions.append(result)

    predictions.sort(
        key=lambda x: (x["score"], x["transaction_count"], x["total_spend"]),
        reverse=True,
    )
    for i, p in enumerate(predictions, 1):
        p["rank"] = i

    return {
        "predictions": predictions,
        "top_services": top_services_summary,
        "metadata": {
            "total_orders": len(orders),
            "historical_orders_used": len(historical),
            "total_customers": len(customer_dates),
            "customers_analyzed": len(customer_dates),
            "customers_shown": len(predictions),
            "skipped": skipped[:20],
            "prediction_date": today_local.isoformat(),
            "timezone": timezone_str,
            "now_utc": now_utc.isoformat(),
            "now_local": now_local.isoformat() if now_local else None,
            "algorithm": "predict-today-v5.1",
            "match_window": [MATCH_DELTA_MIN, MATCH_DELTA_MAX],
        },
    }


def _empty_result(today_local, timezone_str, now_utc, now_local):
    return {
        "top_services": [],
        "predictions": [],
        "metadata": {
            "total_orders": 0, "historical_orders_used": 0,
            "total_customers": 0, "customers_analyzed": 0,
            "customers_shown": 0, "skipped": [],
            "prediction_date": today_local.isoformat(),
            "timezone": timezone_str,
            "now_utc": now_utc.isoformat(),
            "now_local": now_local.isoformat() if now_local else None,
            "algorithm": "predict-today-v5.1",
            "match_window": [MATCH_DELTA_MIN, MATCH_DELTA_MAX],
        },
    }


def _build_top_services(service_stats, routine_services):
    out = []
    for service, stats in sorted(
        service_stats.items(),
        key=lambda x: (x[1]["order_count"], x[1]["revenue"]),
        reverse=True,
    ):
        out.append({
            "service_name": service,
            "usage_count": round(stats["usage_count"], 2),
            "total_orders": stats["order_count"],
            "revenue": round(stats["revenue"]),
            "is_routine": service in routine_services,
        })
    return out


def _analyze_customer(code, dates_map, meta, today_local, skipped):
    name = meta["name"]
    unique_dates = sorted(dates_map.keys())

    if len(unique_dates) < MIN_TRANSACTIONS_FOR_PREDICTION:
        skipped.append({"code": code, "name": name,
                        "reason": f"cuma {len(unique_dates)}x kunjungan unik"})
        return None

    intervals = _extract_intervals(unique_dates)
    if not intervals:
        skipped.append({"code": code, "name": name, "reason": "nggak ada interval valid"})
        return None

    median_cycle = max(1, round(median(intervals)))
    deviation = sum(abs(x - median_cycle) for x in intervals) / len(intervals)

    if median_cycle > 0 and (deviation / median_cycle) > MAX_RELATIVE_DEVIATION:
        skipped.append({"code": code, "name": name,
                        "reason": f"pola liar (rel-dev {deviation / median_cycle:.2f})"})
        return None

    last_tx_date = unique_dates[-1]
    predicted_date = last_tx_date + timedelta(days=median_cycle)
    delta = (predicted_date - today_local).days

    if not (MATCH_DELTA_MIN <= delta <= MATCH_DELTA_MAX):
        skipped.append({"code": code, "name": name,
                        "reason": f"prediksi {predicted_date.isoformat()} (delta {delta})"})
        return None

    agg = _aggregate_transactions(dates_map)
    score = calculate_score(delta, deviation, median_cycle, agg["tx_count"])

    return {
        "customer_code": code,
        "customer_name": name,
        "customer_phone": meta["phone"],
        "prediction_target_date": today_local.isoformat(),
        "rank": 1,
        "score": score,
        "tag": "Reguler",
        "cycle_days": float(median_cycle),
        "cycle_deviation": float(round(deviation, 2)),
        "days_since_last": (today_local - last_tx_date).days,
        "transaction_count": agg["tx_count"],
        "total_spend": round(agg["total_spend"]),
        "avg_spend": round(agg["avg_spend"]),
        "est_spend": round(agg["est_spend"]),
        "favorite_service": agg["favorite_service"],
        "reason": f"Siklus {median_cycle} hari",
        "reason_secondary": f"Prediksi: {predicted_date.isoformat()}",
        "prediction_status": "Hari ini" if delta == 0 else "Kemarin",
        "confidence_level": get_confidence_level(score),
        "last_transaction": last_tx_date.isoformat(),
        "is_carry_over": False,
        "carry_over_count": 0,
    }


def _extract_intervals(unique_dates):
    out = []
    for i in range(1, len(unique_dates)):
        diff = (unique_dates[i] - unique_dates[i - 1]).days
        if MIN_CYCLE_DAYS <= diff <= MAX_CYCLE_DAYS:
            out.append(diff)
    return out


def _aggregate_transactions(dates_map):
    total_spend = 0.0
    tx_count = 0
    service_counter = Counter()

    for _, lst in dates_map.items():
        for o in lst:
            total_spend += get_order_price(o)
            tx_count += 1
            for s in extract_services_from_order(o):
                service_counter[s] += 1

    recent_prices = []
    for _, lst in sorted(dates_map.items(), reverse=True)[:3]:
        for o in lst:
            recent_prices.append(get_order_price(o))

    est_spend = median(recent_prices) if recent_prices else 0
    avg_spend = total_spend / tx_count if tx_count else 0
    favorite = service_counter.most_common(1)[0][0] if service_counter else "Laundry"

    return {
        "total_spend": total_spend,
        "tx_count": tx_count,
        "avg_spend": avg_spend,
        "est_spend": est_spend,
        "favorite_service": favorite,
    }

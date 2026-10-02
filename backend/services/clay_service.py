"""
Clay Prediction Engine v4.7.

Update dari v4.3:
    - Filter konsistensi: skip customer dengan relative deviation > 0.35.
      (Mba Eni cycle 6, dev 2.33 -> 0.39 -> skip)
    - Metadata tambah now_utc_iso & tomorrow_iso untuk verifikasi timezone.

Filosofi: pelanggan gambling (pola nggak jelas) tidak bisa diprediksi.
"""

from datetime import timedelta
from collections import defaultdict, Counter
from statistics import median

from services.shared.customer_utils import (
    get_customer_key,
    get_customer_code,
    get_customer_name,
    get_phone,
)
from services.shared.order_utils import (
    build_service_stats,
    extract_services_from_order,
    get_order_price,
)
from services.shared.cycle_utils import calculate_cycle_days
from services.shared.datetime_utils import (
    parse_datetime,
    get_local_tomorrow,
    to_local,
    utc_now,
)
from services.shared.time_pattern_utils import (
    DAY_NAMES_ID,
    analyze_day_pattern,
    analyze_hour_pattern,
    format_schedule_lines,
)


# ============================================================
# CONFIG
# ============================================================

MIN_SERVICE_USAGE = 5
MIN_TRANSACTIONS_FOR_PREDICTION = 4
TOP_PREDICTIONS_LIMIT = 8
MIN_SCORE_FOR_DISPLAY = 50

MIN_DAYS_ABSOLUTE = 2.0
MIN_DAYS_RATIO = 0.5

MIN_CYCLE_FOR_PATTERN = 6
PATTERN_STRONG_PCT = 0.45

# Filter konsistensi: skip customer kalau pola cycle-nya terlalu berantakan.
# relative_deviation = cycle_deviation / typical_cycle
MAX_RELATIVE_DEVIATION = 0.35


# ============================================================
# STATUS KONTRIBUSI
# ============================================================

def _get_contribution_status(contribution_pct):
    if contribution_pct >= 5.0:
        return "VVIP"
    if contribution_pct >= 4.0:
        return "VIP"
    if contribution_pct >= 3.0:
        return "Best"
    if contribution_pct >= 2.0:
        return "Regular"
    if contribution_pct >= 1.0:
        return "Active"
    return "Go"


# ============================================================
# SPEND
# ============================================================

def _estimate_next_spend(tx_list):
    if not tx_list:
        return 0
    recent = [tx["price"] for tx in tx_list[:3] if tx["price"] > 0]
    if not recent:
        return 0
    if len(recent) == 1:
        return round(recent[0])
    if len(recent) == 2:
        return round(sum(recent) / 2)
    return round(median(recent))


def _get_favorite_service(tx_list):
    counter = Counter()
    for idx, tx in enumerate(tx_list):
        weight = 1.0 / (idx + 1)
        for service in tx["services"]:
            counter[service] += weight
    if not counter:
        return "Tidak diketahui"
    return counter.most_common(1)[0][0]


# ============================================================
# MIN DAYS
# ============================================================

def _is_too_early(days_since_last, typical_cycle):
    min_gap = max(MIN_DAYS_ABSOLUTE, typical_cycle * MIN_DAYS_RATIO)
    return days_since_last < min_gap


# ============================================================
# KONSISTENSI (v4.7 BARU)
# ============================================================

def _is_inconsistent(cycle_deviation, typical_cycle):
    """
    Cek apakah pola cycle customer terlalu berantakan untuk diprediksi.

    relative_deviation = cycle_deviation / typical_cycle

    Contoh:
        Mba Eni: cycle=6, dev=2.33 -> 0.39 -> INCONSISTENT (> 0.35)
        Cici   : cycle=5, dev=1.50 -> 0.30 -> OK
        Bu Era : cycle=4, dev=0.50 -> 0.13 -> OK (konsisten)
    """
    if typical_cycle <= 0:
        return True
    return (cycle_deviation / typical_cycle) > MAX_RELATIVE_DEVIATION


# ============================================================
# DAY PATTERN MODIFIER
# ============================================================

def _day_pattern_modifier(tomorrow, day_info, typical_cycle):
    if typical_cycle < MIN_CYCLE_FOR_PATTERN:
        return 1.0
    if not day_info or not day_info.get("has_strong"):
        return 1.0

    tomorrow_day = DAY_NAMES_ID[tomorrow.weekday()]
    if tomorrow_day == day_info["primary"][0]:
        return 1.0
    if day_info.get("secondary") and tomorrow_day == day_info["secondary"][0]:
        return 1.0

    primary_pct = day_info["primary"][1]
    if primary_pct >= PATTERN_STRONG_PCT:
        return 0.55
    return 0.80


# ============================================================
# SCORING
# ============================================================

def _calculate_prediction_score(
    predicted_return_date,
    tomorrow,
    cycle_deviation,
    transaction_count,
    day_pattern_multiplier=1.0,
):
    delta = (predicted_return_date - tomorrow).days

    if delta == 0:
        timing = 100
    elif delta == -1:
        timing = 82
    elif delta == 1:
        timing = 78
    elif delta == -2:
        timing = 55
    elif delta == 2:
        timing = 50
    else:
        timing = max(5, 25 - (abs(delta) - 2) * 8)

    if cycle_deviation <= 1:
        consistency = 1.00
    elif cycle_deviation <= 2:
        consistency = 0.95
    elif cycle_deviation <= 3:
        consistency = 0.88
    elif cycle_deviation <= 5:
        consistency = 0.78
    else:
        consistency = 0.65

    if transaction_count >= 10:
        history = 1.00
    elif transaction_count >= 7:
        history = 0.96
    elif transaction_count >= 5:
        history = 0.92
    elif transaction_count >= 4:
        history = 0.85
    else:
        history = 0.75

    score = timing * consistency * history * day_pattern_multiplier
    return max(0, min(100, round(score)))


def _get_confidence_level(transaction_count, cycle_deviation):
    if transaction_count >= 8 and cycle_deviation <= 2:
        return "Tinggi"
    if transaction_count >= 5 and cycle_deviation <= 4:
        return "Sedang"
    return "Rendah"


# ============================================================
# MAIN
# ============================================================

def calculate_tomorrow_prediction(orders, timezone_str):
    tomorrow = get_local_tomorrow(timezone_str)
    now_utc = utc_now()
    now_local = to_local(now_utc, timezone_str)

    if not orders:
        return {
            "top_services": [], "predictions": [],
            "metadata": {
                "total_orders": 0, "total_customers": 0,
                "customers_analyzed": 0, "customers_shown": 0,
                "prediction_date": tomorrow.isoformat(),
                "timezone": timezone_str,
                "now_utc": now_utc.isoformat(),
                "now_local": now_local.isoformat() if now_local else None,
                "algorithm": "median-cycle-v4.7",
            },
        }

    # 1. Service stats
    service_stats = build_service_stats(orders)
    routine_services = {
        s for s, st in service_stats.items()
        if st["order_count"] >= MIN_SERVICE_USAGE
    }

    top_services_summary = []
    for service, stats in sorted(
        service_stats.items(),
        key=lambda x: (x[1]["order_count"], x[1]["revenue"]),
        reverse=True,
    ):
        top_services_summary.append({
            "service_name": service,
            "usage_count": round(stats["usage_count"], 2),
            "total_orders": stats["order_count"],
            "revenue": round(stats["revenue"]),
            "is_routine": service in routine_services,
        })

    # 2. Revenue
    total_store_revenue = sum(get_order_price(o) for o in orders)

    # 3. Group per customer
    customer_map = defaultdict(list)
    for order in orders:
        created_at = parse_datetime(order.get("created_at"))
        if not created_at:
            continue
        customer_key = get_customer_key(order)
        services = extract_services_from_order(order) or ["Tidak diketahui"]
        routine_used = [s for s in services if s in routine_services]
        selected = routine_used if routine_used else services

        customer_map[customer_key].append({
            "customer_code": get_customer_code(order),
            "name": get_customer_name(order),
            "phone": get_phone(order),
            "price": get_order_price(order),
            "services": selected,
            "date": created_at,
        })

    # 4. Loop prediksi
    predictions = []
    skipped = []

    for customer_key, tx_list in customer_map.items():
        if len(tx_list) < MIN_TRANSACTIONS_FOR_PREDICTION:
            continue

        tx_list.sort(key=lambda x: x["date"], reverse=True)
        last_tx = tx_list[0]
        last_tx_date = last_tx["date"]
        customer_name = last_tx["name"]
        total_tx = len(tx_list)

        days_since_last = max(
            0.0, (now_utc - last_tx_date).total_seconds() / 86400,
        )

        typical_cycle, _, cycle_deviation = calculate_cycle_days(tx_list)
        if typical_cycle is None:
            continue

        # === FILTER 1: min days ===
        if _is_too_early(days_since_last, typical_cycle):
            min_gap = max(MIN_DAYS_ABSOLUTE, typical_cycle * MIN_DAYS_RATIO)
            skipped.append({
                "name": customer_name,
                "reason": f"terlalu cepat ({days_since_last:.1f}h < {min_gap:.1f}h)",
            })
            continue

        # === FILTER 2: konsistensi (v4.7) ===
        if _is_inconsistent(cycle_deviation, typical_cycle):
            rel = cycle_deviation / typical_cycle if typical_cycle else 0
            skipped.append({
                "name": customer_name,
                "reason": f"pola tidak konsisten (rel-dev {rel:.2f} > {MAX_RELATIVE_DEVIATION})",
            })
            continue

        # Predicted return date (zona toko)
        last_tx_local = to_local(last_tx_date, timezone_str)
        predicted_local = last_tx_local + timedelta(days=typical_cycle)
        predicted_date = predicted_local.date()
        delta_to_tomorrow = (predicted_date - tomorrow).days

        if delta_to_tomorrow < -1 or delta_to_tomorrow > 0:
            continue

        day_info = analyze_day_pattern(tx_list, timezone_str)
        hour_info = analyze_hour_pattern(tx_list, timezone_str)
        pattern_multiplier = _day_pattern_modifier(tomorrow, day_info, typical_cycle)

        total_spend = sum(tx["price"] for tx in tx_list)
        avg_spend = round(total_spend / total_tx) if total_tx > 0 else 0
        est_spend = _estimate_next_spend(tx_list)

        favorite_service = _get_favorite_service(tx_list)

        contribution_pct = (
            round(total_spend / total_store_revenue * 100, 2)
            if total_store_revenue > 0 else 0
        )
        tag = _get_contribution_status(contribution_pct)

        score = _calculate_prediction_score(
            predicted_return_date=predicted_date,
            tomorrow=tomorrow,
            cycle_deviation=cycle_deviation,
            transaction_count=total_tx,
            day_pattern_multiplier=pattern_multiplier,
        )

        if score < MIN_SCORE_FOR_DISPLAY:
            skipped.append({
                "name": customer_name,
                "reason": f"skor {score} < {MIN_SCORE_FOR_DISPLAY}",
            })
            continue

        reason_primary, reason_secondary = format_schedule_lines(
            cycle_days=typical_cycle,
            day_info=day_info,
            hour_info=hour_info,
        )

        confidence_level = _get_confidence_level(total_tx, cycle_deviation)

        predictions.append({
            "customer_code": last_tx["customer_code"],
            "name": last_tx["name"],
            "phone": last_tx["phone"],
            "tag": tag,
            "score": score,
            "reason": reason_primary,
            "reason_secondary": reason_secondary,
            "prediction_status": "Besok" if delta_to_tomorrow == 0 else "Sekitar besok",
            "prediction_date": predicted_date.isoformat(),
            "last_transaction": last_tx_date.isoformat(),
            "days_since_last": round(days_since_last, 1),
            "cycle_days": typical_cycle,
            "cycle_deviation": round(cycle_deviation, 2),
            "transaction_count": total_tx,
            "total_spend": round(total_spend),
            "avg_spend": avg_spend,
            "est_spend": est_spend,
            "favorite_service": favorite_service,
            "contribution_percent": contribution_pct,
            "contribution": f"{contribution_pct}%",
            "confidence_level": confidence_level,
            "pattern_multiplier": round(pattern_multiplier, 2),
        })

    # 5. Sort & limit
    predictions.sort(
        key=lambda x: (x["score"], x["transaction_count"], x["total_spend"]),
        reverse=True,
    )
    top_predictions = predictions[:TOP_PREDICTIONS_LIMIT]

    return {
        "top_services": top_services_summary,
        "predictions": top_predictions,
        "metadata": {
            "total_orders": len(orders),
            "total_customers": len(customer_map),
            "customers_analyzed": len(predictions),
            "customers_shown": len(top_predictions),
            "skipped": skipped[:15],
            "prediction_date": tomorrow.isoformat(),
            "timezone": timezone_str,
            "now_utc": now_utc.isoformat(),
            "now_local": now_local.isoformat() if now_local else None,
            "algorithm": "median-cycle-v4.7",
        },
    }

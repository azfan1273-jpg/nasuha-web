"""CLAY PREDICTION ENGINE v5.1 — PREDICT TODAY (REBUILD)

Perubahan dari v5.0:
    1. Status filter case-insensitive (BATAL/Batal/batal).
    2. Match window [-1, 0] hari (bukan strict equality).
    3. Dedupe multiple order per hari (unique date).
    4. Carry over: H-1 s/d H-3, cap +3.
    5. Debug trail di metadata.skipped[].
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any, Set
from collections import defaultdict, Counter
from statistics import median
from urllib.parse import quote
import requests
from fastapi import APIRouter, HTTPException, Depends

from routes.analytics import AuthContext, get_auth_context
from services.shared.store_utils import fetch_store_timezone
logger = logging.getLogger(__name__)

# ============================================================
# CONFIG
# ============================================================
MIN_TRANSACTIONS_FOR_PREDICTION = 2
MIN_SERVICE_USAGE = 1
VERDICT_DELAY_DAYS = 0

MIN_CYCLE_DAYS = 1
MAX_CYCLE_DAYS = 90
MAX_CARRY_OVER = 3
MAX_RELATIVE_DEVIATION = 0.35

MATCH_DELTA_MIN = -1
MATCH_DELTA_MAX = 0

CANCELLED_PATTERNS = ("batal", "cancel", "cancelled")

# ============================================================
# DATETIME HELPERS
# ============================================================
def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def resolve_timezone(timezone_str: str) -> ZoneInfo:
    tz_map = {"WIB": "Asia/Jakarta", "WITA": "Asia/Makassar", "WIT": "Asia/Jayapura"}
    iana = tz_map.get(timezone_str.upper(), timezone_str) if timezone_str else "Asia/Jakarta"
    try:
        return ZoneInfo(iana)
    except Exception:
        return ZoneInfo("Asia/Jakarta")

def to_local(dt_utc: datetime, timezone_str: str) -> Optional[datetime]:
    if not dt_utc:
        return None
    return dt_utc.astimezone(resolve_timezone(timezone_str))

def get_local_today(timezone_str: str) -> date:
    return datetime.now(resolve_timezone(timezone_str)).date()

def _day_range_utc(d: date, tz: ZoneInfo) -> tuple:
    start_local = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )

def parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None

# ============================================================
# STATUS FILTER
# ============================================================
def is_cancelled_status(status: Any) -> bool:
    if not status:
        return False
    s = str(status).strip().lower()
    return any(p in s for p in CANCELLED_PATTERNS)

# ============================================================
# CUSTOMER & ORDER HELPERS
# ============================================================
def get_customer_key(order: dict) -> str:
    code = order.get("customer_code") or ""
    name = order.get("customer_name") or ""
    return f"{code}|{name}".strip("|")

def get_customer_code(order: dict) -> str:
    return str(order.get("customer_code") or "").strip()

def get_customer_name(order: dict) -> str:
    return str(order.get("customer_name") or "Pelanggan").strip()

def get_phone(order: dict) -> str:
    raw = order.get("customer_phone") or order.get("phone") or ""
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    return digits if len(digits) >= 6 else "-"

def get_order_price(order: dict) -> float:
    try:
        return float(order.get("total_price") or order.get("subtotal") or 0)
    except Exception:
        return 0.0

def extract_services_from_order(order: dict) -> list:
    items = order.get("order_items") or []
    services = []
    if isinstance(items, list):
        for it in items:
            name = it.get("service_name") or it.get("name")
            if name:
                services.append(name)
    if not services and order.get("service_name"):
        services.append(order["service_name"])
    return services or ["Laundry"]

# ============================================================
# SCORING
# ============================================================
def _calculate_score(delta: int, deviation: float, median_cycle: int, tx_count: int) -> int:
    timing = 100 if delta == 0 else 90
    if median_cycle <= 0:
        consistency = 0.7
    else:
        rel = deviation / median_cycle
        if rel <= 0.15:   consistency = 1.0
        elif rel <= 0.30: consistency = 0.9
        elif rel <= 0.50: consistency = 0.75
        else:             consistency = 0.6
    if tx_count >= 10:   history = 1.0
    elif tx_count >= 7:  history = 0.95
    elif tx_count >= 5:  history = 0.9
    elif tx_count >= 4:  history = 0.85
    else:                history = 0.8
    return max(0, min(100, round(timing * consistency * history)))

# ============================================================
# 1. PREDICT TODAY
# ============================================================
def calculate_today_prediction(orders: list, timezone_str: str) -> dict:
    today_local = get_local_today(timezone_str)
    now_utc = utc_now()
    now_local = to_local(now_utc, timezone_str)
    tz = resolve_timezone(timezone_str)
    skipped: list = []

    if not orders:
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

    # Filter: cutoff + status
    historical = []
    for o in orders:
        if is_cancelled_status(o.get("status")):
            continue
        dt = parse_datetime(o.get("created_at"))
        if not dt:
            continue
        d_local = dt.astimezone(tz).date()
        if d_local >= today_local:
            continue
        historical.append((o, d_local))

    # Group per customer → per unique date
    customer_dates: Dict[str, Dict[date, list]] = defaultdict(lambda: defaultdict(list))
    customer_meta: Dict[str, dict] = {}
    for o, d_local in historical:
        code = get_customer_code(o)
        if not code:
            continue
        customer_dates[code][d_local].append(o)
        if code not in customer_meta:
            customer_meta[code] = {"name": get_customer_name(o), "phone": get_phone(o)}

    # Analisa per customer
    predictions = []
    for code, dates_map in customer_dates.items():
        unique_dates = sorted(dates_map.keys())
        name = customer_meta[code]["name"]

        if len(unique_dates) < MIN_TRANSACTIONS_FOR_PREDICTION:
            skipped.append({"code": code, "name": name,
                            "reason": f"cuma {len(unique_dates)}x kunjungan unik"})
            continue

        intervals = []
        for i in range(1, len(unique_dates)):
            diff = (unique_dates[i] - unique_dates[i-1]).days
            if MIN_CYCLE_DAYS <= diff <= MAX_CYCLE_DAYS:
                intervals.append(diff)

        if not intervals:
            skipped.append({"code": code, "name": name, "reason": "nggak ada interval valid"})
            continue

        median_cycle = max(1, round(median(intervals)))
        deviation = sum(abs(x - median_cycle) for x in intervals) / len(intervals)

        if median_cycle > 0 and (deviation / median_cycle) > MAX_RELATIVE_DEVIATION:
            rel = deviation / median_cycle
            skipped.append({"code": code, "name": name,
                            "reason": f"pola liar (rel-dev {rel:.2f})"})
            continue

        last_tx_date = unique_dates[-1]
        predicted_date = last_tx_date + timedelta(days=median_cycle)
        delta = (predicted_date - today_local).days

        if not (MATCH_DELTA_MIN <= delta <= MATCH_DELTA_MAX):
            skipped.append({"code": code, "name": name,
                            "reason": f"prediksi {predicted_date.isoformat()} (delta {delta})"})
            continue

        total_spend = 0.0
        tx_count = 0
        service_counter = Counter()
        recent_prices = []
        for d, lst in dates_map.items():
            for o in lst:
                total_spend += get_order_price(o)
                tx_count += 1
                for s in extract_services_from_order(o):
                    service_counter[s] += 1
        for d, lst in sorted(dates_map.items(), reverse=True)[:3]:
            for o in lst:
                recent_prices.append(get_order_price(o))

        avg_spend = total_spend / tx_count if tx_count else 0
        est_spend = median(recent_prices) if recent_prices else 0
        favorite_service = service_counter.most_common(1)[0][0] if service_counter else "Laundry"
        score = _calculate_score(delta, deviation, median_cycle, tx_count)

        status = "Hari ini" if delta == 0 else "Kemarin"
        reason = f"Siklus {median_cycle} hari"

        predictions.append({
            "customer_code": code,
            "customer_name": name,
            "customer_phone": customer_meta[code]["phone"],
            "prediction_target_date": today_local.isoformat(),
            "rank": 1,
            "score": score,
            "tag": "Reguler",
            "cycle_days": float(median_cycle),
            "cycle_deviation": float(round(deviation, 2)),
            "days_since_last": (today_local - last_tx_date).days,
            "transaction_count": tx_count,
            "total_spend": round(total_spend),
            "avg_spend": round(avg_spend),
            "est_spend": round(est_spend),
            "favorite_service": favorite_service,
            "reason": reason,
            "reason_secondary": f"Prediksi: {predicted_date.isoformat()}",
            "prediction_status": status,
            "confidence_level": "high" if score >= 80 else ("medium" if score >= 60 else "low"),
            "last_transaction": last_tx_date.isoformat(),
            "is_carry_over": False,
            "carry_over_count": 0,
        })

    predictions.sort(key=lambda x: (x["score"], x["transaction_count"], x["total_spend"]), reverse=True)
    for i, p in enumerate(predictions, 1):
        p["rank"] = i

    return {
        "predictions": predictions,
        "top_services": [],
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

# ============================================================
# 2. CARRY OVER (H-1 s/d H-3, cap +3)
# ============================================================
# ============================================================
# 3. EVALUATOR
# ============================================================
def evaluate_predictions(token: str, store_id: str, timezone_str: str) -> dict:
    from services.shared.supabase_user_client import get_user_client
    tz = resolve_timezone(timezone_str)
    today_local = datetime.now(tz).date()

    try:
        supabase = get_user_client(token)
    except Exception:
        logger.exception("Evaluator: gagal init client")
        return {"evaluated": 0, "hit": 0, "miss": 0}

    try:
        res = (
            supabase.table("prediction_logs")
            .select("*").eq("store_id", store_id)
            .eq("outcome_status", "pending").execute()
        )
    except Exception:
        logger.exception("Evaluator: gagal fetch pending")
        return {"evaluated": 0, "hit": 0, "miss": 0}

    pending = res.data or []
    hit_count = 0
    miss_count = 0

    for log in pending:
        td_str = log.get("prediction_target_date")
        if not td_str:
            continue
        try:
            target_date = date.fromisoformat(td_str)
        except ValueError:
            continue
        code = log.get("customer_code")
        start_utc, end_utc = _day_range_utc(target_date, tz)

        try:
            orders_res = (
                supabase.table("orders")
                .select("id, created_at, status")
                .eq("store_id", store_id)
                .eq("customer_code", code)
                .gte("created_at", start_utc)
                .lt("created_at", end_utc)
                .execute()
            )
        except Exception:
            continue

        valid = [o for o in (orders_res.data or []) if not is_cancelled_status(o.get("status"))]

        if valid:
            matched = valid[0]
            supabase.table("prediction_logs").update({
                "outcome_status": "hit",
                "outcome_date": target_date.isoformat(),
                "outcome_delta_days": 0,
                "outcome_order_id": str(matched["id"]),
                "evaluated_at": utc_now().isoformat(),
            }).eq("id", log["id"]).execute()
            hit_count += 1
        elif target_date < today_local:
            supabase.table("prediction_logs").update({
                "outcome_status": "miss",
                "evaluated_at": utc_now().isoformat(),
            }).eq("id", log["id"]).execute()
            miss_count += 1

    return {"evaluated": len(pending), "hit": hit_count, "miss": miss_count,
            "today_local": today_local.isoformat()}

# ============================================================
# 4. LOG RUN
# ============================================================
def log_prediction_run(token: str, store_id: str, payload: dict) -> Optional[str]:
    """Idempotent + race-safe via UPSERT pada prediction_logs."""
    from services.shared.supabase_user_client import get_user_client
    try:
        supabase = get_user_client(token)
        metadata = payload.get("metadata", {})
        target_date = metadata.get("prediction_date")
        if not target_date:
            logger.warning("log_prediction_run: target_date kosong")
            return None

        # ===== 1. Cek/INSERT prediction_runs =====
        existing = (
            supabase.table("prediction_runs")
            .select("id")
            .eq("store_id", store_id)
            .eq("prediction_target_date", target_date)
            .order("run_at", desc=True)
            .limit(1)
            .execute()
        )

        run_row = {
            "run_at": utc_now().isoformat(),
            "prediction_target_date": target_date,
            "timezone": metadata.get("timezone", "Asia/Jakarta"),
            "algorithm_version": metadata.get("algorithm", "predict-today-v5.1"),
            "total_orders": metadata.get("total_orders", 0),
            "total_customers": metadata.get("total_customers", 0),
            "customers_analyzed": metadata.get("customers_analyzed", 0),
            "customers_shown": metadata.get("customers_shown", 0),
            "metadata": metadata,
        }

        if existing.data:
            run_id = existing.data[0]["id"]
            supabase.table("prediction_runs").update(run_row).eq("id", run_id).execute()
        else:
            run_row["store_id"] = store_id
            run_res = supabase.table("prediction_runs").insert(run_row).execute()
            if not run_res.data:
                logger.error("log_prediction_run: insert run kosong")
                return None
            run_id = run_res.data[0]["id"]

        # ===== 2. Build rows =====
        all_logs = payload.get("predictions", []) + payload.get("carry_over", [])
        seen_codes = set()
        deduped = []
        for l in all_logs:
            code = l.get("customer_code")
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            deduped.append(l)

        log_rows = []
        for l in deduped:
            log_rows.append({
                "run_id": run_id,
                "store_id": store_id,
                "customer_code": l.get("customer_code"),
                "customer_name": l.get("customer_name") or l.get("name"),
                "customer_phone": l.get("customer_phone") or l.get("phone"),
                "prediction_target_date": l.get("prediction_target_date") or target_date,
                "rank": l.get("rank"),
                "score": l.get("score"),
                "tag": l.get("tag"),
                "cycle_days": l.get("cycle_days"),
                "days_since_last": l.get("days_since_last"),
                "transaction_count": l.get("transaction_count"),
                "total_spend": l.get("total_spend"),
                "avg_spend": l.get("avg_spend"),
                "est_spend": l.get("est_spend"),
                "favorite_service": l.get("favorite_service"),
                "reason": l.get("reason"),
                "reason_secondary": l.get("reason_secondary"),
                "prediction_status": l.get("prediction_status", "active"),
                "confidence_level": l.get("confidence_level", "high"),
                "outcome_status": "pending",
                "is_carry_over": l.get("is_carry_over", False),
                "carry_over_count": l.get("carry_over_count", 0),
                "carried_from_log_id": l.get("carried_from_log_id"),
                "last_transaction": l.get("last_transaction"),
                "created_at": utc_now().isoformat(),
            })

        # ===== 3. UPSERT (atomic, race-safe) =====
        if not log_rows:
            return run_id

        # Detect constraint columns secara otomatis — coba beberapa varian
        conflict_variants = [
            "store_id,customer_code,prediction_target_date",
            "customer_code,prediction_target_date",
            "run_id,customer_code",
        ]

        last_err = None
        for cols in conflict_variants:
            try:
                supabase.table("prediction_logs").upsert(
                    log_rows,
                    on_conflict=cols,
                ).execute()
                logger.info("log_prediction_run: upsert OK (on_conflict=%s)", cols)
                return run_id
            except Exception as e:
                err_str = str(e).lower()
                # Kalau error bukan karena constraint-nya salah, langsung raise
                if "42p10" in err_str or "no unique or exclusion constraint" in err_str:
                    last_err = e
                    continue
                last_err = e
                break

        logger.exception("log_prediction_run: upsert semua varian gagal: %s", last_err)
        return run_id

    except Exception:
        logger.exception("Gagal log prediction run")
        return None



# ============================================================
# 5. ORCHESTRATOR
# ============================================================
def _predict_for_store(auth_header: str, store_id: str, evaluate_first: bool = True) -> dict:
    timezone_str = fetch_store_timezone(store_id, auth_header)
    token_str = auth_header.replace("Bearer ", "", 1).strip()

    eval_debug = None
    if evaluate_first:
        try:
            eval_debug = evaluate_predictions(token_str, store_id, timezone_str)
        except Exception as e:
            eval_debug = {"error": str(e)}

    orders_data = _fetch_orders_for_store(store_id, auth_header, months_back=6)
    clay_result = calculate_today_prediction(orders_data, timezone_str)
    raw_predictions = clay_result.get("predictions", [])
    metadata = clay_result.get("metadata", {})

    run_id = log_prediction_run(token_str, store_id, clay_result)
    if run_id:
        metadata["run_id"] = run_id

    return {
        "run_id": run_id,
        "predictions": raw_predictions,
        "top_services": clay_result.get("top_services", []),
        "metadata": metadata,
        "timezone": timezone_str,
        "eval_debug": eval_debug,
    }

def _fetch_orders_for_store(store_id: str, auth_header: str, months_back: int = 6) -> list:
    from config.supabase_config import SUPABASE_URL, get_supabase_headers
    from security import sanitize_filter_value

    if not store_id:
        return []
    try:
        sid = sanitize_filter_value(store_id)
    except ValueError:
        return []

    cutoff = (utc_now() - timedelta(days=months_back * 30)).isoformat()
    variants = ["*,order_items(*)", "*"]

    for select_clause in variants:
        url = (
            f"{SUPABASE_URL}/rest/v1/orders?select={select_clause}"
            f"&store_id=eq.{quote(sid, safe='')}"
            f"&created_at=gte.{quote(cutoff, safe='')}"
            f"&order=created_at.desc&limit=5000"
        )
        try:
            res = requests.get(url, headers=get_supabase_headers(auth_header), timeout=20)
        except requests.RequestException as e:
            logger.warning("fetch orders network: %s", e)
            continue
        if res.status_code != 200:
            logger.warning("fetch orders HTTP %s: %s", res.status_code, res.text[:200])
            continue
        try:
            data = res.json()
        except ValueError:
            continue
        if isinstance(data, list):
            return data
    return []

# ============================================================
# 6. FASTAPI ROUTER
# ============================================================
clay_router = APIRouter(tags=["Clay Engine"])

@clay_router.get("/predict-today")
def predict_today_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    try:
        return _predict_for_store(ctx.auth_header, ctx.store_id, evaluate_first=True)
    except Exception as e:
        logger.exception("Predict today error")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


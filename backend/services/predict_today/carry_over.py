"""Predict Today — carry over (pelanggan yang lewat jadwal)."""

import logging
from collections import defaultdict
from datetime import date, timedelta

from services.predict_today.config import MAX_CARRY_OVER
from services.shared.datetime_utils import day_range_utc, parse_datetime, resolve_timezone
from services.shared.order_utils import is_cancelled_order
from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)


def build_carry_over_predictions(token, store_id, today_local, timezone_str, exclude_codes=None):
    exclude_codes = exclude_codes or set()
    tz = resolve_timezone(timezone_str)

    try:
        supabase = get_user_client(token)
    except Exception:
        logger.exception("Carry over: gagal init Supabase")
        return []

    candidate_dates = [
        (today_local - timedelta(days=i)).isoformat()
        for i in range(1, MAX_CARRY_OVER + 1)
    ]

    try:
        res = (
            supabase.table("prediction_logs").select("*")
            .eq("store_id", store_id)
            .in_("prediction_target_date", candidate_dates)
            .in_("outcome_status", ["pending", "miss"])
            .execute()
        )
    except Exception:
        logger.exception("Carry over: gagal fetch logs")
        return []

    logs = res.data or []
    if not logs:
        return []

    by_customer = defaultdict(list)
    for log in logs:
        code = log.get("customer_code")
        td = log.get("prediction_target_date")
        if not code or not td or code in exclude_codes:
            continue
        by_customer[code].append(log)

    if not by_customer:
        return []

    latest_log = {}
    for code, cust_logs in by_customer.items():
        cust_logs.sort(key=lambda x: x["prediction_target_date"])
        latest_log[code] = cust_logs[-1]

    codes = list(latest_log.keys())
    min_date = today_local - timedelta(days=MAX_CARRY_OVER)
    start_utc, _ = day_range_utc(min_date, tz)
    _, end_utc = day_range_utc(today_local + timedelta(days=1), tz)

    try:
        orders_res = (
            supabase.table("orders")
            .select("customer_code, created_at, status")
            .eq("store_id", store_id)
            .in_("customer_code", codes)
            .gte("created_at", start_utc)
            .lt("created_at", end_utc)
            .execute()
        )
    except Exception:
        logger.exception("Carry over: gagal fetch orders")
        return []

    visited_dates = defaultdict(set)
    for o in orders_res.data or []:
        if is_cancelled_order(o):
            continue
        dt = parse_datetime(o.get("created_at"))
        if not dt:
            continue
        visited_dates[o.get("customer_code")].add(dt.astimezone(tz).date())

    result = []
    for code, log in latest_log.items():
        entry = _build_entry(
            code, log, visited_dates.get(code, set()),
            today_local, supabase, store_id,
        )
        if entry:
            result.append(entry)

    result.sort(key=lambda x: (x["carry_over_count"], x["score"]), reverse=True)
    for i, r in enumerate(result, 1):
        r["rank"] = i

    return result


def _build_entry(code, log, visited, today_local, supabase, store_id):
    td_str = log["prediction_target_date"]
    try:
        target_date = date.fromisoformat(td_str)
    except ValueError:
        return None

    if any(d >= target_date for d in visited):
        return None

    prev_carry = log.get("carry_over_count") or 0
    new_carry = prev_carry + 1

    if new_carry > MAX_CARRY_OVER:
        _mark_churn(supabase, store_id, code)
        return None

    base_score = log.get("score") or 50
    new_score = max(40, base_score - 5 * new_carry)

    return {
        "customer_code": code,
        "customer_name": log.get("customer_name"),
        "customer_phone": log.get("customer_phone") or "-",
        "prediction_target_date": today_local.isoformat(),
        "rank": 1,
        "score": new_score,
        "tag": log.get("tag") or "Reguler",
        "cycle_days": log.get("cycle_days"),
        "cycle_deviation": log.get("cycle_deviation"),
        "days_since_last": (log.get("days_since_last") or 0) + 1,
        "transaction_count": log.get("transaction_count"),
        "total_spend": log.get("total_spend"),
        "avg_spend": log.get("avg_spend"),
        "est_spend": log.get("est_spend"),
        "favorite_service": log.get("favorite_service"),
        "reason": f"Telat {new_carry} hari dari jadwal",
        "reason_secondary": f"Target: {td_str}",
        "prediction_status": "Telat",
        "confidence_level": log.get("confidence_level") or "medium",
        "last_transaction": log.get("last_transaction"),
        "is_carry_over": True,
        "carry_over_count": new_carry,
        "carried_from_log_id": log.get("id"),
    }


def _mark_churn(supabase, store_id, code):
    try:
        supabase.table("prediction_logs").update({
            "prediction_status": "churn_potential",
            "outcome_status": "miss",
        }).eq("store_id", store_id).eq("customer_code", code).in_(
            "outcome_status", ["pending", "miss"]
        ).execute()
        logger.info("Carry over: customer %s → churn_potential", code)
    except Exception:
        logger.exception("Gagal update churn untuk %s", code)

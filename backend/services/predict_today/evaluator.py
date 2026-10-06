"""Predict Today — evaluasi hit/miss."""

import logging
from datetime import date, datetime

from services.shared.datetime_utils import day_range_utc, resolve_timezone, utc_now
from services.shared.order_utils import is_cancelled_order
from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)


def evaluate_predictions(token, store_id, timezone_str):
    tz = resolve_timezone(timezone_str)
    today_local = datetime.now(tz).date()

    try:
        supabase = get_user_client(token)
    except Exception:
        logger.exception("Evaluator: gagal init client")
        return _empty(today_local)

    try:
        res = (
            supabase.table("prediction_logs").select("*")
            .eq("store_id", store_id).eq("outcome_status", "pending").execute()
        )
    except Exception:
        logger.exception("Evaluator: gagal fetch pending")
        return _empty(today_local)

    pending = res.data or []
    hit = miss = 0

    for log in pending:
        outcome = _evaluate_one(log, supabase, store_id, tz, today_local)
        if outcome == "hit":    hit += 1
        elif outcome == "miss": miss += 1

    return {
        "evaluated": len(pending),
        "hit": hit,
        "miss": miss,
        "today_local": today_local.isoformat(),
    }


def _evaluate_one(log, supabase, store_id, tz, today_local):
    td_str = log.get("prediction_target_date")
    if not td_str:
        return None
    try:
        target_date = date.fromisoformat(td_str)
    except ValueError:
        return None

    code = log.get("customer_code")
    start_utc, end_utc = day_range_utc(target_date, tz)

    try:
        orders_res = (
            supabase.table("orders")
            .select("id, created_at, status")
            .eq("store_id", store_id).eq("customer_code", code)
            .gte("created_at", start_utc).lt("created_at", end_utc).execute()
        )
    except Exception:
        logger.exception("Evaluator: fetch orders gagal untuk log %s", log.get("id"))
        return None

    valid = [o for o in (orders_res.data or []) if not is_cancelled_order(o)]
    now_iso = utc_now().isoformat()

    if valid:
        try:
            supabase.table("prediction_logs").update({
                "outcome_status": "hit",
                "outcome_date": target_date.isoformat(),
                "outcome_delta_days": 0,
                "outcome_order_id": str(valid[0]["id"]),
                "evaluated_at": now_iso,
            }).eq("id", log["id"]).execute()
        except Exception:
            logger.exception("Evaluator: update hit gagal")
        return "hit"

    if target_date < today_local:
        try:
            supabase.table("prediction_logs").update({
                "outcome_status": "miss",
                "evaluated_at": now_iso,
            }).eq("id", log["id"]).execute()
        except Exception:
            logger.exception("Evaluator: update miss gagal")
        return "miss"

    return None


def _empty(today_local):
    return {"evaluated": 0, "hit": 0, "miss": 0, "today_local": today_local.isoformat()}

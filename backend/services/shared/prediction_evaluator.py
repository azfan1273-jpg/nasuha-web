"""
Evaluator: cocokkin prediksi (prediction_logs) vs realita (orders).

Konsisten dengan engine:
    - Skip BATAL/CANCEL (pakai is_cancelled_order dari order_utils)
    - Keep SELESAI + PROSES + Antrian
    - Dedup: 1 customer × 1 hari = 1 kunjungan
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from services.shared.order_utils import is_cancelled_order
from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)

VERDICT_DELAY_DAYS = 1


def _parse_order_date(order: dict) -> date | None:
    raw = order.get("order_date") or order.get("created_at")
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    return None


def evaluate_predictions(token: str, store_id: str, timezone_str: str) -> dict:
    """
    Evaluasi semua prediction_logs yang pending & udah matang.

    Args:
        token: JWT user (TANPA "Bearer ").
        store_id: UUID toko (dari JWT).
        timezone_str: IANA timezone toko.
    """
    tz = ZoneInfo(timezone_str)
    today_local = datetime.now(tz).date()
    cutoff = today_local - timedelta(days=VERDICT_DELAY_DAYS)

    empty_summary = {
        "evaluated": 0, "hit": 0, "miss": 0, "skipped": 0,
        "accuracy": 0.0,
        "cutoff_date": cutoff.isoformat(),
        "today_local": today_local.isoformat(),
    }

    try:
        supabase = get_user_client(token)
    except Exception:
        logger.exception("Gagal bikin Supabase client")
        return empty_summary

    # STEP 1: log pending yang matang
    try:
        res = (
            supabase.table("prediction_logs")
            .select("id, customer_code, prediction_target_date")
            .eq("store_id", store_id)
            .eq("outcome_status", "pending")
            .lt("prediction_target_date", cutoff.isoformat())
            .execute()
        )
    except Exception:
        logger.exception("Gagal fetch prediction_logs pending")
        return empty_summary

    pending_logs = res.data or []
    if not pending_logs:
        logger.info("Nggak ada prediction_logs pending untuk dievaluasi")
        return empty_summary

    # STEP 2: batch-fetch orders realita
    customer_codes = list({
        log["customer_code"] for log in pending_logs if log.get("customer_code")
    })
    target_dates = [
        date.fromisoformat(log["prediction_target_date"])
        for log in pending_logs if log.get("prediction_target_date")
    ]
    if not customer_codes or not target_dates:
        return empty_summary

    min_date = min(target_dates).isoformat()
    max_date = max(target_dates).isoformat()

    try:
        orders_res = (
            supabase.table("orders")
            .select("id, customer_code, order_date, status")
            .eq("store_id", store_id)
            .in_("customer_code", customer_codes)
            .gte("order_date", min_date)
            .lte("order_date", max_date)
            .execute()
        )
    except Exception:
        logger.exception("Gagal fetch orders realita")
        return empty_summary

    raw_orders = orders_res.data or []

    # STEP 3: filter + dedup jadi visits
    visits: dict[tuple[str, date], str] = {}
    for o in raw_orders:
        if is_cancelled_order(o):
            continue
        d = _parse_order_date(o)
        code = o.get("customer_code")
        if not d or not code:
            continue
        key = (code, d)
        if key not in visits:
            visits[key] = o["id"]

    # STEP 4: vonis per log
    now = datetime.now(timezone.utc)
    hits, misses = [], []

    for log in pending_logs:
        cc = log.get("customer_code")
        target_str = log.get("prediction_target_date")
        if not cc or not target_str:
            continue
        try:
            target = date.fromisoformat(target_str)
        except ValueError:
            continue

        if (cc, target) in visits:
            hits.append({
                "id": log["id"],
                "outcome_status": "hit",
                "outcome_date": target.isoformat(),
                "outcome_delta_days": 0,
                "outcome_order_id": visits[(cc, target)],
                "evaluated_at": now.isoformat(),
            })
        else:
            misses.append({
                "id": log["id"],
                "outcome_status": "miss",
                "outcome_date": None,
                "outcome_delta_days": None,
                "outcome_order_id": None,
                "evaluated_at": now.isoformat(),
            })

    # STEP 5: batch update
    for row in hits + misses:
        log_id = row.pop("id")
        try:
            supabase.table("prediction_logs").update(row).eq("id", log_id).execute()
        except Exception:
            logger.exception("Gagal update prediction_log %s", log_id)

    evaluated = len(hits) + len(misses)
    summary = {
        "evaluated": evaluated,
        "hit": len(hits),
        "miss": len(misses),
        "skipped": 0,
        "accuracy": round(len(hits) / evaluated * 100, 2) if evaluated else 0.0,
        "cutoff_date": cutoff.isoformat(),
        "today_local": today_local.isoformat(),
    }
    logger.info("Evaluate done store=%s: %s", store_id, summary)
    return summary

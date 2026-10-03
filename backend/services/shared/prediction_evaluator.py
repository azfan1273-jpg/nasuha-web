"""
Evaluator: cocokkin prediksi (prediction_logs) vs realita (orders).

Konsisten dengan engine:
    - Skip BATAL/CANCEL (pakai is_cancelled_order dari order_utils)
    - Keep SELESAI + PROSES + Antrian
    - Dedup: 1 customer × 1 hari = 1 kunjungan

Update v2:
    - Fix kolom: order_date → created_at (sesuai skema DB aktual).
    - Timezone-aware: range filter & parse date pakai zona toko.
    - Pakai resolve_timezone() biar support alias (WIB/WITA/WIT).
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from services.shared.order_utils import is_cancelled_order
from services.shared.supabase_user_client import get_user_client
from services.shared.datetime_utils import resolve_timezone

logger = logging.getLogger(__name__)

VERDICT_DELAY_DAYS = 1


def _parse_order_date(order: dict, tz: ZoneInfo) -> date | None:
    """Parse created_at (UTC) → date di zona toko."""
    raw = order.get("created_at") or order.get("order_date")
    if not raw:
        return None

    if isinstance(raw, str):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    elif isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, date):
        return raw
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(tz).date()


def _local_date_to_utc_range(d: date, tz: ZoneInfo) -> tuple[str, str]:
    """
    Konversi 1 hari lokal (00:00-23:59 toko) → range UTC ISO string.
    Return: (start_utc_iso, end_utc_iso) — end eksklusif.
    """
    start_local = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


def evaluate_predictions(token: str, store_id: str, timezone_str: str) -> dict:
    """
    Evaluasi semua prediction_logs yang pending & udah matang.

    Args:
        token: JWT user (TANPA "Bearer ").
        store_id: UUID toko (dari JWT).
        timezone_str: IANA timezone toko ATAU alias (WIB/WITA/WIT).
    """
    tz = resolve_timezone(timezone_str)
    if tz is None:
        logger.error("ZoneInfo tidak tersedia, fallback ke UTC untuk evaluasi")
        tz = timezone.utc

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

    # Range tanggal lokal → UTC (timezone-aware)
    min_date_local = min(target_dates)
    max_date_local = max(target_dates)
    min_dt_utc, _ = _local_date_to_utc_range(min_date_local, tz)
    _, max_dt_utc = _local_date_to_utc_range(max_date_local, tz)

    try:
        orders_res = (
            supabase.table("orders")
            .select("id, customer_code, created_at, status")
            .eq("store_id", store_id)
            .in_("customer_code", customer_codes)
            .gte("created_at", min_dt_utc)
            .lt("created_at", max_dt_utc)
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
        d = _parse_order_date(o, tz)
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

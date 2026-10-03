"""
Carry Over Service.

Konsep:
    Customer yang diprediksi H-1, tapi belum dateng di H-1
    → di-carry over ke H (hari ini), muncul di section "Carry Over".
    → max 3x carry over, terus buang (kandidat churn).
    → score boost +3 per carry (max +15).

Konsisten dengan engine:
    - Skip BATAL/CANCEL (via is_cancelled_order)
    - Skip customer yang sudah ada di normal predictions hari ini (anti-dobel)
    - Skip kalau carry_over_count sudah max
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from services.shared.order_utils import is_cancelled_order

logger = logging.getLogger(__name__)

# ============================================================
# CONFIG
# ============================================================
MAX_CARRY_OVER = 3              # Batas maksimal carry over (3 hari)
SCORE_BOOST_PER_CARRY = 3       # +3 per carry
MAX_SCORE_BOOST = 15            # Cap boost (5 carry × 3 = 15)


# ============================================================
# HELPERS
# ============================================================

def _day_range_utc(target_date: date, tz: ZoneInfo) -> tuple[str, str]:
    """
    Range 1 hari lokal (00:00 - 23:59) di zona toko → convert ke UTC.
    Buat filter query orders.created_at yang UTC.
    """
    start_local = datetime(
        target_date.year, target_date.month, target_date.day,
        0, 0, 0, tzinfo=tz,
    )
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


# ============================================================
# MAIN
# ============================================================

def build_carry_over_predictions(
    token: str,
    store_id: str,
    today_local: date,
    timezone_str: str,
    exclude_codes: set | None = None,
) -> list:
    """
    Deteksi customer dari prediksi H-1 yang belum order di H-1,
    dan belum ada di normal predictions hari ini.

    Args:
        token: JWT user
        store_id: UUID toko
        today_local: tanggal "hari ini" di zona toko
        timezone_str: IANA timezone
        exclude_codes: customer_code yang udah ada di normal predictions
                      (biar nggak dobel tampil)

    Returns:
        list dict siap insert ke prediction_logs (dengan field carry over)
    """
    from services.shared.supabase_user_client import get_user_client

    exclude_codes = exclude_codes or set()
    tz = ZoneInfo(timezone_str)
    yesterday = today_local - timedelta(days=1)

    try:
        supabase = get_user_client(token)
    except Exception:
        logger.exception("Carry over: gagal bikin Supabase client")
        return []

    # ===== STEP 1: Ambil log H-1 =====
    try:
        res = (
            supabase.table("prediction_logs")
            .select("*")
            .eq("store_id", store_id)
            .eq("prediction_target_date", yesterday.isoformat())
            .execute()
        )
    except Exception:
        logger.exception("Carry over: gagal fetch log H-1")
        return []

    yesterday_logs = res.data or []
    if not yesterday_logs:
        logger.info("Carry over: tidak ada log untuk %s", yesterday.isoformat())
        return []

    # ===== STEP 2: Ambil customer_code yang order di H-1 =====
    codes = list({
        log["customer_code"]
        for log in yesterday_logs
        if log.get("customer_code")
    })
    if not codes:
        return []

    start_utc, end_utc = _day_range_utc(yesterday, tz)

    try:
        orders_res = (
            supabase.table("orders")
            .select("customer_code, status")
            .eq("store_id", store_id)
            .in_("customer_code", codes)
            .gte("created_at", start_utc)
            .lt("created_at", end_utc)
            .execute()
        )
    except Exception:
        logger.exception("Carry over: gagal fetch orders H-1")
        return []

    hit_codes = set()
    for o in orders_res.data or []:
        if is_cancelled_order(o):
            continue
        code = o.get("customer_code")
        if code:
            hit_codes.add(code)

    # ===== STEP 2b: Ambil customer_code yang order HARI INI =====
    today_start_utc, today_end_utc = _day_range_utc(today_local, tz)
    
    today_orders_res = (
        supabase.table("orders")
        .select("customer_code, status")
        .eq("store_id", store_id)
        .in_("customer_code", codes)
        .gte("created_at", today_start_utc)
        .lt("created_at", today_end_utc)
        .execute()
    )
    
    today_codes = set()
    for o in today_orders_res.data or []:
        if is_cancelled_order(o):
            continue
        code = o.get("customer_code")
        if code:
            today_codes.add(code)        

    # ===== STEP 3: Filter kandidat carry over =====
    carry_over_payloads = []
    seen_codes = set()

    for log in yesterday_logs:
        code = log.get("customer_code")
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)

        # Skip kalau udah order H-1 (HIT)
        if code in hit_codes:
            continue

        # Skip kalau udah order HARI INI (udah dateng, nggak perlu diingetin)
        if code in today_codes:
            continue

        # Skip kalau udah ada di normal predictions hari ini (anti-dobel)
        if code in exclude_codes:
            continue

        # Cek batas max carry over
        prev_count = log.get("carry_over_count") or 0
        new_count = prev_count + 1
        if new_count > MAX_CARRY_OVER:
            continue

        # Hitung boost score
        base_score = log.get("score") or 0
        boost = min(new_count * SCORE_BOOST_PER_CARRY, MAX_SCORE_BOOST)
        new_score = min(100, base_score + boost)

        # Reason tambahan: "Telat N hari"
        carry_label = f"Telat {new_count} hari"
        original_reason = log.get("reason") or ""
        new_reason = (
            f"{carry_label} · {original_reason}"
            if original_reason else carry_label
        )

        carry_over_payloads.append({
            "customer_code": code,
            "name": log.get("customer_name"),
            "phone": log.get("customer_phone") or "",
            "tag": log.get("tag"),
            "score": new_score,
            "reason": new_reason,
            "reason_secondary": log.get("reason_secondary"),
            "prediction_status": "Telat",
            "prediction_date": log.get("prediction_target_date"),
            "last_transaction": log.get("last_transaction"),
            "days_since_last": (log.get("days_since_last") or 0) + 1,
            "cycle_days": log.get("cycle_days"),
            "cycle_deviation": log.get("cycle_deviation"),
            "transaction_count": log.get("transaction_count"),
            "total_spend": log.get("total_spend"),
            "avg_spend": log.get("avg_spend"),
            "est_spend": log.get("est_spend"),
            "favorite_service": log.get("favorite_service"),
            "contribution_percent": log.get("contribution_percent"),
            "contribution": log.get("contribution"),
            "confidence_level": log.get("confidence_level"),
            "pattern_multiplier": log.get("pattern_multiplier"),
            # Field carry over
            "is_carry_over": True,
            "carry_over_count": new_count,
            "carried_from_log_id": log.get("id"),
        })

    logger.info(
        "Carry over: %d kandidat dari %d log H-1",
        len(carry_over_payloads), len(yesterday_logs),
    )
    return carry_over_payloads

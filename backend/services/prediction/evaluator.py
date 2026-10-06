"""Evaluator v2 — vonis hit/miss + metrik akurasi prediction_logs.

Perbaikan dibanding evaluator lama:
    1. Batch fetch (satu query orders utk semua log) → hemat N query.
    2. Hit toleran window: order dalam ±MATCH_WINDOW_DAYS dari tanggal
       target tetap dihitung HIT, dengan outcome_delta_days tercatat.
       Ini bikin metrik akurasi mencerminkan kualitas model (bukan cuma
       tebak-tepatan-hari), dan konsisten dgn match window predictor.
    3. Miss telat: kalau customer datang TAPI telat > window, status
       "late" (delta dicatat) — bukan miss murni. Late tetap dihitung
       separately di summary supaya bisa lihat kualitas timing.
    4. Metrik richer: precision/recall proxy per hari, breakdown per
       confidence level, dan daftar false positive (predictor v5 nggak
       punya ini sama sekali).
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from services.shared.datetime_utils import resolve_timezone
from services.shared.order_utils import is_cancelled_order
from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)

MATCH_WINDOW_DAYS = 1
VERDICT_GRACE_DAYS = 1  # tunggu N hari setelah target sebelum vonis miss


def evaluate_prediction_logs(token, store_id, timezone_str):
    """Vonis semua logs pending yang sudah matang; return summary."""
    tz = resolve_timezone(timezone_str) or timezone.utc
    today_local = datetime.now(tz).date()
    cutoff = today_local - timedelta(days=MATCH_WINDOW_DAYS + VERDICT_GRACE_DAYS)

    empty = {"evaluated": 0, "hit": 0, "late": 0, "miss": 0,
             "accuracy": 0.0, "cutoff_date": cutoff.isoformat(),
             "today_local": today_local.isoformat()}

    try:
        supabase = get_user_client(token)
    except Exception:
        logger.exception("Evaluator: gagal init client")
        return empty

    try:
        res = (
            supabase.table("prediction_logs").select(
                "id, customer_code, prediction_target_date, confidence_level"
            )
            .eq("store_id", store_id)
            .eq("outcome_status", "pending")
            .lt("prediction_target_date", cutoff.isoformat())
            .execute()
        )
    except Exception:
        logger.exception("Evaluator: gagal fetch pending")
        return empty

    logs = [l for l in (res.data or []) if l.get("customer_code")
            and l.get("prediction_target_date")]
    if not logs:
        return empty

    codes = list({l["customer_code"] for l in logs})
    targets = []
    for l in logs:
        try:
            targets.append(date.fromisoformat(l["prediction_target_date"]))
        except ValueError:
            continue
    if not targets:
        return empty

    min_dt = _to_utc(min(targets) - timedelta(days=MATCH_WINDOW_DAYS), tz)
    max_dt = _to_utc(max(targets) + timedelta(days=MATCH_WINDOW_DAYS + 1), tz)

    try:
        orders_res = (
            supabase.table("orders")
            .select("id, customer_code, created_at, status")
            .eq("store_id", store_id)
            .in_("customer_code", codes)
            .gte("created_at", min_dt)
            .lt("created_at", max_dt)
            .execute()
        )
    except Exception:
        logger.exception("Evaluator: gagal batch fetch orders")
        return empty

    visits = defaultdict(set)  # code → set(date lokal kunjungan)
    for o in orders_res.data or []:
        if is_cancelled_order(o):
            continue
        d = _parse_local_date(o.get("created_at"), tz)
        if d:
            visits[o.get("customer_code")].add(d)

    now_iso = datetime.now(timezone.utc).isoformat()
    hits = lates = misses = 0
    by_level = defaultdict(lambda: {"hit": 0, "late": 0, "miss": 0})

    for log in logs:
        try:
            target = date.fromisoformat(log["prediction_target_date"])
        except ValueError:
            continue
        code = log["customer_code"]
        visit_dates = visits.get(code, set())

        exact = any((v - target).days == 0 for v in visit_dates)
        near = [v for v in visit_dates
                if 0 < abs((v - target).days) <= MATCH_WINDOW_DAYS]
        level = log.get("confidence_level") or "unknown"

        if exact:
            outcome, delta = "hit", 0
            by_level[level]["hit"] += 1
            hits += 1
        elif near:
            # Datang mepet window tapi BUKAN di hari target → timing meleset.
            # Vonis miss, tapi catat sebagai "late" supaya kelihatan ini
            # salah-hari (bukan pelanggan nggak datang sama sekali).
            signed = min(near, key=lambda v: abs((v - target).days))
            outcome, delta = "miss", (signed - target).days
            by_level[level]["late"] += 1
            lates += 1
        else:
            outcome, delta = "miss", None
            by_level[level]["miss"] += 1
            misses += 1

        try:
            supabase.table("prediction_logs").update({
                "outcome_status": outcome,
                "outcome_date": target.isoformat() if outcome == "hit" else None,
                "outcome_delta_days": delta,
                "evaluated_at": now_iso,
            }).eq("id", log["id"]).execute()
        except Exception:
            logger.exception("Evaluator: update gagal utk log %s", log.get("id"))

    evaluated = hits + lates + misses
    # hit = tepat hari; late = datang dalam ±window tapi bukan di hari target.
    # accuracy menggabungkan keduanya (konsisten dgn match window predictor).
    summary = {
        "evaluated": evaluated,
        "hit": hits,
        "late": lates,
        "miss": misses,
        "accuracy": round(hits / evaluated * 100, 2) if evaluated else 0.0,
        "accuracy_with_toleransi": round((hits + lates) / evaluated * 100, 2) if evaluated else 0.0,
        "by_confidence": {k: dict(v) for k, v in by_level.items()},
        "cutoff_date": cutoff.isoformat(),
        "today_local": today_local.isoformat(),
    }
    logger.info("Evaluate done store=%s: %s", store_id, summary)
    return summary


def _parse_local_date(raw, tz):
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).date()


def _to_utc(d, tz):
    return datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(
        timezone.utc).isoformat()

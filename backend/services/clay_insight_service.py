"""
Clay Insight Service — data buat halaman Home & Riwayat Akurasi.

Endpoint yang dilayani:
    GET /api/clay/overview            → sapaan + KPI global + daftar fitur
    GET /api/clay/history/accuracy    → riwayat akurasi per tanggal target

Prinsip:
    - Semua query pakai JWT user (RLS aktif, no bypass).
    - Kalau data kosong, tetap return struktur lengkap (biar frontend gampang).
    - Nggak ada logic berat — cuma agregasi & formatting.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from services.shared.datetime_utils import get_local_today, resolve_timezone
from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)

# ============================================================
# DAFTAR FITUR (hardcoded dulu, nanti bisa dari DB)
# ============================================================
FEATURES = [
    {
        "id": "predict_tomorrow",
        "name": "Predict Tomorrow",
        "icon": "🔮",
        "description": "Prediksi pelanggan yang akan datang besok",
        "status": "active",
        "route": "clay-predict",
    },
    {
        "id": "churn_engine",
        "name": "Churn Engine",
        "icon": "🚨",
        "description": "Deteksi pelanggan yang berisiko hilang",
        "status": "coming_soon",
        "route": None,
    },
    {
        "id": "slot_3",
        "name": "Fitur Baru",
        "icon": "+",
        "description": "Slot tersedia",
        "status": "placeholder",
        "route": None,
    },
    {
        "id": "slot_4",
        "name": "Fitur Baru",
        "icon": "+",
        "description": "Slot tersedia",
        "status": "placeholder",
        "route": None,
    },
]


# ============================================================
# HELPERS
# ============================================================

_HARI_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
_BULAN_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def _format_date_id(d: date) -> str:
    """Format tanggal jadi 'Kamis, 2 Oktober 2026'."""
    return f"{_HARI_ID[d.weekday()]}, {d.day} {_BULAN_ID[d.month - 1]} {d.year}"


def _fetch_owner_name(supabase, user_id: str) -> str:
        """Ambil nama owner dari profiles. Fallback berlapis."""
        try:
            res = (
                supabase.table("profiles")
                .select("nama_pegawai, nama_toko, email")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if res.data:
                row = res.data[0]
                # Prioritas: nama_pegawai → nama_toko → email prefix
                for key in ("nama_pegawai", "nama_toko"):
                    v = row.get(key)
                    if v and str(v).strip():
                        return str(v).strip()
                email = row.get("email") or ""
                if "@" in email:
                    return email.split("@")[0]
        except Exception:
            logger.exception("Gagal fetch nama owner")
        return "Owner"


# ============================================================
# OVERVIEW (Home)
# ============================================================

def build_overview(token: str, store_id: str, user_id: str, timezone_str: str) -> dict:
    """
    Bangun data buat halaman Home Clay Engine.

    Return:
        {
          "greeting": {name, day_local, date_local, date_label, time_local, timezone},
          "kpi": {predictions_tomorrow, accuracy_7d, skipped_today},
          "features": [...]
        }
    """
    supabase = get_user_client(token)
    tz = resolve_timezone(timezone_str)
    now_local = datetime.now(tz)

    today_local = now_local.date()

    # ---- 1. Sapaan ----
    owner_name = _fetch_owner_name(supabase, user_id)

    greeting = {
        "name": owner_name,
        "day_local": _HARI_ID[today_local.weekday()],
        "date_local": today_local.isoformat(),
        "date_label": _format_date_id(today_local),
        "time_local": now_local.strftime("%H:%M"),
        "timezone": timezone_str,
    }

    # ---- 2. KPI ----
    kpi = _build_kpi(supabase, store_id, today_local)

    # ---- 3. Features ----
    features = _build_features(supabase, store_id, kpi)

    return {
        "greeting": greeting,
        "kpi": kpi,
        "features": features,
    }


def _build_kpi(supabase, store_id: str, today_local: date) -> dict:
    """Hitung 3 KPI: prediksi besok, akurasi 7 hari, skip hari ini."""

    # 2a. Ambil run TERAKHIR buat toko ini → predictions_tomorrow & skipped_today
    predictions_tomorrow = 0
    skipped_today = 0
    try:
        res = (
            supabase.table("prediction_runs")
            .select("customers_shown, metadata, run_at")
            .eq("store_id", store_id)
            .order("run_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            row = res.data[0]
            predictions_tomorrow = row.get("customers_shown") or 0
            meta = row.get("metadata") or {}
            skipped_today = len(meta.get("skipped") or [])
    except Exception:
        logger.exception("Gagal fetch KPI prediction_runs")

    # 2b. Akurasi 7 hari terakhir
    accuracy_7d = None
    try:
        since = (today_local - timedelta(days=7)).isoformat()
        res = (
            supabase.table("prediction_logs")
            .select("outcome_status")
            .eq("store_id", store_id)
            .in_("outcome_status", ["hit", "miss"])
            .gte("prediction_target_date", since)
            .execute()
        )
        rows = res.data or []
        total = len(rows)
        if total > 0:
            hit = sum(1 for r in rows if r.get("outcome_status") == "hit")
            accuracy_7d = round(hit / total * 100, 1)
    except Exception:
        logger.exception("Gagal fetch KPI accuracy 7d")

    return {
        "predictions_tomorrow": predictions_tomorrow,
        "accuracy_7d": accuracy_7d,
        "skipped_today": skipped_today,
    }


def _build_features(supabase, store_id: str, kpi: dict) -> list:
    """
    Enrich daftar fitur dengan statistik live.
    Fitur 'predict_tomorrow' dapet stats dari KPI.
    """
    features = []
    for f in FEATURES:
        item = dict(f)
        if f["id"] == "predict_tomorrow" and f["status"] == "active":
            item["stats"] = {
                "predictions": kpi.get("predictions_tomorrow", 0),
                "accuracy": kpi.get("accuracy_7d"),
            }
        else:
            item["stats"] = None
        features.append(item)
    return features


# ============================================================
# HISTORY AKURASI
# ============================================================

PERIOD_MAP = {
    "7d": 7,
    "30d": 30,
    "all": None,
}


def build_accuracy_history(
    token: str,
    store_id: str,
    timezone_str: str,
    period: str = "7d",
) -> dict:
    """
    Riwayat akurasi prediksi, dikelompokkan per prediction_target_date.

    Args:
        period: "7d" | "30d" | "all" (default "7d")
    """
    supabase = get_user_client(token)

    # Normalisasi period
    period_key = period if period in PERIOD_MAP else "7d"
    days = PERIOD_MAP[period_key]

    # Query log (ambilin yang udah ada outcome, exclude pending dulu biar fokus)
    # Tapi tetap include pending biar user bisa liat yang belum dievaluasi.
    query = (
        supabase.table("prediction_logs")
        .select(
            "id, customer_code, customer_name, score, tag, cycle_days, "
            "cycle_deviation, prediction_target_date, "
            "outcome_status, outcome_date, outcome_order_id, "
            "evaluated_at, created_at, is_carry_over, carry_over_count"
        )
        .eq("store_id", store_id)
        .order("prediction_target_date", desc=True)
        .limit(500)
    )

    if days is not None:
        today_local = get_local_today(timezone_str)
        since = (today_local - timedelta(days=days)).isoformat()
        query = query.gte("prediction_target_date", since)

    try:
        res = query.execute()
    except Exception:
        logger.exception("Gagal fetch prediction_logs untuk history")
        return _empty_history(period_key)

    rows = res.data or []
    if not rows:
        return _empty_history(period_key)

    # ---- Summary global ----
    total = len(rows)
    hit = sum(1 for r in rows if r.get("outcome_status") == "hit")
    miss = sum(1 for r in rows if r.get("outcome_status") == "miss")
    pending = sum(1 for r in rows if r.get("outcome_status") == "pending")
    evaluated = hit + miss
    accuracy_pct = round(hit / evaluated * 100, 2) if evaluated else None

    # ---- Group by target_date ----
    groups_map: dict[str, list] = {}
    for r in rows:
        td = r.get("prediction_target_date")
        if not td:
            continue
        groups_map.setdefault(td, []).append(r)

    groups = []
    for td_str in sorted(groups_map.keys(), reverse=True):
        items = groups_map[td_str]
        try:
            td = date.fromisoformat(td_str)
        except ValueError:
            continue

        g_total = len(items)
        g_hit = sum(1 for r in items if r.get("outcome_status") == "hit")
        g_miss = sum(1 for r in items if r.get("outcome_status") == "miss")
        g_pending = sum(1 for r in items if r.get("outcome_status") == "pending")
        g_eval = g_hit + g_miss
        g_acc = round(g_hit / g_eval * 100, 1) if g_eval else None

        # Sort items by score desc
        items_sorted = sorted(items, key=lambda x: x.get("score") or 0, reverse=True)

        predictions = []
        for r in items_sorted:
            predictions.append({
                "id": r.get("id"),
                "customer_code": r.get("customer_code"),
                "customer_name": r.get("customer_name"),
                "score": r.get("score"),
                "tag": r.get("tag"),
                "cycle_days": float(r["cycle_days"]) if r.get("cycle_days") is not None else None,
                "cycle_deviation": float(r["cycle_deviation"]) if r.get("cycle_deviation") is not None else None,
                "outcome_status": r.get("outcome_status") or "pending",
                "outcome_date": r.get("outcome_date"),
                "outcome_order_id": r.get("outcome_order_id"),
                "evaluated_at": r.get("evaluated_at"),
                "is_carry_over": r.get("is_carry_over") or False,
                "carry_over_count": r.get("carry_over_count") or 0,
            })

        groups.append({
            "target_date": td_str,
            "date_label": _format_date_id(td),
            "total": g_total,
            "hit": g_hit,
            "miss": g_miss,
            "pending": g_pending,
            "accuracy_pct": g_acc,
            "predictions": predictions,
        })

    return {
        "period": period_key,
        "summary": {
            "total": total,
            "hit": hit,
            "miss": miss,
            "pending": pending,
            "evaluated": evaluated,
            "accuracy_pct": accuracy_pct,
        },
        "groups": groups,
    }


def _empty_history(period_key: str) -> dict:
    return {
        "period": period_key,
        "summary": {
            "total": 0, "hit": 0, "miss": 0, "pending": 0,
            "evaluated": 0, "accuracy_pct": None,
        },
        "groups": [],
    }

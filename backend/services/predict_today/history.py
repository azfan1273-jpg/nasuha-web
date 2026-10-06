"""Riwayat akurasi prediksi per tanggal (dari prediction_logs yang sudah dievaluasi)."""

import logging

from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)

MAX_LOGS = 1000


def get_prediction_history(token: str, store_id: str, days: int = 30) -> dict:
    """
    Ambil log prediksi yang sudah dievaluasi (hit/miss) dalam `days` terakhir,
    dirangkum per tanggal target: jumlah pelanggan, hit, miss, dan akurasi.

    Return:
        {
          "days": 30,
          "summary": {"total_logs", "total_hit", "total_miss", "accuracy"},
          "daily": [
            {"date", "pelanggan", "hit", "miss", "evaluated", "accuracy", "keterangan"}
          ]
        }
    """
    empty = {
        "days": days,
        "summary": {"total_logs": 0, "total_hit": 0, "total_miss": 0, "accuracy": None},
        "daily": [],
    }

    try:
        supabase = get_user_client(token)
        res = (
            supabase.table("prediction_logs")
            .select("prediction_target_date, customer_name, outcome_status")
            .eq("store_id", store_id)
            .in_("outcome_status", ["hit", "miss"])
            .order("prediction_target_date", desc=True)
            .limit(MAX_LOGS)
            .execute()
        )
    except Exception:
        logger.exception("Gagal fetch riwayat akurasi prediksi")
        return empty

    logs = res.data or []
    if not logs:
        return empty

    # Rangkum per tanggal
    by_date: dict[str, dict] = {}
    for row in logs:
        d = row.get("prediction_target_date")
        if not d:
            continue
        bucket = by_date.setdefault(
            d, {"hit": 0, "miss": 0, "customers": set()}
        )
        status = row.get("outcome_status")
        if status == "hit":
            bucket["hit"] += 1
        elif status == "miss":
            bucket["miss"] += 1
        name = row.get("customer_name")
        if name:
            bucket["customers"].add(name)

    daily = []
    total_hit = total_miss = 0
    for d in sorted(by_date.keys(), reverse=True)[:days]:
        b = by_date[d]
        hit, miss = b["hit"], b["miss"]
        evaluated = hit + miss
        accuracy = round((hit / evaluated) * 100, 1) if evaluated else None
        total_hit += hit
        total_miss += miss
        daily.append({
            "date": d,
            "pelanggan": len(b["customers"]) or evaluated,
            "hit": hit,
            "miss": miss,
            "evaluated": evaluated,
            "accuracy": accuracy,
            "keterangan": _keterangan(hit, miss),
        })

    total_evaluated = total_hit + total_miss
    return {
        "days": days,
        "summary": {
            "total_logs": total_evaluated,
            "total_hit": total_hit,
            "total_miss": total_miss,
            "accuracy": round((total_hit / total_evaluated) * 100, 1) if total_evaluated else None,
        },
        "daily": daily,
    }


def _keterangan(hit: int, miss: int) -> str:
    evaluated = hit + miss
    if evaluated == 0:
        return "Belum ada evaluasi"
    acc = hit / evaluated
    if acc >= 0.8:
        return "Akurasi sangat baik"
    if acc >= 0.6:
        return "Akurasi baik"
    if acc >= 0.4:
        return "Akurasi cukup"
    return "Akurasi rendah, perlu review model"

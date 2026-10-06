"""Cron runner — jalankan prediksi untuk SEMUA toko.

Dipanggil via endpoint POST /api/clay/cron/daily-run (X-Cron-Secret).
Pakai service_role key → bypass RLS, akses lintas toko.
"""

import logging

from services.predict_today.orchestrator import predict_for_store
from services.shared.store_utils import fetch_all_store_ids
from services.shared.supabase_admin_client import get_admin_auth_header

logger = logging.getLogger(__name__)


def run_daily_for_all_stores():
    """Loop semua store, jalankan predict_for_store untuk tiap toko."""
    try:
        admin_auth = get_admin_auth_header()
    except RuntimeError as e:
        logger.exception("Cron: gagal ambil admin auth")
        return {"status": "error", "message": str(e), "results": []}

    store_ids = fetch_all_store_ids(admin_auth)
    logger.info("Cron daily-run: %d store ditemukan", len(store_ids))

    results = []
    for sid in store_ids:
        try:
            r = predict_for_store(admin_auth, sid, evaluate_first=True)
            results.append({
                "store_id": sid,
                "status": "ok",
                "run_id": r.get("run_id"),
                "predictions": len(r.get("predictions", [])),
                "carry_over": len(r.get("carry_over", [])),
                "eval": r.get("eval_debug"),
            })
        except Exception as e:
            logger.exception("Cron: gagal proses store %s", sid)
            results.append({
                "store_id": sid,
                "status": "error",
                "error": str(e),
            })

    ok_count = sum(1 for r in results if r["status"] == "ok")
    return {
        "status": "success",
        "total_stores": len(store_ids),
        "ok": ok_count,
        "error": len(store_ids) - ok_count,
        "results": results,
    }

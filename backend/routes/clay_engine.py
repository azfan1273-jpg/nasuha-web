"""Clay Engine — HTTP routes only.

Semua otak ada di `services/<fitur>/`.
Nambah fitur = bikin folder di services/ + tambah endpoint di sini.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException

from routes.analytics import AuthContext, get_auth_context
from services.predict_today import predict_for_store
from services.predict_today.cron import run_daily_for_all_stores
from services.predict_today.history import get_prediction_history
from services.shared.cron_auth import verify_cron_secret

logger = logging.getLogger(__name__)

clay_router = APIRouter(tags=["Clay Engine"])


# ============================================================
# PREDICT TODAY (user-facing, butuh JWT user)
# ============================================================
@clay_router.get("/predict-today")
def predict_today_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    """Target pelanggan hari ini + carry over."""
    try:
        return predict_for_store(ctx.auth_header, ctx.store_id, evaluate_first=True)
    except Exception as e:
        logger.exception("Predict today error")
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


# ============================================================
# RIWAYAT AKURASI PREDIKSI (user-facing, butuh JWT user)
# ============================================================
@clay_router.get("/history/accuracy")
def history_accuracy_endpoint(
    period: str = "30d",
    ctx: AuthContext = Depends(get_auth_context),
):
    """Rangkum akurasi hit/miss prediksi per tanggal (max 90 hari)."""
    try:
        days = int("".join(ch for ch in period if ch.isdigit()) or 30)
    except ValueError:
        days = 30
    days = max(1, min(days, 90))

    token = ctx.auth_header.replace("Bearer ", "", 1).strip()
    return get_prediction_history(token, ctx.store_id, days=days)


# ============================================================
# CRON DAILY RUN (server-to-server, pakai X-Cron-Secret)
# ============================================================
@clay_router.post("/cron/daily-run")
def cron_daily_run_endpoint(x_cron_secret: str = Header(None, alias="X-Cron-Secret")):
    """Jalankan prediksi untuk SEMUA toko. Dipanggil pg_cron via pg_net."""
    verify_cron_secret(x_cron_secret)
    try:
        return run_daily_for_all_stores()
    except Exception as e:
        logger.exception("Cron daily run error")
        raise HTTPException(status_code=500, detail=f"Cron error: {str(e)}")


# ============================================================
# CHURN CUSTOMER (placeholder)
# ============================================================
# @clay_router.get("/churn")
# def churn_endpoint(ctx: AuthContext = Depends(get_auth_context)):
#     from services.churn_customer import detect_for_store
#     return detect_for_store(ctx.auth_header, ctx.store_id)

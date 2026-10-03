"""
Clay Engine routes.

Endpoint:
    GET  /api/clay/predict-tomorrow       → generate prediksi besok + carry over (user)
    POST /api/clay/evaluate-predictions   → evaluasi akurasi (user)
    GET  /api/clay/overview               → data Home (user)
    GET  /api/clay/history/accuracy       → riwayat akurasi (user)
    POST /api/clay/cron/daily-run         → generate semua store (cron, tanpa JWT user)

Catatan:
    - store_id SELALU dari JWT (via AuthContext), bukan query param.
    - Endpoint /cron/* dipanggil pg_cron pakai header X-Cron-Secret,
      pakai service_role_key buat bypass RLS & loop semua store.
"""

import logging
import os
from typing import Optional
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from config.supabase_config import (
    SUPABASE_URL,
    get_supabase_headers,
    verify_user_jwt,
)

from routes.analytics import AuthContext, get_auth_context
from services.clay_service import calculate_tomorrow_prediction
from services.carry_over_service import build_carry_over_predictions
from services.shared.prediction_evaluator import evaluate_predictions
from services.shared.prediction_logger import log_prediction_run
from services.shared.store_utils import fetch_store_timezone
from security import is_rate_limited, sanitize_filter_value

from services.clay_insight_service import (
    build_accuracy_history,
    build_overview,
)

logger = logging.getLogger(__name__)

clay_router = APIRouter()


def _client_ip(request: Request) -> str:
    """Ambil IP asli (Vercel di balik proxy → X-Forwarded-For)."""
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


# ===========================================================================
# CORE LOGIC — generate + log prediksi untuk 1 store
# ===========================================================================
def _predict_for_store(auth_header: str, store_id: str, evaluate_first: bool = True) -> dict:
    """
    Generate + log prediksi untuk 1 store.

    Args:
        auth_header: "Bearer <jwt_user>" ATAU "Bearer <service_role_key>"
        store_id: UUID toko
        evaluate_first: Kalau True, evaluasi log lama (matang) sebelum generate

    Return: dict detail (predictions, carry_over, top_services, metadata, ...)
    """
    timezone_str = fetch_store_timezone(store_id, auth_header)

    try:
        sid = sanitize_filter_value(store_id)
    except ValueError:
        raise RuntimeError("store_id tidak valid")

    token_str = auth_header.replace("Bearer ", "", 1).strip()

    # ---- Evaluasi log lama (matang) sebelum generate baru ----
    if evaluate_first:
        try:
            eval_summary = evaluate_predictions(token_str, store_id, timezone_str)
            logger.info("Evaluate store %s: %s", store_id, eval_summary)
        except Exception:
            logger.exception("Evaluate gagal untuk store %s, lanjut generate", store_id)

    # ---- Ambil orders + order_items ----
    orders_url = (
        f"{SUPABASE_URL}/rest/v1/orders"
        f"?select=*,order_items(*)&store_id=eq.{quote(sid, safe='')}&limit=2000"
    )
    try:
        orders_res = requests.get(
            orders_url,
            headers=get_supabase_headers(auth_header),
            timeout=30,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Gagal konek Supabase: {e}")

    if orders_res.status_code != 200:
        raise RuntimeError(f"Supabase orders HTTP {orders_res.status_code}")

    orders_data = orders_res.json() or []
    if not isinstance(orders_data, list):
        orders_data = []

    # ---- Generate normal predictions ----
    clay_result = calculate_tomorrow_prediction(orders_data, timezone_str)
    if not isinstance(clay_result, dict):
        clay_result = {"predictions": [], "top_services": [], "metadata": {}}

    raw_predictions = clay_result.get("predictions", [])
    top_services = clay_result.get("top_services", [])
    metadata = clay_result.get("metadata", {})

    # ---- Build carry over ----
    from services.shared.datetime_utils import get_local_today
    today_local = get_local_today(timezone_str)

    normal_codes = {
        p.get("customer_code")
        for p in raw_predictions
        if p.get("customer_code")
    }

    carry_over = build_carry_over_predictions(
        token=token_str,
        store_id=store_id,
        today_local=today_local,
        timezone_str=timezone_str,
        exclude_codes=normal_codes,
    )

    # ---- Log ke DB ----
    clay_result["carry_over"] = carry_over
    run_id = log_prediction_run(token_str, store_id, clay_result)
    if run_id:
        metadata["run_id"] = run_id

    return {
        "run_id": run_id,
        "predictions": raw_predictions,
        "carry_over": carry_over,
        "top_services": top_services,
        "metadata": metadata,
        "timezone": timezone_str,
    }

# ---------------------------------------------------------------------------
# GET /api/clay/predict-tomorrow  (JWT user)
# ---------------------------------------------------------------------------
@clay_router.get("/predict-tomorrow")
def predict_tomorrow(request: Request, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token otentikasi tidak ditemukan")

    token = authorization.split(" ", 1)[1].strip()

    if is_rate_limited(f"clay:{_client_ip(request)}", limit=20, window=60):
        raise HTTPException(status_code=429, detail="Terlalu banyak permintaan")

    # 1. Verifikasi JWT
    try:
        payload = verify_user_jwt(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid atau kedaluwarsa, silakan login ulang",
        )

    user_id = payload.get('sub') or payload.get('id')
    if not user_id:
        raise HTTPException(status_code=401, detail="Token tidak memuat identitas user")

    try:
        uid = sanitize_filter_value(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identitas user tidak valid")

    # 2. store_id dari profil user (anti-IDOR)
    auth_header = f"Bearer {token}"
    try:
        prof_res = requests.get(
            f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{quote(uid, safe='')}&select=store_id",
            headers=get_supabase_headers(auth_header),
            timeout=15,
        )
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Layanan sedang gangguan, coba lagi nanti")

    store_id = None
    if prof_res.status_code == 200:
        body = prof_res.json()
        if isinstance(body, list) and body:
            store_id = body[0].get('store_id')

    if not store_id:
        raise HTTPException(
            status_code=400,
            detail="Gagal mengidentifikasi store_id toko. Silakan login ulang.",
        )

    # 3. Generate
    try:
        result = _predict_for_store(auth_header, store_id, evaluate_first=True)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception:
        logger.exception("predict_tomorrow error untuk store %s", store_id)
        raise HTTPException(status_code=500, detail="Gagal generate prediksi")

    return {
        "status": "success",
        "store_id": store_id,
        "timezone": result["timezone"],
        "predictions": result["predictions"],
        "carry_over": result["carry_over"],
        "top_services": result["top_services"],
        "metadata": result["metadata"],
    }


# ---------------------------------------------------------------------------
# POST /api/clay/cron/daily-run  (pg_cron — header X-Cron-Secret)
# ---------------------------------------------------------------------------
@clay_router.post("/cron/daily-run")
def clay_cron_daily_run(x_cron_secret: Optional[str] = Header(None)):
    """
    Dipanggil pg_cron tiap hari. Loop SEMUA store, generate + log prediksi.
    Auth: header X-Cron-Secret (bukan JWT).
    """
    expected = (os.getenv("CLAY_CRON_SECRET") or "").strip()
    if not expected:
        logger.error("CLAY_CRON_SECRET belum di-set di environment")
        raise HTTPException(status_code=500, detail="Cron secret belum dikonfigurasi")

    if not x_cron_secret or x_cron_secret != expected:
        raise HTTPException(status_code=401, detail="X-Cron-Secret tidak valid")

    service_key = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not service_key:
        logger.error("SUPABASE_SERVICE_ROLE_KEY belum di-set")
        raise HTTPException(status_code=500, detail="Service role key belum dikonfigurasi")

    auth_header = f"Bearer {service_key}"

    # ---- Ambil semua store unik dari profiles ----
    try:
        profiles_url = f"{SUPABASE_URL}/rest/v1/profiles?select=store_id"
        pr = requests.get(
            profiles_url,
            headers=get_supabase_headers(auth_header),
            timeout=15,
        )
        if pr.status_code != 200:
            raise RuntimeError(f"Supabase profiles HTTP {pr.status_code}")
        rows = pr.json() or []
    except Exception as e:
        logger.exception("cron: gagal fetch store list")
        raise HTTPException(status_code=502, detail=f"Gagal fetch store list: {e}")

    store_ids = sorted({r.get("store_id") for r in rows if r.get("store_id")})
    if not store_ids:
        logger.info("cron: tidak ada store")
        return {"status": "success", "total_stores": 0, "results": []}

    logger.info("cron: mulai proses %d store", len(store_ids))

    results = []
    for sid in store_ids:
        try:
            r = _predict_for_store(auth_header, sid, evaluate_first=True)
            results.append({
                "store_id": sid,
                "status": "ok",
                "run_id": r.get("run_id"),
                "predictions": len(r.get("predictions") or []),
                "carry_over": len(r.get("carry_over") or []),
                "target_date": (r.get("metadata") or {}).get("prediction_date"),
            })
        except Exception as e:
            logger.exception("cron: error store %s", sid)
            results.append({
                "store_id": sid,
                "status": "error",
                "message": str(e),
            })

    ok_count = sum(1 for r in results if r["status"] == "ok")
    logger.info("cron: selesai. %d/%d store berhasil", ok_count, len(store_ids))

    return {
        "status": "success",
        "total_stores": len(store_ids),
        "ok": ok_count,
        "failed": len(store_ids) - ok_count,
        "results": results,
    }


# ---------------------------------------------------------------------------
# POST /api/clay/evaluate-predictions
# ---------------------------------------------------------------------------
@clay_router.post("/evaluate-predictions")
def evaluate_predictions_endpoint(ctx: AuthContext = Depends(get_auth_context)):
    token = ctx.auth_header.replace("Bearer ", "", 1).strip() if ctx.auth_header else ""
    if not token:
        raise HTTPException(status_code=401, detail="Token tidak tersedia")

    timezone_str = fetch_store_timezone(ctx.store_id, ctx.auth_header)

    try:
        summary = evaluate_predictions(token, ctx.store_id, timezone_str)
        return {"status": "success", "summary": summary}
    except Exception:
        logger.exception("evaluate_predictions error untuk store %s", ctx.store_id)
        raise HTTPException(status_code=500, detail="Evaluasi gagal dijalankan")


# ---------------------------------------------------------------------------
# GET /api/clay/overview
# ---------------------------------------------------------------------------
@clay_router.get("/overview")
def clay_overview(ctx: AuthContext = Depends(get_auth_context)):
    timezone_str = fetch_store_timezone(ctx.store_id, ctx.auth_header)
    token = ctx.auth_header.replace("Bearer ", "", 1).strip()

    try:
        data = build_overview(
            token=token,
            store_id=ctx.store_id,
            user_id=ctx.user_id,
            timezone_str=timezone_str,
        )
        return {"status": "success", **data}
    except Exception:
        logger.exception("clay_overview error untuk store %s", ctx.store_id)
        raise HTTPException(status_code=500, detail="Gagal memuat overview")


# ---------------------------------------------------------------------------
# GET /api/clay/history/accuracy
# ---------------------------------------------------------------------------
@clay_router.get("/history/accuracy")
def clay_history_accuracy(
    period: str = "7d",
    ctx: AuthContext = Depends(get_auth_context),
):
    if period not in ("7d", "30d", "all"):
        raise HTTPException(status_code=400, detail="period harus 7d / 30d / all")

    timezone_str = fetch_store_timezone(ctx.store_id, ctx.auth_header)
    token = ctx.auth_header.replace("Bearer ", "", 1).strip()

    try:
        data = build_accuracy_history(
            token=token,
            store_id=ctx.store_id,
            timezone_str=timezone_str,
            period=period,
        )
        return {"status": "success", **data}
    except Exception:
        logger.exception("clay_history_accuracy error untuk store %s", ctx.store_id)
        raise HTTPException(status_code=500, detail="Gagal memuat riwayat akurasi")

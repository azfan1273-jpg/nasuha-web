import requests
from urllib.parse import quote
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from config.supabase_config import SUPABASE_URL, get_supabase_headers, verify_user_jwt
from services.clay_service import calculate_tomorrow_prediction
from security import is_rate_limited, sanitize_filter_value

clay_router = APIRouter()


def _client_ip(request: Request) -> str:
    """Ambil IP asli (Vercel di balik proxy → X-Forwarded-For)."""
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


# ---------------------------------------------------------------------------
# GET /api/clay/predict-tomorrow
# ---------------------------------------------------------------------------
@clay_router.get("/predict-tomorrow")
def predict_tomorrow(request: Request, authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token otentikasi tidak ditemukan")

    token = authorization.split(" ", 1)[1].strip()

    # Rate limit pakai IP asli (XFF), bukan request.client (yang bisa jadi IP proxy)
    if is_rate_limited(f"clay:{_client_ip(request)}", limit=20, window=60):
        raise HTTPException(status_code=429, detail="Terlalu banyak permintaan")

    # 1. Verifikasi JWT (signature + expiry)
    try:
        payload = verify_user_jwt(token)
    except Exception as e:
        # DEBUG SEMENTARA — hapus setelah masalah ketemu
        import logging
        logging.getLogger("nasuha").warning(
            "JWKS fallback: iss=%r jwks_url=%r", iss, jwks_url
        )
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid atau kedaluwarsa, silakan login ulang",
        )

    user_id = payload.get('sub') or payload.get('id')
    if not user_id:
        raise HTTPException(status_code=401, detail="Token tidak memuat identitas user")

    # FIX BUG #2: sanitize user_id bisa raise ValueError → harus jadi 400, bukan 500
    try:
        uid = sanitize_filter_value(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identitas user tidak valid")

    # 2. store_id SELALU dari profil user (query param ?store_id DIABAIKAN)
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

    # FIX BUG #2: sanitize store_id juga bisa raise ValueError
    try:
        sid = sanitize_filter_value(store_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data toko tidak valid")

    # 3. Ambil orders + order_items khusus store_id user
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
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Layanan sedang gangguan, coba lagi nanti")

    if orders_res.status_code != 200:
        raise HTTPException(status_code=502, detail="Gagal mengambil data orders")

    orders_data = orders_res.json() or []
    if not isinstance(orders_data, list):
        orders_data = []

    # 4. Jalankan Clay Engine
    clay_result = calculate_tomorrow_prediction(orders_data)
    raw_predictions = clay_result.get("predictions", []) if isinstance(clay_result, dict) else []
    top_services = clay_result.get("top_services", []) if isinstance(clay_result, dict) else []

    return {
        "status": "success",
        "store_id": store_id,
        "predictions": raw_predictions,
        "top_services": top_services,
    }

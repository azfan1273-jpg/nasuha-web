"""Endpoint analytics: transaksi, statistik, dll."""
from urllib.parse import quote

import requests
from fastapi import APIRouter, Depends, HTTPException

from config.supabase_config import SUPABASE_URL, get_supabase_headers
from deps.auth import AuthContext, get_auth_context
from security import sanitize_filter_value

analytics_router = APIRouter()


# ---------------------------------------------------------------------------
# GET /api/transactions
# ---------------------------------------------------------------------------
@analytics_router.get("/transactions")
def get_transactions(ctx: AuthContext = Depends(get_auth_context)):
    try:
        sid = sanitize_filter_value(ctx.store_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data toko tidak valid")

    url = (
        f"{SUPABASE_URL}/rest/v1/orders"
        f"?select=*&store_id=eq.{quote(sid, safe='')}&order=id.desc&limit=500"
    )
    try:
        res = requests.get(url, headers=get_supabase_headers(ctx.auth_header), timeout=15)
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Layanan sedang gangguan, coba lagi nanti")

    if res.status_code != 200:
        raise HTTPException(status_code=502, detail="Gagal mengambil data transaksi")

    data = res.json()
    if not isinstance(data, list):
        data = []

    return {"status": "success", "store_id": ctx.store_id, "data": data}
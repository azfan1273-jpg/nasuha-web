"""Endpoint downloads: daftar file/aplikasi yang bisa diunduh."""
import requests
from fastapi import APIRouter, HTTPException, Request

from config.supabase_config import SUPABASE_URL, get_supabase_headers
from security import get_client_ip, is_rate_limited

downloads_router = APIRouter()


# ---------------------------------------------------------------------------
# GET /api/downloads
# ---------------------------------------------------------------------------
@downloads_router.get("/downloads")
def get_downloads(request: Request):
    if is_rate_limited(f"downloads:{get_client_ip(request)}", limit=30, window=60):
        raise HTTPException(status_code=429, detail="Terlalu banyak permintaan")

    anon_auth = f"Bearer {get_supabase_headers()['apikey']}"
    headers = get_supabase_headers(anon_auth)
    url = (
        f"{SUPABASE_URL}/rest/v1/app_downloads"
        f"?select=title,version,type,size,description,download_url,created_at"
        f"&order=id.desc&limit=100"
    )
    try:
        res = requests.get(url, headers=headers, timeout=15)
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Layanan sedang gangguan, coba lagi nanti")

    if res.status_code != 200:
        raise HTTPException(status_code=502, detail="Gagal mengambil data unduhan")

    data = res.json()
    if not isinstance(data, list):
        data = []

    return {"status": "success", "data": data}
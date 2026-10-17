"""Endpoint autentikasi: login + data user sendiri."""
from urllib.parse import quote

import requests
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from config.supabase_config import SUPABASE_URL, get_supabase_headers
from deps.auth import AuthContext, fetch_own_store_id, get_auth_context
from security import (
    get_client_ip,
    is_rate_limited,
    is_valid_email,
    sanitize_filter_value,
)

auth_router = APIRouter()


# ---------------------------------------------------------------------------
# POST /api/login
# ---------------------------------------------------------------------------
@auth_router.post("/login")
def login(request: Request, body: dict = Body(...)):
    if is_rate_limited(f"login:{get_client_ip(request)}", limit=5, window=60):
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak percobaan login. Coba lagi dalam 1 menit.",
        )

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Format request tidak valid")

    email = str(body.get('email') or '').strip().lower()
    password = str(body.get('password') or '')

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email dan password wajib diisi")
    if not is_valid_email(email):
        raise HTTPException(status_code=400, detail="Format email tidak valid")
    if len(password) > 128:
        raise HTTPException(status_code=401, detail="Kredensial tidak valid")

    try:
        headers = {
            "apikey": get_supabase_headers()["apikey"],
            "Content-Type": "application/json",
        }
        url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
        res = requests.post(
            url,
            json={"email": email, "password": password},
            headers=headers,
            timeout=15,
        )
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Layanan sedang gangguan, coba lagi nanti")

    if res.status_code != 200:
        raise HTTPException(status_code=401, detail="Email atau password salah")

    res_data = res.json()
    user_info = res_data.get("user", {})
    user_id = user_info.get("id")
    store_id = None

    if user_id:
        try:
            user_auth_header = f"Bearer {res_data.get('access_token')}"
            store_id = fetch_own_store_id(user_id, user_auth_header)
        except (ValueError, requests.RequestException):
            store_id = None
        except Exception:
            store_id = None

    return {
        "status": "success",
        "access_token": res_data.get("access_token"),
        "store_id": store_id,
        "user": user_info,
    }


# ---------------------------------------------------------------------------
# GET /api/me  → data user + store untuk frontend
# ---------------------------------------------------------------------------
@auth_router.get("/me")
def get_me(ctx: AuthContext = Depends(get_auth_context)):
    """Ambil data user yang login beserta info store-nya.

    Dipakai frontend buat hydrate elemen [data-user="..."].
    """
    try:
        uid = sanitize_filter_value(ctx.user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identitas user tidak valid")

    # Ambil profile user
    url = (
        f"{SUPABASE_URL}/rest/v1/profiles"
        f"?id=eq.{quote(uid, safe='')}&select=*&limit=1"
    )
    try:
        res = requests.get(
            url,
            headers=get_supabase_headers(ctx.auth_header),
            timeout=10,
        )
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Layanan sedang gangguan, coba lagi nanti")

    if res.status_code != 200:
        raise HTTPException(status_code=502, detail="Gagal ambil profil user")

    body = res.json()
    profile = body[0] if isinstance(body, list) and body else {}

    # ---------------------------------------------------------------
    # Ambil nama store (source of truth) dari tabel stores
    # ---------------------------------------------------------------
    org_name = profile.get("nama_toko") or "Organisasi Saya"
    org_code = ""
    store_id = profile.get("store_id") or ctx.store_id

    if store_id:
        try:
            sid = sanitize_filter_value(store_id)
            store_url = (
                f"{SUPABASE_URL}/rest/v1/stores"
                f"?id=eq.{quote(sid, safe='')}&select=name,store_code&limit=1"
            )
            sres = requests.get(
                store_url,
                headers=get_supabase_headers(ctx.auth_header),
                timeout=10,
            )
            if sres.status_code == 200:
                sbody = sres.json()
                if isinstance(sbody, list) and sbody:
                    org_name = sbody[0].get("name") or org_name
                    org_code = sbody[0].get("store_code") or ""
        except (ValueError, requests.RequestException):
            pass  # nama store opsional, fallback ke profiles.nama_toko

    # ---------------------------------------------------------------
    # Full name: pakai nama_pegawai kalau ada, fallback email prefix
    # ---------------------------------------------------------------
    email = profile.get("email") or ""
    full_name = (
        profile.get("nama_pegawai")
        or (email.split("@")[0] if email else "User")
    )

    return {
        "status": "success",
        "userId": profile.get("id") or ctx.user_id,
        "email": email,
        "fullName": full_name,
        "role": profile.get("role") or "Owner",
        "orgName": org_name,
        "orgCode": org_code,
        "storeId": store_id,
    }
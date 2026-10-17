"""Dependency injection: verifikasi JWT + ambil konteks user."""
from typing import Optional
from urllib.parse import quote

import requests
from fastapi import Header, HTTPException

from config.supabase_config import SUPABASE_URL, get_supabase_headers, verify_user_jwt
from security import sanitize_filter_value


class AuthContext:
    __slots__ = ("store_id", "auth_header", "user_id")

    def __init__(self, store_id: str, auth_header: str, user_id: str):
        self.store_id = store_id
        self.auth_header = auth_header
        self.user_id = user_id


def fetch_own_store_id(user_id: str, auth_header: str) -> Optional[str]:
    """Ambil store_id milik user yang token-nya SUDAH terverifikasi.

    Raise ValueError kalau user_id tidak valid (caller harus tangkap → 400).
    Raise requests.RequestException kalau Supabase error.
    """
    uid = sanitize_filter_value(user_id)
    res = requests.get(
        f"{SUPABASE_URL}/rest/v1/profiles?id=eq.{quote(uid, safe='')}&select=store_id",
        headers=get_supabase_headers(auth_header),
        timeout=10,
    )
    if res.status_code == 200:
        body = res.json()
        if isinstance(body, list) and body:
            return body[0].get("store_id")
    return None


def get_auth_context(authorization: Optional[str] = Header(None)) -> AuthContext:
    """Verifikasi JWT (signature+exp) lalu kembalikan store_id milik user.

    Anti-IDOR: store_id TIDAK diambil dari query param klien.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Sesi tidak valid, silakan login dulu")

    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = verify_user_jwt(token)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid atau sudah kedaluwarsa, silakan login ulang",
        )

    user_id = payload.get('sub') or payload.get('id')
    if not user_id:
        raise HTTPException(status_code=401, detail="Token tidak memuat identitas user")

    auth_header = f"Bearer {token}"

    try:
        store_id = fetch_own_store_id(user_id, auth_header)
    except ValueError:
        raise HTTPException(status_code=400, detail="Identitas user tidak valid")
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="Layanan sedang gangguan, coba lagi nanti")

    if not store_id:
        raise HTTPException(
            status_code=400,
            detail="Akun Anda belum terhubung dengan toko mana pun",
        )

    return AuthContext(store_id=store_id, auth_header=auth_header, user_id=user_id)
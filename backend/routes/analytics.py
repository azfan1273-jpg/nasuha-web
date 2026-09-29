import requests
from urllib.parse import quote
from typing import Optional

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request

from config.supabase_config import SUPABASE_URL, get_supabase_headers, verify_user_jwt
from security import is_rate_limited, sanitize_filter_value, is_valid_email

analytics_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _client_ip(request: Request) -> str:
    fwd = request.headers.get('X-Forwarded-For', '')
    if fwd:
        return fwd.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


def _fetch_own_store_id(user_id: str, auth_header: str) -> Optional[str]:
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


# ---------------------------------------------------------------------------
# Dependency: verifikasi JWT + ambil store_id milik user
# ---------------------------------------------------------------------------
class AuthContext:
    __slots__ = ("store_id", "auth_header", "user_id")

    def __init__(self, store_id: str, auth_header: str, user_id: str):
        self.store_id = store_id
        self.auth_header = auth_header
        self.user_id = user_id


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

    # FIX BUG #2: bedakan ValueError (400) vs RequestException (503)
    try:
        store_id = _fetch_own_store_id(user_id, auth_header)
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


# ---------------------------------------------------------------------------
# 1. POST /api/login
# ---------------------------------------------------------------------------
@analytics_router.post("/login")
def login(request: Request, body: dict = Body(...)):
    if is_rate_limited(f"login:{_client_ip(request)}", limit=5, window=60):
        raise HTTPException(
            status_code=429,
            detail="Terlalu banyak percobaan login. Coba lagi dalam 1 menit.",
        )

    # FIX: body harus dict, bukan list/string (kalau client kirim JSON aneh)
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
            store_id = _fetch_own_store_id(user_id, user_auth_header)
        except (ValueError, requests.RequestException):
            # Login tetap sukses walau store_id gagal di-fetch.
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
# 2. GET /api/transactions
# ---------------------------------------------------------------------------
@analytics_router.get("/transactions")
def get_transactions(ctx: AuthContext = Depends(get_auth_context)):
    # FIX BUG #2: sanitize store_id dari DB bisa raise ValueError
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


# ---------------------------------------------------------------------------
# 3. GET /api/downloads
# ---------------------------------------------------------------------------
@analytics_router.get("/downloads")
def get_downloads(request: Request):
    if is_rate_limited(f"downloads:{_client_ip(request)}", limit=30, window=60):
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

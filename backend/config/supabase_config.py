import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

# Kunci untuk memverifikasi JWT user secara lokal.
# Di Supabase (GoTrue), JWT signed dengan "JWT secret" project.
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
SUPABASE_JWT_ISSUER = os.environ.get("SUPABASE_JWT_ISSUER", "supabase").strip()

supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        # Jangan mencetak isi key/config ke log.
        print(f"Error init Supabase client: {type(e).__name__}")


def get_supabase_headers(auth_header=None):
    """Header untuk request REST/Auth Supabase.

    PENTING: `auth_header` harus berisi 'Bearer <JWT user>'. Jika kosong,
    TIDAK ada fallback ke service key di sini — caller wajib menolak request
    tanpa token user, supaya tidak bisa membaca/menulis data lintas toko.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Konfigurasi Supabase tidak tersedia di server")
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    if auth_header:
        headers["Authorization"] = auth_header
    return headers


def verify_user_jwt(token: str) -> dict:
    """Verifikasi signature + issuer + expiry JWT user.

    Mengembalikan payload jika valid; melempar jwt.InvalidTokenError jika tidak.
    Ini menutup celah IDOR: sebelumnya token di-decode TANPA verifikasi
    signature sehingga siapa pun bisa memalsukan claim 'sub'/'store_id'.
    """
    import jwt as pyjwt

    if not SUPABASE_JWT_SECRET:
        # Fail closed: tanpa secret, kita tidak akan pernah menerima token.
        raise pyjwt.InvalidTokenError("Server tidak dikonfigurasi untuk verifikasi token")

    return pyjwt.decode(
        token,
        SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        issuer=SUPABASE_JWT_ISSUER,
        options={"require": ["exp"]},
        leeway=30,
    )

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


def _decode_unverified(token: str) -> dict:
    """Decode payload TANPA verifikasi (hanya untuk membaca klaim 'iss')."""
    import jwt as pyjwt
    return pyjwt.decode(token, options={"verify_signature": False})


def verify_user_jwt(token: str) -> dict:
    """Verifikasi signature + expiry JWT user.

    Strategi dua tingkat (defense in depth):
    1. Verifikasi lokal HS256 memakai SUPABASE_JWT_SECRET; jika tidak cocok,
       coba fallback ke legacy secret / anon key (kompatibel project lama/baru).
    2. Jika semua secret lokal gagal, verifikasi via endpoint JWKS Supabase
       (issuer diambil dari token itu sendiri) — selalu valid selama token
       memang berasal dari project Supabase lo.

    Mengembalikan payload jika valid; melempar exception jika tidak.
    """
    import jwt as pyjwt

    candidates = [s.strip() for s in (SUPABASE_JWT_SECRET, SUPABASE_KEY) if s and s.strip()]

    last_error = None
    for secret in candidates:
        try:
            return pyjwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"require": ["exp"]},
                leeway=30,
            )
        except pyjwt.InvalidTokenError as e:
            last_error = e

    # Fallback: verifikasi signature pakai public key JWKS milik issuer di token.
    try:
        unverified = _decode_unverified(token)
        iss = unverified.get("iss")
        if not iss:
            raise pyjwt.InvalidTokenError("Token tanpa issuer")
        jwks_client = pyjwt.PyJWKClient(f"{iss}/auth/v1/.well-known/jwks.json")
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        return pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "HS256"],
            issuer=iss,
            options={"require": ["exp"]},
            leeway=30,
        )
    except Exception:
        raise last_error or pyjwt.InvalidTokenError("Token tidak valid")

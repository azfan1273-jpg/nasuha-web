import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env dari root project.
# Struktur: nasuha-web/.env (root) ← backend/config/supabase_config.py
# Naik 3 level: config/ → backend/ → nasuha-web/
# ---------------------------------------------------------------------------
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(_env_path)

from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

# Kunci untuk memverifikasi JWT user secara lokal (HS256).
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


def _build_jwks_url(iss: str) -> str:
    """Normalisasi issuer Supabase jadi URL JWKS yang benar.

    Supabase punya beberapa variasi nilai `iss`:
        - "https://xxx.supabase.co/auth/v1"   (format baru, umum)
        - "https://xxx.supabase.co"           (format lama)
        - "supabase"                          (legacy, non-URL)

    Untuk yang non-URL, lempar InvalidTokenError supaya tidak bikin URL
    sampah seperti "supabase/auth/v1/.well-known/jwks.json".
    """
    import jwt as pyjwt

    base = (iss or "").rstrip("/")

    if not base.startswith("http://") and not base.startswith("https://"):
        raise pyjwt.InvalidTokenError("Issuer bukan URL valid, JWKS dilewati")

    # Kalau issuer sudah termasuk "/auth/v1", strip dulu biar tidak dobel.
    if base.endswith("/auth/v1"):
        base = base[: -len("/auth/v1")]

    return f"{base}/auth/v1/.well-known/jwks.json"


def verify_user_jwt(token: str) -> dict:
    """Verifikasi signature + expiry JWT user (support HS256 + ES256/RS256)."""
    import jwt as pyjwt
    import requests as http_requests

    # ------------------------------------------------------------------
    # 1. Cek alg token dulu
    # ------------------------------------------------------------------
    try:
        header = pyjwt.get_unverified_header(token)
    except Exception:
        raise pyjwt.InvalidTokenError("Token tidak valid")

    alg = header.get("alg", "")
    kid = header.get("kid")

    # ------------------------------------------------------------------
    # 2. Kalau HS256 (legacy), pakai JWT_SECRET
    # ------------------------------------------------------------------
    if alg == "HS256":
        if not SUPABASE_JWT_SECRET:
            raise pyjwt.InvalidTokenError("SUPABASE_JWT_SECRET tidak diset")
        return pyjwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience="authenticated",
            options={"require": ["exp"]},
            leeway=30,
        )
    # ------------------------------------------------------------------
    # 3. Kalau ES256/RS256, fetch JWKS manual (bypass PyJWKClient)
    # ------------------------------------------------------------------
    if alg not in ("ES256", "RS256"):
        raise pyjwt.InvalidTokenError(f"Algoritma {alg} tidak didukung")

    # Decode unverified buat ambil issuer
    unverified = pyjwt.decode(token, options={"verify_signature": False})
    iss = unverified.get("iss")
    if not iss:
        raise pyjwt.InvalidTokenError("Token tanpa issuer")

    # Normalisasi issuer → JWKS URL
    base = iss.rstrip("/")
    if base.endswith("/auth/v1"):
        base = base[: -len("/auth/v1")]
    jwks_url = f"{base}/auth/v1/.well-known/jwks.json"

    # Fetch JWKS manual
    try:
        resp = http_requests.get(jwks_url, timeout=10)
        resp.raise_for_status()
        jwks = resp.json()
    except Exception as e:
        raise pyjwt.InvalidTokenError(f"Gagal fetch JWKS: {e}")

    # Cari key yang sesuai kid
    keys = jwks.get("keys", [])
    if not keys:
        raise pyjwt.InvalidTokenError("JWKS kosong")

    signing_key = None
    for key in keys:
        if kid and key.get("kid") != kid:
            continue
        signing_key = key
        break

    if not signing_key:
        raise pyjwt.InvalidTokenError(f"Key dengan kid={kid} tidak ditemukan di JWKS")

    # Bangun public key dari JWK
    try:
        from jwt.algorithms import ECAlgorithm, RSAAlgorithm
        if alg == "ES256":
            pub_key = ECAlgorithm.from_jwk(signing_key)
        else:
            pub_key = RSAAlgorithm.from_jwk(signing_key)
    except Exception as e:
        raise pyjwt.InvalidTokenError(f"Gagal parse JWK: {e}")

    return pyjwt.decode(
        token,
        pub_key,
        algorithms=[alg],
        issuer=iss,
        audience="authenticated",
        options={"require": ["exp"]},
        leeway=30,
    )

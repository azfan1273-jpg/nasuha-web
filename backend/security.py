"""Utilitas keamanan: rate limiting in-memory + sanitasi input untuk query string Supabase."""
import re
import time
from collections import defaultdict, deque
from threading import Lock

# ---------------------------------------------------------------------------
# Rate limiter sederhana (in-memory). Cukup untuk single-instance; jika
# deploy multi-instance, ganti dengan Redis.
# ---------------------------------------------------------------------------
_hits = defaultdict(deque)
_lock = Lock()


def is_rate_limited(key: str, limit: int = 10, window: int = 60) -> bool:
    """Return True jika `key` sudah melebihi `limit` request dalam `window` detik."""
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(now)
        return False


# ---------------------------------------------------------------------------
# Sanitasi nilai yang disisipkan ke query string PostgREST
# (mis. ?store_id=eq.<value>). Ini mencegah "parameter injection" ke REST API,
# ekuivalen proteksi SQL-injection pada pola raw-string-query.
# ---------------------------------------------------------------------------
_UUID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")


def sanitize_filter_value(value, max_len: int = 128) -> str:
    """Validasi & normalisasi nilai filter. Melempar ValueError jika tidak valid."""
    if value is None:
        raise ValueError("Nilai filter kosong")
    s = str(value).strip()
    if not s or len(s) > max_len:
        raise ValueError("Nilai filter tidak valid")
    # UUID (user id / store id umumnya UUID Supabase)
    if _UUID_RE.match(s):
        return s
    # Alternatif: alfanumerik + dash/underscore saja. Karakter seperti &, =, ., *,
    # spasi, kurung diblokir agar tidak bisa menyuntik filter tambahan.
    if re.match(r"^[A-Za-z0-9_-]+$", s):
        return s
    raise ValueError("Format nilai filter tidak diizinkan")


SAFE_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str, max_len: int = 254) -> bool:
    return bool(email) and len(email) <= max_len and bool(SAFE_EMAIL_RE.match(email))

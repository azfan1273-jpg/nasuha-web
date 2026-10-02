"""
Helper parsing tanggal/waktu + konversi timezone.

Konteks:
    - Supabase menyimpan semua timestamp dalam UTC.
    - Setiap toko punya zona waktu sendiri (kolom `stores.timezone`).
    - Display ke user (frontend) harus pakai zona waktu toko.

Aturan:
    - Semua datetime dari DB: parse sebagai UTC → timezone-aware.
    - Perhitungan "hari ini" / "besok" untuk toko tertentu: convert
      ke zona toko, baru ambil .date().
"""

from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except ImportError:
    ZoneInfo = None  # fallback: caller harus handle


# Mapping kode zona ke nama IANA.
# Dipakai kalau ada data lama yang formatnya bukan IANA.
# (Contoh: user input "WIB" manual, atau "WIB" dari dropdown.)
TIMEZONE_ALIASES = {
    "WIB": "Asia/Jakarta",
    "WITA": "Asia/Makassar",
    "WIT": "Asia/Jayapura",
    "UTC": "UTC",
}


def parse_datetime(value):
    """
    Parse ISO datetime string dari Supabase dan normalisasi ke UTC.

    Args:
        value: ISO string, datetime, atau None.

    Returns:
        datetime (timezone-aware, UTC) atau None kalau tidak valid.
    """
    if not value:
        return None

    try:
        value = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


def resolve_timezone(timezone_str):
    """
    Resolve string timezone jadi objek ZoneInfo.

    Menerima:
        - IANA name: "Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura"
        - Alias: "WIB", "WITA", "WIT", "UTC"
        - None / kosong -> default ke Asia/Jakarta (WIB)

    Return:
        ZoneInfo object, atau None kalau zoneinfo tidak tersedia.
    """
    if ZoneInfo is None:
        return None

    if not timezone_str:
        timezone_str = "Asia/Jakarta"

    tz_name = TIMEZONE_ALIASES.get(
        str(timezone_str).strip().upper(),
        str(timezone_str).strip(),
    )

    try:
        return ZoneInfo(tz_name)
    except Exception:
        # Fallback kalau timezone string invalid
        return ZoneInfo("Asia/Jakarta")


def utc_now():
    """Waktu sekarang dalam UTC (timezone-aware)."""
    return datetime.now(timezone.utc)


def to_local(dt_utc, timezone_str):
    """
    Convert datetime UTC ke zona waktu toko.

    Args:
        dt_utc: datetime (timezone-aware UTC) atau None.
        timezone_str: IANA name atau alias.

    Returns:
        datetime di zona lokal, atau None kalau dt_utc None.
    """
    if dt_utc is None:
        return None

    tz = resolve_timezone(timezone_str)
    if tz is None:
        return dt_utc  # fallback: biarin UTC

    return dt_utc.astimezone(tz)


def get_local_today(timezone_str):
    """
    Tanggal 'hari ini' menurut zona waktu toko.

    Contoh:
        UTC = 2026-09-30 23:00
        Toko WIB (UTC+7) -> 2026-10-01 06:00 -> return date(2026, 10, 1)
    """
    tz = resolve_timezone(timezone_str)
    now = datetime.now(timezone.utc)

    if tz is None:
        return now.date()

    return now.astimezone(tz).date()


def get_local_tomorrow(timezone_str):
    """
    Tanggal 'besok' menurut zona waktu toko.

    Dipakai Clay Engine untuk menentukan "target prediksi".
    """
    today = get_local_today(timezone_str)
    return today + timedelta(days=1)

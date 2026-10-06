"""Helper parsing tanggal/waktu + konversi timezone."""

from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None


TIMEZONE_ALIASES = {
    "WIB": "Asia/Jakarta",
    "WITA": "Asia/Makassar",
    "WIT": "Asia/Jayapura",
    "UTC": "UTC",
}


def parse_datetime(value):
    """Parse ISO datetime dari Supabase → timezone-aware UTC."""
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
    """Resolve string timezone jadi ZoneInfo. Default WIB."""
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
        return ZoneInfo("Asia/Jakarta")


def utc_now():
    return datetime.now(timezone.utc)


def to_local(dt_utc, timezone_str):
    if dt_utc is None:
        return None
    tz = resolve_timezone(timezone_str)
    if tz is None:
        return dt_utc
    return dt_utc.astimezone(tz)


def get_local_today(timezone_str):
    tz = resolve_timezone(timezone_str)
    now = datetime.now(timezone.utc)
    if tz is None:
        return now.date()
    return now.astimezone(tz).date()


def get_local_tomorrow(timezone_str):
    return get_local_today(timezone_str) + timedelta(days=1)


def day_range_utc(d, tz):
    """Tanggal lokal → range UTC ISO [start, end). end eksklusif."""
    start_local = datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )

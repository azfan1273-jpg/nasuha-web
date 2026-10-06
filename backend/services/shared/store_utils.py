"""Helper info toko."""

import logging

import requests

from config.supabase_config import SUPABASE_URL, get_supabase_headers

logger = logging.getLogger(__name__)


DEFAULT_TIMEZONE = "Asia/Jakarta"


def fetch_store_timezone(store_id, auth_header, timeout=10):
    """Ambil timezone toko dari table `stores`. Soft-fail → default."""
    from urllib.parse import quote
    from security import sanitize_filter_value

    if not store_id:
        return DEFAULT_TIMEZONE

    try:
        sid = sanitize_filter_value(store_id)
    except ValueError:
        return DEFAULT_TIMEZONE

    url = (
        f"{SUPABASE_URL}/rest/v1/stores"
        f"?id=eq.{quote(sid, safe='')}&select=timezone&limit=1"
    )

    try:
        res = requests.get(url, headers=get_supabase_headers(auth_header), timeout=timeout)
    except requests.RequestException:
        return DEFAULT_TIMEZONE

    if res.status_code != 200:
        return DEFAULT_TIMEZONE

    try:
        data = res.json()
    except ValueError:
        return DEFAULT_TIMEZONE

    if not isinstance(data, list) or not data:
        return DEFAULT_TIMEZONE

    tz = data[0].get("timezone")
    if not tz or not isinstance(tz, str):
        return DEFAULT_TIMEZONE

    return tz.strip() or DEFAULT_TIMEZONE


def fetch_all_store_ids(auth_header, timeout=15):
    """
    Ambil semua store_id dari table `stores`.
    Butuh service_role (bypass RLS) — kalau pakai JWT user, bakal cuma
    return store user tsb.

    Return: list[str] UUID. Empty list kalau gagal.
    """
    url = f"{SUPABASE_URL}/rest/v1/stores?select=id&order=created_at.asc"

    try:
        res = requests.get(url, headers=get_supabase_headers(auth_header), timeout=timeout)
    except requests.RequestException as e:
        logger.warning("fetch_all_store_ids network: %s", e)
        return []

    if res.status_code != 200:
        logger.warning("fetch_all_store_ids HTTP %s: %s", res.status_code, res.text[:200])
        return []

    try:
        data = res.json()
    except ValueError:
        return []

    if not isinstance(data, list):
        return []

    return [row["id"] for row in data if row.get("id")]

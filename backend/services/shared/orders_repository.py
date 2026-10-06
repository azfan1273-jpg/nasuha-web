"""Fetch orders 1 toko dari Supabase REST. Shared oleh semua engine."""

import logging
from datetime import timedelta
from urllib.parse import quote

import requests

from config.supabase_config import SUPABASE_URL, get_supabase_headers
from security import sanitize_filter_value
from services.shared.datetime_utils import utc_now

logger = logging.getLogger(__name__)


def fetch_orders_for_store(store_id, auth_header, months_back=6, limit=5000):
    """Ambil orders 1 toko via REST. Soft-fail → [] kalau error."""
    if not store_id:
        return []

    try:
        sid = sanitize_filter_value(store_id)
    except ValueError:
        logger.warning("fetch_orders_for_store: store_id invalid")
        return []

    cutoff = (utc_now() - timedelta(days=months_back * 30)).isoformat()
    variants = ["*,order_items(*)", "*"]

    for select_clause in variants:
        url = (
            f"{SUPABASE_URL}/rest/v1/orders?select={select_clause}"
            f"&store_id=eq.{quote(sid, safe='')}"
            f"&created_at=gte.{quote(cutoff, safe='')}"
            f"&order=created_at.desc&limit={limit}"
        )
        try:
            res = requests.get(url, headers=get_supabase_headers(auth_header), timeout=20)
        except requests.RequestException as e:
            logger.warning("fetch orders network: %s", e)
            continue

        if res.status_code != 200:
            logger.warning("fetch orders HTTP %s: %s", res.status_code, res.text[:200])
            continue

        try:
            data = res.json()
        except ValueError:
            continue

        if isinstance(data, list):
            return data

    return []

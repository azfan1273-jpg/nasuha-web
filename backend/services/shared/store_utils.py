"""
Helper info toko.

Konteks:
    Table `stores` menyimpan data per toko, termasuk kolom `timezone`
    (format IANA, contoh: "Asia/Jakarta", "Asia/Makassar", "Asia/Jayapura").

    Clay Engine butuh timezone toko untuk:
        - Hitung "besok" sesuai zona toko (bukan zona server).
        - Convert timestamp UTC dari Supabase ke waktu lokal.

Aturan:
    - Semua query WAJIB filter `store_id` (pintu masuk otentikasi).
    - Kalau fetch gagal, return default timezone (Asia/Jakarta) daripada
      crash atau salah hitung.
"""

import requests
from urllib.parse import quote

from config.supabase_config import SUPABASE_URL, get_supabase_headers
from security import sanitize_filter_value


# Default timezone kalau fetch gagal atau kolom kosong.
DEFAULT_TIMEZONE = "Asia/Jakarta"


def fetch_store_timezone(store_id, auth_header, timeout=10):
    """
    Ambil timezone toko dari table `stores`.

    Args:
        store_id: UUID toko (dari profile user, sudah terverifikasi).
        auth_header: Header Authorization berisi "Bearer <JWT user>".
        timeout: Timeout HTTP request (default 10 detik).

    Returns:
        String IANA timezone (contoh: "Asia/Jakarta").
        Fallback ke DEFAULT_TIMEZONE kalau:
            - store_id kosong
            - request gagal
            - kolom timezone kosong
            - response tidak sesuai ekspektasi

    Catatan:
        Fungsi ini sengaja TIDAK raise exception. Karena timezone bukan
        data krusial (masih bisa jalan pakai default), lebih baik soft-fail
        daripada bikin seluruh engine 500.
    """
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
        res = requests.get(
            url,
            headers=get_supabase_headers(auth_header),
            timeout=timeout,
        )
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

"""
Helper pembacaan order dan order_items.

Update v2:
    - Tambah filter status SELESAI (buang BATAL, PROSES, Antrian).
    - Tambah dedupe order dalam window 6 jam (1 customer, 1 event).
      Contoh: Keke order 2x dalam 5 menit → dianggap 1 kunjungan.

Konteks struktur Supabase:
    orders:
        id, customer_code, customer_name, service_name, total_price,
        status, created_at, store_id, ...
    order_items:
        id, order_id, service_name, qty, price, subtotal, unit, store_id, ...

Prinsip:
    - Hanya order SELESAI yang dianggap transaksi valid.
    - orders.service_name HANYA fallback kalau order_items kosong.
    - Revenue dihitung dari subtotal item, fallback ke price * qty.
"""

from collections import defaultdict
from datetime import datetime, timezone

from services.shared.customer_utils import get_customer_key
from services.shared.datetime_utils import parse_datetime


# ============================================================
# STATUS FILTER
# ============================================================

# ============================================================
# STATUS FILTER
# ============================================================

VALID_ORDER_STATUS = "selesai"
CANCELLED_ORDER_STATUS = "batal"

# Pattern buat skip order BATAL/CANCEL/CANCELLED (case-insensitive)
CANCELLED_PATTERNS = ("batal", "cancel", "cancelled")


def is_completed_order(order):
    """Cek apakah order berstatus SELESAI (untuk revenue)."""
    status = str(order.get("status") or "").strip().lower()
    return status == VALID_ORDER_STATUS


def is_cancelled_order(order):
    """Skip BATAL/CANCEL/CANCELLED (case-insensitive, pattern)."""
    status = str(order.get("status") or "").strip().lower()
    return any(p in status for p in CANCELLED_PATTERNS)


def filter_completed_orders(orders):
    """Filter list orders, cuma keep yang statusnya SELESAI (untuk revenue)."""
    return [o for o in orders if is_completed_order(o)]


def filter_non_cancelled_orders(orders):
    """
    Filter list orders, buang yang BATAL.

    Dipakai untuk hitung CYCLE & last_transaction, karena customer
    yang lagi Antrian/PROSES dianggap UDAH DATANG (bawa cucian).
    """
    return [o for o in orders if not is_cancelled_order(o)]
    
# ============================================================
# DEDUPE (1 customer, 1 event)
# ============================================================

# Window dedup: order dalam 6 jam dianggap 1 kunjungan yang sama.
DEDUPE_WINDOW_SECONDS = 6 * 3600


def dedupe_orders_by_window(orders, window_seconds=DEDUPE_WINDOW_SECONDS):
    """
    Gabung order yang terjadi dalam window waktu yang sama per customer.

    Contoh kasus:
        Keke order jam 20:18 dan 20:23 (5 menit selisih) → 1 event.
        Keke order 17 Sep pagi dan 17 Sep malam (>6 jam) → 2 event.

    Logic:
        - Group order by customer_key (dari customer_utils).
        - Sort tiap group by created_at.
        - Iterasi: keep order pertama, skip yang gap-nya <= window
          dari order yang TERAKHIR DI-KEEP (bukan terakhir dilihat).
        - Kalau gap > window, itu event baru → keep.

    Args:
        orders: list order.
        window_seconds: window dedup dalam detik (default 6 jam).

    Returns:
        list order yang udah di-dedup.
    """
    by_customer = defaultdict(list)

    for order in orders:
        key = get_customer_key(order)
        by_customer[key].append(order)

    result = []

    for group in by_customer.values():
        # Sort by created_at asc, fallback ke datetime.min kalau invalid
        def _sort_key(o):
            dt = parse_datetime(o.get("created_at"))
            return dt if dt else datetime.min.replace(tzinfo=timezone.utc)

        group_sorted = sorted(group, key=_sort_key)

        last_kept_dt = None

        for order in group_sorted:
            dt = parse_datetime(order.get("created_at"))

            if dt is None:
                # Tanggal invalid, biarin aja (nggak bisa dedup)
                result.append(order)
                continue

            if last_kept_dt is None:
                result.append(order)
                last_kept_dt = dt
                continue

            gap_seconds = (dt - last_kept_dt).total_seconds()
            if gap_seconds > window_seconds:
                # Event baru
                result.append(order)
                last_kept_dt = dt
            # else: skip (dedup)

    return result


# ============================================================
# ORDER PRICE & ITEMS
# ============================================================

def get_order_price(order):
    """Ambil total_price dari order. Return 0.0 kalau gagal parse."""
    try:
        return float(order.get("total_price") or 0)
    except (ValueError, TypeError):
        return 0.0


def get_items(order):
    """Ambil list order_items. Return [] kalau tidak ada / bukan list."""
    items = order.get("order_items")
    if not isinstance(items, list):
        return []
    return items


def get_item_service(item):
    """Ambil nama service dari 1 item. Kosong kalau tidak ada."""
    return str(item.get("service_name") or "").strip()


def get_item_qty(item):
    """Ambil qty item. Default 1.0 kalau kosong / <= 0 / invalid."""
    try:
        qty = float(item.get("qty") or 1)
        if qty <= 0:
            return 1.0
        return qty
    except (ValueError, TypeError):
        return 1.0


def get_item_subtotal(item):
    """
    Ambil subtotal 1 item dengan fallback berlapis.
        Priority: subtotal → price × qty → 0.0
    """
    try:
        subtotal = float(item.get("subtotal") or 0)
        if subtotal != 0:
            return subtotal
    except (ValueError, TypeError):
        pass

    try:
        price = float(item.get("price") or 0)
        qty = get_item_qty(item)
        return price * qty
    except (ValueError, TypeError):
        return 0.0


def extract_services_from_order(order):
    """
    Ambil SEMUA service dari 1 order.
        Priority: order_items → orders.service_name
    """
    items = get_items(order)

    services = []
    for item in items:
        service = get_item_service(item)
        if service:
            services.append(service)

    if services:
        return services

    fallback = str(order.get("service_name") or "").strip()
    return [fallback] if fallback else []


def build_service_stats(orders):
    """
    Hitung statistik per-service dari list orders.

    Untuk tiap service:
        - usage_count  : total qty
        - order_count  : jumlah order unik
        - revenue      : total subtotal
    """
    service_stats = defaultdict(
        lambda: {"usage_count": 0.0, "order_count": 0, "revenue": 0.0}
    )

    for order in orders:
        items = get_items(order)

        if items:
            seen_in_order = set()
            for item in items:
                service = get_item_service(item)
                if not service:
                    continue

                qty = get_item_qty(item)
                subtotal = get_item_subtotal(item)

                service_stats[service]["usage_count"] += qty
                service_stats[service]["revenue"] += subtotal

                if service not in seen_in_order:
                    service_stats[service]["order_count"] += 1
                    seen_in_order.add(service)
        else:
            service = str(order.get("service_name") or "").strip()
            if service:
                service_stats[service]["usage_count"] += 1
                service_stats[service]["order_count"] += 1
                service_stats[service]["revenue"] += get_order_price(order)

    return service_stats

"""
Helper identitas customer.

Aturan (per arahan user):
    - Grouping customer WAJIB pakai `customer_code`.
    - Nomor HP TIDAK PERNAH dipakai untuk grouping/identifikasi.
      (phone sering kosong / cuma "08" / "-" di data lapangan.)
    - Nomor HP tetap disimpan untuk DISPLAY saja (tombol WA reminder).

Kenapa `customer_code`?
    1. Format konsisten (contoh: NASUHA-93716) — di-generate sistem.
    2. Tidak berubah sepanjang umur customer.
    3. Ada di table `customers` (induk) dan `orders` (referensi).
"""


def clean_text(value):
    """Normalisasi text: None -> '', whitespace di-trim."""
    if value is None:
        return ""
    return str(value).strip()


def normalize_phone(value):
    """
    Normalisasi nomor HP jadi digit murni (untuk DISPLAY saja).

    Catatan:
        - Fungsi ini TIDAK BOLEH dipakai untuk grouping/identifikasi.
        - Hanya untuk bersihin format sebelum ditampilkan / dikirim WA.
    """
    value = clean_text(value)

    if not value or value in {"-", "null", "NULL"}:
        return ""

    digits = "".join(ch for ch in value if ch.isdigit())

    if len(digits) < 6:
        return ""

    return digits


def get_customer_code(order):
    """
    Ambil customer_code dari order.

    Prioritas kolom:
        1. customer_code   (kolom utama — sudah ada di table orders)
        2. customer_id     (fallback kalau ada)
        3. customer_uuid   (fallback kalau ada)

    Return string kosong kalau tidak ada sama sekali.
    """
    code = clean_text(order.get("customer_code"))
    if code:
        return code

    return clean_text(
        order.get("customer_id") or order.get("customer_uuid")
    )


def get_phone(order):
    """
    Ambil nomor HP dari order untuk DISPLAY saja.

    TIDAK dipakai untuk grouping. Kalau butuh identifikasi,
    pakai `get_customer_code()`.

    Kolom yang dicek:
        customer_phone, phone, customer_number, customer_no
    """
    candidates = (
        "customer_phone",
        "phone",
        "customer_number",
        "customer_no",
    )

    for field in candidates:
        value = normalize_phone(order.get(field))
        if value:
            return value

    return ""


def get_customer_name(order):
    """
    Ambil nama customer dengan fallback berlapis.

    Priority:
        1. customer_name
        2. name
        3. "Pelanggan Anonim"
    """
    return (
        clean_text(order.get("customer_name"))
        or clean_text(order.get("name"))
        or "Pelanggan Anonim"
    )


def get_customer_key(order):
    """
    Bikin key unik untuk grouping order per customer.

    Priority:
        1. customer_code       -> "code:<kode>"
        2. customer_id / uuid  -> "id:<uuid>"
        3. nama (lowercase)    -> "name:<nama>"

    PENTING: Phone TIDAK dipakai di sini.

    Kenapa nama jadi fallback terakhir?
        Karena secara statistik hampir semua order punya customer_code.
        Kalau ada order dengan customer_code NULL (data lama / import
        gagal), kita masih coba grouping by nama daripada dianggap
        customer baru sendiri-sendiri.

    Prefix ("code:", "id:", "name:") mencegah tabrakan antar kategori.
    """
    # 1. customer_code (paling prioritas, sesuai arahan)
    code = get_customer_code(order)
    if code:
        return f"code:{code}"

    # 2. Fallback terakhir: nama
    name = get_customer_name(order).lower()
    return f"name:{name}"

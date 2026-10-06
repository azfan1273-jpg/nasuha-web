"""
Shared utilities untuk semua engine di Nasuha Web.

Modul ini berisi fungsi-fungsi umum yang dipakai bersama oleh:
    - Clay Engine      (prediksi customer balik)
    - Churn Engine     (nanti)
    - Forecast Engine  (nanti)
    - Segment Engine   (nanti)

Prinsip:
    - Fungsi di sini TIDAK BOLEH bergantung ke engine manapun.
    - Fungsi di sini harus generic: ambil data, bersihin, hitung statistik dasar.
    - Logic spesifik engine (scoring, filtering, tagging) ada di file engine masing-masing.

Struktur:
    datetime_utils.py  -> parsing tanggal/waktu
    customer_utils.py  -> helper identitas customer (nama, HP, key)
    order_utils.py     -> helper order & order_items + service stats
    cycle_utils.py     -> hitung siklus antar transaksi customer
"""

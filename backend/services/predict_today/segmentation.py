"""Segmentasi pelanggan berdasarkan bentuk pola kunjungannya.

Kenapa penting: satu aturan untuk semua pelanggan bikin prediksi jelek di
kedua ujung. Pelanggan "rutin" (interval rapi) harusnya dapat skor penuh;
pelanggan "sporadis" (jarang, interval acak) jangan pernah tampil dengan
skor 85+ padahal model nggak punya dasar kuat.

Kategori:
    rutin     → interval konsisten (rel-dev rendah), siklus pendek-menengah
    weekend   → pola hari spesifik (selalu Sabtu/Minggu dsb.)
    musiman   → siklus panjang (>21 hari) atau jeda mengulang per bulan
    sporadis  → sisanya; data cukup tapi polanya nggak jelas
"""

from collections import Counter
from datetime import timedelta

WEEKEND_PATTERN_MIN_SHARE = 0.75   # >=75% kunjungan di <=2 hari yang sama
LONG_CYCLE_DAYS = 21               # cycle > ini dianggap musiman
ROUTINE_MAX_REL = 0.30             # rel-dev maksimum utk disebut rutin

SEGMENT_TAGS = {
    "routine": "Rutin",
    "weekend": "Weekend",
    "seasonal": "Musiman",
    "sporadic": "Sporadis",
}

# Penyesuaian skor mentah per segmen (ditambah setelah pembobotan faktor).
SEGMENT_SCORE_ADJUST = {
    "routine": +3,     # polanya terbukti, layak sedikit ekstra percaya diri
    "weekend": 0,
    "seasonal": -2,    # siklus panjang = lebih banyak hal yang bisa berubah
    "sporadic": -8,    # sengaja dijatuhkan biar nggak numpuk di top list
}


def classify_segment(unique_dates, intervals, cycle_days, rel_dev):
    """Tentukan segmen pelanggan dari histori tanggal kunjugan.

    Args:
        unique_dates: list date unik (ascending).
        intervals: list selisih hari antar kunjungan.
        cycle_days: cycle terpilih (hasil detect_cycle).
        rel_dev: relative deviation cycle tsb.

    Return: salah satu dari "weekend" | "seasonal" | "routine" | "sporadic".
    """
    if not unique_dates or not intervals:
        return "sporadic"

    # 1) Pola hari tetap (misal selalu Minggu): share dominan di <=2 weekday.
    wd_counter = Counter(d.weekday() for d in unique_dates)
    top_share = sum(c for _, c in wd_counter.most_common(2)) / len(unique_dates)
    distinct_wd = len(wd_counter)
    if distinct_wd <= 2 and top_share >= WEEKEND_PATTERN_MIN_SHARE:
        return "weekend"

    # 2) Siklus panjang → musiman (bulanan/2-mingguan).
    if cycle_days > LONG_CYCLE_DAYS:
        return "seasonal"

    # 3) Interval rapi → rutin.
    if rel_dev <= ROUTINE_MAX_REL:
        return "routine"

    return "sporadic"

"""
Helper hitung siklus transaksi customer.

Dipakai bersama oleh:
    - Clay Engine      (prediksi kapan customer balik)
    - Churn Engine     (nanti: deteksi customer yang lewat siklus)

Kenapa MEDIAN, bukan MEAN?
    Contoh interval (hari): [7, 7, 8, 60, 7]
        Mean   = 17.8  (tertarik outlier 60)
        Median = 7     (tahan outlier)
    Untuk laundry, pola 7 hari itu rutin mingguan. Satu kali
    customer telat 2 bulan nggak boleh ngerusak prediksi.

Kenapa ada batas MIN/MAX cycle?
    Interval di bawah MIN_CYCLE_DAYS (misal 0.5 hari) biasanya
    bukan pola — customer order 2x dalam sehari karena kebutuhan
    mendesak, bukan siklus.

    Interval di atas MAX_CYCLE_DAYS (misal 200 hari) dianggap
    customer sudah "lupa" — bukan siklus normal.
"""

from statistics import median


# Batas cycle yang dianggap valid (hari).
MIN_CYCLE_DAYS = 1
MAX_CYCLE_DAYS = 90


def calculate_cycle_days(transactions):
    """
    Hitung siklus tipikal customer dari list transaksi.

    Args:
        transactions: list of dict, tiap dict minimal punya key "date"
                      (datetime timezone-aware UTC). Boleh sudah di-sort
                      atau belum — fungsi ini akan sort sendiri.

    Returns:
        Tuple (typical_cycle, intervals, avg_deviation):

        typical_cycle : int atau None
            Siklus tipikal dalam hari (median, dibulatkan).
            Return None kalau tidak ada interval valid — supaya engine
            yang manggil bisa skip prediksi (bukan pakai default palsu).

        intervals : list[float]
            Semua interval valid (setelah filter MIN/MAX).
            Berguna buat debugging / engine yang mau analisis distribusi.

        avg_deviation : float
            Rata-rata deviasi absolut dari typical_cycle.
            Menunjukkan seberapa konsisten customer ini.
            Contoh: 1.2 -> konsisten, 8.5 -> tidak konsisten.
    """
    # Ambil tanggal saja, buang yang None, sort ascending
    dates = sorted(
        [tx["date"] for tx in transactions if tx.get("date")],
        reverse=False,
    )

    if len(dates) < 2:
        return None, [], 0.0

    # Hitung selisih hari antar transaksi berurutan
    intervals = []
    for i in range(len(dates) - 1):
        diff_days = (dates[i + 1] - dates[i]).total_seconds() / 86400
        if MIN_CYCLE_DAYS <= diff_days <= MAX_CYCLE_DAYS:
            intervals.append(diff_days)

    if not intervals:
        return None, [], 0.0

    # Siklus tipikal = median interval, minimal 1 hari
    typical_cycle = max(1, round(median(intervals)))

    # Rata-rata deviasi dari typical_cycle
    deviations = [abs(interval - typical_cycle) for interval in intervals]
    avg_deviation = sum(deviations) / len(deviations) if deviations else 0.0

    return typical_cycle, intervals, avg_deviation

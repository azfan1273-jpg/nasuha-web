"""Deteksi siklus kunjungan pelanggan dari riwayat tanggal transaksi.

Prinsip:
    - Tanggal dedup per hari (2 order sehari = 1 kunjungan).
    - Cycle utama = MODE (interval paling sering) yang lolos validasi
      spread, fallback ke median kalau distribusi terlalu menyebar.
      Kenapa? Pola laundry weekend ("besok lagi terus libur seminggu")
      menghasilkan interval [1,6,1,6,...] → median bisa jatuh ke nilai
      yang salah dan semua prediksi jadi kacau.
    - Deviasi diukur dari cycle terpilih; rel-dev > MAX_RELATIVE_DEVIATION
      dianggap "pola liar" → tidak diprediksi.
"""

import math
from collections import Counter
from statistics import median

MIN_CYCLE_DAYS = 1
MAX_CYCLE_DAYS = 90
MAX_RELATIVE_DEVIATION = 0.35
# Spread (mean |interval - candidate| / candidate) maksimum agar sebuah
# kandidat interval layak dipilih sebagai mode-cycle.
MAX_MODE_SPREAD = 0.5

# --- Exponential weighted cycle (recency bias) -------------------
# Interval terbaru lebih penting dari yang lama: pelanggan bisa berubah
# kebiasaan (langganan naik, pindah jadwal). Half-life dalam jumlah
# interval — interval paling baru berbobot 1.0, yang berjarak N langkah
# berbobot 0.5^N. Median berbobot = kandidat utama (tahan outlier);
# rata-rata berbobot hanya dipakai sebagai PENDEKAT kalau keduanya
# sepakat (selisih <= 1 hari) — itu menandakan distribusi baru benar-
# benar bergeser, bukan sekadar satu kunjungan iseng kemarin sore.
EWMA_HALF_LIFE = 6


def unique_visit_dates(orders, parse_date):
    """Ekstrak daftar tanggal kunjungan unik, sorted ascending.

    Args:
        orders: list order dict.
        parse_date: callable(order) -> date | None (timezone-aware milik caller).
    """
    visits = set()
    for o in orders:
        d = parse_date(o)
        if d is not None:
            visits.add(d)
    return sorted(visits)


def extract_intervals(sorted_dates):
    out = []
    for i in range(1, len(sorted_dates)):
        diff = (sorted_dates[i] - sorted_dates[i - 1]).days
        if MIN_CYCLE_DAYS <= diff <= MAX_CYCLE_DAYS:
            out.append(diff)
    return out


def weighted_median(values, weights):
    """Median dengan bobot per elemen (dipakai utk cycle berbobot-recency)."""
    if not values:
        return None
    pairs = sorted(zip(values, weights))
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return float(v)
    return float(pairs[-1][0])


def recency_weights(intervals, half_life=EWMA_HALF_LIFE):
    """Bobot eksponensial: interval TERBARU (urutan terakhir) bobot 1.0."""
    n = len(intervals)
    decay = math.log(2) / max(1, half_life)
    return [math.exp(-decay * (n - 1 - i)) for i in range(n)]


def ewm_cycle(intervals):
    """Kandidat cycle berbobot-recency.

    Return (cycle_float, agrees: bool) atau None kalau data kosong.
    cycle = median berbobot (robust). `agrees` True kalau rata-rata
    berbobot dan median berbobot selisihnya <= 1 hari → distribusi
    kompak, angka bisa langsung dipakai sebagai metode "ewm".
    """
    if not intervals:
        return None
    w = recency_weights(intervals)
    tw = sum(w)
    wmean = sum(x * wi for x, wi in zip(intervals, w)) / tw
    wmed = weighted_median(intervals, w)
    agrees = abs(wmean - wmed) <= 1.0
    return wmed, agrees


def detect_cycle(intervals):
    """Return (cycle_days, deviation, relative_deviation, method) atau None.

    Kandidat yang diadu (pilih spread paling kecil; seri dimenangkan
    oleh prioritas ewm > mode > median):
        "ewm"    — median berbobot-recency, distribusi kompak.
        "mode"   — interval paling sering, lolos validasi spread.
        "median" — fallback utk distribusi menyebar.
    Recency bikin pelanggan yang pindah jadwal terdeteksi lebih cepat;
    per-ekspresi tetap dilindungi spread supaya satu kunjungan iseng
    nggak menggeser prediksi.
    """
    if not intervals:
        return None

    def spread_of(candidate):
        return sum(abs(x - candidate) for x in intervals) / len(intervals) / candidate

    plain_median = max(1, round(median(intervals)))
    candidates = []  # (spread, priority, cycle)

    ewm = ewm_cycle(intervals)
    if ewm is not None:
        wmed, agrees = ewm
        wmed_r = max(1, round(wmed))
        if agrees:
            candidates.append((spread_of(wmed_r), 0, wmed_r))

    counter = Counter(intervals)
    best_mode = None
    for cand_val in counter:
        key = (spread_of(cand_val), -counter[cand_val], cand_val)
        if best_mode is None or key < best_mode:
            best_mode = key
    mode_spread, mode_candidate = best_mode[0], best_mode[2]
    if mode_spread <= MAX_MODE_SPREAD:
        candidates.append((spread_of(max(1, round(mode_candidate))), 1,
                           max(1, round(mode_candidate))))

    candidates.append((spread_of(plain_median), 2, plain_median))

    _, _, cycle = min(candidates, key=lambda t: (t[0], t[1]))
    method = {0: "ewm", 1: "mode", 2: "median"}[
        min(candidates, key=lambda t: (t[0], t[1]))[1]]

    deviation = sum(abs(x - cycle) for x in intervals) / len(intervals)
    rel = deviation / cycle if cycle > 0 else 999.0
    return cycle, round(deviation, 2), round(rel, 3), method


def analyze_visits(sorted_dates):
    """Ringkasan siklus lengkap dari daftar tanggal unik (ascending).

    Return:
        None                  → data belum cukup.
        {"wild": True, ...}   → pola liar, jangan diprediksi.
        {..., "wild": False}  → siklus valid, siap dipakai prediksi.
    """
    if len(sorted_dates) < 2:
        return None

    intervals = extract_intervals(sorted_dates)
    detected = detect_cycle(intervals)
    if detected is None:
        return None

    cycle, deviation, rel, method = detected
    if rel > MAX_RELATIVE_DEVIATION:
        return {"wild": True, "relative_deviation": rel}

    return {
        "wild": False,
        "cycle_days": cycle,
        "deviation": deviation,
        "relative_deviation": rel,
        "method": method,
        "last_visit": sorted_dates[-1],
    }

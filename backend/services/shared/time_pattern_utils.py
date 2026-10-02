"""
Helper analisa pola hari & jam transaksi.

Dipakai untuk memberi info lebih kaya di kolom "Analisa Siklus":
    Baris 1: "Siklus 5 hari, Favorit Jumat Sore"
    Baris 2: "atau Senin Pagi"

Prinsip:
    - Semua timestamp UTC di-convert ke zona waktu TOKO dulu, baru
      dihitung distribusi hari/jam-nya. Kalau nggak, customer yang
      biasa datang "Jumat pagi WIB" bakal salah dianggap "Kamis malam".
    - "Favorit"   = hari/slot dengan frekuensi tertinggi.
    - "Sekunder"  = hari kedua tertinggi, tapi cuma ditampilkan
      kalau proporsinya >= 15% (biar nggak nampilin hari random
      yang cuma 1x).
"""

from collections import Counter

from services.shared.datetime_utils import to_local


# Nama hari Indonesia. Index .weekday(): 0=Senin .. 6=Minggu
DAY_NAMES_ID = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]

# Minimal proporsi supaya hari "sekunder" layak ditampilkan
SECONDARY_MIN_PCT = 0.15

# Minimal proporsi hari utama supaya dianggap "pola kuat"
STRONG_PATTERN_MIN_PCT = 0.40


def _hour_slot(hour):
    """Kelompokkan jam jadi 4 slot: Pagi, Siang, Sore, Malam."""
    if 5 <= hour < 12:
        return "Pagi"
    if 12 <= hour < 16:
        return "Siang"
    if 16 <= hour < 19:
        return "Sore"
    return "Malam"


def analyze_day_pattern(tx_list, timezone_str):
    """
    Hitung distribusi transaksi per hari (dalam zona waktu toko).

    Args:
        tx_list: list of dict, tiap dict punya key "date" (datetime UTC).
        timezone_str: IANA timezone toko (misal "Asia/Jakarta").

    Returns:
        dict {
            "primary":      ("Jumat", 0.47) atau None,
            "secondary":    ("Sabtu", 0.29) atau None,
            "distribution": {"Senin": 2, "Jumat": 8, ...},
            "total":        17,
            "has_strong":   True,   # primary >= 40%
        }
        atau None kalau tidak ada data valid.
    """
    if not tx_list:
        return None

    counter = Counter()

    for tx in tx_list:
        dt_utc = tx.get("date")
        if not dt_utc:
            continue

        dt_local = to_local(dt_utc, timezone_str)
        if dt_local is None:
            continue

        day_name = DAY_NAMES_ID[dt_local.weekday()]
        counter[day_name] += 1

    total = sum(counter.values())
    if total == 0:
        return None

    # Sort by count desc
    ranked = counter.most_common()

    primary_name, primary_count = ranked[0]
    primary_pct = primary_count / total

    secondary = None
    if len(ranked) >= 2:
        sec_name, sec_count = ranked[1]
        sec_pct = sec_count / total
        if sec_pct >= SECONDARY_MIN_PCT:
            secondary = (sec_name, round(sec_pct, 2))

    return {
        "primary": (primary_name, round(primary_pct, 2)),
        "secondary": secondary,
        "distribution": dict(counter),
        "total": total,
        "has_strong": primary_pct >= STRONG_PATTERN_MIN_PCT,
    }


def analyze_hour_pattern(tx_list, timezone_str):
    """
    Hitung distribusi transaksi per slot jam (dalam zona waktu toko).

    Returns:
        dict {
            "primary":      ("Sore", 0.53) atau None,
            "distribution": {"Pagi": 3, "Sore": 9, ...},
            "total":        17,
        }
        atau None kalau tidak ada data valid.
    """
    if not tx_list:
        return None

    counter = Counter()

    for tx in tx_list:
        dt_utc = tx.get("date")
        if not dt_utc:
            continue

        dt_local = to_local(dt_utc, timezone_str)
        if dt_local is None:
            continue

        slot = _hour_slot(dt_local.hour)
        counter[slot] += 1

    total = sum(counter.values())
    if total == 0:
        return None

    primary_slot, primary_count = counter.most_common(1)[0]
    primary_pct = primary_count / total

    return {
        "primary": (primary_slot, round(primary_pct, 2)),
        "distribution": dict(counter),
        "total": total,
    }


def format_schedule_lines(cycle_days, day_info, hour_info):
    """
    Format baris display "Analisa Siklus" (2 baris).

    Args:
        cycle_days: int (dari calculate_cycle_days) atau None.
        day_info: hasil analyze_day_pattern, atau None.
        hour_info: hasil analyze_hour_pattern, atau None.

    Returns:
        tuple (primary_line, secondary_line):
            primary_line   : str  -> "Siklus 5 hari, Favorit Jumat Sore"
            secondary_line : str or None -> "atau Senin Pagi"

    Aturan:
        - Kalau cycle_days ada, tampilkan "Siklus X hari".
        - Kalau day_info punya pola kuat (>=40%), tambahkan ", Favorit {hari}".
        - Kalau hour_info ada, tambahkan " {slot}" setelah nama hari.
        - Kalau day_info punya sekunder (>=15%), tampilkan baris 2:
          "atau {hari sekunder} {slot jam sekunder}".
        - Kalau tidak ada info sama sekali, primary_line = "Belum cukup data".
    """
    parts = []

    if cycle_days:
        parts.append(f"Siklus {cycle_days} hari")

    # Info hari + jam (pola utama)
    day_primary = day_info.get("primary") if day_info else None
    hour_primary = hour_info.get("primary") if hour_info else None

    if day_primary and day_info and day_info.get("has_strong"):
        day_name = day_primary[0]
        slot = hour_primary[0] if hour_primary else None
        fav_text = f"Favorit {day_name}"
        if slot:
            fav_text += f" {slot}"
        parts.append(fav_text)

    primary_line = ", ".join(parts) if parts else "Belum cukup data"

    # Baris 2: sekunder (opsional)
    secondary_line = None
    if day_info and day_info.get("secondary"):
        sec_day = day_info["secondary"][0]
        # Cari slot jam sekunder? Untuk simplifikasi, pakai slot jam utama.
        slot = hour_primary[0] if hour_primary else None
        sec_text = sec_day
        if slot:
            sec_text += f" {slot}"
        secondary_line = f"atau {sec_text}"

    return primary_line, secondary_line

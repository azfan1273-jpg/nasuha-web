"""Prediction v2 — target kedatangan hari ini.

Upgrade utama dibanding predict-today-v5.1:
    1. Multi-cycle: interval yang sama-sama valid (misal pola mingguan
       7 hari DAN pola weekend [1,6]) dipakai sebagai KANDIDAT tanggal
       prediksi, bukan cuma satu cycle median.
    2. Day-of-week prior: distribusi hari kunjungan jadi sinyal kedua.
       Kalau semua kandidat siklus meleset dari hari ini, tapi customer
       punya pola kuat di hari ini (>=40% kunjungan), tetap diprediksi
       dengan confidence lebih rendah.
    3. Confidence berbasis data historis: skor dipetakan ke akurasi
       empiris per level (dihitung dari prediction_logs yang sudah
       divonis), bukan angka mentah hasil kali faktor.
    4. Score tidak lagi "semua 90+" — timing, konsistensi, jumlah
       histori, dan kecocokan hari digabung dengan bobot eksplisit.

Output tetap kompatibel dengan bentuk payload lama (predictions list
dengan field-field yang dipakai UI).
"""

import logging
import math
from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median

from services.predict_today.cycle import (
    MAX_RELATIVE_DEVIATION, detect_cycle, extract_intervals,
)
from services.predict_today.segmentation import (
    SEGMENT_SCORE_ADJUST, SEGMENT_TAGS, classify_segment,
)
from services.predict_today.weights import build_cycle_corrections
from services.shared.customer_utils import get_customer_code, get_customer_name, get_phone
from services.shared.datetime_utils import (
    get_local_today, parse_datetime, resolve_timezone, to_local, utc_now,
)
from services.shared.order_utils import (
    build_service_stats, extract_services_from_order, get_order_price, is_cancelled_order,
)

logger = logging.getLogger(__name__)

ALGORITHM_VERSION = "prediction-v2.1"

MIN_UNIQUE_VISITS = 2          # minimal kunjungan unik supaya bisa dihitung siklus
MATCH_WINDOW_DAYS = 1          # |predicted - today| <= 1 dianggap cocok
DOW_MIN_SHARE = 0.40           # share hari minimum utk sinyal day-of-week (skor bonus)
DOW_STRONG_SHARE = 0.60        # share minimum utk jadi kandidat prediksi standalone
DOW_SCORE_CAP = 65             # plafon skor utk prediksi yang murni dari pola hari
SPORADIC_SCORE_CAP = 55        # plafon skor utk pelanggan sporadis yg lolos filter liar

# Sinyal kalender: pelanggan yang selalu datang di "paruh awal/akhir
# bulan" (misal gajian → laundry tanggal muda) punya pola yang nggak
# kelihatan dari interval doang. Diukur dari fraction kunjungan yang
# jatuh di 1-10 atau 25-31; kalau dominan, proyeksi kalender hanya
# diterima pada paruh yang sama.
MONTH_HALF_MIN_SHARE = 0.70

# Bobot faktor skor (harus >= 0, total timing+konsistency+histori = 1.0)
W_TIMING, W_CONSISTENCY, W_HISTORY, W_DOW = 0.45, 0.30, 0.15, 0.10


def predict_arrivals(orders, timezone_str, accuracy_by_level=None,
                     evaluated_logs=None):
    """Hitung pelanggan yang diprediksi datang hari ini.

    Args:
        orders: list order (boleh lintas status; batal diskip internal).
        timezone_str: IANA tz atau alias toko.
        accuracy_by_level: opsional dict {"high": 82.5, "medium": 60.0,
            "low": 30.0} hasil kalkulasi akurasi historis — dipakai untuk
            mengisi field predicted_accuracy_pct.
        evaluated_logs: opsional list prediction_logs yang sudah divonis
            ({customer_code, outcome_status, outcome_delta_days}) — dipakai
            feedback loop utk koreksi cycle per pelanggan.
    """
    today_local = get_local_today(timezone_str)
    now_utc = utc_now()
    now_local = to_local(now_utc, timezone_str)
    tz = resolve_timezone(timezone_str)
    skipped = []

    empty_acc = {"high": None, "medium": None, "low": None}
    accuracy_by_level = {**empty_acc, **(accuracy_by_level or {})}

    # Feedback loop: koreksi cycle dari bias Hit/Miss historis per kode.
    corrections = build_cycle_corrections(evaluated_logs)

    if not orders:
        return _empty_result(today_local, timezone_str, now_utc, now_local,
                             accuracy_by_level)

    historical = []
    for o in orders:
        if is_cancelled_order(o):
            continue
        dt = parse_datetime(o.get("created_at"))
        if not dt:
            continue
        d_local = dt.astimezone(tz).date()
        if d_local >= today_local:
            continue
        historical.append((o, d_local))

    service_stats = build_service_stats(orders)
    top_services_summary = _build_top_services(service_stats)

    by_customer = defaultdict(lambda: defaultdict(list))
    customer_meta = {}
    for o, d_local in historical:
        code = get_customer_code(o)
        if not code:
            continue
        by_customer[code][d_local].append(o)
        customer_meta.setdefault(code, {
            "name": get_customer_name(o),
            "phone": get_phone(o),
        })

    predictions = []
    for code, dates_map in by_customer.items():
        p = _analyze_customer(code, dates_map, customer_meta[code],
                              today_local, tz, accuracy_by_level, skipped,
                              correction=corrections.get(code, 0))
        if p:
            predictions.append(p)

    predictions.sort(key=lambda x: (x["score"], x["transaction_count"],
                                    x["total_spend"]), reverse=True)
    for i, p in enumerate(predictions, 1):
        p["rank"] = i

    return {
        "predictions": predictions,
        "top_services": top_services_summary,
        "metadata": {
            "total_orders": len(orders),
            "historical_orders_used": len(historical),
            "total_customers": len(by_customer),
            "customers_analyzed": len(by_customer),
            "customers_shown": len(predictions),
            "skipped": skipped[:20],
            "prediction_date": today_local.isoformat(),
            "timezone": timezone_str,
            "now_utc": now_utc.isoformat(),
            "now_local": now_local.isoformat() if now_local else None,
            "algorithm": ALGORITHM_VERSION,
            "match_window_days": MATCH_WINDOW_DAYS,
        },
    }


# ------------------------------------------------------------------
# Per-customer analysis
# ------------------------------------------------------------------

def _analyze_customer(code, dates_map, meta, today_local, tz,
                      accuracy_by_level, skipped, correction=0):
    name = meta["name"]
    unique_dates = sorted(dates_map.keys())

    if len(unique_dates) < MIN_UNIQUE_VISITS:
        skipped.append({"code": code, "name": name,
                        "reason": f"cuma {len(unique_dates)}x kunjungan unik"})
        return None

    intervals = extract_intervals(unique_dates)
    if not intervals:
        skipped.append({"code": code, "name": name, "reason": "nggak ada interval valid"})
        return None

    detected = detect_cycle(intervals)
    if detected is None:
        return None
    primary_cycle, deviation, rel, method = detected

    # Feedback loop: geser cycle sesuai bias timing pelanggan (Hit/Miss).
    adjusted_cycle = max(1, primary_cycle + correction)

    segment = classify_segment(unique_dates, intervals, primary_cycle, rel)

    last_visit = unique_dates[-1]

    # --- Fase siklus (residu mod cycle) -----------------------------
    # Proyeksi yang SAH hanya kelipatan dari kunjungan TERAKHIR
    # (next_due = last_visit + k*cycle). Tanpa kunci fase, proyeksi dari
    # tanggal historis lama bisa "mundur" lalu mendarat lagi di tanggal
    # masa lalu → hit palsu di backtest & salah hari di dunia nyata.
    # Fase longgar (misal weekend Jumat+Sabtu → residu {5,6}) tetap
    # menghormati semua tanggal fase — selama ≤3 residu.
    phase = {(last_visit - d).days % primary_cycle for d in unique_dates}
    if len(phase) > 3:
        phase = None                       # terlalu liar → tidak dikunci
    next_due = last_visit + timedelta(days=primary_cycle)

    candidates = _build_candidate_dates(unique_dates, intervals, last_visit,
                                        today_local,
                                        primary_cycle=adjusted_cycle)
    if phase is not None and adjusted_cycle == primary_cycle:
        def _in_phase(dt):
            return (next_due - dt).days % primary_cycle in phase
        filtered = [c for c in candidates if _in_phase(c[0])]
        keep = []
        for c in filtered:
            # Kandidat dari sumber non-siklus (weekday-calendar /
            # weekday-pattern) tidak terikat fase proyeksi — biarkan.
            if c[2] not in ("primary-cycle", "dominant-interval"):
                keep.append(c)
                continue
            dd = (c[0] - today_local).days
            # Kandidat MASA DEPAN (termasuk besok) harus benar-benar
            # kelipatan dari kunjungan terakhir; kalau fase hasil filter
            # bukan kelipatan murni (misal lompatan ±1 akibat koreksi),
            # buang — mencegah prediksi "hantu" di hari yang salah.
            if dd <= 0 or (c[0] - last_visit).days % int(round(c[1])) == 0:
                keep.append(c)
        candidates = keep

    dow_share = _day_of_week_share(unique_dates, today_local.weekday(), tz)

    def _tiebreak(cand_date):
        # Prioritas: PAS hari ini > BESOK (belum terjadi, actionable hari
        # ini) > KEMARIN (sudah lewat, tinggal divonis evaluator).
        dd = (cand_date - today_local).days
        return 0 if dd == 0 else (1 if dd > 0 else -1)

    best = None
    for cand_date, cycle_used, source in candidates:
        delta_days = (cand_date - today_local).days
        delta = abs(delta_days)
        if delta > MATCH_WINDOW_DAYS:
            continue
        score = _score(delta=delta, rel=rel, tx=len(unique_dates),
                       dow_bonus=dow_share, via_dow=False, segment=segment)
        key = (score, _tiebreak(cand_date))
        if best is None or key > best[0]:
            best = (key, cand_date, cycle_used, source, delta, score)

    # Fallback: pola hari kuat, meskipun siklus nggak jatuh ke hari ini
    visited_wd_count = len({d.weekday() for d in unique_dates})
    if (best is None and dow_share >= DOW_STRONG_SHARE
            and visited_wd_count <= 2):
        score = _score(delta=MATCH_WINDOW_DAYS + 1, rel=rel,
                       tx=len(unique_dates), dow_bonus=dow_share, via_dow=True,
                       segment=segment)
        best = ((score, -99), today_local, primary_cycle, "weekday-pattern",
                None, score)

    if best is None:
        nearest = min(
            ((abs(((last_visit + timedelta(days=c)) - today_local).days), c)
             for c in {primary_cycle} | set(intervals)), default=None)
        pred = (last_visit + timedelta(days=nearest[1])).isoformat() if nearest else "?"
        skipped.append({"code": code, "name": name,
                        "reason": f"prediksi terdekat {pred} (di luar window)"})
        return None

    _, cand_date, cycle_used, source, delta, score = best

    if rel > MAX_RELATIVE_DEVIATION and source != "weekday-pattern":
        # Segment "sporadis" tetap diberi peluang dengan skor terpotong,
        # karena bagi mereka pola interval emang nggak pernah rapi.
        if segment == "sporadic" and dow_share >= DOW_MIN_SHARE:
            score = min(score, SPORADIC_SCORE_CAP)
        else:
            skipped.append({"code": code, "name": name,
                            "reason": f"pola liar (rel-dev {rel:.2f})"})
            return None

    agg = _aggregate_transactions(dates_map)
    confidence = _confidence_level(score)

    reason = (
        f"Pola hari ({int(dow_share * 100)}% kunjungan di hari ini)"
        if source == "weekday-pattern"
        else f"Siklus {cycle_used} hari ({method}, {source})"
    )
    if correction:
        reason += f" + koreksi {correction:+d}h dari riwayat"

    return {
        "customer_code": code,
        "customer_name": name,
        "customer_phone": meta["phone"],
        "prediction_target_date": today_local.isoformat(),
        "predicted_visit_date": cand_date.isoformat(),
        "rank": 1,
        "score": score,
        "tag": SEGMENT_TAGS.get(segment, "Reguler"),
        "segment": segment,
        "cycle_days": float(cycle_used),
        "cycle_deviation": float(deviation),
        "cycle_method": method,
        "cycle_correction_days": int(correction),
        "prediction_source": source,
        "weekday_share": round(dow_share, 2),
        "days_since_last": (today_local - last_visit).days,
        "transaction_count": agg["tx_count"],
        "total_spend": round(agg["total_spend"]),
        "avg_spend": round(agg["avg_spend"]),
        "est_spend": round(agg["est_spend"]),
        "favorite_service": agg["favorite_service"],
        "reason": reason,
        "reason_secondary": f"Kandidat: {cand_date.isoformat()} (Δ{delta if delta is not None else '-'} hari)",
        "prediction_status": "Hari ini" if delta == 0 else ("Kemarin" if delta == 1 else "Besok"),
        "confidence_level": confidence,
        "predicted_accuracy_pct": accuracy_by_level.get(confidence),
        "last_transaction": last_visit.isoformat(),
        "is_carry_over": False,
        "carry_over_count": 0,
    }


def _build_candidate_dates(unique_dates, intervals, last_visit, today_local,
                           primary_cycle=None):
    """Kandidat tanggal prediksi dari SEMUA interval yang sering muncul.

    Multi-cycle: misal interval [7,7,7,1,6,1,6] → kandidat dari cycle 7
    (mingguan) dan kombinasi 1/6 (weekend), bukan cuma median-nya.
    Kandidat juga mencakup proyeksi kalender weekday (lihat
    _weekday_calendar_candidates) supaya customer "setiap Rabu" tetap
    terprediksi walau siklus median-nya meleset.

    primary_cycle: kalau diisi (sudah dikoreksi feedback loop), pakai
    angka itu utk proyeksi utama — bukan hasil detect_cycle mentah.
    """
    freq = Counter(intervals)
    candidates = []
    seen = set()

    def add(date_val, cycle_used, source):
        # Ambang "sudah lewat": kandidat yang jatuh > MATCH_WINDOW_DAYS
        # sebelum HARI INI dibuang. Batasnya today (bukan last_visit) —
        # kalau dibatasi last_visit, pelanggan cycle-nya lebih panjang dari
        # selisih ke hari ini jadi nggak pernah punya kandidat sama sekali
        # (kasus: cycle 7, datang kemarin → seharusnya terprediksi besok).
        if date_val in seen:
            return
        if (today_local - date_val).days > MATCH_WINDOW_DAYS:
            return
        # Sinyal kalender "tanggal muda/gajian": kalau pelanggan hampir
        # selalu datang di tanggal 1-10, proyeksi yang jatuh di luar
        # paruh itu dibuang (kebalikannya juga berlaku utk akhir bulan).
        if month_half and date_val.day > 10:
            return
        if month_late and date_val.day < 25:
            return
        seen.add(date_val)
        candidates.append((date_val, cycle_used, source))

    month_half, month_late = _month_half_pattern(unique_dates)

    detected = detect_cycle(intervals)
    primary = detected[0] if primary_cycle is None else max(1, int(primary_cycle))

    horizon = today_local + timedelta(days=MATCH_WINDOW_DAYS)

    def project(cyc, source, max_steps=60):
        # Proyeksi multi-kelipatan DARI SETIAP tanggal historis, bukan cuma
        # last_visit. Kalau hanya last_visit yang jadi anchor, pelanggan
        # cycle-nya lebih panjang dari jarak ke hari ini (misal weekend
        # cycle 7, terakhir Sabtu → harusnya terprediksi Sabtu besok)
        # tidak akan pernah punya kandidat di window, karena kelipatan
        # murni dari last_visit selalu melewati horizon.
        for anchor in reversed(unique_dates):
            k = 1
            while True:
                da = anchor + timedelta(days=cyc * k)
                if da > horizon:
                    break
                # anchor historis TIDAK BOLEH memunculkan tanggal ≤
                # kunjungan terakhir — itu masa lalu, bukan prediksi.
                # (hanya proyeksi dari last_visit yang boleh jatuh sedikit
                # di belakang hari ini: kasus "harusnya kemarin belum datang")
                if da > last_visit or (da == last_visit and anchor == last_visit):
                    add(da, cyc, source)
                k += 1

    total_iv = sum(freq.values())
    rel_primary = detected[2] if detected else 999.0
    # Kalau cycle sudah dikoreksi feedback loop, kita percaya prosesnya
    # sudah belajar — proyeksikan walau rel-dev historis agak tinggi.
    if rel_primary <= MAX_RELATIVE_DEVIATION or primary_cycle is not None:
        # cycle primer kredibel → proyeksikan kelipatannya sampai horizon
        project(primary, "primary-cycle")

    # interval dominan (>=40% histori) selalu jadi kandidat, apapun cycle-nya
    for cyc, count in list(freq.items()):
        if cyc == primary or count < 3 or count / total_iv < 0.4:
            continue
        project(cyc, "dominant-interval", max_steps=30)

    # 2) Proyeksi kalender weekday: hari-hari yang pernah dikunjungi,
    #    dimajukan ke kemunculan terdekat ≤ today+window
    visited_weekdays = {d.weekday() for d in unique_dates}
    for wd in visited_weekdays:
        d = today_local
        while d.weekday() != wd:
            d -= timedelta(days=1)
        # majukan sampai masuk window [today-1, today+1]
        while d < today_local - timedelta(days=MATCH_WINDOW_DAYS):
            d += timedelta(days=7)
        # kalau proyeksi masih sebelum kunjungan terakhir, geser lagi
        while d <= last_visit:
            d += timedelta(days=7)
        if d <= today_local + timedelta(days=MATCH_WINDOW_DAYS) and d > last_visit:
            visits_on_wd = [x for x in unique_dates if x.weekday() == wd]
            share = len(visits_on_wd) / len(unique_dates)
            # Guard anti-spam (kalender mingguan murni = prior lemah):
            #   - setia maks 2 hari/minggu
            #   - share hari itu >= ambang kuat
            #   - minimal 3 kunjungan di hari itu ATAU histori total masih kecil
            #     (belum bisa lihat pola interval yang jelas)
            if (len(visited_weekdays) <= 2 and share >= DOW_STRONG_SHARE
                    and (len(visits_on_wd) >= 3 or len(unique_dates) < 5)):
                add(d, 7, "weekday-calendar")

    return candidates


def _month_half_pattern(unique_dates):
    """Deteksi pola 'tanggal muda / akhir bulan'.

    Return (early, late) boolean:
        early=True → >=MONTH_HALF_MIN_SHARE kunjungan di tanggal 1-10
        late=True  → >=MONTH_HALF_MIN_SHARE kunjungan di tanggal 25-akhir
    Butuh minimal 4 kunjungan biar nggak kebetulan.
    """
    if len(unique_dates) < 4:
        return False, False
    days = [d.day for d in unique_dates]
    early = sum(1 for x in days if x <= 10) / len(days)
    late = sum(1 for x in days if x >= 25) / len(days)
    return early >= MONTH_HALF_MIN_SHARE, late >= MONTH_HALF_MIN_SHARE


def _day_of_week_share(unique_dates, weekday, tz):
    """Proporsi kunjungan yang jatuh di hari yang sama dengan hari ini."""
    counter = Counter(d.weekday() for d in unique_dates)
    total = sum(counter.values())
    if total == 0:
        return 0.0
    return counter.get(weekday, 0) / total


def _score(delta, rel, tx, dow_bonus, via_dow, segment="regular"):
    """Skor 0..100 dari faktor berbobot + penyesuaian per segmen."""
    if via_dow:
        timing = 0.5
    elif delta == 0:
        timing = 1.0
    else:
        timing = 0.75

    consistency = max(0.0, min(1.0, 1.0 - rel))          # rel 0 → 1.0 ; rel 1 → 0
    history = min(1.0, 0.4 + 0.1 * tx)                    # tx2→0.6 … tx6+→1.0
    dow = max(0.0, min(1.0, dow_bonus))

    raw = (W_TIMING * timing + W_CONSISTENCY * consistency +
           W_HISTORY * history + W_DOW * dow)

    # Segment adjustment: rutin = sinyal paling bisa dipercaya, sporadis
    # jangan pernah tampil percaya diri.
    adj = SEGMENT_SCORE_ADJUST.get(segment, 0)
    score = round(raw * 100) + adj
    if via_dow:
        score = min(score, DOW_SCORE_CAP)
    if segment == "sporadic":
        score = min(score, SPORADIC_SCORE_CAP)
    return max(0, min(100, score))


def _confidence_level(score):
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def _aggregate_transactions(dates_map):
    total_spend = 0.0
    tx_count = 0
    service_counter = Counter()

    for _, lst in dates_map.items():
        for o in lst:
            total_spend += get_order_price(o)
            tx_count += 1
            for s in extract_services_from_order(o):
                service_counter[s] += 1

    recent_prices = []
    for _, lst in sorted(dates_map.items(), reverse=True)[:3]:
        for o in lst:
            recent_prices.append(get_order_price(o))

    est_spend = median(recent_prices) if recent_prices else 0
    avg_spend = total_spend / tx_count if tx_count else 0
    favorite = service_counter.most_common(1)[0][0] if service_counter else "Laundry"

    return {
        "total_spend": total_spend,
        "tx_count": tx_count,
        "avg_spend": avg_spend,
        "est_spend": est_spend,
        "favorite_service": favorite,
    }


def _build_top_services(service_stats):
    out = []
    for service, stats in sorted(
        service_stats.items(),
        key=lambda x: (x[1]["order_count"], x[1]["revenue"]),
        reverse=True,
    ):
        out.append({
            "service_name": service,
            "usage_count": round(stats["usage_count"], 2),
            "total_orders": stats["order_count"],
            "revenue": round(stats["revenue"]),
        })
    return out


def _empty_result(today_local, timezone_str, now_utc, now_local, accuracy_by_level):
    return {
        "predictions": [],
        "top_services": [],
        "metadata": {
            "total_orders": 0, "historical_orders_used": 0,
            "total_customers": 0, "customers_analyzed": 0,
            "customers_shown": 0, "skipped": [],
            "prediction_date": today_local.isoformat(),
            "timezone": timezone_str,
            "now_utc": now_utc.isoformat(),
            "now_local": now_local.isoformat() if now_local else None,
            "algorithm": ALGORITHM_VERSION,
            "match_window_days": MATCH_WINDOW_DAYS,
        },
    }

"""Feedback loop — koreksi siklus dari riwayat vonis Hit/Miss.

Ide: evaluator sudah nyimpen `outcome_delta_days` (−1 = customer datang
sehari lebih awal dari prediksi, +1 = sehari lebih telat). Kalau seorang
customer konsisten meleset ke arah yang sama, berarti siklusnya yang
perlu digeser — bukan kebetulan.

Aturan aman (biar nggak overfit ke data sedikit):
    - Minimal 3 vonis utk customer itu.
    - Rasio |bias| terhadap jumlah vonis >= MIN_BIAS_RATIO (0.4) →
      bias dianggap nyata, bukan noise.
    - Koreksi dibatasi ±MAX_CORRECTION_DAYS (2 hari), dan hasil akhir
      cycle dikunci minimal 1 hari.

Return dict {customer_code: correction_days} utk dipakai predictor.
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

MIN_VERDICTS = 3          # minimal vonis hit/miss sebelum berani koreksi
MIN_BIAS_RATIO = 0.4      # rasio rata-rata delta thd jumlah vonis
MAX_CORRECTION_DAYS = 2   # plafon geseran per koreksi


def build_cycle_corrections(logs):
    """Rangkum prediction_logs ter-evaluasi jadi koreksi cycle per customer.

    Args:
        logs: list dict {customer_code, outcome_status, outcome_delta_days}.
            Baris pending / tanpa delta diabaikan.

    Return:
        {code: int} — hanya berisi customer dengan bias timing yang jelas.
        Nilai positif → customer cenderung datang LEBYAR Telat dari
        proyeksi (cycle perlu ditambah); negatif → lebih awal.
    """
    deltas = defaultdict(list)
    for l in logs or []:
        code = l.get("customer_code")
        status = l.get("outcome_status")
        delta = l.get("outcome_delta_days")
        if not code or status not in ("hit", "miss"):
            continue
        if delta is None:
            continue
        try:
            deltas[code].append(int(delta))
        except (TypeError, ValueError):
            continue

    corrections = {}
    for code, vals in deltas.items():
        if len(vals) < MIN_VERDICTS:
            continue
        avg_signed = sum(vals) / len(vals)
        # Bias harus dominan satu arah; kalau campur (+1 −1 selang-seling)
        # rata-rata bertanda kecil → dianggap noise. Tapi delta "0" (hit
        # tepat hari) tidak boleh menetralkan bias — hitung kekuatan arah
        # hanya dari vonis yang meleset.
        off = [v for v in vals if v != 0]
        if not off:
            continue
        directional_strength = abs(sum(off)) / len(off)   # 0..max |delta|
        coverage = len(off) / len(vals)                   # bagian yg meleset
        if directional_strength < MIN_BIAS_RATIO or coverage < 0.5:
            continue
        corr = int(round(avg_signed))
        corr = max(-MAX_CORRECTION_DAYS, min(MAX_CORRECTION_DAYS, corr))
        if corr != 0:
            corrections[code] = corr
    return corrections


def fetch_cycle_corrections(supabase, store_id, days_back=90):
    """Ambil koreksi cycle dari Supabase untuk satu toko."""
    from datetime import date, timedelta

    since = (date.today() - timedelta(days=days_back)).isoformat()
    res = (
        supabase.table("prediction_logs")
        .select("customer_code, outcome_status, outcome_delta_days")
        .eq("store_id", store_id)
        .in_("outcome_status", ["hit", "miss"])
        .gte("prediction_target_date", since)
        .execute()
    )
    return build_cycle_corrections(res.data or [])

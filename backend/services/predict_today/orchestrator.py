"""Predict Today — orchestrator (alur utama 1 toko).
v2.1: engine internal (cycle, predictor, segmentation, weights, evaluator)
ada di folder ini, tinggal panggil langsung.
"""
import logging
from datetime import date

from services.predict_today.carry_over import build_carry_over_predictions
from services.predict_today.logger import log_prediction_run
from services.predict_today.evaluator import evaluate_prediction_logs
from services.predict_today.predictor import predict_arrivals
from services.shared.datetime_utils import get_local_today
from services.shared.orders_repository import fetch_orders_for_store
from services.shared.store_utils import fetch_store_timezone
from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)

# Skor di bawah ini dianggap spekulasi -> jangan tampil di list utama.
MIN_DISPLAY_SCORE = 80
# Urutan operasional: yang jatuh hari ini dulu, lalu besok, lalu telat.
_STATUS_ORDER = {"Hari ini": 0, "Besok": 1}


def predict_for_store(auth_header, store_id, evaluate_first=True):
    timezone_str = fetch_store_timezone(store_id, auth_header)
    token = auth_header.replace("Bearer ", "", 1).strip()

    eval_debug = None
    if evaluate_first:
        try:
            eval_debug = evaluate_prediction_logs(token, store_id, timezone_str)
        except Exception as e:
            logger.exception("Evaluasi prediksi gagal")
            eval_debug = {"error": str(e)}

    orders = fetch_orders_for_store(store_id, auth_header)

    # Feedback loop + akurasi empiris per level confidence.
    evaluated_logs = _fetch_evaluated_logs(token, store_id)
    accuracy = _accuracy_by_level(evaluated_logs)

    clay_result = predict_arrivals(
        orders,
        timezone_str,
        accuracy_by_level=accuracy,
        evaluated_logs=evaluated_logs,
    )
    today_local = get_local_today(timezone_str)
    normal_predictions = clay_result.get("predictions", [])

    # 1) Label status pakai bahasa operasional toko (Hari ini / Telat N / Besok).
    for p in normal_predictions:
        _relabel_status(p, today_local)

    # 2) Buang spekulasi skor rendah dari list utama (tetap dihitung di metadata).
    hidden = [p for p in normal_predictions if (p.get("score") or 0) < MIN_DISPLAY_SCORE]
    normal_predictions = [
        p for p in normal_predictions if (p.get("score") or 0) >= MIN_DISPLAY_SCORE
    ]

    # 3) Sort operasional: Hari ini -> Besok -> Telat; di dalamnya urutan skor.
    normal_predictions.sort(
        key=lambda x: (
            _STATUS_ORDER.get(x.get("prediction_status", ""), 2),
            -(x.get("score") or 0),
            -(x.get("transaction_count") or 0),
        ),
    )
    for i, p in enumerate(normal_predictions, 1):
        p["rank"] = i

    metadata = clay_result.get("metadata", {})
    metadata["customers_hidden_low_score"] = len(hidden)
    metadata["match_window"] = [-1, 1]  # alias utk kompatibilitas UI lama

    normal_codes = {
        p.get("customer_code") for p in normal_predictions if p.get("customer_code")
    }
    carry_over = build_carry_over_predictions(
        token=token,
        store_id=store_id,
        today_local=today_local,
        timezone_str=timezone_str,
        exclude_codes=normal_codes,
    )
    clay_result["carry_over"] = carry_over
    clay_result["predictions"] = normal_predictions

    # Update metadata biar akurat setelah filter MIN_DISPLAY_SCORE
    metadata["customers_shown"] = len(normal_predictions)
    metadata["algorithm"] = metadata.get("algorithm", "prediction-v2.1")

    run_id = log_prediction_run(token, store_id, clay_result)
    if run_id:
        metadata["run_id"] = run_id

    return {
        "run_id": run_id,
        "predictions": normal_predictions,
        "carry_over": carry_over,
        "top_services": clay_result.get("top_services", []),
        "metadata": metadata,
        "timezone": timezone_str,
        "eval_debug": eval_debug,
    }


def _relabel_status(p, today_local):
    """Samakan label status dgn bahasa operasional v6 biar UI nggak bingung."""
    pv = p.get("predicted_visit_date")
    if not pv:
        p["delta_days"] = 0
        return
    try:
        d = date.fromisoformat(pv)
    except ValueError:
        p["delta_days"] = 0
        return
    dd = (d - today_local).days
    p["delta_days"] = dd
    if dd == 0:
        p["prediction_status"] = "Hari ini"
    elif dd < 0:
        p["prediction_status"] = f"Telat {-dd} hari"
    else:
        p["prediction_status"] = "Besok"


def _fetch_evaluated_logs(token, store_id, days_back=90):
    """Log yg sudah divonis hit/miss -> bahan feedback loop & akurasi empiris."""
    try:
        from datetime import timedelta
        since = (date.today() - timedelta(days=days_back)).isoformat()
        supabase = get_user_client(token)
        res = (
            supabase.table("prediction_logs")
            .select("customer_code, outcome_status, outcome_delta_days, confidence_level")
            .eq("store_id", store_id)
            .in_("outcome_status", ["hit", "miss"])
            .gte("prediction_target_date", since)
            .execute()
        )
        return res.data or []
    except Exception:
        logger.exception("Gagal fetch evaluated logs (feedback loop dilewati)")
        return []


def _accuracy_by_level(logs):
    """Akurasi empiris (%) per confidence level dari vonis historis."""
    agg = {}
    for l in logs:
        lvl = l.get("confidence_level") or "unknown"
        slot = agg.setdefault(lvl, {"hit": 0, "n": 0})
        slot["n"] += 1
        if l.get("outcome_status") == "hit":
            slot["hit"] += 1
    out = {}
    for lvl, a in agg.items():
        out[lvl] = round(a["hit"] / a["n"] * 100, 1) if a["n"] else None
    return out

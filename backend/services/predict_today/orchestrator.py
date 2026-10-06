"""Predict Today — orchestrator (alur utama 1 toko)."""

import logging

from services.predict_today.carry_over import build_carry_over_predictions
from services.predict_today.evaluator import evaluate_predictions
from services.predict_today.logger import log_prediction_run
from services.predict_today.predictor import calculate_today_prediction
from services.shared.datetime_utils import get_local_today
from services.shared.orders_repository import fetch_orders_for_store
from services.shared.store_utils import fetch_store_timezone

logger = logging.getLogger(__name__)


def predict_for_store(auth_header, store_id, evaluate_first=True):
    timezone_str = fetch_store_timezone(store_id, auth_header)
    token = auth_header.replace("Bearer ", "", 1).strip()

    eval_debug = None
    if evaluate_first:
        try:
            eval_debug = evaluate_predictions(token, store_id, timezone_str)
        except Exception as e:
            logger.exception("Evaluasi prediksi gagal")
            eval_debug = {"error": str(e)}

    orders = fetch_orders_for_store(store_id, auth_header)
    clay_result = calculate_today_prediction(orders, timezone_str)
    normal_predictions = clay_result.get("predictions", [])
    metadata = clay_result.get("metadata", {})

    today_local = get_local_today(timezone_str)
    normal_codes = {p.get("customer_code") for p in normal_predictions if p.get("customer_code")}

    carry_over = build_carry_over_predictions(
        token=token, store_id=store_id,
        today_local=today_local, timezone_str=timezone_str,
        exclude_codes=normal_codes,
    )
    clay_result["carry_over"] = carry_over

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

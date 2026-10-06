"""Predict Today — simpan hasil prediksi ke Supabase."""

import logging

from services.shared.datetime_utils import utc_now
from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)

_CONFLICT_VARIANTS = (
    "store_id,customer_code,prediction_target_date",
    "customer_code,prediction_target_date",
    "run_id,customer_code",
)


def log_prediction_run(token, store_id, payload):
    try:
        supabase = get_user_client(token)
        metadata = payload.get("metadata", {})
        target_date = metadata.get("prediction_date")
        if not target_date:
            logger.warning("log_prediction_run: target_date kosong")
            return None

        run_id = _upsert_run(supabase, store_id, target_date, metadata)
        if not run_id:
            return None

        rows = _build_log_rows(store_id, run_id, target_date, payload)
        if rows:
            _upsert_logs(supabase, rows)

        return run_id
    except Exception:
        logger.exception("log_prediction_run error")
        return None


def _upsert_run(supabase, store_id, target_date, metadata):
    existing = (
        supabase.table("prediction_runs").select("id")
        .eq("store_id", store_id).eq("prediction_target_date", target_date)
        .order("run_at", desc=True).limit(1).execute()
    )

    run_row = {
        "run_at": utc_now().isoformat(),
        "prediction_target_date": target_date,
        "timezone": metadata.get("timezone", "Asia/Jakarta"),
        "algorithm_version": metadata.get("algorithm", "predict-today-v5.1"),
        "total_orders": metadata.get("total_orders", 0),
        "total_customers": metadata.get("total_customers", 0),
        "customers_analyzed": metadata.get("customers_analyzed", 0),
        "customers_shown": metadata.get("customers_shown", 0),
        "metadata": metadata,
    }

    if existing.data:
        run_id = existing.data[0]["id"]
        supabase.table("prediction_runs").update(run_row).eq("id", run_id).execute()
        return run_id

    run_row["store_id"] = store_id
    res = supabase.table("prediction_runs").insert(run_row).execute()
    if not res.data:
        logger.error("insert run kosong")
        return None
    return res.data[0]["id"]


def _build_log_rows(store_id, run_id, target_date, payload):
    all_logs = payload.get("predictions", []) + payload.get("carry_over", [])

    seen = set()
    deduped = []
    for l in all_logs:
        code = l.get("customer_code")
        if not code or code in seen:
            continue
        seen.add(code)
        deduped.append(l)

    now_iso = utc_now().isoformat()
    rows = []
    for l in deduped:
        rows.append({
            "run_id": run_id,
            "store_id": store_id,
            "customer_code": l.get("customer_code"),
            "customer_name": l.get("customer_name") or l.get("name"),
            "customer_phone": l.get("customer_phone") or l.get("phone"),
            "prediction_target_date": l.get("prediction_target_date") or target_date,
            "rank": l.get("rank"),
            "score": l.get("score"),
            "tag": l.get("tag"),
            "cycle_days": l.get("cycle_days"),
            "days_since_last": l.get("days_since_last"),
            "transaction_count": l.get("transaction_count"),
            "total_spend": l.get("total_spend"),
            "avg_spend": l.get("avg_spend"),
            "est_spend": l.get("est_spend"),
            "favorite_service": l.get("favorite_service"),
            "reason": l.get("reason"),
            "reason_secondary": l.get("reason_secondary"),
            "prediction_status": l.get("prediction_status", "active"),
            "confidence_level": l.get("confidence_level", "high"),
            "outcome_status": "pending",
            "is_carry_over": l.get("is_carry_over", False),
            "carry_over_count": l.get("carry_over_count", 0),
            "carried_from_log_id": l.get("carried_from_log_id"),
            "last_transaction": l.get("last_transaction"),
            "created_at": now_iso,
        })
    return rows


def _upsert_logs(supabase, log_rows):
    last_err = None
    for cols in _CONFLICT_VARIANTS:
        try:
            supabase.table("prediction_logs").upsert(
                log_rows, on_conflict=cols,
            ).execute()
            logger.info("log_prediction_run: upsert OK (%s)", cols)
            return
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            if "42p10" not in err_str and "no unique or exclusion constraint" not in err_str:
                break
    logger.exception("upsert logs gagal: %s", last_err)

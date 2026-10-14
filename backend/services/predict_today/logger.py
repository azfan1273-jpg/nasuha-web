"""Predict Today — simpan hasil prediksi ke Supabase (v2.1 schema)."""

import logging

from services.shared.datetime_utils import utc_now
from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)


def log_prediction_run(token, store_id, payload):
    """Simpan 1 run + semua prediksi (normal + carry over) ke DB."""
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
    """Upsert run — pakai schema baru (target_date, total_orders_analyzed, dst)."""
    existing = (
        supabase.table("prediction_runs").select("id")
        .eq("store_id", store_id).eq("target_date", target_date)
        .limit(1).execute()
    )

    run_row = {
        "run_at": utc_now().isoformat(),
        "target_date": target_date,
        "algorithm_version": metadata.get("algorithm", "prediction-v2.1"),
        "total_orders_analyzed":     metadata.get("total_orders", 0),
        "total_customers_analyzed":  metadata.get("total_customers", 0),
        "predictions_count":         metadata.get("customers_shown", 0),
        "carry_over_count":          0,
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
            "target_date": l.get("prediction_target_date") or target_date,

            "customer_code":  l.get("customer_code"),
            "customer_name":  l.get("customer_name") or l.get("name"),
            "customer_phone": l.get("customer_phone") or l.get("phone"),

            "rank":  l.get("rank"),
            "score": l.get("score"),
            "tag":   l.get("tag"),
            "segment":  l.get("segment"),
            "confidence_level": l.get("confidence_level"),
            "prediction_status": l.get("prediction_status"),
            "reason":            l.get("reason"),
            "reason_secondary":  l.get("reason_secondary"),

            # Cycle
            "cycle_days":             l.get("cycle_days"),
            "cycle_deviation":        l.get("cycle_deviation"),
            "cycle_method":           l.get("cycle_method"),
            "cycle_correction_days":  l.get("cycle_correction_days"),
            "rel_dev":                l.get("rel_dev"),

            # Tanggal & source
            "predicted_visit_date":   l.get("predicted_visit_date"),
            "last_transaction":       l.get("last_transaction"),
            "expected_date":          l.get("expected_date"),
            "prediction_source":      l.get("prediction_source"),
            "weekday_share":          l.get("weekday_share"),
            "days_since_last":        l.get("days_since_last"),

            # Spend
            "transaction_count": l.get("transaction_count"),
            "total_spend":       l.get("total_spend"),
            "avg_spend":         l.get("avg_spend"),
            "est_spend":         l.get("est_spend"),
            "favorite_service":  l.get("favorite_service"),

            # Akurasi
            "predicted_accuracy_pct": l.get("predicted_accuracy_pct"),

            # Carry over
            "is_carry_over":        bool(l.get("is_carry_over", False)),
            "carry_over_count":     l.get("carry_over_count", 0),
            "carried_from_log_id":  l.get("carried_from_log_id"),

            # Outcome
            "outcome_status": "pending",
            "created_at": now_iso,
        })
    return rows


def _upsert_logs(supabase, log_rows):
    """Insert logs. Replace strategy: hapus dulu by run_id."""
    run_id = log_rows[0]["run_id"] if log_rows else None
    if run_id:
        try:
            supabase.table("prediction_logs").delete().eq("run_id", run_id).execute()
        except Exception:
            logger.exception("Gagal delete logs lama untuk run %s", run_id)

    try:
        supabase.table("prediction_logs").insert(log_rows).execute()
        logger.info("Insert %d prediction_logs OK", len(log_rows))
    except Exception as e:
        logger.exception("Gagal insert prediction_logs: %s", e)
"""Logging prediksi ke Supabase untuk analisis akurasi (of truth)."""

import logging

from services.shared.supabase_user_client import get_user_client

logger = logging.getLogger(__name__)


def _build_log_row(
    run_id: str,
    store_id: str,
    target_date: str,
    p: dict,
    rank: int,
    is_carry_over: bool = False,
) -> dict:
    """Bikin 1 row prediction_logs dari payload."""
    row = {
        "run_id": run_id,
        "store_id": store_id,
        "customer_code": p.get("customer_code"),
        "customer_name": p.get("name"),
        "customer_phone": p.get("phone"),
        "prediction_target_date": target_date,
        "rank": rank,
        "score": p.get("score"),
        "tag": p.get("tag"),
        "cycle_days": p.get("cycle_days"),
        "cycle_deviation": p.get("cycle_deviation"),
        "days_since_last": p.get("days_since_last"),
        "transaction_count": p.get("transaction_count"),
        "total_spend": p.get("total_spend"),
        "avg_spend": p.get("avg_spend"),
        "est_spend": p.get("est_spend"),
        "favorite_service": p.get("favorite_service"),
        "reason": p.get("reason"),
        "reason_secondary": p.get("reason_secondary"),
        "prediction_status": p.get("prediction_status"),
        "confidence_level": p.get("confidence_level"),
        "last_transaction": p.get("last_transaction"),
        # === FIX: selalu set, karena kolom NOT NULL ===
        "is_carry_over": bool(is_carry_over),
        "carry_over_count": p.get("carry_over_count") or 0,
        "carried_from_log_id": p.get("carried_from_log_id"),  # nullable, aman
    }
    return row


def log_prediction_run(token: str, store_id: str, payload: dict) -> str | None:
    """
    Simpan 1 run + semua prediksi (normal + carry over) ke DB.

    DEDUP: Kalau sudah ada run untuk (store_id, prediction_target_date)
    yang sama → SKIP, balikin run_id lama.
    """
    try:
        supabase = get_user_client(token)
        meta = payload.get("metadata", {})
        target_date = meta.get("prediction_date")
        tz = payload.get("timezone") or meta.get("timezone")

        if not target_date:
            logger.warning("Skip log: prediction_date kosong")
            return None

        # ===== CEK DULU: udah ada run hari ini? =====
        existing = (
            supabase.table("prediction_runs")
            .select("id")
            .eq("store_id", store_id)
            .eq("prediction_target_date", target_date)
            .limit(1)
            .execute()
        )
        if existing.data:
            existing_id = existing.data[0]["id"]
            logger.info(
                "Skip log: run untuk %s sudah ada (run_id=%s)",
                target_date, existing_id,
            )
            return existing_id

        # ===== INSERT RUN BARU =====
        run_row = {
            "store_id": store_id,
            "prediction_target_date": target_date,
            "timezone": tz,
            "algorithm_version": meta.get("algorithm", "unknown"),
            "total_orders": meta.get("total_orders"),
            "total_customers": meta.get("total_customers"),
            "customers_analyzed": meta.get("customers_analyzed"),
            "customers_shown": meta.get("customers_shown"),
            "metadata": meta,
        }
        res = supabase.table("prediction_runs").insert(run_row).execute()
        if not res.data:
            logger.error("Gagal insert prediction_runs: %s", res)
            return None

        run_id = res.data[0]["id"]

        # ===== INSERT NORMAL PREDICTIONS =====
        log_rows = []
        for idx, p in enumerate(payload.get("predictions", []), start=1):
            log_rows.append(_build_log_row(run_id, store_id, target_date, p, idx, False))

        # ===== INSERT CARRY OVER =====
        carry_over = payload.get("carry_over", [])
        for idx, p in enumerate(carry_over, start=1):
            log_rows.append(_build_log_row(run_id, store_id, target_date, p, idx, True))

        if log_rows:
            try:
                insert_res = supabase.table("prediction_logs").insert(log_rows).execute()
                logger.info(
                    "Run %s: logged %d normal + %d carry over",
                    run_id, len(payload.get("predictions", [])), len(carry_over),
                )
                if not insert_res.data:
                    logger.error("Insert prediction_logs returned empty: %s", insert_res)
            except Exception as e:
                logger.exception("GAGAL insert prediction_logs: %s", e)
        else:
            logger.info("Run %s: nggak ada prediksi, skip logs", run_id)

        return run_id

    except Exception as e:
        logger.exception("Error log_prediction_run: %s", e)
        return None

from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter
from statistics import median

from config.supabase_config import supabase


# ============================================================
# CLAY PREDICTION ENGINE
# Database:
#   orders
#   order_items
#
# orders (sesuai struktur yang terlihat):
#   id, customer_name, service_name, total_price,
#   created_at, store_id, dst.
#
# order_items:
#   id, order_id, service_name, qty, price, subtotal,
#   created_at, unit, store_id
#
# Prinsip:
#   Supabase = data
#   Python   = business logic / prediction
#   Flutter  = display
# ============================================================


# ============================================================
# CONFIG
# ============================================================

MIN_SERVICE_USAGE = 10
MIN_TRANSACTIONS_FOR_PREDICTION = 3
TOP_PREDICTIONS_LIMIT = 5

# Cycle yang terlalu ekstrem dianggap outlier.
MIN_CYCLE_DAYS = 1
MAX_CYCLE_DAYS = 90

# Kandidat sekitar "besok".
# 0 = tepat besok
# 1 = satu hari sebelum / sesudah
PREDICTION_TOLERANCE_DAYS = 1


# ============================================================
# DATETIME HELPERS
# ============================================================

def _parse_datetime(value):
    """Parse ISO datetime dan normalisasi ke UTC."""
    if not value:
        return None

    try:
        value = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


# ============================================================
# CUSTOMER HELPERS
# ============================================================

def _clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def _normalize_phone(value):
    """
    Normalisasi nomor HP sederhana.
    '-' / kosong tidak dianggap sebagai nomor.
    """
    value = _clean_text(value)

    if not value or value in {"-", "null", "NULL"}:
        return ""

    digits = "".join(ch for ch in value if ch.isdigit())

    if len(digits) < 6:
        return ""

    return digits


def _get_phone(order):
    """
    Screenshot menunjukkan kolom customer_ terpotong.
    Karena nama kolom sebenarnya tidak terlihat penuh, engine
    mendukung beberapa nama umum tanpa mengharuskan salah satunya.

    Kalau database lu ternyata punya nama kolom lain, tambahkan
    nama field-nya di list ini.
    """
    candidates = (
        "customer_phone",
        "phone",
        "customer_number",
        "customer_no",
        "customer_",
    )

    for field in candidates:
        value = _normalize_phone(order.get(field))

        if value:
            return value

    return ""


def _get_customer_name(order):
    return (
        _clean_text(order.get("customer_name"))
        or _clean_text(order.get("name"))
        or "Pelanggan Anonim"
    )


def _get_customer_key(order):
    """
    Karena struktur screenshot tidak menunjukkan customer_id yang
    bisa dipastikan, identitas dibuat:

        customer_id (jika tersedia)
        -> phone
        -> normalized name

    Jadi nama yang sama dengan nomor berbeda tidak digabung.
    """
    customer_id = _clean_text(
        order.get("customer_id")
        or order.get("customer_uuid")
    )

    if customer_id:
        return f"id:{customer_id}"

    phone = _get_phone(order)

    if phone:
        return f"phone:{phone}"

    name = _get_customer_name(order).lower()

    return f"name:{name}"


# ============================================================
# ORDER / ITEM HELPERS
# ============================================================

def _get_order_price(order):
    try:
        return float(order.get("total_price") or 0)
    except (ValueError, TypeError):
        return 0.0


def _get_items(order):
    items = order.get("order_items")

    if not isinstance(items, list):
        return []

    return items


def _get_item_service(item):
    return _clean_text(item.get("service_name"))


def _get_item_qty(item):
    try:
        qty = float(item.get("qty") or 1)

        if qty <= 0:
            return 1.0

        return qty

    except (ValueError, TypeError):
        return 1.0


def _get_item_subtotal(item):
    """
    Prioritas subtotal.
    Fallback price * qty.

    Ini penting karena order_items memang menyediakan:
        price
        qty
        subtotal
    """
    try:
        subtotal = float(item.get("subtotal") or 0)

        if subtotal != 0:
            return subtotal
    except (ValueError, TypeError):
        pass

    try:
        price = float(item.get("price") or 0)
        qty = _get_item_qty(item)

        return price * qty

    except (ValueError, TypeError):
        return 0.0


def _extract_services_from_order(order):
    """
    Sumber utama service untuk Clay = order_items.

    orders.service_name hanya dijadikan fallback kalau relationship
    order_items tidak tersedia.
    """
    items = _get_items(order)

    services = []

    for item in items:
        service = _get_item_service(item)

        if service:
            services.append(service)

    if services:
        return services

    fallback = _clean_text(order.get("service_name"))

    return [fallback] if fallback else []


# ============================================================
# SERVICE ANALYSIS
# ============================================================

def _build_service_stats(orders):
    """
    Hitung penggunaan service berdasarkan order_items.

    Satu item service:
        usage_count += qty

    Satu order yang mengandung service:
        order_count += 1

    Revenue:
        berasal dari subtotal item.
    """
    service_stats = defaultdict(
        lambda: {
            "usage_count": 0.0,
            "order_count": 0,
            "revenue": 0.0,
        }
    )

    for order in orders:
        items = _get_items(order)

        # Kalau order_items tersedia, gunakan item-level data.
        if items:
            seen_in_order = set()

            for item in items:
                service = _get_item_service(item)

                if not service:
                    continue

                qty = _get_item_qty(item)
                subtotal = _get_item_subtotal(item)

                service_stats[service]["usage_count"] += qty
                service_stats[service]["revenue"] += subtotal

                if service not in seen_in_order:
                    service_stats[service]["order_count"] += 1
                    seen_in_order.add(service)

        else:
            # Fallback untuk order lama yang mungkin belum punya
            # row di order_items.
            service = _clean_text(order.get("service_name"))

            if service:
                service_stats[service]["usage_count"] += 1
                service_stats[service]["order_count"] += 1
                service_stats[service]["revenue"] += _get_order_price(order)

    return service_stats


# ============================================================
# CYCLE CALCULATION
# ============================================================

def _calculate_cycle_days(transactions):
    """
    Hitung typical customer cycle menggunakan MEDIAN.

    Contoh:
        7, 7, 8, 60, 7

    Mean   = 17.8
    Median = 7

    Median jauh lebih tahan terhadap transaksi abnormal.
    """
    dates = sorted(
        [
            tx["date"]
            for tx in transactions
            if tx.get("date")
        ],
        reverse=False,
    )

    intervals = []

    for i in range(len(dates) - 1):
        diff_days = (
            dates[i + 1] - dates[i]
        ).total_seconds() / 86400

        if MIN_CYCLE_DAYS <= diff_days <= MAX_CYCLE_DAYS:
            intervals.append(diff_days)

    if not intervals:
        return 7, [], 0.0

    typical_cycle = max(
        1,
        round(median(intervals)),
    )

    deviations = [
        abs(interval - typical_cycle)
        for interval in intervals
    ]

    avg_deviation = (
        sum(deviations) / len(deviations)
        if deviations
        else 0.0
    )

    return (
        typical_cycle,
        intervals,
        avg_deviation,
    )


# ============================================================
# SCORE
# ============================================================

def _calculate_prediction_score(
    predicted_return_date,
    tomorrow,
    cycle_deviation,
    transaction_count,
):
    """
    Score 0-100.

    IMPORTANT:
    score bukan probability.

    Score mengukur seberapa dekat tanggal prediksi customer
    terhadap besok + seberapa konsisten histori cycle.
    """

    delta_days = abs(
        (
            predicted_return_date.date()
            - tomorrow
        ).days
    )

    # Timing
    if delta_days == 0:
        timing_score = 100
    elif delta_days == 1:
        timing_score = 85
    elif delta_days == 2:
        timing_score = 65
    elif delta_days == 3:
        timing_score = 45
    else:
        timing_score = 20

    # Consistency
    if cycle_deviation <= 1:
        consistency_multiplier = 1.00
    elif cycle_deviation <= 2:
        consistency_multiplier = 0.95
    elif cycle_deviation <= 4:
        consistency_multiplier = 0.85
    else:
        consistency_multiplier = 0.70

    # History strength
    if transaction_count >= 8:
        history_multiplier = 1.00
    elif transaction_count >= 5:
        history_multiplier = 0.95
    else:
        history_multiplier = 0.90

    score = round(
        timing_score
        * consistency_multiplier
        * history_multiplier
    )

    return max(0, min(100, score))


# ============================================================
# CONFIDENCE
# ============================================================

def _get_confidence_level(
    transaction_count,
    cycle_deviation,
):
    if transaction_count >= 8 and cycle_deviation <= 2:
        return "Tinggi"

    if transaction_count >= 5 and cycle_deviation <= 4:
        return "Sedang"

    return "Rendah"


# ============================================================
# TAG
# ============================================================

def _get_customer_tag(
    total_tx,
    total_spend,
    days_since_last,
    typical_cycle,
):
    if total_tx >= 5 and total_spend >= 150000:
        base_tag = "VIP"
    else:
        base_tag = "Aktif"

    if days_since_last > typical_cycle + 7:
        return "Resiko Churn"

    return base_tag


# ============================================================
# MAIN ENGINE
# ============================================================

def calculate_tomorrow_prediction(orders):
    """
    Main Clay prediction engine.

    Input:
        orders dari Supabase dengan nested order_items.

    Output:
        top_services
        predictions
        metadata
    """

    now_utc = datetime.now(timezone.utc)
    tomorrow = (
        now_utc + timedelta(days=1)
    ).date()

    if not orders:
        return {
            "top_services": [],
            "predictions": [],
            "metadata": {
                "total_orders": 0,
                "total_customers": 0,
                "customers_analyzed": 0,
                "prediction_date": tomorrow.isoformat(),
                "algorithm": "median-cycle-v3",
            },
        }

    # ========================================================
    # 1. SERVICE STATISTICS
    # ========================================================

    service_stats = _build_service_stats(orders)

    # Routine service berdasarkan jumlah ORDER,
    # bukan qty kilogram/pieces.
    routine_services = {
        service
        for service, stats in service_stats.items()
        if stats["order_count"] >= MIN_SERVICE_USAGE
    }

    top_services_summary = []

    for service, stats in sorted(
        service_stats.items(),
        key=lambda x: (
            x[1]["order_count"],
            x[1]["revenue"],
        ),
        reverse=True,
    ):
        top_services_summary.append({
            "service_name": service,
            "usage_count": round(stats["usage_count"], 2),
            "total_orders": stats["order_count"],
            "revenue": round(stats["revenue"]),
            "is_routine": service in routine_services,
        })

    # ========================================================
    # 2. STORE REVENUE
    # ========================================================
    # Ambil revenue langsung dari orders.
    # Ini tidak dibatasi routine service.
    total_store_revenue = sum(
        _get_order_price(order)
        for order in orders
    )

    # ========================================================
    # 3. GROUP TRANSACTIONS PER CUSTOMER
    # ========================================================

    customer_map = defaultdict(list)

    for order in orders:
        created_at = _parse_datetime(
            order.get("created_at")
        )

        if not created_at:
            continue

        customer_key = _get_customer_key(order)

        services = _extract_services_from_order(order)

        if not services:
            services = ["Tidak diketahui"]

        # Service yang benar-benar routine.
        routine_used = [
            service
            for service in services
            if service in routine_services
        ]

        # Untuk analisa customer:
        # kalau customer punya routine service, gunakan itu.
        # kalau tidak, gunakan semua service histori.
        selected_services = (
            routine_used
            if routine_used
            else services
        )

        customer_map[customer_key].append({
            "customer_id": (
                order.get("customer_id")
                or order.get("customer_uuid")
            ),
            "name": _get_customer_name(order),
            "phone": _get_phone(order),
            "price": _get_order_price(order),
            "services": selected_services,
            "date": created_at,
        })

    # ----------------------------------------------------
    # Prediction Status (HARI INI vs BESOK vs TERLEWAT)
    # ----------------------------------------------------
    today = now_utc.date()
    
    if predicted_return_date == today:
        prediction_status = "Hari Ini"
        status_badge = "Hari Ini"
    elif delta_to_tomorrow == 0:
        prediction_status = "Besok"
        status_badge = "Besok"
    elif delta_to_tomorrow < 0:
        prediction_status = "Sudah lewat"
        status_badge = "Terlewat"
    elif delta_to_tomorrow <= 3:
        prediction_status = "Segera"
        status_badge = "Segera"
    else:
        prediction_status = "Belum"
        status_badge = "Belum"

    # ----------------------------------------------------
    # Reason Teks Dinamis
    # ----------------------------------------------------
    if prediction_status == "Hari Ini":
        reason = f"Estimasi siklus {typical_cycle} harian jatuh HARI INI."
    elif prediction_status == "Besok":
        reason = f"Estimasi siklus {typical_cycle} harian jatuh BESOK."
    elif prediction_status == "Sudah lewat":
        days_over = abs((today - predicted_return_date).days)
        reason = f"Terlewat {days_over} hari dari siklus {typical_cycle} hari."
    elif prediction_status == "Segera":
        reason = f"Estimasi kembali {predicted_return_date.isoformat()}."
    else:
        reason = f"Estimasi kembali {predicted_return_date.isoformat()}."

    confidence_level = _get_confidence_level(
        transaction_count=total_tx,
        cycle_deviation=cycle_deviation,
    )

    predictions.append({
        "customer_id": last_transaction.get("customer_id"),
        "name": last_transaction["name"],
        "phone": last_transaction["phone"],
        "tag": tag,
        "status": status_badge,  # 🟢 KOLOM STATUS BARU (Hari Ini / Besok / Terlewat / Segera / Belum)
        "score": score,
        "reason": reason,
        "prediction_status": prediction_status,
        "prediction_date": predicted_return_date.isoformat(),
        "last_transaction": last_tx_date.isoformat(),
        "days_since_last": round(days_since_last, 1),
        "cycle_days": typical_cycle,
        "cycle_deviation": round(cycle_deviation, 2),
        "transaction_count": total_tx,
        "total_spend": round(total_spend),
        "est_spend": avg_spend,
        "favorite_service": favorite_service,
        "contribution_percent": contribution_pct,
        "contribution": f"{contribution_pct}%",
        "confidence_level": confidence_level,
    })

    # ========================================================
    # 5. TOP PREDICTIONS (PENGELOMPOKAN HARI INI & BESOK)
    # ========================================================
    
    # 🟢 Prediksi Pelanggan HARI INI (Score >= 60)
    today_predictions = [
        prediction for prediction in predictions
        if prediction["status"] == "Hari Ini" and prediction["score"] >= 60
    ]
    today_predictions.sort(
        key=lambda x: (x["score"], x["transaction_count"], x["total_spend"]),
        reverse=True
    )

    # 🟢 Prediksi Pelanggan BESOK (Score >= 60)
    tomorrow_predictions = [
        prediction for prediction in predictions
        if prediction["status"] == "Besok" and prediction["score"] >= 60
    ]
    tomorrow_predictions.sort(
        key=lambda x: (x["score"], x["transaction_count"], x["total_spend"]),
        reverse=True
    )

    # Fallback/Top gabungan untuk kompatibilitas lama (Limit 5)
    top_predictions = (today_predictions + tomorrow_predictions)[:TOP_PREDICTIONS_LIMIT]

    # ========================================================
    # 6. RESULT
    # ========================================================
    return {
        "top_services": top_services_summary,
        "today_predictions": today_predictions,       # 🟢 ARRAY KHUSUS HARI INI
        "tomorrow_predictions": tomorrow_predictions, # 🟢 ARRAY KHUSUS BESOK
        "predictions": predictions,                   # Semua data hasil analisa
        "metadata": {
            "total_orders": len(orders),
            "total_customers": len(customer_map),
            "customers_analyzed": len(predictions),
            "today_count": len(today_predictions),
            "tomorrow_count": len(tomorrow_predictions),
            "prediction_date": today.isoformat(),
            "algorithm": "median-cycle-v4-today-tomorrow",
        },
    }


    # ============================================================
    # SUPABASE WRAPPER
    # ============================================================

    def get_clay_predictions(store_id):
        """
        Ambil orders + order_items dari Supabase.
        Semua calculation dilakukan di Python backend.
        """
        try:
            response = (
                supabase
                .table("orders")
                .select("*, order_items(*)")
                .eq("store_id", store_id)
                .execute()
            )

            orders = response.data or []
            return calculate_tomorrow_prediction(orders)

        except Exception as e:
            print(f"Error fetching orders for Clay prediction: {str(e)}")
            return {
                "top_services": [],
                "today_predictions": [],
                "tomorrow_predictions": [],
                "predictions": [],
                "metadata": {
                    "error": str(e),
                },
            }

    # ========================================================
    # 5. TOP PREDICTIONS
    # ========================================================
    #
    # Ambil customer yang predicted return date:
    #   tepat besok
    #   atau maksimal +/- 1 hari
    #
    # Prioritas:
    #   1. score
    #   2. histori transaksi
    #   3. total spending
    #

    filtered_predictions = [
        prediction
        for prediction in predictions
        if prediction["prediction_status"]
        in {"Besok", "Sekitar besok"}
        and prediction["score"] >= 70
    ]

    filtered_predictions.sort(
        key=lambda x: (
            x["score"],
            x["transaction_count"],
            x["total_spend"],
        ),
        reverse=True,
    )

    top_predictions = (
        filtered_predictions[
            :TOP_PREDICTIONS_LIMIT
        ]
    )

    # ========================================================
    # 6. RESULT
    # ========================================================

    return {
        "top_services": top_services_summary,

        "predictions": top_predictions,

        "metadata": {
            "total_orders": len(orders),
            "total_customers": len(customer_map),
            "customers_analyzed": len(predictions),
            "prediction_date": tomorrow.isoformat(),
            "algorithm": "median-cycle-v3",
        },
    }


# ============================================================
# SUPABASE WRAPPER
# ============================================================

def get_clay_predictions(store_id):
    """
    Ambil orders + order_items dari Supabase.

    Relasi yang diharapkan:
        order_items.order_id -> orders.id

    Semua calculation dilakukan di Python backend.
    """

    try:
        response = (
            supabase
            .table("orders")
            .select(
                "*, order_items(*)"
            )
            .eq(
                "store_id",
                store_id,
            )
            .execute()
        )

        orders = response.data or []

        return calculate_tomorrow_prediction(
            orders
        )

    except Exception as e:
        print(
            "Error fetching orders for Clay prediction: "
            f"{str(e)}"
        )

        return {
            "top_services": [],
            "predictions": [],
            "metadata": {
                "error": str(e),
            },
        }

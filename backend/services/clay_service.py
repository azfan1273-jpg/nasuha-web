from datetime import datetime, timezone
from collections import defaultdict, Counter

def calculate_tomorrow_prediction(orders):
    if not orders:
        return {
            "top_services": [],
            "predictions": []
        }

    now_utc = datetime.now(timezone.utc)
    
    # -------------------------------------------------------------
    # 1. HITUNG FREKUENSI LAYANAN GLOBAL (FILTER LAYANAN EVENT)
    # -------------------------------------------------------------
    service_counter = Counter()
    for order in orders:
        items = order.get("order_items") or []
        for item in items:
            s_name = item.get("service_name")
            if s_name:
                service_counter[s_name] += 1

    # Ambang batas minimum layanan rutin (misal >= 10x pemesanan global)
    # Layanan di bawah kuota ini dianggap 'Event/Insidental' dan diabaikan dari prediksi
    MIN_SERVICE_THRESHOLD = 10
    routine_services = {srv for srv, count in service_counter.items() if count >= MIN_SERVICE_THRESHOLD}

    # Data ringkasan Top Services untuk UI Penanda
    top_services_summary = []
    for srv, count in service_counter.most_common():
        top_services_summary.append({
            "service_name": srv,
            "total_orders": count,
            "is_routine": srv in routine_services
        })

    # -------------------------------------------------------------
    # 2. KELOMPOKKAN TRANSAKSI PER PELANGGAN (HANYA LAYANAN RUTIN)
    # -------------------------------------------------------------
    customer_map = defaultdict(list)
    total_store_revenue = 0

    for order in orders:
        name = order.get("customer_name") or order.get("name") or "Pelanggan Anonim"
        phone = order.get("customer_phone") or order.get("phone") or ""
        price = float(order.get("total_price") or 0)
        created_at_str = order.get("created_at")

        items = order.get("order_items") or []
        # Ambil layanan favorit pelanggan yang masuk kategori rutin
        valid_items = [i.get("service_name") for i in items if i.get("service_name") in routine_services]
        
        # Jika transaksi ini murni cuci event (tidak ada item rutin), lewati transaksi ini dari perhitungan siklus
        if not valid_items and items:
            continue

        service_used = valid_items[0] if valid_items else (items[0].get("service_name") if items else "Cuci Komplit")

        total_store_revenue += price

        if created_at_str:
            try:
                date_obj = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if date_obj.tzinfo is None:
                    date_obj = date_obj.replace(tzinfo=timezone.utc)
            except Exception:
                date_obj = now_utc
        else:
            date_obj = now_utc

        customer_map[name].append({
            "phone": phone,
            "price": price,
            "service": service_used,
            "date": date_obj
        })

    # -------------------------------------------------------------
    # 3. ANALISIS SIKLUS CUCI PER PELANGGAN
    # -------------------------------------------------------------
    predictions = []

    for name, tx_list in customer_map.items():
        total_tx = len(tx_list)
        
        # SYARAT: Minimal 3 transaksi rutin agar punya data siklus yang valid
        if total_tx < 3:
            continue

        tx_list.sort(key=lambda x: x["date"], reverse=True)
        last_tx_date = tx_list[0]["date"]
        days_since_last = (now_utc - last_tx_date).days
        
        total_spend = sum(t["price"] for t in tx_list)
        avg_spend = round(total_spend / total_tx)

        services = [t["service"] for t in tx_list]
        favorite_service = max(set(services), key=services.count)
        contribution_pct = round((total_spend / total_store_revenue * 100)) if total_store_revenue > 0 else 0

        # Hitung interval rata-rata antar cuci (avg_cycle)
        intervals = []
        for i in range(len(tx_list) - 1):
            diff = (tx_list[i]["date"] - tx_list[i+1]["date"]).days
            if diff > 0:
                intervals.append(diff)
        
        avg_cycle = round(sum(intervals) / len(intervals)) if intervals else 7

        # Penentuan Tag & Skor
        tag = "Aktif"
        if total_tx >= 5 and total_spend >= 150000:
            tag = "VIP"

        # Cek apakah tanggal hari ini pas dengan jadwal rutinnya
        if days_since_last > (avg_cycle + 7):
            tag = "Resiko Churn"
            score = 35
            reason = f"Terlambat cuci (Siklus {avg_cycle} hari, sudah {days_since_last} hari absensi)"
        elif abs(days_since_last - avg_cycle) <= 1:
            score = 92
            reason = f"Jadwal cuci rutin (Tiap {avg_cycle} hari sekali)"
        elif days_since_last < avg_cycle:
            score = 40
            reason = f"Baru cuci {days_since_last} hari lalu (Belum waktunya)"
        else:
            score = 75
            reason = f"Mendekati siklus cuci rutin ({avg_cycle} hari)"

        phone = tx_list[0]["phone"]

        predictions.append({
            "name": name,
            "phone": phone,
            "tag": tag,
            "score": score,
            "reason": reason,
            "est_spend": avg_spend,
            "favorite_service": favorite_service,
            "total_tx": total_tx,
            "contribution": f"{contribution_pct}%"
        })

    # Filter hanya yang berpeluang tinggi (skor >= 70) & ambil Top 5 paling mendekati riil toko
    filtered_predictions = [p for p in predictions if p["score"] >= 70]
    filtered_predictions.sort(key=lambda x: x["score"], reverse=True)
    top_predictions = filtered_predictions[:5] # Batasi max 5 pelanggan per hari

    return {
        "top_services": top_services_summary,
        "predictions": top_predictions
    }


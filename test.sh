#!/usr/bin/env bash
set -e

EMAIL="nasuhalaundry@gmail.com"
PASSWORD="Yolde3garde"
BASE="http://localhost:8080"

echo "🔑 Login..."
TOKEN=$(curl -s -X POST "$BASE/api/login" -H "Content-Type: application/json" -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

if [ -z "$TOKEN" ]; then
  echo "❌ Login gagal. Cek email/password atau server mati."
  exit 1
fi

echo "✅ Token: ${TOKEN:0:30}..."
echo ""

# ============================================================
# Test 1: Fresh predict
# ============================================================
echo "🧪 Test 1: Fresh predict"
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/clay/predict-today" \
  | python -c "import sys,json; d=json.load(sys.stdin); print(f\"  run_id: {d.get('run_id')} | predictions: {len(d.get('predictions',[]))} | carry_over: {len(d.get('carry_over',[]))}\")"

echo ""

# ============================================================
# Test 2: Hit lagi (simulasi cron 2x) — cek gak double
# ============================================================
echo "🧪 Test 2: Hit lagi (simulasi cron 2x)"
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/clay/predict-today" \
  | python -c "import sys,json; d=json.load(sys.stdin); print(f\"  run_id: {d.get('run_id')} | predictions: {len(d.get('predictions',[]))} | carry_over: {len(d.get('carry_over',[]))}\")"

echo ""
echo "✅ Selesai. Cek duplikat di Supabase pakai query di bawah."

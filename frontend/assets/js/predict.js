// ==========================================
// PREDICT.JS - Fitur Clay Engine
// ==========================================

// 1. Tampilan HTML Clay Engine
function renderClayEngine() {
  const contentArea = document.getElementById('content-area');
  if (!contentArea) return;
  
  document.title = 'Nasuha Labs — Clay Engine';

  contentArea.innerHTML = `
    <div class="page-title">
      <h1>Clay Engine</h1>
      <p id="clay-engine-date" style="color: var(--text-secondary); font-size: 0.85rem;">Memuat tanggal...</p>
    </div>
    
    <!-- Stats -->
    <div style="display: flex; gap: 16px; margin-bottom: 24px;">
      <div class="table-container" style="flex:1; padding: 16px;">
        <div style="font-size: 0.8rem; color: var(--text-secondary);">Total Potensial</div>
        <div id="stat-total-potensial" style="font-size: 1.2rem; font-weight: bold; margin-top: 8px;">—</div>
      </div>
      <div class="table-container" style="flex:1; padding: 16px;">
        <div style="font-size: 0.8rem; color: var(--text-secondary);">Estimasi Omset</div>
        <div id="stat-total-omset" style="font-size: 1.2rem; font-weight: bold; margin-top: 8px;">—</div>
      </div>
      <div class="table-container" style="flex:1; padding: 16px;">
        <div style="font-size: 0.8rem; color: var(--text-secondary);">Rata-rata Score</div>
        <div id="stat-avg-score" style="font-size: 1.2rem; font-weight: bold; margin-top: 8px;">—</div>
      </div>
    </div>

    <!-- Table -->
    <div class="table-container">
      <div style="padding: 12px 16px; border-bottom: 1px solid var(--border-default); display: flex; justify-content: space-between; align-items: center;">
        <span style="font-size: 0.85rem; font-weight: 600;">Prediksi Pelanggan</span>
        <span id="badge-count-normal" style="font-size: 0.75rem; background: var(--bg-hover); padding: 2px 8px; border-radius: 12px;">0 items</span>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th>#</th><th>NAMA</th><th>TAG</th><th>STATUS NOTA</th><th>SCORE</th><th>CYCLE</th><th>KODE</th><th>PHONE</th><th>AKSI</th>
          </tr>
        </thead>
        <tbody id="tbody-predict">
          <tr><td colspan="9" style="text-align:center; padding: 24px; color: var(--text-secondary);">Memuat data...</td></tr>
        </tbody>
      </table>
    </div>
  `;

  // Fetch Data setelah HTML dirender
  fetchClayEngineData();
}

// 2. Fetch Data dari Backend
async function fetchClayEngineData() {
  const tbody = document.getElementById("tbody-predict");
  const dateEl = document.getElementById("clay-engine-date");
  const token = localStorage.getItem("access_token");
  const storeId = localStorage.getItem("store_id");

  // Set Tanggal
  if (dateEl) {
    const tz = localStorage.getItem("store_timezone") || "Asia/Jakarta";
    try {
      const fmt = new Intl.DateTimeFormat("id-ID", { weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: tz });
      dateEl.textContent = `📅 ${fmt.format(new Date())} (${tz})`;
    } catch (_) { dateEl.textContent = `📅 ${new Date().toLocaleString("id-ID")}`; }
  }

  if (!token) return;

  try {
    let apiUrl = "/api/clay/predict-today";
    if (storeId) apiUrl += `?store_id=${encodeURIComponent(storeId)}`;

    const response = await fetch(apiUrl, {
      method: "GET",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` }
    });

    const result = await response.json();
    if (!response.ok) throw new Error(result.message || "Gagal fetch data");

    const predictions = Array.isArray(result.predictions) ? result.predictions : [];
    
    // Update Stats
    const totalOmset = predictions.reduce((s, i) => s + Number(i.est_spend || 0), 0);
    const avgScore = predictions.length > 0 ? Math.round(predictions.reduce((s, i) => s + (Number(i.score) || 0), 0) / predictions.length) : null;

    document.getElementById("stat-total-potensial").innerText = `${predictions.length} Pelanggan`;
    document.getElementById("stat-total-omset").innerText = `Rp ${totalOmset.toLocaleString("id-ID")}`;
    document.getElementById("stat-avg-score").innerText = avgScore !== null ? `${avgScore}%` : "—";
    document.getElementById("badge-count-normal").innerText = `${predictions.length} items`;

    renderPredictTable(predictions);

  } catch (error) {
    if(tbody) tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:20px; color:#ff5252;">Error: ${error.message}</td></tr>`;
  }
}

// 3. Render Tabel
function renderPredictTable(items) {
  const tbody = document.getElementById("tbody-predict");
  if (!tbody) return;

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:#888;">Tidak ada prediksi hari ini.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map((item, idx) => {
    const name = item.name || item.customer_name || "Pelanggan";
    const phone = item.phone || item.customer_phone || "-";
    const code = item.customer_code || "-";
    const tag = item.tag || "Reguler";
    const score = Number(item.score) || 0;
    const cycle = item.cycle_days ? `${Math.round(item.cycle_days)} hari` : "-";
    
    return `
      <tr style="border-bottom: 1px solid #27272a;">
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: #aaa;">${idx + 1}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: #fff; font-weight: 600;">${name}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a;"><span class="tag">${tag}</span></td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: #28c8ff;">${item.prediction_status || 'active'}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; font-weight:700; color: ${score >= 80 ? '#00E676' : (score >= 60 ? '#ffc107' : '#ff5252')};">${score}%</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:#ccc;">${cycle}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:#28c8ff; font-family: monospace;">${code}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:#ccc;">${phone}</td>
        <td style="padding: 12px 14px; text-align: center;">
          <button onclick="sendWA('${phone}', '${name}')" style="background: #25D366; color: #000; border: none; font-weight: 700; padding: 6px 12px; border-radius: 6px; cursor: pointer;">💬 WA</button>
        </td>
      </tr>
    `;
  }).join("");
}

// 4. Fungsi WhatsApp
function sendWA(phone, name) {
  if (!phone || phone === "-") return alert(`Nomor telepon ${name} tidak tersedia.`);
  
  let formatted = String(phone).replace(/\D/g, "");
  if (formatted.startsWith("0")) formatted = "62" + formatted.slice(1);
  else if (formatted.startsWith("8")) formatted = "62" + formatted;

  const text = `Halo Kak ${name}, dari Nasuha Laundry! 👋\n\nBerdasarkan jadwal rutin, besok waktunya laundry pakaian lagi nih Kak. Mau kami bantu siapkan slot laundry-nya besok? Ditunggu kedatangannya ya Kak! 🧺✨`;
  window.open(`https://wa.me/${formatted}?text=${encodeURIComponent(text)}`, "_blank");
}
// ==========================================
// ANALYTICS.JS — Chart PIUTANG (Clay Engine)
// Candlestick saldo piutang + volume 2 warna.
// Konvensi nyusul predict.js:
//   token  -> localStorage 'access_token'
//   store  -> localStorage 'store_id'
//   api    -> relative '/api/...'
//
// Endpoint : GET /api/analytics/piutang-candle?timeframe=1d|4h&days=N
//
// MAKNA CANDLE (KEBALIKAN dari saham, jangan kebalik baca!):
//   merah gede   = saldo turun = pembayaran masuk  -> BAGUS
//   hijau terus  = saldo naik   = utang numpuk     -> pantau menunggak
// ==========================================

let _piutangChart = null;   // instance ApexCharts candle
let _volumeChart = null;    // instance ApexCharts volume
let _piutangTf = '1d';      // timeframe aktif: '1d' | '4h'

// 1. Tampilan HTML halaman Chart Piutang
function renderAnalyticsChart() {
  const contentArea = document.getElementById('content-area');
  if (!contentArea) return;

  document.title = 'Nasuha Labs — Chart Piutang';

  contentArea.innerHTML = `
    <div class="page-title">
      <h1>Chart Piutang</h1>
      <p style="color: var(--text-secondary); font-size: 0.85rem;">
        Candlestick saldo piutang — data langsung dari backend
      </p>
    </div>

    <!-- Stats -->
    <div style="display: flex; gap: 16px; margin-bottom: 24px;">
      <div class="table-container" style="flex:1.3; padding: 16px;">
        <div style="font-size: 0.8rem; color: var(--text-secondary);">Saldo Piutang Sekarang</div>
        <div id="stat-piutang-saldo" style="font-size: 1.3rem; font-weight: bold; margin-top: 8px; color: var(--yellow);">—</div>
      </div>
      <div class="table-container" style="flex:1; padding: 16px;">
        <div style="font-size: 0.8rem; color: var(--text-secondary);">Timeframe</div>
        <div id="stat-piutang-tf" style="font-size: 1.2rem; font-weight: bold; margin-top: 8px;">1D</div>
      </div>
      <div class="table-container" style="flex:1; padding: 16px;">
        <div style="font-size: 0.8rem; color: var(--text-secondary);">Timezone</div>
        <div id="stat-piutang-tz" style="font-size: 1.2rem; font-weight: bold; margin-top: 8px;">—</div>
      </div>
    </div>

    <!-- Toggle timeframe -->
    <div class="tf-toggle" style="margin-bottom: 12px;">
      <button id="tf-btn-1d" class="tf-btn active" type="button">1D</button>
      <button id="tf-btn-4h" class="tf-btn" type="button">4H</button>
      <span style="font-size: 0.75rem; color: var(--text-secondary); margin-left: 10px;">
        4H = potongan 4 jam (00/04/08/12/16/20), default 7 hari ke belakang
      </span>
    </div>

    <!-- Candle chart -->
    <div class="table-container" style="padding: 16px;">
      <div id="piutang-chart">
        <div style="text-align:center; padding:40px; color: var(--text-secondary);">Memuat chart...</div>
      </div>
      <div class="ohlc-legend">
        <span style="color:var(--green);font-weight:700;">■</span> saldo naik (utang lahir) &nbsp;·&nbsp;
        <span style="color:var(--red);font-weight:700;">■</span> saldo turun (pembayaran masuk) &nbsp;·&nbsp;
        ⏳ = bucket masih berjalan
        <br>⚠ <b>Kebalikan saham</b>: candle merah gede = pelanggan lunas = kabar baik.
        Hijau beruntun = piutang numpuk = saatnya cek watchlist menunggak.
      </div>
    </div>

    <!-- Volume inflow/outflow -->
    <div class="table-container" style="padding: 16px; margin-top: 16px;">
      <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 8px;">
        Volume — <span style="color:#4ade80;font-weight:700;">inflow</span> = utang baru lahir &nbsp;·&nbsp;
        <span style="color:#ff5f6d;font-weight:700;">outflow</span> = pembayaran masuk &nbsp;·&nbsp;
        delta = outflow − inflow (positif = piutang "lunas lebih banyak dari utang baru")
      </div>
      <div id="piutang-volume"></div>
    </div>
  `;

  // Wire toggle timeframe
  document.getElementById('tf-btn-1d').addEventListener('click', () => switchTimeframe('1d'));
  document.getElementById('tf-btn-4h').addEventListener('click', () => switchTimeframe('4h'));

  // Fetch Data setelah HTML dirender
  fetchPiutangData(_piutangTf);
}

function switchTimeframe(tf) {
  if (tf === _piutangTf) return;
  _piutangTf = tf;
  document.getElementById('tf-btn-1d').classList.toggle('active', tf === '1d');
  document.getElementById('tf-btn-4h').classList.toggle('active', tf === '4h');
  fetchPiutangData(tf);
}

// 2. Fetch Data dari Backend
async function fetchPiutangData(tf) {
  const chartEl = document.getElementById('piutang-chart');
  const token = localStorage.getItem('access_token');
  const storeId = localStorage.getItem('store_id');
  const tz = localStorage.getItem('store_timezone') || 'Asia/Jakarta';

  const tzEl = document.getElementById('stat-piutang-tz');
  const tfEl = document.getElementById('stat-piutang-tf');
  if (tzEl) tzEl.innerText = tz;
  if (tfEl) tfEl.innerText = tf.toUpperCase();

  if (chartEl) chartEl.innerHTML = '<div style="text-align:center; padding:40px; color: var(--text-secondary);">Memuat data piutang...</div>';

  if (!token) {
    showPiutangError(chartEl, 'Token gak ada. Login dulu ya.');
    return;
  }

  try {
    let apiUrl = `/api/analytics/piutang-candle?timeframe=${encodeURIComponent(tf)}`;
    if (storeId) apiUrl += `&store_id=${encodeURIComponent(storeId)}`;

    const response = await fetch(apiUrl, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
    });

    const result = await response.json();
    if (!response.ok || result.status !== 'success') {
      throw new Error(result.message || result.detail || `HTTP ${response.status}`);
    }

    const candles = Array.isArray(result.data) ? result.data : [];

    // Update stat saldo
    const saldoEl = document.getElementById('stat-piutang-saldo');
    if (saldoEl) saldoEl.innerText = rupiahPiutang(result.saldo_sekarang || 0);

    if (candles.length === 0) {
      destroyPiutangCharts();
      showPiutangError(chartEl, 'Belum ada data piutang buat digambar.');
      if (document.getElementById('piutang-volume')) {
        document.getElementById('piutang-volume').innerHTML = '';
      }
      return;
    }

    renderPiutangCandleChart(chartEl, candles, tf);

    const volEl = document.getElementById('piutang-volume');
    if (volEl) renderPiutangVolumeChart(volEl, candles, tf);

  } catch (error) {
    showPiutangError(chartEl, `Error: ${error.message}`);
  }
}

function showPiutangError(el, msg) {
  if (el) el.innerHTML = `<div style="text-align:center; padding:40px; color:#ff5252;">${msg}</div>`;
}

function destroyPiutangCharts() {
  if (_piutangChart) { _piutangChart.destroy(); _piutangChart = null; }
  if (_volumeChart) { _volumeChart.destroy(); _volumeChart = null; }
}

function rupiahPiutang(v) {
  return 'Rp ' + Number(v).toLocaleString('id-ID');
}

// '2026-11-01' -> '01 Nov' ; '2026-11-01 08:00' -> '01 Nov 08'
function shortBucket(bucket, tf) {
  const parts = String(bucket).split(' ');
  const d = parts[0].split('-');
  const bulan = ['Jan','Feb','Mar','Apr','Mei','Jun','Jul','Agu','Sep','Okt','Nov','Des'];
  const base = `${parseInt(d[2], 10)} ${bulan[parseInt(d[1], 10) - 1]}`;
  return tf === '4h' ? `${base} ${parts[1] ? parts[1].slice(0, 2) : ''}` : base;
}

// 3. Render Candle Chart (ApexCharts, tema Sakura Night)
function renderPiutangCandleChart(el, candles, tf) {
  if (typeof ApexCharts === 'undefined') {
    showPiutangError(el, 'Library ApexCharts belum ke-load. Cek <script src="assets/js/apexcharts.min.js"> di dashboard.html');
    return;
  }

  // Bucket berjalan ditandain di label sumbu-X (anotasi di puncak chart
  // ke-clip ApexCharts, udah dibuktikan pas feature omzet dulu)
  const berjalanSet = new Set(candles.filter(c => c.berjalan).map(c => c.bucket));

  const options = {
    chart: {
      type: 'candlestick',
      height: 380,
      fontFamily: 'inherit',
      foreColor: '#a89eaf',           // --text-secondary
      background: 'transparent',
      toolbar: {
        tools: { selection: false, zoom: true, zoomin: true, zoomout: true, pan: true, reset: true },
      },
    },
    series: [{
      name: 'Saldo Piutang',
      data: candles.map(c => ({
        x: c.bucket,
        y: [c.open, c.high, c.low, c.close],
      })),
    }],
    plotOptions: {
      candlestick: {
        colors: { up: '#4ade80', down: '#ff5f6d' },  // --green / --red
      },
    },
    grid: { borderColor: '#2e2635' },  // --border-default
    xaxis: {
      type: 'category',
      tickPlacement: 'on',
      axisBorder: { color: '#2e2635' },
      axisTicks: { color: '#2e2635' },
      labels: {
        style: { fontSize: '10px' },
        rotate: tf === '4h' ? -45 : 0,
        formatter: v => (berjalanSet.has(v) ? shortBucket(v, tf) + ' ⏳' : shortBucket(v, tf)),
      },
    },
    yaxis: {
      opposite: true,
      labels: { formatter: v => rupiahPiutang(v) },
    },
    tooltip: {
      custom: ({ dataPointIndex }) => {
        const c = candles[dataPointIndex];
        if (!c) return '';
        const up = c.close >= c.open;
        return `
          <div style="padding:10px 12px; font-size:12px; line-height:1.7; background:#1c1822; border:1px solid #3a2f42; border-radius:8px; color:#f5f2f7;">
            <b>${c.bucket}</b>${c.berjalan ? ' <span style="color:#ffb84d;">⏳ berjalan</span>' : ''}<br>
            Open&nbsp;&nbsp;: ${rupiahPiutang(c.open)}<br>
            High&nbsp;&nbsp;: ${rupiahPiutang(c.high)}<br>
            Low&nbsp;&nbsp;&nbsp;: ${rupiahPiutang(c.low)}<br>
            Close: <span style="color:${up ? '#4ade80' : '#ff5f6d'}; font-weight:700;">${rupiahPiutang(c.close)}</span><br>
            <span style="border-top:1px solid #3a2f42; display:block; margin-top:4px; padding-top:4px;">
              Utang baru&nbsp;&nbsp;: ${rupiahPiutang(c.inflow)} (${c.n_order} order)<br>
              Pembayaran: ${rupiahPiutang(c.outflow)} (${c.n_payment} bayar)<br>
              Delta&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;: <b style="color:${c.delta >= 0 ? '#4ade80' : '#ff5f6d'};">${rupiahPiutang(c.delta)}</b>
            </span>
          </div>`;
      },
    },
  };

  if (_piutangChart) { _piutangChart.destroy(); _piutangChart = null; }
  el.innerHTML = '';
  _piutangChart = new ApexCharts(el, options);
  _piutangChart.render();
}

// 4. Render Volume 2 Warna (inflow hijau / outflow merah)
function renderPiutangVolumeChart(el, candles, tf) {
  const options = {
    chart: {
      type: 'bar',
      height: 160,
      fontFamily: 'inherit',
      foreColor: '#a89eaf',
      background: 'transparent',
      toolbar: { show: false },
      animations: { enabled: false },
    },
    series: [
      { name: 'Utang baru (inflow)',   data: candles.map(c => c.inflow) },
      { name: 'Pembayaran (outflow)',  data: candles.map(c => c.outflow) },
    ],
    colors: ['#4ade80', '#ff5f6d'],
    plotOptions: {
      bar: { columnWidth: '70%', borderRadius: 2 },
    },
    grid: { borderColor: '#2e2635' },
    xaxis: {
      categories: candles.map(c => c.bucket),
      axisBorder: { color: '#2e2635' },
      axisTicks: { color: '#2e2635' },
      labels: {
        style: { fontSize: '10px' },
        rotate: tf === '4h' ? -45 : 0,
        formatter: v => shortBucket(v, tf),
        hideOverlappingLabels: true,
      },
    },
    yaxis: {
      opposite: true,
      labels: { formatter: v => rupiahPiutang(v) },
    },
    legend: {
      show: true,
      position: 'top',
      horizontalAlign: 'right',
      markers: { size: 6 },
      itemMargin: { horizontal: 6 },
    },
    tooltip: {
      shared: true,
      intersect: false,  // wajib false kalau shared: true, kalau gak ApexCharts error
      custom: ({ dataPointIndex }) => {
        const c = candles[dataPointIndex];
        if (!c) return '';
        return `
          <div style="padding:8px 10px; font-size:12px; line-height:1.7; background:#1c1822; border:1px solid #3a2f42; border-radius:8px; color:#f5f2f7;">
            <b>${c.bucket}</b><br>
            <span style="color:#4ade80;">■</span> Utang baru&nbsp;&nbsp;: ${rupiahPiutang(c.inflow)}<br>
            <span style="color:#ff5f6d;">■</span> Pembayaran: ${rupiahPiutang(c.outflow)}<br>
            Delta: <b style="color:${c.delta >= 0 ? '#4ade80' : '#ff5f6d'};">${rupiahPiutang(c.delta)}</b>
          </div>`;
      },
    },
  };

  if (_volumeChart) { _volumeChart.destroy(); _volumeChart = null; }
  el.innerHTML = '';
  _volumeChart = new ApexCharts(el, options);
  _volumeChart.render();
}

// =====================================================
// NASUHA LABS — APP.JS (v2 — Table Layout Clay Engine)
// =====================================================

// =====================================================
// UTILITIES
// =====================================================

async function loadComponent(elementId, filePath) {
  try {
    const response = await fetch(filePath);
    if (!response.ok) throw new Error(`HTTP ${response.status}: Gagal memuat ${filePath}`);
    const html = await response.text();
    const container = document.getElementById(elementId);
    if (container) container.innerHTML = html;
  } catch (error) {
    console.error(error);
    const container = document.getElementById(elementId);
    if (container) {
      container.innerHTML = `<div style="color: #ff5252; padding: 20px;">
        <h3>Gagal Memuat Komponen</h3>
        <p>${escHTML(error.message)}</p>
        <small>Pastikan <code>${escHTML(filePath)}</code> ada & server running.</small>
      </div>`;
    }
  }
}

// =====================================================
// INIT
// =====================================================

document.addEventListener("DOMContentLoaded", async () => {
  await loadComponent("sidebar-container", "components/sidebar.html");
  await loadComponent("header-container", "components/header.html");

  renderAuthState();

  // Default page = Clay Engine Home
  await loadClayHome();

  setupEventListeners();
  setupAuthListeners();
});

// =====================================================
// NAVIGASI SIDEBAR
// =====================================================

function setupEventListeners() {
  if (document.body.dataset.navBound === "true") return;
  document.body.dataset.navBound = "true";

  document.addEventListener("click", async (e) => {
    const navLink = e.target.closest(".nav-item a");
    if (!navLink) return;

    e.preventDefault();
    const pageName = navLink.getAttribute("data-page");

    const pageTitleEl = document.getElementById("current-page-title");
    if (pageTitleEl) pageTitleEl.innerText = pageName;

    document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
    navLink.parentElement.classList.add("active");

    if (pageName === "Database") {
      await loadComponent("content-area", "components/database.html");
      loadDatabaseRealData();
    } else if (pageName === "Download") {
      await loadComponent("content-area", "components/download.html");
      loadDownloadData();
    } else if (pageName === "Clay Engine") {
      await loadClayHome();
    }
  });
}

// =====================================================
// CLAY ENGINE — NAVIGASI (HOME <-> PREDICT)
// =====================================================

async function loadClayHome() {
  await loadComponent("content-area", "components/clay_home.html");
  setupClayHomeListeners();
  loadClayHomeData();
}

async function loadClayPredict() {
  await loadComponent("content-area", "components/clay_engine.html");
  loadClayEngineData();
}

function setupClayHomeListeners() {
  const card = document.getElementById("clay-card-predict");
  if (card && !card.dataset.bound) {
    card.dataset.bound = "true";
    card.addEventListener("click", () => loadClayPredict());
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        loadClayPredict();
      }
    });
  }
}

// =====================================================
// CLAY ENGINE — HOME DATA (Greeting, Jam, KPI)
// =====================================================

async function loadClayHomeData() {
  const greetingEl = document.getElementById("clay-greeting");
  const datetimeEl = document.getElementById("clay-datetime");

  // Greeting
  let displayName = "Bos";
  try {
    const raw = localStorage.getItem("user_info");
    if (raw) {
      const info = JSON.parse(raw);
      displayName = info.nama_pegawai || info.name || info.email || "Bos";
    }
  } catch (_) {}

  const hour = new Date().getHours();
  let timeGreeting = "Halo";
  if (hour < 11) timeGreeting = "Selamat pagi";
  else if (hour < 15) timeGreeting = "Selamat siang";
  else if (hour < 18) timeGreeting = "Selamat sore";
  else timeGreeting = "Selamat malam";

  if (greetingEl) greetingEl.textContent = `${timeGreeting}, ${displayName} 👋`;

  // DateTime
  const tz = localStorage.getItem("store_timezone") || "Asia/Jakarta";
  try {
    const fmt = new Intl.DateTimeFormat("id-ID", {
      weekday: "long", day: "numeric", month: "long", year: "numeric",
      hour: "2-digit", minute: "2-digit", timeZone: tz,
    });
    if (datetimeEl) datetimeEl.textContent = `${fmt.format(new Date())} (${tz})`;
  } catch (_) {
    if (datetimeEl) datetimeEl.textContent = new Date().toLocaleString("id-ID");
  }

  // Fetch KPI
  const token = localStorage.getItem("access_token");
  const storeId = localStorage.getItem("store_id");
  if (!token) {
    setKPI("clay-kpi-predict", "—");
    setKPI("clay-kpi-accuracy", "—");
    setKPI("clay-kpi-skipped", "—");
    return;
  }

  const headers = { "Authorization": `Bearer ${token}`, "Content-Type": "application/json" };
  const qs = storeId ? `?store_id=${encodeURIComponent(storeId)}` : "";

  // Predict
  try {
    const res = await fetch(`/api/clay/predict-tomorrow${qs}`, { headers });
    if (res.ok) {
      const data = await res.json();
      const preds = Array.isArray(data.predictions) ? data.predictions : [];
      const carry = Array.isArray(data.carry_over) ? data.carry_over : [];
      const skipped = (data.metadata && Array.isArray(data.metadata.skipped)) ? data.metadata.skipped : [];
      setKPI("clay-kpi-predict", `${preds.length + carry.length}`);
      setKPI("clay-kpi-skipped", `${skipped.length}`);
    }
  } catch (e) {
    console.warn("KPI predict error:", e);
  }

  // Accuracy 7d
  try {
    const sep = qs ? "&" : "?";
    const res = await fetch(`/api/clay/history/accuracy${qs}${sep}period=7d`, { headers });
    if (res.ok) {
      const data = await res.json();
      const acc = data.accuracy_pct ?? data.accuracy ?? data.accuracy_rate ?? data.rate ?? null;
      const hit = data.hit ?? data.total_hit ?? null;
      const total = data.total ?? data.evaluated ?? null;

      if (acc != null) setKPI("clay-kpi-accuracy", `${Number(acc).toFixed(1)}%`);
      else if (hit != null && total != null && total > 0) setKPI("clay-kpi-accuracy", `${((hit / total) * 100).toFixed(1)}%`);
      else setKPI("clay-kpi-accuracy", "—");
    } else {
      setKPI("clay-kpi-accuracy", "—");
    }
  } catch (e) {
    console.warn("KPI accuracy error:", e);
  }
}

function setKPI(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

// =====================================================
// CLAY ENGINE — PREDICT PAGE (TABLE LAYOUT)
// =====================================================

async function loadClayEngineData() {
  const tbodyPredict = document.getElementById("tbody-predict");
  const tbodyCarry = document.getElementById("tbody-carry");
  const statPotensialEl = document.getElementById("stat-total-potensial");
  const statCarryEl = document.getElementById("stat-total-carry-over");
  const statOmsetEl = document.getElementById("stat-total-omset");
  const badgeCountNormal = document.getElementById("badge-count-normal");
  const badgeCountCarry = document.getElementById("badge-count-carry");
  const dateEl = document.getElementById("clay-engine-date");

  // Set tanggal header
  if (dateEl) {
    const tz = localStorage.getItem("store_timezone") || "Asia/Jakarta";
    try {
      const fmt = new Intl.DateTimeFormat("id-ID", {
        weekday: "long", day: "numeric", month: "long", year: "numeric",
        hour: "2-digit", minute: "2-digit", timeZone: tz,
      });
      dateEl.textContent = `📅 ${fmt.format(new Date())} (${tz})`;
    } catch (_) {
      dateEl.textContent = `📅 ${new Date().toLocaleString("id-ID")}`;
    }
  }

	// Bind back-to-home
	const btnBack = document.getElementById("btn-back-home");
	if (btnBack && !btnBack.dataset.bound) {
	  btnBack.dataset.bound = "true";
	  btnBack.addEventListener("click", () => {
	   const pageTitleEl = document.getElementById("current-page-title");
	   if (pageTitleEl) pageTitleEl.innerText = "Clay Engine";
	   document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
	   const clayNav = document.querySelector('.nav-item a[data-page="Clay Engine"]');
	   if (clayNav) clayNav.parentElement.classList.add("active");
	   loadClayHome();
	 });
	}

  // Bind refresh
  const btnRefresh = document.getElementById("btn-refresh-clay");
  if (btnRefresh && !btnRefresh.dataset.bound) {
    btnRefresh.dataset.bound = "true";
    btnRefresh.addEventListener("click", () => {
      loadClayEngineData();
      loadClayHistory();
    });
  }

  // Bind history filter
  document.querySelectorAll(".history-filter-btn").forEach(btn => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = "true";
    btn.addEventListener("click", () => {
      document.querySelectorAll(".history-filter-btn").forEach(b => {
        b.classList.remove("history-filter-active");
        b.style.background = "#2a2a2e";
        b.style.color = "#ccc";
        b.style.border = "1px solid #3a3a3e";
      });
      btn.classList.add("history-filter-active");
      btn.style.background = "#28c8ff";
      btn.style.color = "#000";
      btn.style.border = "none";
      
    });
  });

  const token = localStorage.getItem("access_token");
  const storeId = localStorage.getItem("store_id");

  if (!token) {
    if (tbodyPredict) {
      tbodyPredict.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:#ffb74d;">Sesi habis atau belum login.</td></tr>`;
    }
    if (tbodyCarry) {
      tbodyCarry.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:#ffb74d;">—</td></tr>`;
    }
    return;
  }

  try {
    let apiUrl = "/api/clay/predict-tomorrow";
    if (storeId) apiUrl += `?store_id=${encodeURIComponent(storeId)}`;

    const response = await fetch(apiUrl, {
      method: "GET",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` }
    });

    if (response.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user_info");
      renderAuthState();
      if (tbodyPredict) {
        tbodyPredict.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:#ff5252;">🔒 Sesi berakhir. Silakan login ulang.</td></tr>`;
      }
      return;
    }

    const result = await response.json();
    if (!response.ok || result.status === "error") {
      throw new Error(result.message || result.error || "Gagal fetch data");
    }

    const predictions = Array.isArray(result.predictions) ? result.predictions : [];
    const carryOvers = Array.isArray(result.carry_over) ? result.carry_over : [];

    const omsetNormal = predictions.reduce((s, i) => s + Number(i.est_spend || 0), 0);
    const omsetCarry = carryOvers.reduce((s, i) => s + Number(i.est_spend || 0), 0);
    const totalOmset = omsetNormal + omsetCarry;

    if (statPotensialEl) statPotensialEl.innerText = `${predictions.length} Pelanggan`;
    if (statCarryEl) statCarryEl.innerText = `${carryOvers.length} Pelanggan`;
    if (statOmsetEl) statOmsetEl.innerText = `Rp ${totalOmset.toLocaleString("id-ID")}`;
    if (badgeCountNormal) badgeCountNormal.innerText = `${predictions.length} items`;
    if (badgeCountCarry) badgeCountCarry.innerText = `${carryOvers.length} items`;

    renderPredictTable(predictions);
    renderCarryOverTable(carryOvers);
    bindWaButtons();

    // Load history juga
    loadClayHistory();

  } catch (error) {
    console.error("Clay Engine Error:", error);
    if (tbodyPredict) {
      tbodyPredict.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:20px; color:#ff5252;">Error: ${escHTML(error.message)}</td></tr>`;
    }
    if (tbodyCarry) {
      tbodyCarry.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:20px; color:#ff5252;">—</td></tr>`;
    }
  }
}

// =====================================================
// HELPERS — Badge & Warna
// =====================================================

function getTagStyle(tag) {
  const colors = {
    "VIP":          { bg: "rgba(255,193,7,0.15)",  color: "#ffc107", border: "#ffc107" },
    "Resiko Churn": { bg: "rgba(255,82,82,0.15)",  color: "#ff5252", border: "#ff5252" },
    "Reguler":      { bg: "rgba(40,200,255,0.12)", color: "#28c8ff", border: "#28c8ff" },
  };
  return colors[tag] || colors["Reguler"];
}

function getScoreColor(score) {
  if (score >= 80) return "#00E676";
  if (score >= 60) return "#ffc107";
  return "#ff5252";
}

function getCarryBadge(count) {
  if (count >= 3) return { bg: "rgba(255,82,82,0.15)",  color: "#ff5252", label: `🔴 Telat ${count} hari` };
  if (count === 2) return { bg: "rgba(255,152,0,0.15)", color: "#ff9800", label: `🟠 Telat ${count} hari` };
  return { bg: "rgba(255,193,7,0.15)", color: "#ffc107", label: `🟡 Telat ${count} hari` };
}

// =====================================================
// RENDER — TABLE PREDICT
// =====================================================

function renderPredictTable(items) {
  const tbody = document.getElementById("tbody-predict");
  if (!tbody) return;

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:24px; color:#888;">Tidak ada prediksi pelanggan untuk besok hari.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map((item, idx) => {
    const name = item.name || item.customer_name || "Pelanggan";
    const phone = item.phone || item.customer_phone || "-";
    const code = item.customer_code || "-";
    const tag = item.tag || "Reguler";
    const score = Number(item.score) || 0;
    const cycle = item.cycle_days ? `${Math.round(item.cycle_days)} hari` : "-";
    const tagStyle = getTagStyle(tag);
    const scoreColor = getScoreColor(score);

    return `
      <tr style="border-bottom: 1px solid #27272a;">
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: #aaa; font-size: 0.85rem;">${idx + 1}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: #fff; font-weight: 600; font-size: 0.85rem;">${escHTML(name)}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a;">
          <span style="background:${tagStyle.bg}; color:${tagStyle.color}; border:1px solid ${tagStyle.border}; padding:2px 8px; border-radius:6px; font-size:0.72rem; font-weight:600;">${escHTML(tag)}</span>
        </td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:${scoreColor}; font-weight:700; font-size:0.9rem;">${score}%</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:#ccc; font-size:0.83rem;">${cycle}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:#28c8ff; font-family: monospace; font-size:0.8rem;">${escHTML(code)}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:#ccc; font-size:0.83rem;">${escHTML(phone)}</td>
        <td style="padding: 12px 14px; text-align: center;">
          <button class="btn-wa-action" data-phone="${escHTML(phone)}" data-name="${escHTML(name)}" data-is-carry="false" data-carry-count="0"
            style="background: #25D366; color: #000; border: none; font-weight: 700; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.75rem;">
            💬 WA
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

// =====================================================
// RENDER — TABLE CARRY OVER
// =====================================================

function renderCarryOverTable(items) {
  const tbody = document.getElementById("tbody-carry");
  if (!tbody) return;

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:#888;">Tidak ada pelanggan carry over saat ini.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map((item, idx) => {
    const name = item.name || item.customer_name || "Pelanggan";
    const phone = item.phone || item.customer_phone || "-";
    const tag = item.tag || "Reguler";
    const score = Number(item.score) || 0;
    const cycle = item.cycle_days ? `${Math.round(item.cycle_days)} hari` : "-";
    const carry = item.carry_over_count || 1;
    const reason = item.reason || "-";
    const tagStyle = getTagStyle(tag);
    const scoreColor = getScoreColor(score);
    const carryBadge = getCarryBadge(carry);

    return `
      <tr style="border-bottom: 1px solid #27272a;">
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: #aaa; font-size: 0.85rem;">${idx + 1}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: #fff; font-weight: 600; font-size: 0.85rem;">${escHTML(name)}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a;">
          <span style="background:${tagStyle.bg}; color:${tagStyle.color}; border:1px solid ${tagStyle.border}; padding:2px 8px; border-radius:6px; font-size:0.72rem; font-weight:600;">${escHTML(tag)}</span>
        </td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a;">
          <span style="background:${carryBadge.bg}; color:${carryBadge.color}; padding:3px 10px; border-radius:10px; font-size:0.72rem; font-weight:700;">${carryBadge.label}</span>
        </td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:${scoreColor}; font-weight:700; font-size:0.9rem;">${score}%</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:#ccc; font-size:0.83rem;">${cycle}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:#ccc; font-size:0.83rem;">${escHTML(phone)}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color:#aaa; font-size:0.8rem; max-width: 280px;">${escHTML(reason)}</td>
        <td style="padding: 12px 14px; text-align: center;">
          <button class="btn-wa-action" data-phone="${escHTML(phone)}" data-name="${escHTML(name)}" data-is-carry="true" data-carry-count="${carry}"
            style="background: #25D366; color: #000; border: none; font-weight: 700; padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 0.75rem;">
            💬 WA
          </button>
        </td>
      </tr>
    `;
  }).join("");
}

// =====================================================
// HISTORY PREDIKSI — ROBUST VERSION
// =====================================================

function _num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function _acc(hit, miss, pctFallback) {
  if (pctFallback != null && Number.isFinite(Number(pctFallback))) {
    return Number(pctFallback);
  }
  const evaluated = hit + miss;
  return evaluated > 0 ? (hit / evaluated) * 100 : 0;
}

function normalizeHistoryRows(data, period) {
  if (!data || typeof data !== "object") return [];

  // ---- Case A: ada `groups` (object key = tanggal) ----
  // ---- Case A0: groups = array of precomputed objects (format backend skrg) ----
  if (Array.isArray(data.groups)) {
    return data.groups.map(g => {
      const hit = _num(g.hit);
      const miss = _num(g.miss);
      const pending = _num(g.pending);
      const total = _num(g.total) || (hit + miss + pending);
      return {
        date: g.target_date || g.date_label || "-",
        total, hit, miss, pending,
        accuracy: _acc(hit, miss, g.accuracy_pct),
      };
    });
  }

  const groups = data.groups;
  if (groups && typeof groups === "object" && !Array.isArray(groups)) {
    const rows = Object.keys(groups).map(dateKey => {
      const val = groups[dateKey];

      // A1: value = array of logs
      if (Array.isArray(val)) {
        const total = val.length;
        const hit = val.filter(i => (i.outcome_status || i.status) === "hit").length;
        const miss = val.filter(i => (i.outcome_status || i.status) === "miss").length;
        const pending = val.filter(i => (i.outcome_status || i.status) === "pending").length;
        return { date: dateKey, total, hit, miss, pending, accuracy: _acc(hit, miss) };
      }

      // A2: value = precomputed object
      if (val && typeof val === "object") {
        const hit = _num(val.hit);
        const miss = _num(val.miss);
        const pending = _num(val.pending);
        const total = _num(val.total) || (hit + miss + pending);
        return {
          date: dateKey,
          total, hit, miss, pending,
          accuracy: _acc(hit, miss, val.accuracy_pct ?? val.accuracy),
        };
      }

      return null;
    }).filter(Boolean);

    if (rows.length > 0) {
      return rows.sort((a, b) => (a.date < b.date ? 1 : -1));
    }
  }

  // ---- Case B: array bentuk lain ----
  const arr = Array.isArray(data) ? data
    : Array.isArray(data.blocks) ? data.blocks
    : Array.isArray(data.daily) ? data.daily
    : Array.isArray(data.data) ? data.data
    : [];

  if (arr.length > 0) {
    return arr.map(b => {
      const hit = _num(b.hit);
      const miss = _num(b.miss);
      const pending = _num(b.pending);
      return {
        date: b.date || b.target_date || b.prediction_target_date || "-",
        total: _num(b.total) || (hit + miss + pending),
        hit, miss, pending,
        accuracy: _acc(hit, miss, b.accuracy_pct ?? b.accuracy),
      };
    });
  }

  // ---- Case C: summary global (fallback) ----
  if (data.total != null || data.hit != null || data.miss != null) {
    const hit = _num(data.hit);
    const miss = _num(data.miss);
    const pending = _num(data.pending);
    return [{
      date: `Semua (${period})`,
      total: _num(data.total) || (hit + miss + pending),
      hit, miss, pending,
      accuracy: _acc(hit, miss, data.accuracy_pct ?? data.accuracy),
    }];
  }

  return [];
}

async function loadClayHistory() {
  const tbody = document.getElementById("tbody-history");
  const btnWrap = document.getElementById("btn-history-loadmore-wrap");
  const btnLoadMore = document.getElementById("btn-history-loadmore");
  if (!tbody) return;

  tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:#888;">Memuat history...</td></tr>`;
  if (btnWrap) btnWrap.style.display = "none";

  const token = localStorage.getItem("access_token");
  const storeId = localStorage.getItem("store_id");

  if (!token) {
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:#ffb74d;">Login dulu untuk lihat history.</td></tr>`;
    return;
  }

  try {
    let url = `/api/clay/history/accuracy?period=all`;
    if (storeId) url += `&store_id=${encodeURIComponent(storeId)}`;

    const res = await fetch(url, { headers: { "Authorization": `Bearer ${token}` } });

    if (res.status === 401) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:#ff5252;">🔒 Sesi berakhir. Silakan login ulang.</td></tr>`;
      if (typeof handleUnauthorized === "function") handleUnauthorized("Token expired di loadClayHistory");
      return;
    }

    if (!res.ok) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:#ffb74d;">Gagal load history (HTTP ${res.status}).</td></tr>`;
      return;
    }

    const data = await res.json();
    const groups = Array.isArray(data.groups) ? data.groups : [];

    if (groups.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:#888;">Belum ada history prediksi.</td></tr>`;
      return;
    }

    // ---- Flatten semua prediksi dari semua tanggal ----
    const allItems = [];
    groups.forEach(g => {
      (g.predictions || []).forEach(p => {
        allItems.push({ target_date: g.target_date, ...p });
      });
    });

    // ---- Sort ASC by date (untuk hitung kumulatif dari awal) ----
    allItems.sort((a, b) => a.target_date < b.target_date ? -1 : a.target_date > b.target_date ? 1 : 0);

    // ---- Hitung kumulatif per customer ----
    const cumul = {};
    const rows = [];

    allItems.forEach(item => {
      const code = item.customer_code || item.customer_name;
      if (!cumul[code]) cumul[code] = { total: 0, hit: 0, miss: 0, carry: {} };
      const c = cumul[code];

      c.total += 1;
      if (item.outcome_status === "hit") c.hit += 1;
      if (item.outcome_status === "miss") c.miss += 1;
      if (item.is_carry_over && item.carry_over_count > 0) {
        const lvl = item.carry_over_count;
        c.carry[lvl] = (c.carry[lvl] || 0) + 1;
      }

      const evaluated = c.hit + c.miss;
      const accuracy = evaluated > 0 ? (c.hit / evaluated * 100) : null;

      rows.push({
        target_date: item.target_date,
        customer_name: item.customer_name || "Pelanggan",
        outcome_status: item.outcome_status || "pending",
        total: c.total,
        hit: c.hit,
        miss: c.miss,
        accuracy: accuracy,
        carry: { ...c.carry },
      });
    });

    // ---- Sort DESC by date, ASC by nama ----
    rows.sort((a, b) => {
      if (a.target_date !== b.target_date) return a.target_date < b.target_date ? 1 : -1;
      return a.customer_name.localeCompare(b.customer_name);
    });

    // ---- Pre-group by target_date (biar pagination per tanggal) ----
    const dateGroups = [];
    let curGroup = null;
    rows.forEach(r => {
      if (!curGroup || curGroup.date !== r.target_date) {
        curGroup = { date: r.target_date, items: [] };
        dateGroups.push(curGroup);
      }
      curGroup.items.push(r);
    });

    const DATE_PAGE_SIZE = 10;
    let shownDates = 0;

    const renderPage = () => {
      const sliceGroups = dateGroups.slice(shownDates, shownDates + DATE_PAGE_SIZE);

      let html = "";
      sliceGroups.forEach((group, gi) => {
        let dateShort = group.date;
        try {
          const d = new Date(group.date);
          dateShort = d.toLocaleDateString("id-ID", { day: "2-digit", month: "short" });
        } catch (_) {}

        const isLastGroupInAll = (shownDates + gi === dateGroups.length - 1);
        const thickBorder = "3px solid #666";
        const thinBorder = "1px solid #27272a";
        const groupEndBorder = isLastGroupInAll ? thinBorder : thickBorder;

        group.items.forEach((r, idx) => {
          const isLastRow = (idx === group.items.length - 1);
          const accColor = r.accuracy == null ? "#888" : r.accuracy >= 70 ? "#00E676" : r.accuracy >= 50 ? "#ffc107" : "#ff5252";
          const accText  = r.accuracy == null ? "—" : `${r.accuracy.toFixed(0)}%`;

          let badge = "";
          if (r.outcome_status === "hit")  badge = `<span style="margin-left:6px;">✅</span>`;
          else if (r.outcome_status === "miss") badge = `<span style="margin-left:6px;">❌</span>`;
          else badge = `<span style="margin-left:6px;">⏳</span>`;

          let carryHtml = `<span style="color:#555;">—</span>`;
          const carryKeys = Object.keys(r.carry).map(Number).sort((a, b) => a - b);
          if (carryKeys.length > 0) {
            carryHtml = carryKeys.map(lvl =>
              `<div style="color:#ffb74d; font-size:0.78rem; line-height:1.45;">${r.carry[lvl]}x <span style="color:#888;">(telat ${lvl} hari)</span></div>`
            ).join("");
          }

          const dateCell = idx === 0
            ? `<td rowspan="${group.items.length}" style="padding:10px 14px; border-right:1px solid #27272a; border-bottom:${groupEndBorder}; color:#28c8ff; font-weight:700; font-size:0.85rem; white-space:nowrap; vertical-align:top;">${escHTML(dateShort)}</td>`
            : "";

          const rowBorder = isLastRow ? groupEndBorder : thinBorder;

          html += `
            <tr style="border-bottom:${rowBorder};">
              ${dateCell}
              <td style="padding:10px 14px; border-right:1px solid #27272a; color:#fff; font-weight:600; font-size:0.85rem;">${escHTML(r.customer_name)}${badge}</td>
              <td style="padding:10px 14px; border-right:1px solid #27272a; color:${accColor}; font-weight:700; font-size:0.85rem;">${accText}</td>
              <td style="padding:10px 14px; border-right:1px solid #27272a; color:#ccc; font-size:0.83rem;">${r.total}x</td>
              <td style="padding:10px 14px; border-right:1px solid #27272a; color:#00E676; font-weight:600; font-size:0.83rem;">${r.hit}x</td>
              <td style="padding:10px 14px; border-right:1px solid #27272a; color:#ff5252; font-weight:600; font-size:0.83rem;">${r.miss}x</td>
              <td style="padding:10px 14px; font-size:0.83rem;">${carryHtml}</td>
            </tr>
          `;
        });
      });

      if (shownDates === 0) tbody.innerHTML = html;
      else tbody.insertAdjacentHTML("beforeend", html);

      shownDates += sliceGroups.length;
      if (btnWrap) btnWrap.style.display = shownDates < dateGroups.length ? "block" : "none";
    };

    renderPage();

    if (btnLoadMore && !btnLoadMore.dataset.bound) {
      btnLoadMore.dataset.bound = "true";
      btnLoadMore.addEventListener("click", renderPage);
    }

  } catch (err) {
    console.error("[loadClayHistory] error:", err);
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:24px; color:#ff5252;">Error: ${escHTML(err.message)}</td></tr>`;
  }
}

// =====================================================
// BIND WA BUTTONS
// =====================================================

function bindWaButtons() {
  document.querySelectorAll(".btn-wa-action").forEach(btn => {
    if (btn.dataset.bound) return;
    btn.dataset.bound = "true";
    btn.addEventListener("click", () => {
      const phone = btn.dataset.phone || "";
      const name = btn.dataset.name || "";
      const isCarry = btn.dataset.isCarry === "true";
      const carryCount = btn.dataset.carryCount || "1";
      sendWhatsAppReminder(phone, name, isCarry, carryCount);
    });
  });
}

// FORMAT NO WA & KIRIM FOLLOW UP
function sendWhatsAppReminder(phone, name, isCarryOver = false, carryCount = 1) {
  if (!phone || phone === "-") {
    alert(`Nomor telepon untuk ${name} tidak tersedia.`);
    return;
  }

  let formattedPhone = phone.replace(/\D/g, "");
  if (formattedPhone.startsWith("0")) formattedPhone = "62" + formattedPhone.slice(1);
  else if (formattedPhone.startsWith("8")) formattedPhone = "62" + formattedPhone;

  let text = "";
  if (isCarryOver) {
    text = `Halo Kak ${name}, kabar baik dari Nasuha Laundry! 👋\n\nSekadar mengingatkan nih Kak, jadwal laundry rutin Kakak sepertinya sudah lewat ${carryCount} hari. Pakaian kotornya sudah menumpuk? Yuk kami bantu laundry biar bersih dan wangi kembali. Hubungi kami untuk penjemputan ya Kak! 🧺✨`;
  } else {
    text = `Halo Kak ${name}, dari Nasuha Laundry! 👋\n\nBerdasarkan jadwal rutin, besok waktunya laundry pakaian lagi nih Kak. Mau kami bantu siapkan slot laundry-nya besok? Ditunggu kedatangannya ya Kak! 🧺✨`;
  }

  const waUrl = `https://wa.me/${formattedPhone}?text=${encodeURIComponent(text)}`;
  window.open(waUrl, "_blank");
}

// =====================================================
// AUTH
// =====================================================

function setupAuthListeners() {
  if (document.body.dataset.authBound === "true") return;
  document.body.dataset.authBound = "true";

  const loginModal = document.getElementById("login-modal");
  const closeBtn = document.getElementById("btn-close-login");
  const formLogin = document.getElementById("form-login");

  document.addEventListener("click", (e) => {
    if (e.target.closest("#user-profile-btn") || e.target.closest(".text-login") || e.target.closest(".text-register")) {
      const token = localStorage.getItem("access_token");
      if (token) {
        if (confirm("Apakah Anda yakin ingin logout?")) {
          localStorage.removeItem("access_token");
          localStorage.removeItem("store_id");
          localStorage.removeItem("user_info");
          window.location.reload();
        }
      } else {
        if (loginModal) loginModal.classList.remove("hidden");
      }
    }
  });

  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      if (loginModal) loginModal.classList.add("hidden");
    });
  }

  if (formLogin) {
    formLogin.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errorMsg = document.getElementById("login-error-msg") || document.getElementById("loginError");
      if (errorMsg) errorMsg.classList.add("hidden");

      const email = document.getElementById("login-email").value;
      const password = document.getElementById("login-password").value;

      try {
        const res = await fetch("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password })
        });

        const result = await res.json();
        if (!res.ok || result.status === "error") {
          throw new Error(result.message || "Login gagal, periksa email dan password.");
        }

        if (result.access_token) localStorage.setItem("access_token", result.access_token);
        if (result.store_id) localStorage.setItem("store_id", result.store_id);
        if (result.user) localStorage.setItem("user_info", JSON.stringify(result.user));

        if (loginModal) loginModal.classList.add("hidden");
        renderAuthState();

        await loadClayHome();

      } catch (err) {
        if (errorMsg) {
          errorMsg.innerText = err.message;
          errorMsg.classList.remove("hidden");
        }
      }
    });
  }
}

function renderAuthState() {
  const token = localStorage.getItem("access_token");
  const userInfoRaw = localStorage.getItem("user_info");

  // FIX: pakai selector yang bener (id + class fallback)
  const headerTextGroup = document.querySelector("#header-user-text") 
                        || document.querySelector(".user-text-group");
  const headerIcon      = document.querySelector(".user-icon");
  const sidebarName     = document.querySelector("#sidebar-user-name") 
                        || document.querySelector(".brand-title");
  const sidebarAvatar   = document.querySelector("#sidebar-user-avatar") 
                        || document.querySelector(".brand-logo-wrapper");

  if (token) {
    let userDisplayName = "Kasir";
    try {
      if (userInfoRaw) {
        const info = JSON.parse(userInfoRaw);
        userDisplayName = info.nama_pegawai || info.name || info.email || "Kasir";
      }
    } catch (e) {}

    if (headerTextGroup) {
      headerTextGroup.innerHTML = `
        <span class="text-login" style="color:#ffffff;">${escHTML(userDisplayName)}</span>
        <span class="text-separator">/</span>
        <span class="text-register" style="color:#ff5252; font-weight:600; cursor:pointer;">Logout</span>
      `;
    }
    if (headerIcon) headerIcon.innerText = "👨‍🍳";
    if (sidebarName) sidebarName.innerText = userDisplayName;
    if (sidebarAvatar) sidebarAvatar.innerHTML = `<span style="font-size:1.2rem;">✅</span>`;
  } else {
    if (headerTextGroup) {
      headerTextGroup.innerHTML = `
        <span class="text-login">Login</span>
        <span class="text-separator">/</span>
        <span class="text-register">Register</span>
      `;
    }
    if (headerIcon) headerIcon.innerText = "🧺";
    if (sidebarName) sidebarName.innerText = "Login Your Account";
    if (sidebarAvatar) sidebarAvatar.innerHTML = `<span style="font-size:1.2rem;">👤</span>`;
  }
}

// =====================================================
// DATABASE
// =====================================================

async function loadDatabaseRealData() {
  const tableBody = document.getElementById("db-table-body");
  const token = localStorage.getItem("access_token");

  if (!token) {
    if (tableBody) tableBody.innerHTML = `<tr><td colspan="13" style="color: #ffb74d; text-align: center; padding: 20px;">Silakan login terlebih dahulu.</td></tr>`;
    return;
  }

  try {
    const response = await fetch("/api/transactions", {
      headers: { "Authorization": `Bearer ${token}` }
    });

    if (response.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("user_info");
      renderAuthState();
      if (tableBody) {
        tableBody.innerHTML = `<tr><td colspan="13" style="text-align: center; padding: 28px; color: #ff5252;">🔒 Sesi berakhir. Silakan login ulang.</td></tr>`;
      }
      const lm = document.getElementById("login-modal");
      if (lm) lm.classList.remove("hidden");
      return;
    }

    const result = await response.json();
    const listData = Array.isArray(result) ? result : (result.data || []);

    if (tableBody) {
      if (listData.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="13" style="text-align:center; padding: 20px;">Belum ada data orders.</td></tr>`;
        return;
      }

      tableBody.innerHTML = listData.map(row => `
        <tr>
          <td>${escHTML(row.id)}</td>
          <td><strong>${escHTML(row.order_number || row.nota_number || '-')}</strong></td>
          <td>${escHTML(row.customer_name || '-')}</td>
          <td>${escHTML(row.service_name || '-')}</td>
          <td>Rp ${Number(row.total_price || 0).toLocaleString('id-ID')}</td>
          <td><span class="badge ${row.status === 'Lunas' ? 'badge-success' : 'badge-warning'}">${escHTML(row.status || 'Proses')}</span></td>
          <td>${escHTML(row.payment_method || '-')}</td>
          <td>${row.created_at ? new Date(row.created_at).toLocaleDateString('id-ID') : '-'}</td>
          <td>${escHTML(row.date_estimate || '-')}</td>
          <td>${escHTML(row.date_paid || '-')}</td>
          <td>Rp ${Number(row.discount || 0).toLocaleString('id-ID')}</td>
          <td>${escHTML(row.notes || '-')}</td>
          <td><button class="btn-sm btn-edit">Edit</button></td>
        </tr>
      `).join("");
    }

  } catch (error) {
    console.error("Database Fetch Error:", error);
    if (tableBody) tableBody.innerHTML = `<tr><td colspan="13" style="color: #ff5252; text-align: center; padding: 20px;">Error: ${escHTML(error.message)}</td></tr>`;
  }
}

// =====================================================
// DOWNLOAD
// =====================================================

async function loadDownloadData() {
  const container = document.getElementById("download-list-container");
  if (!container) return;

  try {
    const response = await fetch("/api/downloads");
    if (!response.ok) throw new Error("Gagal mengambil data rilis.");

    const result = await response.json();
    if (result.status === "error") throw new Error(result.message);

    const data = result.data || [];

    if (data.length === 0) {
      container.innerHTML = `<div style="color: #888; padding: 20px;">Belum ada file aplikasi.</div>`;
      return;
    }

    container.innerHTML = data.map(app => `
      <div class="download-card">
        <div class="app-icon">${app.type === 'APK' ? '📱' : '💻'}</div>
        <div class="app-details">
          <h3>${escHTML(app.title)}</h3>
          <p class="app-meta">Versi ${escHTML(app.version)} • ${escHTML(app.type)} • ${escHTML(app.size)}</p>
          <p class="app-desc">${escHTML(app.description || '')}</p>
        </div>
        <div class="app-action">
          <a href="${safeUrl(app.download_url)}" target="_blank" rel="noopener noreferrer" download class="btn-primary btn-download">
            ⬇️ Download ${escHTML(app.type)}
          </a>
        </div>
      </div>
    `).join("");

  } catch (error) {
    console.error("Download Fetch Error:", error);
    container.innerHTML = `<div style="color: #ff5252; padding: 20px;">Gagal memuat: ${escHTML(error.message)}</div>`;
  }
}

// =====================================================
// NASUHA LABS — APP.JS (v2.1 — FIXED)
// Perbaikan:
//   - renderPredictTable: tambah kolom "Status Nota" (9 kolom)
//   - colspan 8 -> 9
//   - handleUnauthorized di-define proper
//   - guard history table (kalau HTML belum punya tbody-history)
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

function handleUnauthorized(reason = "Sesi berakhir") {
  console.warn("[auth]", reason);
  localStorage.removeItem("access_token");
  localStorage.removeItem("store_id");
  localStorage.removeItem("user_info");
  if (typeof renderAuthState === "function") renderAuthState();
  const lm = document.getElementById("login-modal");
  if (lm) lm.classList.remove("hidden");
}

// =====================================================
// INIT
// =====================================================

document.addEventListener("DOMContentLoaded", async () => {
  await loadComponent("sidebar-container", "components/sidebar.html");
  await loadComponent("header-container", "components/header.html");

  renderAuthState();
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

  // Predict today
  try {
    const res = await fetch(`/api/clay/predict-today${qs}`, { headers });
    if (res.ok) {
      const data = await res.json();
      const preds = Array.isArray(data.predictions) ? data.predictions : [];
      const carry = Array.isArray(data.carry_over) ? data.carry_over : [];
      const skipped = (data.metadata && Array.isArray(data.metadata.skipped)) ? data.metadata.skipped : [];
      setKPI("clay-kpi-predict", `${preds.length + carry.length}`);
      setKPI("clay-kpi-skipped", `${skipped.length}`);
    } else if (res.status === 401) {
      handleUnauthorized("KPI predict: token expired");
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
      // Backend clay_insight_service return shape:
      //   { summary: { accuracy_pct, hit, miss, evaluated, total, ... }, groups: [...] }
      const summary = data.summary || data;
      const acc = summary.accuracy_pct ?? data.accuracy_pct ?? null;
      const hit = summary.hit ?? data.hit ?? null;
      const total = summary.evaluated ?? summary.total ?? data.evaluated ?? data.total ?? null;

      if (acc != null) setKPI("clay-kpi-accuracy", `${Number(acc).toFixed(1)}%`);
      else if (hit != null && total != null && total > 0) setKPI("clay-kpi-accuracy", `${((hit / total) * 100).toFixed(1)}%`);
      else setKPI("clay-kpi-accuracy", "—");
    } else {
      setKPI("clay-kpi-accuracy", "—");
    }
  } catch (e) {
    console.warn("KPI accuracy error:", e);
    setKPI("clay-kpi-accuracy", "—");
  }
}

function setKPI(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

// =====================================================
// CLAY ENGINE — PREDICT PAGE (TABLE LAYOUT)
// =====================================================

let _clayEngineInflight = false;
  
  async function loadClayEngineData() {
    if (_clayEngineInflight) {
      console.debug("[loadClayEngineData] skip: request sebelumnya masih jalan");
      return;
    }
    _clayEngineInflight = true;
    try {
      await _loadClayEngineDataInner();
    } finally {
      _clayEngineInflight = false;
    }
  }
  
  async function _loadClayEngineDataInner() {
  const tbodyPredict = document.getElementById("tbody-predict");
  const statPotensialEl = document.getElementById("stat-total-potensial");
  const statOmsetEl = document.getElementById("stat-total-omset");
  const badgeCountNormal = document.getElementById("badge-count-normal");
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

  // Bind history filter (kalau ada)
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
      tbodyPredict.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:#ffb74d;">Sesi habis atau belum login.</td></tr>`;
    }
    return;
  }

  try {
    let apiUrl = "/api/clay/predict-today";
    if (storeId) apiUrl += `?store_id=${encodeURIComponent(storeId)}`;

    const response = await fetch(apiUrl, {
      method: "GET",
      headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` }
    });

    if (response.status === 401) {
      handleUnauthorized("Predict page: token expired");
      if (tbodyPredict) {
        tbodyPredict.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:#ff5252;">🔒 Sesi berakhir. Silakan login ulang.</td></tr>`;
      }
      return;
    }

    const result = await response.json();
    if (!response.ok || result.status === "error") {
      throw new Error(result.message || result.error || "Gagal fetch data");
    }

    const predictions = Array.isArray(result.predictions) ? result.predictions : [];
    const totalOmset = predictions.reduce((s, i) => s + Number(i.est_spend || 0), 0);
    const avgScore = predictions.length > 0
      ? Math.round(predictions.reduce((s, i) => s + (Number(i.score) || 0), 0) / predictions.length)
      : null;

    if (statPotensialEl) statPotensialEl.innerText = `${predictions.length} Pelanggan`;
    if (statOmsetEl) statOmsetEl.innerText = `Rp ${totalOmset.toLocaleString("id-ID")}`;
    const statAvgScoreEl = document.getElementById("stat-avg-score");
    if (statAvgScoreEl) statAvgScoreEl.innerText = avgScore !== null ? `${avgScore}%` : "—";
    if (badgeCountNormal) badgeCountNormal.innerText = `${predictions.length} items`;

    renderPredictTable(predictions);
    bindWaButtons();

  } catch (error) {
    console.error("Clay Engine Error:", error);
    if (tbodyPredict) {
      tbodyPredict.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:20px; color:#ff5252;">Error: ${escHTML(error.message)}</td></tr>`;
    }
  }
}

// =====================================================
// HELPERS — Badge & Warna
// =====================================================

function getTagStyle(tag) {
  const colors = {
    "VIP":          { bg: "rgba(255,193,7,0.15)",  color: "#ffc107", border: "#ffc107" },
    "VVIP":         { bg: "rgba(255,193,7,0.20)",  color: "#ffb300", border: "#ffb300" },
    "Best":         { bg: "rgba(156,39,176,0.15)", color: "#ce93d8", border: "#ce93d8" },
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
// RENDER — TABLE PREDICT (9 kolom, sesuai header HTML)
// =====================================================

function renderPredictTable(items) {
  const tbody = document.getElementById("tbody-predict");
  if (!tbody) return;

  if (items.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:24px; color:#888;">Tidak ada prediksi pelanggan untuk hari ini.</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map((item, idx) => {
    const name = item.name || item.customer_name || "Pelanggan";
    const phone = item.phone || item.customer_phone || "-";
    const code = item.customer_code || "-";
    const tag = item.tag || "Reguler";
    const score = Number(item.score) || 0;
    const cycle = item.cycle_days ? `${Math.round(item.cycle_days)} hari` : "-";
    const statusNota = item.prediction_status || "active";
    const tagStyle = getTagStyle(tag);
    const scoreColor = getScoreColor(score);

    // Warna badge status nota
    let statusColor = "#28c8ff";
    if (statusNota === "Besok") statusColor = "#00E676";
    else if (statusNota === "Sekitar besok") statusColor = "#ffc107";
    else if (statusNota === "Telat") statusColor = "#ff9800";
    else if (statusNota === "active") statusColor = "#8a8a93";

    return `
      <tr style="border-bottom: 1px solid #27272a;">
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: #aaa; font-size: 0.85rem;">${idx + 1}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: #fff; font-weight: 600; font-size: 0.85rem;">${escHTML(name)}</td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a;">
          <span style="background:${tagStyle.bg}; color:${tagStyle.color}; border:1px solid ${tagStyle.border}; padding:2px 8px; border-radius:6px; font-size:0.72rem; font-weight:600;">${escHTML(tag)}</span>
        </td>
        <td style="padding: 12px 14px; border-right: 1px solid #27272a; color: ${statusColor}; font-size: 0.8rem; font-weight: 600;">${escHTML(statusNota)}</td>
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

// =====================================================
// HISTORY PREDIKSI
// =====================================================

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

function sendWhatsAppReminder(phone, name, isCarryOver = false, carryCount = 1) {
  if (!phone || phone === "-") {
    alert(`Nomor telepon untuk ${name} tidak tersedia.`);
    return;
  }

  let formattedPhone = String(phone).replace(/\D/g, "");
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
      handleUnauthorized("loadDatabaseRealData: token expired");
      if (tableBody) {
        tableBody.innerHTML = `<tr><td colspan="13" style="text-align: center; padding: 28px; color: #ff5252;">🔒 Sesi berakhir. Silakan login ulang.</td></tr>`;
      }
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

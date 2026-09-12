// Fungsi loader komponen HTML
async function loadComponent(elementId, filePath) {
  try {
    const response = await fetch(filePath);
    if (!response.ok) throw new Error(`HTTP Error ${response.status}: Gagal memuat ${filePath}`);
    const html = await response.text();
    const container = document.getElementById(elementId);
    if (container) {
      container.innerHTML = html;
    }
  } catch (error) {
    console.error(error);
    const container = document.getElementById(elementId);
    if (container) {
      container.innerHTML = `<div style="color: #ff5252; padding: 20px;">
        <h3>Gagal Memuat Komponen</h3>
        <p>${error.message}</p>
        <small>Pastikan server backend/python berjalan dan lokasi file <code>${filePath}</code> sudah benar.</small>
      </div>`;
    }
  }
}

// Inisialisasi Utama
document.addEventListener("DOMContentLoaded", async () => {
  // Load Layout Dasar
  await loadComponent("sidebar-container", "components/sidebar.html");
  await loadComponent("header-container", "components/header.html");

  // Render State Auth UI (Sidebar & Header)
  renderAuthState();

  // Load Halaman Default
  const contentArea = document.getElementById("content-area");
  if (contentArea) {
    contentArea.innerHTML = "2 OverviewSelamat datang di Dashboard Nasuha Web.";
  }

  setupEventListeners();
  setupAuthListeners();
});

function setupEventListeners() {
  // Event Listener Navigasi Global
  document.addEventListener("click", async (e) => {
    const navLink = e.target.closest(".nav-item a");
    if (!navLink) return;

    e.preventDefault();
    const pageName = navLink.getAttribute("data-page");

    // Update Judul Header
    const pageTitleEl = document.getElementById("current-page-title");
    if (pageTitleEl) pageTitleEl.innerText = pageName;

    // Update Status Class Active
    document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
    navLink.parentElement.classList.add("active");

    // Routing Komponen Halaman
    if (pageName === "Database") {
      await loadComponent("content-area", "components/database.html");
      loadDatabaseRealData();
    } else if (pageName === "Download") {
      await loadComponent("content-area", "components/download.html");
      loadDownloadData();
    } else if (pageName === "Clay Engine") {
      await loadComponent("content-area", "components/clay_engine.html");
      loadClayEngineData();
    } else {
      const contentArea = document.getElementById("content-area");
      if (contentArea) {
        contentArea.innerHTML = `2 ${pageName}Halaman ${pageName} sedang dalam pengembangan.`;
      }
    }
  });
}

// --- HANDLE AUTHENTICATION ---
function setupAuthListeners() {
  const loginModal = document.getElementById("login-modal");
  const closeBtn = document.getElementById("btn-close-login");
  const formLogin = document.getElementById("form-login");

  // Handler Klik Global pada Profil / Login / Logout
  document.addEventListener("click", (e) => {
    let target = e.target;
    if (target.nodeType === 3) target = target.parentNode;

    const profileTrigger = target.closest("#user-profile-btn, .user-profile");
    
    if (profileTrigger) {
      e.preventDefault();
      const token = localStorage.getItem("access_token");

      if (token) {
        // --- JIKA SUDAH LOGIN: TAMPILKAN KONFIRMASI LOGOUT ---
        const confirmLogout = confirm("Apakah Anda yakin ingin keluar / logout dari akun ini?");
        if (confirmLogout) {
          // Hapus token dan info user
          localStorage.removeItem("access_token");
          localStorage.removeItem("user_info");

          // Re-render UI & Muat Ulang Data
          renderAuthState();
          loadDatabaseRealData();
          alert("Anda telah berhasil logout.");
        }
      } else {
        // --- JIKA BELUM LOGIN: BUKA MODAL LOGIN ---
        if (loginModal) loginModal.classList.remove("hidden");
      }
    }
  });

  // Listener Tutup Modal
  if (closeBtn) {
    closeBtn.addEventListener("click", () => {
      if (loginModal) loginModal.classList.add("hidden");
    });
  }

  // Listener Submit Form Login
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

        if (!res.ok) {
          // Tampilkan pesan error custom dari JSON backend
          if (errorMsg) {
            errorMsg.innerText = result.error || 'Email atau password salah / tidak terdaftar';
            errorMsg.classList.remove("hidden");
            errorMsg.style.display = 'block';
          } else {
            alert(result.error || 'Email atau password salah / tidak terdaftar');
          }
          return;
        }

        // --- PERBAIKAN: Ambil token dari berbagai struktur respon backend/Supabase ---
        const token = result.access_token || (result.session && result.session.access_token);

        if (!token) {
          if (errorMsg) {
            errorMsg.innerText = "Login berhasil, namun token tidak ditemukan dari server.";
            errorMsg.classList.remove("hidden");
            errorMsg.style.display = 'block';
          } else {
            alert("Login berhasil, namun token tidak ditemukan dari server.");
          }
          return;
        }

        // Simpan Session
        localStorage.setItem("access_token", token);
        localStorage.setItem("user_info", JSON.stringify(result.user));

        if (loginModal) loginModal.classList.add("hidden");

        // Update UI secara instan tanpa reload halaman
        renderAuthState();
        loadDatabaseRealData();

      } catch (err) {
        if (errorMsg) {
          errorMsg.innerText = "Gagal terhubung ke server";
          errorMsg.classList.remove("hidden");
          errorMsg.style.display = 'block';
        }
      }
    });
  }
}

// --- RENDER DYNAMIC UI STATE BASED ON AUTH ---
function renderAuthState() {
  const token = localStorage.getItem("access_token");
  const userInfoRaw = localStorage.getItem("user_info");
  
  const headerTextGroup = document.getElementById("header-user-text");
  const headerIcon = document.getElementById("header-user-icon");
  const sidebarName = document.getElementById("sidebar-user-name");
  const sidebarAvatar = document.getElementById("sidebar-user-avatar");

  if (token && userInfoRaw) {
    const user = JSON.parse(userInfoRaw);
    // Mengambil nama depan dari email atau metadata user
    const userDisplayName = user.user_metadata?.full_name || user.email?.split("@")[0] || "Kasir Toko";

    // 1. Update Header Kanan Atas -> Ubah Login/Register jadi Nama & Logout
    if (headerTextGroup) {
      headerTextGroup.innerHTML = `
        <span class="text-login" style="color: #ffffff;">${userDisplayName}</span>
        <span class="text-register" style="color: #ff5252; font-weight: 600;">Logout</span>
      `;
    }
    if (headerIcon) headerIcon.innerText = "👨‍🍳"; // Icon profil aktif

    // 2. Update Sidebar Kiri Atas -> Tampilkan Nama User & Avatar
    if (sidebarName) sidebarName.innerText = userDisplayName;
    if (sidebarAvatar) sidebarAvatar.innerHTML = `<span style="font-size: 1.2rem;">✅</span>`;

  } else {
    // State Belum Login (Guest)
    if (headerTextGroup) {
      headerTextGroup.innerHTML = `
        <span class="text-login">Login</span>
        <span class="text-register">Register</span>
      `;
    }
    if (headerIcon) headerIcon.innerText = "🧺";

    if (sidebarName) sidebarName.innerText = "Login Your Account";
    if (sidebarAvatar) sidebarAvatar.innerHTML = `<span style="font-size: 1.2rem;">👤</span>`;
  }
}

// --- FETCH DATA ORDERS DENGAN TOKEN ---
async function loadDatabaseRealData() {
  const tableBody = document.getElementById("db-table-body");
  const totalTablesEl = document.getElementById("stat-total-tables");
  const dbStatusEl = document.getElementById("stat-db-status");

  // Ambil token JWT dari localStorage
  const token = localStorage.getItem("access_token");

  if (!token) {
    if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="13" style="color: #ffb74d; text-align: center; padding: 20px;">Silakan klik tombol <strong>Login</strong> untuk mengakses data toko.</td></tr>`;
    }
    if (dbStatusEl) {
      dbStatusEl.innerText = "Unauthorized";
      dbStatusEl.style.color = "#ffb74d";
    }
    return;
  }

  try {
    const response = await fetch("/api/transactions", {
      headers: {
        "Authorization": `Bearer ${token}`
      }
    });

    const result = await response.json();
    if (!response.ok || result.status === "error") throw new Error(result.message);

    const listData = result.data || [];

    if (totalTablesEl) totalTablesEl.innerText = `${listData.length} Orders`;
    if (dbStatusEl) {
      dbStatusEl.innerText = "Connected";
      dbStatusEl.style.color = "#00e676";
    }

    if (tableBody) {
      if (listData.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="13" style="text-align:center; padding: 20px;">Belum ada data orders untuk toko ini.</td></tr>`;
        return;
      }

      tableBody.innerHTML = listData.map(row => `
        <tr>
          <td>${row.id || '-'}</td>
          <td><strong>${row.order_number || row.nota_number || '-'}</strong></td>
          <td>${row.customer_name || '-'}</td>
          <td>${row.service_name || '-'}</td>
          <td>Rp ${Number(row.total_price || 0).toLocaleString('id-ID')}</td>
          <td><span class="badge ${row.status === 'Lunas' ? 'badge-success' : 'badge-warning'}">${row.status || 'Proses'}</span></td>
          <td>${row.payment_method || '-'}</td>
          <td>${row.created_at ? new Date(row.created_at).toLocaleDateString('id-ID') : '-'}</td>
          <td>${row.date_estimate || '-'}</td>
          <td>${row.date_paid || '-'}</td>
          <td>Rp ${Number(row.discount || 0).toLocaleString('id-ID')}</td>
          <td>${row.notes || '-'}</td>
          <td><button class="btn-sm btn-edit">Edit</button></td>
        </tr>
      `).join("");
    }

  } catch (error) {
    console.error("Database Fetch Error:", error);
    if (tableBody) {
      tableBody.innerHTML = `<tr><td colspan="13" style="color: #ff5252; text-align: center; padding: 20px;">Gagal mengambil data: ${error.message}</td></tr>`;
    }
    if (dbStatusEl) {
      dbStatusEl.innerText = "Error";
      dbStatusEl.style.color = "#ff5252";
    }
  }
}

// Definisi fungsi loadDownloadData agar nav Download tidak crash
async function loadDownloadData() {
  const container = document.getElementById("download-list-container");
  if (!container) return;
  
  try {
    const response = await fetch("/api/downloads");
    if (!response.ok) throw new Error("Gagal mengambil data rilis dari server.");

    const result = await response.json();
    if (result.status === "error") throw new Error(result.message);

    const data = result.data || [];

    if (data.length === 0) {
      container.innerHTML = `<div style="color: #888; padding: 20px;">Belum ada file aplikasi yang diunggah.</div>`;
      return;
    }

    container.innerHTML = data.map(app => `
      <div class="download-card">
        <div class="app-icon">${app.type === 'APK' ? '📱' : '💻'}</div>
        <div class="app-details">
          <h3>${app.title}</h3>
          <p class="app-meta">Versi ${app.version} • ${app.type} • ${app.size}</p>
          <p class="app-desc">${app.description || ''}</p>
        </div>
        <div class="app-action">
          <a href="${app.download_url}" target="_blank" download class="btn-primary btn-download">
            ⬇️ Download ${app.type}
          </a>
        </div>
      </div>
    `).join("");

  } catch (error) {
    console.error("Download Fetch Error:", error);
    container.innerHTML = `<div style="color: #ff5252; padding: 20px;">Gagal memuat daftar aplikasi: ${error.message}</div>`;
  }
}

// CLAY ENGINE - FETCH DATA PREDIKSI
async function loadClayEngineData() {
  const tableBody = document.getElementById("clay-table-body");
  const totalPotensialEl = document.getElementById("stat-total-potensial");
  const totalOmsetEl = document.getElementById("stat-total-omset");

  const token = localStorage.getItem("access_token");

  if (!token) {
    if (tableBody) tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 20px; color:#ffb74d;">Sesi habis. Silakan login terlebih dahulu.</td></tr>`;
    return;
  }

  try {
    const response = await fetch("/api/clay/predict-tomorrow", {
      headers: { "Authorization": `Bearer ${token}` }
    });

    const result = await response.json();
    
    if (!response.ok || result.status === "error") {
      const errMsg = typeof result === 'object' ? (result.message || JSON.stringify(result)) : result;
      throw new Error(errMsg);
    }

    const predictions = Array.isArray(result.predictions) ? result.predictions : [];

    if (predictions.length === 0) {
      if (totalPotensialEl) totalPotensialEl.innerText = "0 Pelanggan";
      if (totalOmsetEl) totalOmsetEl.innerText = "Rp 0";
      if (tableBody) tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 20px; color:#888;">Belum ada data riwayat yang mencukupi untuk diprediksi hari ini</td></tr>`;
      return;
    }

    let totalOmset = 0;
    predictions.forEach(item => {
      totalOmset += Number(item.est_spend || 0);
    });

    if (totalPotensialEl) totalPotensialEl.innerText = `${predictions.length} Pelanggan`;
    if (totalOmsetEl) totalOmsetEl.innerText = `Rp ${totalOmset.toLocaleString('id-ID')}`;

    if (tableBody) {
      tableBody.innerHTML = predictions.map(item => {
        const tagColor = item.tag === 'VIP' ? '#ffc107' : (item.tag === 'Resiko Churn' ? '#ff5252' : '#00E676');
        const scoreColor = item.score >= 80 ? '#00E676' : (item.score >= 55 ? '#ffc107' : '#ff9800');

        return `
          <tr style="border-bottom: 1px solid rgba(255,255,255,0.05); font-size: 0.85rem;">
            <td style="padding: 12px;">
              <strong style="color: #fff; display: block;">${item.name || '-'}</strong>
              <span style="font-size: 0.75rem; color: ${tagColor}; font-weight: 600;">${item.tag}</span>
            </td>
            <td style="padding: 12px; font-weight: bold; color: ${scoreColor};">${item.score}%</td>
            <td style="padding: 12px; color: #ccc;">${item.reason || '-'}</td>
            <td style="padding: 12px; font-weight: bold; color: #00E676;">Rp ${Number(item.est_spend || 0).toLocaleString('id-ID')}</td>
            <td style="padding: 12px; color: #ccc;">${item.favorite_service || '-'}</td>
            <td style="padding: 12px; color: #28c8ff; font-weight: bold;">${item.total_tx} Order</td>
            <td style="padding: 12px; color: #ccc;">${item.contribution}</td>
            <td style="padding: 12px; text-align: center;">
              <button onclick="sendWhatsAppReminder('${item.phone || ''}', '${item.name || ''}')" 
                      style="background: rgba(0, 230, 118, 0.15); border: 1px solid rgba(0, 230, 118, 0.4); color: #00E676; padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 0.75rem; font-weight: bold;">
                💬 WA
              </button>
            </td>
          </tr>
        `;
      }).join("");
    }

  } catch (error) {
    console.error("Clay Engine Error:", error);
    if (tableBody) tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 20px; color:#ff5252;">Error: ${error.message}</td></tr>`;
  }
}

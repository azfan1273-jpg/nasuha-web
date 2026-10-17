// ==========================================
// AUTH.JS - Mengatur User & Sesi
// ==========================================

const TOKEN_KEY = 'access_token';

document.addEventListener('DOMContentLoaded', () => {
  hydrateUserData();
  setupLogout();
});

// 1. Ambil Data User & Update Header
async function hydrateUserData() {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) {
    // Kalau gak ada token, tendang ke landing page
    window.location.href = 'landing.html';
    return;
  }

  try {
    const res = await fetch('/api/me', {
      headers: { 'Authorization': `Bearer ${token}`, 'Accept': 'application/json' }
    });
    
    if (!res.ok) throw new Error('Token expired');
    
    const data = await res.json();

    // TAMBAHKAN BARIS INI BIAR NAMA USER BISA DIPAKE DI UI.JS
    localStorage.setItem('user_info', JSON.stringify(data)); 
    
    // Fallback jika data backend kurang lengkap
    const orgName = data.orgName || data.nama_toko || (data.email ? data.email.split('@')[0] + "'s Org" : "Nasuha Org");
    const fullName = data.fullName || data.name || "User";

    // Update DOM
    const orgNameEl = document.getElementById('header-org-name');
    const avatarEl = document.getElementById('header-user-avatar');

    if (orgNameEl) orgNameEl.textContent = orgName;
    if (avatarEl) avatarEl.textContent = fullName.charAt(0).toUpperCase();

  } catch (error) {
    console.warn("Auth error:", error.message);
    // Hapus token jika expired dan redirect
    localStorage.removeItem(TOKEN_KEY);
    window.location.href = 'landing.html';
  }
}

// 2. Logout
function setupLogout() {
  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) {
    btnLogout.addEventListener('click', () => {
      if (confirm('Apakah Anda yakin ingin logout?')) {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem('store_id');
        localStorage.removeItem('user_info');
        window.location.href = 'landing.html';
      }
    });
  }
}
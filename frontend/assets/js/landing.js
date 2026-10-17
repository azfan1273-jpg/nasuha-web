// ============================================================
// API BASE URL
// ============================================================
const API_BASE = 'http://localhost:8081';

// ============================================================
// LANDING — Auth state + Login modal
// ============================================================

(function () {
  const authBtn    = document.getElementById('landing-auth-btn');
  const ctaBtn     = document.getElementById('landing-cta-btn');
  const avatarEl   = document.getElementById('landing-avatar');
  const loginModal = document.getElementById('login-modal');
  const closeBtn   = document.getElementById('btn-close-login');
  const formLogin  = document.getElementById('form-login');
  const errorMsg   = document.getElementById('login-error-msg');

  // ---------- RENDER AUTH STATE ----------
  function renderAuthState() {
    const token = localStorage.getItem('access_token');
    const userInfoRaw = localStorage.getItem('user_info');

    if (token) {
      // === SUDAH LOGIN → tombol jadi "Dashboard" ===
      let displayName = 'User';
      let initial = '👤';
      try {
        if (userInfoRaw) {
          const info = JSON.parse(userInfoRaw);
          displayName = info.nama_pegawai || info.name || info.email || 'User';
          initial = (displayName.charAt(0) || 'U').toUpperCase();
        }
      } catch (_) {}

      authBtn.textContent = 'Dashboard';
      authBtn.dataset.authState = 'user';
      authBtn.title = `Masuk sebagai ${displayName}`;
      if (avatarEl) avatarEl.textContent = initial;

    } else {
      // === BELUM LOGIN → "Login Your Account" ===
      authBtn.textContent = 'Login Your Account';
      authBtn.dataset.authState = 'guest';
      authBtn.title = 'Login ke akun Anda';
      if (avatarEl) avatarEl.textContent = '🧺';
    }
  }

  // ---------- MODAL ----------
  function openLoginModal() {
    if (errorMsg) { errorMsg.classList.add('hidden'); errorMsg.textContent = ''; }
    if (formLogin) formLogin.reset();
    if (loginModal) loginModal.classList.remove('hidden');
    setTimeout(() => {
      const emailInput = document.getElementById('login-email');
      if (emailInput) emailInput.focus();
    }, 50);
  }

  function closeLoginModal() {
    if (loginModal) loginModal.classList.add('hidden');
  }

  // ---------- KLIK TOMBOL AUTH ----------
  if (authBtn) {
    authBtn.addEventListener('click', () => {
      const state = authBtn.dataset.authState;
      if (state === 'user') {
        window.location.href = 'dashboard.html'; // ← udah login, masuk ke akun/dashboard
      } else {
        openLoginModal();                    // ← belum login, buka modal
      }
    });
  }

  // ---------- KLIK "GET STARTED" (hero CTA) ----------
if (ctaBtn) {
  ctaBtn.addEventListener('click', () => {
    const token = localStorage.getItem('access_token');
    if (token) {
      // Sudah login → langsung ke workspace
      window.location.href = 'akun.html';
    } else {
      // Belum login → buka modal login
      openLoginModal();
    }
  });
}

  // ---------- KLIK AVATAR (logout) ----------
  if (avatarEl) {
    avatarEl.addEventListener('click', () => {
      const token = localStorage.getItem('access_token');
      if (token) {
        if (confirm('Yakin mau logout?')) {
          localStorage.removeItem('access_token');
          localStorage.removeItem('store_id');
          localStorage.removeItem('user_info');
          renderAuthState();
        }
      } else {
        openLoginModal();
      }
    });
  }

  // ---------- CLOSE MODAL ----------
  if (closeBtn) closeBtn.addEventListener('click', closeLoginModal);

  if (loginModal) {
    loginModal.addEventListener('click', (e) => {
      if (e.target === loginModal) closeLoginModal();
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && loginModal && !loginModal.classList.contains('hidden')) {
      closeLoginModal();
    }
  });

  // ---------- SUBMIT LOGIN ----------
  if (formLogin) {
    formLogin.addEventListener('submit', async (e) => {
      e.preventDefault();
      if (errorMsg) errorMsg.classList.add('hidden');

      const email    = document.getElementById('login-email').value.trim();
      const password = document.getElementById('login-password').value;
      const submitBtn = formLogin.querySelector('button[type="submit"]');

      if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Logging in...'; }

      try {
        const res = await fetch(`${API_BASE}/api/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });

        // Baca response sebagai text dulu, baru coba parse JSON
        const rawText = await res.text();
        let result;
        try {
          result = JSON.parse(rawText);
        } catch (_) {
          // Bukan JSON → tampilkan error yang lebih jelas
          console.error('[login] Non-JSON response:', res.status, rawText.slice(0, 300));
          throw new Error(
            `Server error (${res.status}): ${rawText.slice(0, 100) || 'Empty response'}`
          );
        }

        if (result.access_token) localStorage.setItem('access_token', result.access_token);
        if (result.store_id)     localStorage.setItem('store_id', result.store_id);
        if (result.user)         localStorage.setItem('user_info', JSON.stringify(result.user));

        closeLoginModal();
        renderAuthState();

        // Auto-redirect ke dashboard setelah login (uncomment kalau mau):
        // window.location.href = 'akun.html';

      } catch (err) {
        if (errorMsg) {
          errorMsg.textContent = err.message;
          errorMsg.classList.remove('hidden');
        }
      } finally {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = 'Login'; }
      }
    });
  }

  // ---------- INIT ----------
  renderAuthState();
})();
// ============================================================
// USER CONTEXT — Ambil data user dari backend FastAPI
// Key token: 'access_token' (sesuai app.js)
// ============================================================

(function (global) {
  'use strict';

  const CACHE_KEY = 'nasuha_user_ctx';
  const CACHE_TTL = 5 * 60 * 1000; // 5 menit
  const TOKEN_KEY = 'access_token'; 

  // ------------------------------------------------------------
  // Fetch /api/me
  // ------------------------------------------------------------
  async function fetchFromAPI() {
    const token = localStorage.getItem(TOKEN_KEY);
    if (!token) {
      console.warn('[UserContext] Token gak ada, skip fetch');
      return null;
    }

    try {
      const res = await fetch('/api/me', {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
      });

      if (res.status === 401) {
        console.warn('[UserContext] Token expired');
        return null;
      }

      if (!res.ok) {
        console.warn('[UserContext] Status:', res.status);
        return null;
      }

      const data = await res.json();
      return {
        userId: data.userId,
        email: data.email,
        fullName: data.fullName || data.name || "User", // Fallback
        role: data.role,
        orgName: data.orgName || data.nama_toko || "Nasuha Org", // Fallback
        orgCode: data.orgCode,
        storeId: data.storeId,
        fetchedAt: Date.now(),
      };
    } catch (e) {
      console.error('[UserContext] Fetch error:', e.message);
      return null;
    }
  }

  // ------------------------------------------------------------
  // Cache
  // ------------------------------------------------------------
  function readCache() {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      if (!raw) return null;
      const data = JSON.parse(raw);
      if (Date.now() - data.fetchedAt > CACHE_TTL) {
        localStorage.removeItem(CACHE_KEY);
        return null;
      }
      return data;
    } catch { return null; }
  }

  function writeCache(data) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(data)); } catch {}
  }

  // ------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------
  const UserContext = {
    async get(force = false) {
      if (!force) {
        const c = readCache();
        if (c) return c;
      }
      const f = await fetchFromAPI();
      if (f) writeCache(f);
      return f;
    },

    getSync() { return readCache(); },

    async hydrate(root = document) {
      const user = await this.get();
      if (!user) {
        console.warn('[UserContext] Gak ada data user, skip hydrate');
        return;
      }

      // 1. TARGET SPESIFIK: Isi Nama Org di Header
      const orgNameEl = document.getElementById('header-org-name');
      if (orgNameEl) {
        orgNameEl.textContent = user.orgName;
      }

      // 2. TARGET SPESIFIK: Isi Avatar (Huruf Pertama)
      const avatarEl = document.getElementById('header-user-avatar');
      if (avatarEl) {
        avatarEl.textContent = user.fullName.charAt(0).toUpperCase();
      }

      // 3. FALLBACK: Masih mendukung atribut data-user (kalau lu butuh di tempat lain)
      root.querySelectorAll('[data-user]').forEach(el => {
        const key = el.dataset.user;
        if (user[key] != null) {
          el.textContent = user[key];
        }
      });
      
      console.log('[UserContext] Data berhasil dimuat ke UI ✅');
    },

    clearCache() {
      localStorage.removeItem(CACHE_KEY);
    },
  };

  global.UserContext = UserContext;

  // Auto jalan pas DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => UserContext.hydrate());
  } else {
    UserContext.hydrate();
  }

})(window);
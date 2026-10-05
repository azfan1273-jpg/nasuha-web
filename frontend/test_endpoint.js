// ==== 1. Cari token di mana-mana ====
function findToken() {
  const candidates = [
    'access_token', 'sb-access-token', 'token',
    'nasuha_session', 'session', 'auth',
  ];

  for (const key of candidates) {
    const v = localStorage.getItem(key);
    if (!v) continue;
    try {
      const parsed = JSON.parse(v);
      if (parsed.access_token) return parsed.access_token;
      if (parsed.token) return parsed.token;
    } catch (e) {
      if (v.startsWith('eyJ')) return v;
    }
  }

  // Fallback: scan semua key
  for (let i = 0; i < localStorage.length; i++) {
    const k = localStorage.key(i);
    const v = localStorage.getItem(k);
    if (v && v.startsWith('eyJ') && v.length > 100) return v;
    try {
      const parsed = JSON.parse(v);
      if (parsed && parsed.access_token) return parsed.access_token;
    } catch (e) {}
  }
  return null;
}

// ==== 2. Tampilkan semua key localStorage ====
function showKeys() {
  const lines = [];
  if (localStorage.length === 0) {
    lines.push('(kosong — belum login?)');
  } else {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      let v = localStorage.getItem(k) || '';
      const preview = v.length > 80 ? v.slice(0, 80) + '…' : v;
      lines.push(`• ${k}\n  → ${preview}`);
    }
  }
  document.getElementById('ls-keys').textContent = lines.join('\n\n');
}

// ==== 3. Tampilkan status token ====
function showTokenStatus() {
  const token = findToken();
  const el = document.getElementById('token-status');
  if (!token) {
    el.innerHTML = '<span class="err">❌ Token TIDAK ditemukan</span>';
    return null;
  }
  el.innerHTML = `<span class="ok">✅ Token ditemukan</span> (${token.length} chars)<br><small style="color:#666">${token.slice(0, 50)}…</small>`;
  return token;
}

// ==== 4. Hit endpoint ====
async function hit(type) {
  const out = document.getElementById('output');
  out.textContent = '⏳ Loading...';

  const token = findToken();
  if (!token) {
    out.textContent = '❌ Token kosong. Cek box "Status Token" di atas.';
    return;
  }

  const url = type === 'overview'
    ? '/api/clay/overview'
    : `/api/clay/history/accuracy?period=${type}`;

  try {
    const res = await fetch(url, {
      headers: { 'Authorization': 'Bearer ' + token }
    });
    const text = await res.text();
    let pretty;
    try {
      pretty = JSON.stringify(JSON.parse(text), null, 2);
    } catch (e) {
      pretty = text;
    }
    out.textContent = `HTTP ${res.status}\n\n${pretty}`;
  } catch (e) {
    out.textContent = `❌ Error: ${e.message}`;
  }
}

// ==== 5. Auto-run waktu page load ====
(function init() {
  showKeys();
  const token = showTokenStatus();
  if (token) {
    hit('overview');
  } else {
    document.getElementById('output').textContent =
      '⚠️ Belum ada token. Silakan login dulu di tab lain, lalu refresh halaman ini.';
  }

  // Bind tombol
  document.querySelectorAll('button[data-endpoint]').forEach(btn => {
    btn.addEventListener('click', () => hit(btn.dataset.endpoint));
  });
})();

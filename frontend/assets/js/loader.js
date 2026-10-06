// ============================================================
// Loader — conditional load debug console
// Dipisah dari index.html karena CSP block inline script
// ============================================================
(function () {
  const host = location.hostname;
  const params = new URLSearchParams(location.search);

  // Skip di production
  const isProd = host.endsWith('.vercel.app')
              || host === 'nasuha-web.com'
              || host === 'www.nasuha-web.com';

  // Force debug: tambah ?debug=1 di URL
  const forceDebug = params.get('debug') === '1';

  if (!isProd || forceDebug) {
    const s = document.createElement('script');
    s.src = 'assets/js/debug.js';
    document.body.appendChild(s);
    console.log('[loader] Debug Console loaded (host=' + host + ')');
  }
})();

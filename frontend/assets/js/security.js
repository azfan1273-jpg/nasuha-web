// Utilitas keamanan frontend: escaping HTML untuk mencegah DOM XSS.
(function () {
  window.escHTML = function (value) {
    if (value === null || value === undefined) return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  // Validasi URL download: hanya http/https, blokir javascript:, data:, dll.
  window.safeUrl = function (url) {
    try {
      const u = new URL(String(url), window.location.origin);
      return (u.protocol === 'http:' || u.protocol === 'https:') ? u.href : '#';
    } catch (e) {
      return '#';
    }
  };
})();

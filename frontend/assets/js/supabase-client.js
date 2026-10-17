// ============================================================
// SUPABASE CLIENT — Inisialisasi sekali, dipakai di semua halaman
// ============================================================
(function (global) {
  // 🔽 GANTI dengan URL & anon key Supabase lo
  const SUPABASE_URL  = 'https://xxxxx.supabase.co';
  const SUPABASE_ANON = 'eyJhbGciOiJIUzI1NiIsInR5cCI6...'; 

  // Pastikan library supabase-js udah ke-load dari CDN
  if (!global.supabase || !global.supabase.createClient) {
    console.error('[Supabase] Library belum di-load. Tambahkan <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script> di <head>');
    return;
  }

  global.supabaseClient = global.supabase.createClient(SUPABASE_URL, SUPABASE_ANON);
  // Alias biar kompatibel
  global.supabase = global.supabaseClient;

  console.log('[Supabase] Client ready ✅');
})(window);
/**
 * Debug Console — panel floating untuk lihat log tanpa DevTools.
 *
 * FITUR:
 *  - Tombol 🐛 → toggle panel
 *  - Auto-log semua fetch request + response
 *  - Auto-cek DOM element Clay Engine (tbody-predict, tbody-carry, dll)
 *  - Command bar (mini-console) → ketik JS command di panel
 *  - Tombol "CEK DOM" → verifikasi HTML/JS baru
 */
(function () {
  let panel, logContainer, isOpen = false, inputBar;

  // =====================================================
  // INIT PANEL
  // =====================================================
  function init() {
    // ---- Toggle Button ----
    const btn = document.createElement("button");
    btn.id = "dbg-toggle";
    btn.textContent = "🐛";
    btn.setAttribute("aria-label", "Debug Console");
    btn.style.cssText = `
      position: fixed;
      bottom: 16px;
      right: 16px;
      width: 44px;
      height: 44px;
      border-radius: 50%;
      background: #0088ff;
      color: white;
      border: none;
      font-size: 1.2rem;
      cursor: pointer;
      z-index: 99998;
      box-shadow: 0 4px 12px rgba(0,0,0,0.4);
      display: flex;
      align-items: center;
      justify-content: center;
    `;
    btn.onclick = toggle;
    document.body.appendChild(btn);

    // ---- Panel ----
    panel = document.createElement("div");
    panel.id = "dbg-panel";
    panel.style.cssText = `
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      height: 65vh;
      background: #0a0a0c;
      border-top: 2px solid #0088ff;
      z-index: 99999;
      display: none;
      flex-direction: column;
      font-family: 'Courier New', monospace;
      font-size: 0.75rem;
    `;

    // ---- Header ----
    const header = document.createElement("div");
    header.style.cssText = `
      padding: 8px 12px;
      background: #1c1c1e;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #333;
      flex-shrink: 0;
      gap: 8px;
      flex-wrap: wrap;
    `;
    header.innerHTML = `
      <strong style="color: #28c8ff;">Debug Console</strong>
      <div style="display: flex; gap: 6px; flex-wrap: wrap;">
        <button id="dbg-check-dom" style="background: #28c8ff; color: #000; border: none; padding: 4px 10px; border-radius: 4px; font-size: 0.7rem; cursor: pointer; font-weight: 600;">🔍 CEK DOM</button>
        <button id="dbg-check-js" style="background: #00E676; color: #000; border: none; padding: 4px 10px; border-radius: 4px; font-size: 0.7rem; cursor: pointer; font-weight: 600;">⚙️ CEK JS</button>
        <button id="dbg-clear" style="background: #ff5252; color: white; border: none; padding: 4px 10px; border-radius: 4px; font-size: 0.7rem; cursor: pointer;">Clear</button>
        <button id="dbg-close" style="background: #333; color: white; border: none; padding: 4px 10px; border-radius: 4px; font-size: 0.7rem; cursor: pointer;">Close</button>
      </div>
    `;
    panel.appendChild(header);

    // ---- Log container ----
    logContainer = document.createElement("div");
    logContainer.style.cssText = `
      flex: 1;
      overflow-y: auto;
      padding: 8px 12px;
      color: #e5e5e5;
    `;
    panel.appendChild(logContainer);

    // ---- Input bar (mini-console) ----
    inputBar = document.createElement("div");
    inputBar.style.cssText = `
      display: flex;
      border-top: 1px solid #333;
      background: #141416;
      flex-shrink: 0;
    `;
    inputBar.innerHTML = `
      <span style="padding: 8px 10px; color: #28c8ff; font-weight: 700;">&gt;</span>
      <input id="dbg-input" type="text" placeholder="ketik JS command di sini... (Enter untuk run)"
        style="flex: 1; background: transparent; border: none; outline: none; color: #e5e5e5; font-family: 'Courier New', monospace; font-size: 0.75rem; padding: 8px 0;" />
      <button id="dbg-run" style="background: #0088ff; color: white; border: none; padding: 0 14px; font-size: 0.7rem; cursor: pointer; font-weight: 600;">RUN</button>
    `;
    panel.appendChild(inputBar);

    document.body.appendChild(panel);

    // ---- Bind buttons ----
    document.getElementById("dbg-close").onclick = toggle;
    document.getElementById("dbg-clear").onclick = () => { logContainer.innerHTML = ""; };
    document.getElementById("dbg-check-dom").onclick = runDOMCheck;
    document.getElementById("dbg-check-js").onclick = runJSCheck;

    // ---- Bind input bar ----
    const input = document.getElementById("dbg-input");
    const runBtn = document.getElementById("dbg-run");

    const runCommand = () => {
      const code = input.value.trim();
      if (!code) return;
      dbgLog(`> ${code}`, "info");
      input.value = "";
      try {
        // eslint-disable-next-line no-eval
        const result = eval(code);
        let display;
        try {
          if (result === undefined) display = "undefined";
          else if (result === null) display = "null";
          else if (typeof result === "object") display = JSON.stringify(result, null, 2);
          else display = String(result);
        } catch (_) {
          display = String(result);
        }
        dbgLog(display, "success");
      } catch (err) {
        dbgLog(`✗ ERROR: ${err.message}`, "error");
      }
    };

    runBtn.onclick = runCommand;
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        runCommand();
      }
    });

    // ---- Banner ----
    dbgLog("Debug Console aktif. Tombol 🐛 buat buka/tutup.", "info");
    dbgLog("Gunakan tombol [🔍 CEK DOM] & [⚙️ CEK JS] untuk verifikasi.", "info");
    dbgLog("Atau ketik command JS di bar bawah (contoh: typeof renderPredictTable)", "info");
  }

  // =====================================================
  // TOGGLE
  // =====================================================
  function toggle() {
    isOpen = !isOpen;
    panel.style.display = isOpen ? "flex" : "none";
  }

  // =====================================================
  // LOG HELPER
  // =====================================================
  function formatTime() {
    const d = new Date();
    return d.toTimeString().substring(0, 8);
  }

  function dbgLog(msg, type = "info") {
    const color = {
      info: "#e5e5e5",
      success: "#00e676",
      warn: "#ffc107",
      error: "#ff5252",
      data: "#28c8ff",
      bold: "#ffffff",
    }[type] || "#e5e5e5";

    if (!logContainer) {
      console.log(`[dbg] ${msg}`);
      return;
    }

    const line = document.createElement("div");
    line.style.cssText = `color: ${color}; margin-bottom: 4px; word-break: break-word; white-space: pre-wrap;`;
    if (type === "bold") line.style.fontWeight = "700";
    line.textContent = `[${formatTime()}] ${msg}`;
    logContainer.appendChild(line);
    logContainer.scrollTop = logContainer.scrollHeight;

    while (logContainer.children.length > 500) {
      logContainer.removeChild(logContainer.firstChild);
    }
  }

  window.dbgLog = dbgLog;

  // =====================================================
  // DIAGNOSTIC — CEK DOM
  // =====================================================
  function runDOMCheck() {
    dbgLog("──────── CEK DOM ────────", "bold");

    // Cek halaman aktif
    const isClayHome = !!document.getElementById("clay-greeting");
    const isClayEngine = !!document.getElementById("tbody-predict");

    dbgLog(`Halaman aktif: ${isClayHome ? "🏠 Clay Home" : isClayEngine ? "🔮 Clay Engine (Predict)" : "❓ Lainnya"}`, "data");

    // Cek elemen Clay Engine baru
    const checks = [
      { id: "tbody-predict",       label: "tbody-predict" },
      { id: "tbody-carry",         label: "tbody-carry" },
      { id: "tbody-history",       label: "tbody-history" },
      { id: "stat-total-potensial", label: "KPI Normal" },
      { id: "stat-total-carry-over",label: "KPI Carry" },
      { id: "stat-total-omset",    label: "KPI Omset" },
      { id: "btn-refresh-clay",    label: "Tombol Refresh" },
    ];

    let foundCount = 0;
    checks.forEach(c => {
      const el = document.getElementById(c.id);
      if (el) {
        foundCount++;
        dbgLog(`✅ ${c.label} — OK`, "success");
      } else {
        dbgLog(`❌ ${c.label} — TIDAK DITEMUKAN`, "error");
      }
    });

    // Cek elemen LAMA (yang seharusnya udah nggak ada)
    dbgLog("──── Elemen Lama (harusnya ❌) ────", "warn");
    const oldChecks = [
      { id: "container-predict-tomorrow", label: "container-predict-tomorrow (LAMA)" },
      { id: "container-carry-over",       label: "container-carry-over (LAMA)" },
    ];
    oldChecks.forEach(c => {
      const el = document.getElementById(c.id);
      if (el) {
        dbgLog(`⚠️ ${c.label} — MASIH ADA (HTML lama belum diganti!)`, "error");
      } else {
        dbgLog(`✅ ${c.label} — OK (tidak ada)`, "success");
      }
    });

    dbgLog(`──────── RINGKASAN ────────`, "bold");
    dbgLog(`Total elemen baru ditemukan: ${foundCount}/${checks.length}`, foundCount === checks.length ? "success" : "warn");

    if (foundCount === checks.length) {
      dbgLog("✅ HTML BARU — Sudah ke-load dengan benar!", "success");
    } else {
      dbgLog("❌ HTML LAMA atau HTML baru belum di-save", "error");
      dbgLog("💡 Solusi: replace total file components/clay_engine.html", "warn");
    }
  }

  // =====================================================
  // DIAGNOSTIC — CEK JS
  // =====================================================
  function runJSCheck() {
    dbgLog("──────── CEK JS ────────", "bold");

    const functions = [
      { name: "renderPredictTable",    label: "renderPredictTable (baru)" },
      { name: "renderCarryOverTable",  label: "renderCarryOverTable (baru)" },
      { name: "loadClayHistory",       label: "loadClayHistory (baru)" },
      { name: "bindWaButtons",         label: "bindWaButtons (baru)" },
      { name: "loadClayEngineData",    label: "loadClayEngineData" },
      { name: "loadClayHome",          label: "loadClayHome" },
      { name: "createCustomerCard",    label: "createCustomerCard (LAMA - harusnya ❌)" },
    ];

    functions.forEach(f => {
      const type = typeof window[f.name];
      if (type === "function") {
        if (f.name === "createCustomerCard") {
          dbgLog(`⚠️ ${f.label} — MASIH ADA (harusnya dihapus!)`, "error");
        } else {
          dbgLog(`✅ ${f.label} — OK`, "success");
        }
      } else {
        if (f.name === "createCustomerCard") {
          dbgLog(`✅ ${f.label} — OK (tidak ada)`, "success");
        } else {
          dbgLog(`❌ ${f.label} — TIDAK ADA`, "error");
        }
      }
    });

    dbgLog("──────── SELESAI ────────", "bold");
  }

  // =====================================================
  // PATCH window.fetch — auto-log request/response
  // =====================================================
  const _origFetch = window.fetch;
  window.fetch = async function (...args) {
    const url = String(args[0]);
    const opts = args[1] || {};
    const method = (opts.method || "GET").toUpperCase();

    const isAsset = /\.(css|js|png|jpg|jpeg|svg|ico|woff2?)(\?|$)/i.test(url);
    if (!isAsset) dbgLog(`→ ${method} ${url}`, "info");

    try {
      const res = await _origFetch.apply(this, args);

      if (!isAsset) dbgLog(`← ${res.status} ${url}`, res.ok ? "success" : "error");

      // Khusus clay endpoint: log metadata
      if (url.includes("predict-tomorrow") && res.ok) {
        const clone = res.clone();
        try {
          const data = await clone.json();
          const meta = data.metadata || {};

          dbgLog(`──────── CLAY METADATA ────────`, "data");
          dbgLog(`🌏 timezone       : ${meta.timezone || "(kosong)"}`, "data");
          dbgLog(`🕐 now_local      : ${meta.now_local || "-"}`, "data");
          dbgLog(`📅 prediction_date: ${meta.prediction_date || "-"}`, "data");
          dbgLog(`👥 customers      : ${meta.total_customers || 0}`, "data");

          const skipped = meta.skipped || [];
          if (skipped.length > 0) {
            dbgLog(`──────── SKIPPED (${skipped.length}) ────────`, "warn");
            skipped.slice(0, 5).forEach(s => dbgLog(`🚫 ${s.name}: ${s.reason}`, "warn"));
            if (skipped.length > 5) dbgLog(`... dan ${skipped.length - 5} lainnya`, "warn");
          }

          const preds = data.predictions || [];
          if (preds.length > 0) {
            dbgLog(`──────── PREDICTIONS (${preds.length}) ────────`, "success");
            preds.forEach(p => {
              dbgLog(`✅ ${p.name} · ${p.score}% · pred ${p.prediction_date}`, "success");
            });
          }

          const carry = data.carry_over || [];
          if (carry.length > 0) {
            dbgLog(`──────── CARRY OVER (${carry.length}) ────────`, "warn");
            carry.forEach(c => {
              dbgLog(`🚨 ${c.name} · telat ${c.carry_over_count || 1}x · ${c.score}%`, "warn");
            });
          }
        } catch (e) {
          dbgLog(`⚠ gagal parse JSON: ${e.message}`, "warn");
        }
      }

      return res;
    } catch (err) {
      dbgLog(`✗ NETWORK ERROR ${url}: ${err.message}`, "error");
      throw err;
    }
  };

  // =====================================================
  // AUTO-DIAGNOSTIC saat halaman Clay Engine render
  // =====================================================
  function autoCheckClayEngine() {
    // Cek tiap 500ms selama 5 detik, apakah clay engine page udah ke-render
    let attempts = 0;
    const interval = setInterval(() => {
      attempts++;
      const tbodyPredict = document.getElementById("tbody-predict");
      if (tbodyPredict) {
        clearInterval(interval);
        dbgLog("🎯 Halaman Clay Engine terdeteksi. Menjalankan auto-check...", "data");
        setTimeout(() => {
          runDOMCheck();
          runJSCheck();
        }, 1000);
      }
      if (attempts > 20) clearInterval(interval);
    }, 500);
  }

  // =====================================================
  // BOOT
  // =====================================================
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      init();
      autoCheckClayEngine();
    });
  } else {
    init();
    autoCheckClayEngine();
  }
})();

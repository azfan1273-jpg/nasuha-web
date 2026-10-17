// ============================================================
// AKUN — Sidebar toggle + page routing (with inline fallback)
// ============================================================

(function () {
  const SIDEBAR_KEY = 'akun_sidebar_expanded';
  const PAGE_KEY    = 'akun_active_page';

  const sidebarEl = document.getElementById('akun-sidebar');
  const toggleBtn = document.getElementById('sidebar-toggle');
  const contentEl = document.getElementById('akun-content');
  const navItems  = document.querySelectorAll('.akun-nav-item[data-page]');

  // ---------- INLINE FALLBACK HTML ----------
  // Dipakai kalau fetch ke components/akun/*.html gagal
  // (contoh: dibuka lewat file:// atau folder belum ada)
  const INLINE_HTML = {
    projects: `
      <div class="projects-page">
        <div class="page-header"><h1>Projects</h1></div>
        <div class="filter-bar">
          <div class="filter-left">
            <input type="text" class="filter-search" placeholder="Search for a project" />
            <button class="filter-chip">Status <span class="chev">▾</span></button>
            <button class="filter-chip">Sorted by name <span class="chev">▾</span></button>
          </div>
          <div class="filter-right">
            <button class="view-toggle" title="Grid view">▦</button>
            <button class="view-toggle" title="List view">☰</button>
            <button class="btn-primary">+ New project</button>
          </div>
        </div>
        <div class="projects-grid">
          <a href="dashboard.html" class="project-card">
            <div class="project-card-header">
              <span class="project-card-name">Nasuha</span>
              <button class="project-menu" onclick="event.preventDefault();">⋮</button>
            </div>
            <span class="project-region">ap-southeast-1</span>
            <span class="project-size">NANO</span>
          </a>
        </div>
        <div class="usage-section">
          <div class="usage-header">
            <div>
              <h2>Free plan usage</h2>
              <p>Current billing cycle</p>
            </div>
            <button class="btn-secondary">Upgrade to Pro</button>
          </div>
          <div class="usage-list">
            <div class="usage-item"><span class="usage-dot"></span><span class="usage-label">Egress</span><span class="usage-value">0.06 / 5 GB</span></div>
            <div class="usage-item"><span class="usage-dot"></span><span class="usage-label">Database size</span><span class="usage-value">31 / 500 MB</span></div>
            <div class="usage-item"><span class="usage-dot"></span><span class="usage-label">Monthly active users</span><span class="usage-value">5 / 50,000</span></div>
            <div class="usage-item"><span class="usage-dot"></span><span class="usage-label">File storage</span><span class="usage-value">0.03 / 1 GB</span></div>
            <div class="usage-item"><span class="usage-dot"></span><span class="usage-label">Log Ingestion</span><span class="usage-value">0.07 / 1 GB</span></div>
            <div class="usage-item"><span class="usage-dot"></span><span class="usage-label">Log Query</span><span class="usage-value">14.0 / 100 GB</span></div>
          </div>
        </div>
      </div>
    `,
    team: `
      <div class="team-page">
        <div class="page-header">
          <h1>Team</h1>
          <p class="page-subtitle">Manage team members and invitations</p>
        </div>
        <div class="filter-bar">
          <div class="filter-left">
            <input type="text" class="filter-search" placeholder="Filter members" />
            <button class="filter-chip">MFA status <span class="chev">▾</span></button>
            <button class="filter-chip">Roles <span class="chev">▾</span></button>
          </div>
          <div class="filter-right">
            <button class="btn-secondary">📖 Docs</button>
            <button class="btn-primary">Invite members</button>
          </div>
        </div>
        <div class="team-table-card">
          <table class="team-table">
            <thead>
              <tr>
                <th>Member</th>
                <th class="col-mfa">MFA</th>
                <th class="col-role">Role</th>
                <th class="col-action"></th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>
                  <div class="member-cell">
                    <span class="member-avatar">A</span>
                    <span class="member-email">azfanl273@gmail.com</span>
                    <span class="member-you">you</span>
                  </div>
                </td>
                <td class="col-mfa center"><button class="mfa-btn">✕</button></td>
                <td class="col-role">Owner</td>
                <td class="col-action right"><button class="btn-secondary btn-sm">Leave team</button></td>
              </tr>
            </tbody>
          </table>
          <div class="team-footer"><span class="team-count">1 member</span></div>
        </div>
      </div>
    `,
    settings: `
      <div class="settings-page">
        <div class="page-header">
          <h1>Settings</h1>
          <p class="page-subtitle">Configure your organization and account preferences</p>
        </div>
        <div class="settings-section">
          <h2>Organization</h2>
          <p>General information about your organization.</p>
          <button class="btn-secondary">Edit organization</button>
        </div>
        <div class="settings-section">
          <h2>Billing</h2>
          <p>Manage your plan, invoices, and payment methods.</p>
          <button class="btn-secondary">Open billing</button>
        </div>
        <div class="settings-section">
          <h2>API Keys</h2>
          <p>Manage secrets and tokens for your projects.</p>
          <button class="btn-secondary">Manage keys</button>
        </div>
      </div>
    `
  };

  // ---------- SIDEBAR TOGGLE ----------
  function setExpanded(expanded) {
    sidebarEl.classList.toggle('is-expanded', expanded);
    localStorage.setItem(SIDEBAR_KEY, expanded ? '1' : '0');
  }

  const saved = localStorage.getItem(SIDEBAR_KEY);
  const defaultExpanded = window.innerWidth > 768;
  setExpanded(saved === null ? defaultExpanded : saved === '1');

  toggleBtn.addEventListener('click', () => {
    setExpanded(!sidebarEl.classList.contains('is-expanded'));
  });

  // ---------- PAGE ROUTING ----------
  async function loadPage(pageName) {
    if (!pageName) return;

    navItems.forEach(item => {
      item.classList.toggle('is-active', item.dataset.page === pageName);
    });

    const projectSeg = document.querySelector('[data-page-only="projects"]');
    if (projectSeg) {
      projectSeg.style.display = (pageName === 'projects') ? 'flex' : 'none';
    }

    contentEl.innerHTML = '<div class="content-loading">Loading...</div>';

    // Coba fetch dulu
    let html = null;
    try {
      const res = await fetch(`components/dashboard/${pageName}.html`);
      if (res.ok) html = await res.text();
    } catch (_) { /* fallback ke inline */ }

    // Kalau fetch gagal → pakai inline
    if (!html) {
      html = INLINE_HTML[pageName] || '<div class="content-error">Halaman tidak ditemukan.</div>';
      console.warn(`[akun] fetch gagal, pakai inline HTML untuk "${pageName}"`);
    }

    contentEl.innerHTML = html;
    document.title = `Nasuha Labs — ${capitalize(pageName)}`;
    localStorage.setItem(PAGE_KEY, pageName);
  }

  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      const page = item.dataset.page;
      if (!page) return;
      e.preventDefault();
      loadPage(page);
    });
  });

  const lastPage = localStorage.getItem(PAGE_KEY) || 'projects';
  loadPage(lastPage);

  function capitalize(s) {
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
})();
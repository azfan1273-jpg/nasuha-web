// ==========================================
// UI.JS - Mengatur Tampilan, Sidebar & Routing
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
  setupSidebarToggle();
  setupNavigation();
  
  // Render halaman awal (Product)
  renderProducts();
});

// 1. FUNGSI TOGGLE SIDEBAR
function setupSidebarToggle() {
  document.addEventListener('click', function(e) {
    const toggleBtn = e.target.closest('#toggle-sidebar');
    const spacer = e.target.closest('#sidebar-spacer');

    if (toggleBtn || spacer) {
      e.preventDefault();
      e.stopPropagation(); 
      
      const sidebar = document.getElementById('sidebar');
      const icon = document.getElementById('toggle-icon');
      
      if (sidebar) {
        sidebar.classList.toggle('collapsed');
        if (icon) {
          icon.innerHTML = sidebar.classList.contains('collapsed') 
            ? '<polyline points="9 18 15 12 9 6"></polyline>' 
            : '<polyline points="15 18 9 12 15 6"></polyline>';
        }
      }
    }
  }, true);
}

// 2. FUNGSI NAVIGASI MENU
function setupNavigation() {
  const navItems = document.querySelectorAll('.sidebar-nav .nav-item');
  
  navItems.forEach(item => {
    item.addEventListener('click', (e) => {
      if (item.id === 'toggle-sidebar') return; 
      e.preventDefault();
      
      navItems.forEach(nav => nav.classList.remove('active'));
      item.classList.add('active');
      
      const target = item.getAttribute('data-target');
      const contentArea = document.getElementById('content-area');
      
      // Routing Halaman
      if (target === 'product') {
        renderProducts();
      } else if (target === 'clay') {
        if (typeof renderClayEngine === 'function') renderClayEngine();
      } else if (target === 'team') {
        contentArea.innerHTML = `<div class="page-title"><h1>Team</h1></div><p>Halaman Team belum tersedia.</p>`;
      } else if (target === 'database') {
        contentArea.innerHTML = `<div class="page-title"><h1>Database</h1></div><p>Halaman Database belum tersedia.</p>`;
      } else if (target === 'settings') {
        contentArea.innerHTML = `<div class="page-title"><h1>Settings</h1></div><p>Halaman Settings belum tersedia.</p>`;
      }
    });
  });
}

// 3. RENDER HALAMAN PRODUCT
function renderProducts() {
  const contentArea = document.getElementById('content-area');
  if (!contentArea) return;

  document.title = 'Nasuha Labs — Product';

  // Ambil nama user dari localStorage (disimpan oleh auth.js)
  let userName = 'User';
  try {
    const rawUser = localStorage.getItem('user_info');
    if (rawUser) {
      const u = JSON.parse(rawUser);
      userName = u.fullName || u.name || u.nama_pegawai || u.email || 'User';
    }
  } catch(e) {}

  contentArea.innerHTML = `
    <div class="page-title"><h1>Product</h1></div>
    
    <div class="toolbar">
      <div class="toolbar-left">
        <div class="search-input">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" placeholder="Search for a product">
        </div>
        <button class="btn-secondary">Status ⌄</button>
        <button class="btn-secondary">Sorted by name</button>
      </div>
      <div class="toolbar-right">
        <button class="btn-primary">+ New product</button>
      </div>
    </div>

    <div class="table-container">
      <table class="data-table">
        <thead>
          <tr>
            <th>PRODUCT ↑</th>
            <th>USER</th>
            <th>ROLE</th>
            <th>PACKAGE</th>
            <th>STATUS</th>
            <th>CREATED</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>
              <div class="project-name">Kasir-app</div>
              <div class="project-id">app-001xyz</div>
            </td>
            <td>${userName}</td>
            <td>Owner</td>
            <td><span class="tag">Free</span></td>
            <td><span class="status-badge">ACTIVE</span></td>
            <td>17 Aug 26 03:13:00</td>
            <td><button class="icon-btn" style="font-size: 1.2rem;">⋮</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="usage-section">
      <div class="usage-header">
        <div>
          <h2>Free plan usage</h2>
          <p>Current billing cycle</p>
        </div>
        <button class="btn-upgrade">Upgrade to Pro</button>
      </div>
      <div class="usage-list">
        <div class="usage-item"><div class="usage-item-left"><span class="usage-dot"></span><span class="usage-label">Egress</span></div><span class="usage-value">0.06 / 5 GB</span></div>
        <div class="usage-item"><div class="usage-item-left"><span class="usage-dot"></span><span class="usage-label">Database size</span></div><span class="usage-value">31 / 500 MB</span></div>
        <div class="usage-item"><div class="usage-item-left"><span class="usage-dot"></span><span class="usage-label">Monthly active users</span></div><span class="usage-value">5 / 50.000</span></div>
        <div class="usage-item"><div class="usage-item-left"><span class="usage-dot"></span><span class="usage-label">File storage</span></div><span class="usage-value">0.03 / 1 GB</span></div>
        <div class="usage-item"><div class="usage-item-left"><span class="usage-dot"></span><span class="usage-label">Log Ingestion</span></div><span class="usage-value">0.07 / 1 GB</span></div>
        <div class="usage-item"><div class="usage-item-left"><span class="usage-dot"></span><span class="usage-label">Log Query</span></div><span class="usage-value">15.4 / 100 GB</span></div>
      </div>
    </div>
  `;
}
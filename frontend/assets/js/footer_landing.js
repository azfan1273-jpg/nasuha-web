// Footer Landing Logic
document.addEventListener('DOMContentLoaded', () => {
  // Update tahun copyright otomatis
  const yearEl = document.getElementById('footer-year');
  if (yearEl) {
    yearEl.textContent = new Date().getFullYear();
  }
});
// ============================================================
// PRICING — duration picker + select plan + konfirmasi
// ============================================================

(function () {

  const PRICES = {
    plus: {
      '1': { label: 'Rp 50.000',  period: '/ bulan',   monthsText: '1 Bulan',  monthsVal: '1' },
      '3': { label: 'Rp 140.000', period: '/ 3 bulan', monthsText: '3 Bulan',  monthsVal: '3' },
    },
    premium: {
      '1': { label: 'Rp 150.000', period: '/ bulan',   monthsText: '1 Bulan',  monthsVal: '1' },
      '3': { label: 'Rp 400.000', period: '/ 3 bulan', monthsText: '3 Bulan',  monthsVal: '3' },
    },
  };

  const PLAN_NAMES = {
    plus: 'Plus',
    premium: 'Premium',
  };

  let selectedPlan = null;

  // ============================================================
  // FUNGSI UTAMA: Update UI saat plan dipilih
  // ============================================================
  function updateSelection(plan, card) {
    selectedPlan = plan;

    // 1. Reset teks semua tombol jadi "Pilih ..."
    document.querySelectorAll('[data-select]').forEach(b => {
      if (b.dataset.select === 'plus') b.textContent = 'Pilih Plus';
      if (b.dataset.select === 'premium') b.textContent = 'Pilih Premium';
    });

    // 2. Ubah teks tombol yang lagi aktif jadi "Terpilih"
    const activeBtn = card.querySelector('[data-select]');
    if (activeBtn) activeBtn.textContent = 'Terpilih';

    // 3. Hapus highlight dari SEMUA pilihan harga
    document.querySelectorAll('.duration-opt').forEach(opt => {
      opt.classList.remove('is-active');
    });

    // 4. Tambahin highlight ke pilihan harga yang aktif di card ini
    const checkedRadio = card.querySelector('input[type="radio"]:checked');
    if (checkedRadio) {
      checkedRadio.closest('.duration-opt').classList.add('is-active');
    }
  }

  // ============================================================
  // 1. EVENT: Klik tombol "Pilih Plus/Premium"
  // ============================================================
  document.querySelectorAll('[data-select]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const card = btn.closest('.plan-card');
      updateSelection(btn.dataset.select, card);
    });
  });

  // ============================================================
  // 2. EVENT: Ganti durasi (1 Bulan / 3 Bulan)
  // ============================================================
  document.querySelectorAll('.duration-opt input[type="radio"]').forEach(radio => {
    radio.addEventListener('change', () => {
      const parent = radio.closest('.duration-picker');
      const plan   = parent.dataset.duration;
      const card   = parent.closest('.plan-card');
      
      updateSelection(plan, card);
      
      const value  = radio.value;
      const label  = card.querySelector('[data-price-label]');
      const period = card.querySelector('[data-price-period]');
      const data   = PRICES[plan]?.[value];
      if (data && label && period) {
        label.textContent  = data.label;
        period.textContent = data.period;
      }
    });
  });

  // ============================================================
  // 3. EVENT: Klik seluruh area card
  // ============================================================
  document.querySelectorAll('.plan-card[data-plan]').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.duration-picker')) return;
      const btn = card.querySelector('[data-select]');
      if (btn) btn.click();
    });
  });

  // ============================================================
  // 4. BOTTOM CTA — Tampilkan Modal Konfirmasi
  // ============================================================
  const modal       = document.getElementById('confirm-modal');
  const confirmName = document.getElementById('confirm-plan-name');
  const confirmDur  = document.getElementById('confirm-duration');
  const confirmPrc  = document.getElementById('confirm-price');
  const btnCancel   = document.getElementById('btn-cancel-confirm');
  const btnOk       = document.getElementById('btn-ok-confirm');
  const btnContinue = document.getElementById('btn-continue');

  if (btnContinue) {
    btnContinue.addEventListener('click', () => {
      if (!selectedPlan) {
        alert('Silakan pilih paket terlebih dahulu ya, bro! 🙏');
        return;
      }

      const card = document.querySelector(`[data-plan="${selectedPlan}"]`);
      const radioChecked = card.querySelector('input[type="radio"]:checked');
      const monthsVal = radioChecked ? radioChecked.value : '1';
      const priceData = PRICES[selectedPlan][monthsVal];

      // Isi data ke modal
      confirmName.textContent = PLAN_NAMES[selectedPlan];
      confirmDur.textContent  = priceData.monthsText;
      confirmPrc.textContent  = priceData.label;

      // Tampilkan modal
      modal.classList.remove('hidden');
    });
  }

  // Tombol Batal
  if (btnCancel) {
    btnCancel.addEventListener('click', () => {
      modal.classList.add('hidden');
    });
  }

  // Klik overlay buat nutup modal
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });
  }

    // Tombol "Ya, Lanjutkan" -> Tampilkan pesan Midtrans (Versi Pro)
  if (btnOk) {
    btnOk.addEventListener('click', () => {
      const modalCard = document.querySelector('.confirm-card');
      
      // Ganti isi modal jadi pesan maintenance
      modalCard.innerHTML = `
        <div class="confirm-icon" style="font-size: 2.5rem; margin-bottom: 12px;">🛠️</div>
        <h3 class="confirm-title">Segera Hadir!</h3>
        <p class="confirm-desc" style="margin-bottom: 24px;">
          Terima kasih atas antusiasme Anda! Saat ini sistem pembayaran kami (<b>Midtrans</b>) sedang dalam tahap akhir verifikasi. Fitur langganan akan segera tersedia.
        </p>
        <p class="confirm-note" style="color: var(--accent); margin-bottom: 24px;">Mohon maaf atas ketidaknyamanannya.</p>
        
        <div class="confirm-actions" style="justify-content: center;">
          <button id="btn-tutup-maintenance" class="plan-btn btn-primary" style="width: 100%;">Mengerti</button>
        </div>
      `;

      // Tombol Tutup
      document.getElementById('btn-tutup-maintenance').addEventListener('click', () => {
        modal.classList.add('hidden');
        // Reload halaman biar modal balik normal
        window.location.reload(); 
      });
    });
  }

})();
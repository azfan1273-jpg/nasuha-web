// ============================================================
// PRICING — Duration picker & Redirection ke Flutter Web
// ============================================================

document.addEventListener('DOMContentLoaded', function () {

  const PRICES = {
    plus: {
      '1': { label: 'Rp 50.000',  period: '/ bulan',   monthsText: '1 Bulan' },
      '3': { label: 'Rp 140.000', period: '/ 3 bulan', monthsText: '3 Bulan' },
    },
    premium: {
      '1': { label: 'Rp 150.000', period: '/ bulan',   monthsText: '1 Bulan' },
      '3': { label: 'Rp 400.000', period: '/ 3 bulan', monthsText: '3 Bulan' },
    },
  };

  const PLAN_NAMES = {
    plus: 'Plus',
    premium: 'Premium',
  };

  let selectedPlan = null;

  // URL Aplikasi Flutter Web kamu
  const FLUTTER_APP_URL = 'https://nasuhakasir.vercel.app';

  function updateSelection(plan, card) {
    if (!card) return;
    selectedPlan = plan;

    document.querySelectorAll('[data-select]').forEach(b => {
      if (b.dataset.select === 'plus') b.textContent = 'Pilih Plus';
      if (b.dataset.select === 'premium') b.textContent = 'Pilih Premium';
    });

    const activeBtn = card.querySelector('[data-select]');
    if (activeBtn) activeBtn.textContent = 'Terpilih';

    document.querySelectorAll('.duration-opt').forEach(opt => {
      opt.classList.remove('is-active');
    });

    const checkedRadio = card.querySelector('input[type="radio"]:checked');
    if (checkedRadio) {
      const durationOpt = checkedRadio.closest('.duration-opt');
      if (durationOpt) durationOpt.classList.add('is-active');
    }
  }

  // 1. Pilih Paket
  document.querySelectorAll('[data-select]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const card = btn.closest('.plan-card');
      updateSelection(btn.dataset.select, card);
    });
  });

  // 2. Ganti Durasi
  document.querySelectorAll('.duration-opt input[type="radio"]').forEach(radio => {
    radio.addEventListener('change', () => {
      const parent = radio.closest('.duration-picker');
      if (!parent) return;
      const plan   = parent.dataset.duration;
      const card   = parent.closest('.plan-card');
      if (!card) return;
      
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

  // 3. Klik Card Area
  document.querySelectorAll('.plan-card[data-plan]').forEach(card => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.duration-picker')) return;
      const btn = card.querySelector('[data-select]');
      if (btn) btn.click();
    });
  });

  // 4. Modal Konfirmasi & Pengarahan
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
        alert('Silakan pilih paket terlebih dahulu.');
        return;
      }

      const card = document.querySelector(`[data-plan="${selectedPlan}"]`);
      if (!card) return;
      const radioChecked = card.querySelector('input[type="radio"]:checked');
      const monthsVal = radioChecked ? radioChecked.value : '1';
      const priceData = PRICES[selectedPlan]?.[monthsVal];

      if (!priceData) return;

      if (confirmName) confirmName.textContent = PLAN_NAMES[selectedPlan];
      if (confirmDur)  confirmDur.textContent  = priceData.monthsText;
      if (confirmPrc)  confirmPrc.textContent  = priceData.label;

      if (modal) modal.classList.remove('hidden');
    });
  }

  if (btnCancel) {
    btnCancel.addEventListener('click', () => {
      if (modal) modal.classList.add('hidden');
    });
  }

  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.classList.add('hidden');
    });
  }

  // 5. Langsung arahkan ke halaman Login Flutter Web
  if (btnOk) {
    btnOk.addEventListener('click', () => {
      window.location.href = FLUTTER_APP_URL;
    });
  }

});
document.addEventListener('DOMContentLoaded', () => loadBookForm());

async function loadBookForm() {
  try {
    const res  = await fetch('/book-form');
    if (!res.ok) throw new Error(`Server responded ${res.status}`);
    const html = await res.text();

    const placeholder = document.querySelector('script#replace_with_book');
    const wrapper     = document.createElement('div'); 
    wrapper.innerHTML = html;
    placeholder.parentNode.replaceChild(wrapper, placeholder);

    initBookForm(wrapper);
  } catch (err) {
    console.error('Error loading booking form:', err);
  }
}


function initBookForm(root) {
  setupDatePicker(root.querySelector('#date'));
  setupCityDropdowns(root);
  setupWizard(root);
}

function setupDatePicker(dateInput) {
  if (!dateInput) return;

  const today = new Date();
  const fmt   = d => d.toISOString().split('T')[0];

  dateInput.min = fmt(today);
  const max = new Date(today);
  max.setDate(max.getDate() + 90);
  dateInput.max = fmt(max);

  dateInput.addEventListener('input', () => {
    const dow = new Date(dateInput.value).getDay();   // 0-Sun, 6-Sat
    if (dow === 0 || dow === 6) {
      alert('Bookings are only allowed Monday–Friday');
      dateInput.value = '';
    }
  });
}

function setupCityDropdowns(root){
    const leaveSel  = root.querySelector('[name="leave-city-options"]');
    const arriveSel = root.querySelector('[name="arrive-city-options"]');
  
    const qs = new URLSearchParams(location.search);
    const leaveParam  = qs.get('leave');   // ?leave=CITY
    const arriveParam = qs.get('arrive');  // ?arrive=CITY
  
    if (leaveParam) leaveSel.value = leaveParam;
  
    fetch('/get-travel-options')
      .then(r => r.json())
      .then(routes => {
        const departures = [...new Set(routes.map(r => r.departure))].sort();
      leaveSel.innerHTML = departures
        .map(d => `<option value="${d}">${d}</option>`)
        .join('');

      // pre-select ?leave=…  or fall back to the first city
      leaveSel.value = leaveParam || departures[0];
        const buildArrivals = dep => {
          arriveSel.innerHTML = '';
          const list = routes.filter(r => r.departure === dep);
          if (!list.length){
            arriveSel.innerHTML =
              '<option>No available destinations</option>';
            return;
          }
          arriveSel.innerHTML = list
            .map(r => `<option value="${r.arrival}">${r.arrival}</option>`)
            .join('');
            const list2 = routes.filter(r => r.departure === dep);

          arriveSel.innerHTML = list2.length
            ? list2.map(r => `<option value="${r.arrival}">${r.arrival}</option>`).join('')
            : '<option disabled>No available destinations</option>';
        };
        buildArrivals(leaveSel.value);
      if (arriveParam) arriveSel.value = arriveParam;

        buildArrivals(leaveSel.value);
  
        if (arriveParam) arriveSel.value = arriveParam;

        leaveSel.addEventListener('change',
          () => buildArrivals(leaveSel.value));
      })
      .catch(err => console.error('travel-options fetch:', err));
  }
  
  document.addEventListener('DOMContentLoaded',
    () => setupCityDropdowns(document));
  

    function setupWizard(root) {
    const steps   = [
    root.querySelector('.travel-container'),
    root.querySelector('.payment-container')
    ];
    let current   = 0;
    show();

    root.querySelector('.next-btn').addEventListener('click', async e => {
    e.preventDefault();
    if (current !== 0) return;

    try {
        const fd    = new FormData(root.querySelector('#regForm'));
        const resp  = await fetch('/get-price-to-pay', { method: 'POST', body: fd });
        if (!resp.ok) throw new Error(`status ${resp.status}`);
        const data = await resp.json();
        const { price, discount } = data; 

        root.querySelector('#price-out').textContent = price.toFixed(2);
        root.querySelector('#discount-out').textContent = discount;
        current = 1;
        show();
    } catch (err) {
        console.error('price fetch:', err);
        alert('Could not load price: ' + err.message);
    }
    });

  function show() {
    steps.forEach((el, i) => (el.style.display = i === current ? 'block' : 'none'));
  }
}

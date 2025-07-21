    document.addEventListener('DOMContentLoaded', () => {

      fetch('/cookies')
      .then(res => res.text())
      .then(html => {

        const ph = document.getElementById('cookies-placeholder');
        ph.innerHTML = html;
        
        const banner  = document.getElementById('cookie-banner');
        const accept  = banner?.querySelector('#accept-cookies');
        const decline = banner?.querySelector('#decline-cookies');

        if (accept) {
          accept.addEventListener('click', async () => {
            await fetch('/accept_cookies', { method: 'POST' });
            banner.remove();        // hide banner
          });
        }
        if (decline) {
          decline.addEventListener('click', async () => {
            await fetch('/decline_cookies', { method: 'POST' });
            banner.remove();        // hide banner
          });
        }
      })
      .catch(err => console.error('Error loading cookie banner:', err));
  });

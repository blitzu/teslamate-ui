/* Pagina publica de urmarire: interogheaza /share/<token>/data la 10 s */
(() => {
  const tok = location.pathname.split('/').filter(Boolean)[1];
  const RO = !(navigator.language || 'ro').toLowerCase().startsWith('en');
  const X = (ro, en) => (RO ? ro : en);
  const $ = (id) => document.getElementById(id);
  const map = L.map('map', { zoomControl: false, attributionControl: true }).setView([45.9, 25], 6);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(map);
  let mk = null, first = true, timer = null;
  const clock = (ts) => new Date(ts * 1000).toLocaleTimeString(RO ? 'ro-RO' : 'en-GB', { hour: '2-digit', minute: '2-digit' });
  async function tick() {
    try {
      const r = await fetch('/share/' + tok + '/data', { cache: 'no-store' });
      if (r.status === 410 || r.status === 404) { clearInterval(timer); $('t1').textContent = X('Linkul a expirat', 'This link has expired'); $('t2').textContent = ''; return; }
      const d = await r.json();
      if (d.lat != null) {
        const ll = [d.lat, d.lon];
        if (!mk) mk = L.marker(ll, { icon: L.divIcon({ className: '', html: '<div class="dot"></div>', iconSize: [14, 14] }) }).addTo(map); else mk.setLatLng(ll);
        if (first) { map.setView(ll, 15); first = false; } else map.panTo(ll);
      } else if (mk) { map.removeLayer(mk); mk = null; }
      const who = d.name ? d.name + ' · ' : '';
      if (d.state === 'home') { $('t1').textContent = who + X('Acasă', 'At home'); $('t2').textContent = X('Poziția exactă e ascunsă.', 'The exact position is hidden.'); }
      else if (d.eta_ts) { $('t1').textContent = who + X('Ajunge la ', 'Arrives at ') + clock(d.eta_ts); $('t2').textContent = X('în ', 'in ') + d.eta_min + ' min' + (d.dest ? ' · ' + d.dest : '') + (d.speed ? ' · ' + d.speed + ' km/h' : ''); }
      else if (d.state === 'driving') { $('t1').textContent = who + X('Pe drum', 'On the road'); $('t2').textContent = d.speed ? d.speed + ' km/h' : ''; }
      else { $('t1').textContent = who + X('Oprită', 'Parked'); $('t2').textContent = X('Se actualizează la fiecare 10 secunde · valabil până la ', 'Updates every 10 seconds · valid until ') + clock(d.expires); }
    } catch (e) { $('t2').textContent = X('Conexiune întreruptă…', 'Connection lost…'); }
  }
  tick(); timer = setInterval(tick, 10000);
})();

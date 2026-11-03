/* Pagina publica de urmarire: interogheaza /share/<token>/data la 10 s. Daca linkul are curse salvate pentru comparare, le deseneaza pe harta
   si arata unde era fiecare dupa acelasi timp scurs de la plecarea cursei curente. */
(() => {
  const tok = location.pathname.split('/').filter(Boolean)[1];
  const RO = !(navigator.language || 'ro').toLowerCase().startsWith('en');
  const X = (ro, en) => (RO ? ro : en);
  const $ = (id) => document.getElementById(id);
  const map = L.map('map', { zoomControl: false, attributionControl: true }).setView([45.9, 25], 6);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(map);
  let mk = null, first = true, timer = null, trips = null, gh = [], el0 = null;
  const COL = ['#ff9a3c', '#b45be0'];
  const clock = (ts) => new Date(ts * 1000).toLocaleTimeString(RO ? 'ro-RO' : 'en-GB', { hour: '2-digit', minute: '2-digit' });
  const dur = (s) => { s = Math.max(0, Math.round(s)); return s >= 3600 ? Math.floor(s / 3600) + 'h ' + String(Math.floor(s % 3600 / 60)).padStart(2, '0') + 'm' : Math.floor(s / 60) + 'm ' + String(s % 60).padStart(2, '0') + 's'; };
  const at = (pts, e) => {                                              // pozitia la timpul scurs e (interpolare liniara intre puncte)
    if (e <= pts[0][0]) return pts[0];
    const z = pts[pts.length - 1]; if (e >= z[0]) return z;
    let lo = 0, hi = pts.length - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (pts[m][0] <= e) lo = m; else hi = m; }
    const a = pts[lo], b = pts[hi], f = (e - a[0]) / Math.max(1, b[0] - a[0]);
    return [e, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f, Math.round(a[3] + (b[3] - a[3]) * f), Math.round(a[4] + (b[4] - a[4]) * f), a[5] + (b[5] - a[5]) * f];
  };
  async function loadTrips() {
    try {
      const r = await fetch('/share/' + tok + '/trips', { cache: 'no-store' }); if (!r.ok) { trips = []; return; }
      trips = (await r.json()).trips || [];
    } catch (e) { trips = null; return; }
    const box = $('cmp'); box.textContent = '';
    trips.forEach((c, i) => {
      const ll = c.pts.map((p) => [p[1], p[2]]);
      L.polyline(ll, { color: COL[i], weight: 5, opacity: .55 }).addTo(map);
      const m = L.circleMarker(ll[0], { radius: 7, color: '#fff', weight: 3, fillColor: COL[i], fillOpacity: 1 }).addTo(map);
      const row = document.createElement('div'); row.className = 'cr'; row.style.setProperty('--c', COL[i]);
      const lb = document.createElement('b'), tx = document.createElement('span');
      lb.textContent = X('Comparația ', 'Comparison ') + (i + 1) + ' · ' + new Date(c.t0 * 1000).toLocaleDateString(RO ? 'ro-RO' : 'en-GB', { day: 'numeric', month: 'short' });
      tx.textContent = nfmt(c.km) + ' km · ' + dur(c.dur);
      row.append(lb, tx); box.appendChild(row);
      gh.push({ c, m, tx });
    });
    if (gh.length) { const all = []; trips.forEach((c) => c.pts.forEach((p) => all.push([p[1], p[2]]))); if (mk) all.push(mk.getLatLng()); if (all.length) map.fitBounds(all, { padding: [30, 150] }); }
    ghosts();
  }
  const nfmt = (v) => Number(v).toLocaleString(RO ? 'ro-RO' : 'en-GB', { maximumFractionDigits: 1 });
  function ghosts() {
    const e = el0 ? el0.s + (Date.now() - el0.at) / 1000 : null;
    gh.forEach((g) => {
      const p0 = g.c.pts[0];
      if (e == null) { g.m.setLatLng([p0[1], p0[2]]); g.tx.textContent = nfmt(g.c.km) + ' km · ' + dur(g.c.dur); return; }
      const p = at(g.c.pts, p0[0] + e);
      g.m.setLatLng([p[1], p[2]]);
      g.tx.textContent = e >= g.c.dur + p0[0] ? X('a ajuns · ', 'arrived · ') + dur(g.c.dur) : p[3] + ' km/h · ' + nfmt(p[5]) + ' km · ' + dur(e) + ' · ' + p[4] + '%';
    });
  }
  async function tick() {
    try {
      const r = await fetch('/share/' + tok + '/data', { cache: 'no-store' });
      if (r.status === 410 || r.status === 404) { clearInterval(timer); $('t1').textContent = X('Linkul a expirat', 'This link has expired'); $('t2').textContent = ''; $('cmp').textContent = ''; return; }
      const d = await r.json();
      el0 = d.elapsed_s != null ? { s: d.elapsed_s, at: Date.now() } : null;
      if (d.ntrips && trips === null) { trips = []; loadTrips(); }
      if (d.lat != null) {
        const ll = [d.lat, d.lon];
        if (!mk) mk = L.marker(ll, { icon: L.divIcon({ className: '', html: '<div class="dot"></div>', iconSize: [14, 14] }) }).addTo(map); else mk.setLatLng(ll);
        if (first) { if (!gh.length) map.setView(ll, 15); first = false; } else if (!gh.length) map.panTo(ll);
      } else if (mk) { map.removeLayer(mk); mk = null; }
      const who = d.name ? d.name + ' · ' : '';
      if (d.state === 'home') { $('t1').textContent = who + X('Acasă', 'At home'); $('t2').textContent = X('Poziția exactă e ascunsă.', 'The exact position is hidden.'); }
      else if (d.eta_ts) { $('t1').textContent = who + X('Ajunge la ', 'Arrives at ') + clock(d.eta_ts); $('t2').textContent = X('în ', 'in ') + d.eta_min + ' min' + (d.dest ? ' · ' + d.dest : '') + (d.speed ? ' · ' + d.speed + ' km/h' : ''); }
      else if (d.state === 'driving') { $('t1').textContent = who + X('Pe drum', 'On the road'); $('t2').textContent = d.speed ? d.speed + ' km/h' : ''; }
      else { $('t1').textContent = who + X('Oprită', 'Parked'); $('t2').textContent = X('Se actualizează la fiecare 10 secunde · valabil până la ', 'Updates every 10 seconds · valid until ') + clock(d.expires); }
      ghosts();
    } catch (e) { $('t2').textContent = X('Conexiune întreruptă…', 'Connection lost…'); }
  }
  tick(); timer = setInterval(tick, 10000); setInterval(ghosts, 1000);
})();

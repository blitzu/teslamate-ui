/* Cursa in desfasurare (#/live): traseul parcurs, masina pe hartă, destinatia navigatiei (pin), km ramasi si ora sosirii, plus distanta / durata / energie / cost de pana acum.
   Se reimprospateaza la 5 s cat timp pagina e deschisa. Pe pagina Masina apare un card care duce aici cat timp masina e in miscare. */
const ldDest = (n) => !n ? '' : /^home$/i.test(n) ? X('Acasă', 'Home') : n;
const ldClock = (ts) => new Date(ts * 1000).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });
const ldKm = (v) => v == null ? '—' : v < 10 ? nf(v, 1) : nf(v, 0);

/* randul de sub titlu: "45 km/h · 1,7 km rămași · sosire 19:45" */
function ldSub(r) {
  const ro = r.route || {};
  return [r.speed != null ? nf(r.speed, 0) + ' km/h' : '', ro.km != null ? ldKm(ro.km) + ' km ' + X('rămași', 'left') : '', ro.eta ? X('sosire ', 'arrival ') + ldClock(ro.eta) : ''].filter(Boolean).join(' · ');
}

/* cardul de pe pagina Masina (starea live e deja in pagina, fara cerere noua) */
function liveDriveBanner(L) {
  const ro = L.active_route && typeof L.active_route === 'object' && !L.active_route.error ? L.active_route : null;
  const km = ro && ro.miles_to_arrival != null ? ro.miles_to_arrival * 1.609344 : null;
  const eta = ro && ro.minutes_to_arrival != null ? Date.now() / 1000 + ro.minutes_to_arrival * 60 : null;
  const sub = [L.speed != null ? nf(L.speed, 0) + ' km/h' : '', km != null ? ldKm(km) + ' km ' + X('rămași', 'left') : '', eta ? X('sosire ', 'arrival ') + ldClock(eta) : ''].filter(Boolean).join(' · ');
  return `<a class="card ldb" href="#/live"><small>${X('CURSĂ ÎN DESFĂȘURARE', 'DRIVE IN PROGRESS')}</small><b>${ro && ro.destination ? X('Către ', 'To ') + esc(ldDest(ro.destination)) : X('Vezi traseul pe hartă', 'See the route on the map')}</b><span>${esc(sub)}</span><i>›</i></a>`;
}

const LD = { el: null, map: null, layers: null, timer: null, fit: true, data: null, idle: 0 };
const ldCarIcon = (h) => window.L.divIcon({ className: '', iconSize: [34, 34], iconAnchor: [17, 17], html: `<i class="ldpulse"></i><svg class="ldcar" viewBox="0 0 34 34" style="transform:rotate(${Math.round(h || 0)}deg)"><circle cx="17" cy="17" r="15" fill="#1f6feb" stroke="#fff" stroke-width="3"/><path d="M17 6l7 17-7-4-7 4z" fill="#fff"/></svg>` });
const ldPinIcon = () => window.L.divIcon({ className: '', iconSize: [30, 40], iconAnchor: [15, 38], html: '<svg class="ldpin" viewBox="0 0 30 40"><path d="M15 1C7 1 1 7 1 15c0 10 14 24 14 24s14-14 14-24C29 7 23 1 15 1z" fill="#e5484d" stroke="#fff" stroke-width="2"/><circle cx="15" cy="15" r="5" fill="#5b1013"/></svg>' });

function ldStop() { if (LD.timer) { clearInterval(LD.timer); LD.timer = null; } }
const ldHere = () => !!($('#ldin') || ($('#ldh') && location.hash.startsWith('#/live')));          // exista o harta a cursei pe ecran (pagina Masina sau #/live)

/* harta cursei vine pe pagina Masina in locul hartii "Locatie"; pagina Masina se redeseneaza des, deci harta Leaflet traieste intr-un element tinut deoparte si e doar mutata in pagina noua (fara sa se reincarce dalele) */
function liveDriveMap() {
  return `<h2>${X('Cursa de acum', 'This drive')}</h2><div id="map" class="ldmap" data-ld="1"></div><div id="ldin">${LD.data && LD.data.active ? ldStatsHtml(LD.data) : ''}</div>`;
}
function ldMount(el, lat, lon) {
  if (!el || !el.hasAttribute('data-ld') || !window.L) return false;
  if (!LD.el) { LD.el = document.createElement('div'); LD.el.style.cssText = 'width:100%;height:100%'; }
  el.innerHTML = ''; el.appendChild(LD.el);
  if (!LD.map) {
    LD.map = window.L.map(LD.el, { zoomControl: false }).setView([lat ?? 44.43, lon ?? 26.1], 14);
    mapTiles().addTo(LD.map);
    if (typeof fsControl === 'function') fsControl(LD.map);
    LD.layers = null; LD.fit = true;
  } else LD.map.invalidateSize();
  if (LD.data && LD.data.active) { ldFill(LD.data); if (LD.fit) ldDraw(LD.data); }
  if (!LD.timer && Date.now() > LD.idle) { LD.timer = setInterval(ldTick, 5000); ldTick(); }
  return true;
}

function ldDraw(r) {
  if (!window.L || !LD.map) return;
  if (LD.layers) LD.layers.remove();
  const g = LD.layers = window.L.layerGroup().addTo(LD.map), P = window.L;
  const pts = (r.points || []).map((p) => [p[1], p[2]]).filter((p) => p[0] != null && p[1] != null);
  const me = r.lat != null && r.lon != null ? [r.lat, r.lon] : pts[pts.length - 1];
  const ro = r.route || {};
  const to = ro.lat != null && ro.lon != null ? [ro.lat, ro.lon] : null;
  if (pts.length > 1) {                                                              // traseul: stralucire + culoare dupa viteza (albastru lent, verde, auriu, rosu rapid)
    P.polyline(pts, { color: '#4c8dff', weight: 16, opacity: .15, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(g);
    const raw = (r.points || []).filter((p) => p[1] != null && p[2] != null), col = (v) => v < 30 ? '#7aa8ff' : v < 70 ? '#6fd6b8' : v < 110 ? '#d9ba80' : '#ef7a7a';
    let run = [[raw[0][1], raw[0][2]]], c = col(raw[0][3] || 0);
    for (let i = 1; i < raw.length; i++) {
      const cc = col(raw[i][3] || 0); run.push([raw[i][1], raw[i][2]]);
      if (cc !== c || i === raw.length - 1) { P.polyline(run, { color: c, weight: 6, opacity: .96, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(g); run = [[raw[i][1], raw[i][2]]]; c = cc; }
    }
    P.circleMarker(pts[0], { radius: 6, color: '#0b0d10', weight: 3, fillColor: '#6fd6b8', fillOpacity: 1, interactive: false }).addTo(g);          // punctul de plecare
  }
  if (me && to) P.polyline([me, to], { color: '#9fb4d6', weight: 3, opacity: .8, dashArray: '2 9', lineCap: 'round' }).addTo(g);          // pana la destinatie: linie dreapta (traseul exact nu e publicat)
  if (to) P.marker(to, { icon: ldPinIcon(), interactive: false }).addTo(g);
  if (me) P.marker(me, { icon: ldCarIcon(r.heading), interactive: false, zIndexOffset: 1000 }).addTo(g);
  if (LD.fit) {                                                                       // prima data cuprinde tot; apoi harta nu mai sare cat o muti cu degetul
    LD.fit = false;
    const all = pts.concat(me ? [me] : [], to ? [to] : []);
    if (all.length > 1) LD.map.fitBounds(all, { padding: [34, 34], maxZoom: 16 }); else if (me) LD.map.setView(me, 15);
  }
}

function ldStatsHtml(r) {
  const cu = typeof CU === 'function' ? CU() : '';
  return `<div class="grid g3">${stat(X('Distanță', 'Distance'), r.km != null ? nf(r.km, 1) : '—', 'km')}${stat(X('Durată', 'Duration'), r.min != null ? hm(r.min) : '—')}${stat(X('Baterie', 'Battery'), r.soc != null ? nf(r.soc, 0) : '—', '%')}</div>
    <h2>${X('Energie', 'Energy')}</h2><div class="grid g3">${stat(X('Consumat', 'Used'), r.kwh != null ? nf(r.kwh, 2) : '—', 'kWh')}${stat(X('Medie', 'Average'), r.wh_km != null ? nf(r.wh_km, 0) : '—', 'Wh/km')}${stat(X('Putere', 'Power'), r.power != null ? nf(r.power, 0) : '—', 'kW')}</div>
    ${r.cost != null ? `<h2>${X('Cost', 'Cost')}</h2><div class="grid g3">${stat(X('Electric (estimat)', 'Electric (est.)'), nf(r.cost, 2), cu)}${stat(X('Preț kWh', 'Price per kWh'), nf(r.price, 2), cu)}</div>` : ''}`;
}

function ldFill(r) {
  const inl = $('#ldin'); if (inl) inl.innerHTML = ldStatsHtml(r);
  const h = $('#ldh'), st = $('#ldst'); if (!h || !st) return;
  const ro = r.route || {};
  h.innerHTML = `<small>${X('CURSĂ ÎN DESFĂȘURARE', 'DRIVE IN PROGRESS')}</small><h1 style="font-size:23px">${ro.name ? X('Către ', 'To ') + esc(ldDest(ro.name)) : X('Fără destinație', 'No destination')}</h1><div class="ldsub">${esc(ldSub(r))}</div>${ro.soc_arrival != null ? `<div class="ldsub" style="margin-top:2px">${X('La sosire: ', 'On arrival: ')}<b>${nf(ro.soc_arrival, 0)}%</b>${ro.delay ? ' · ' + X('trafic +', 'traffic +') + nf(ro.delay, 0) + ' min' : ''}</div>` : ''}`;
  st.innerHTML = ldStatsHtml(r);
  const pts = r.points || [], ch = $('#ldch');
  if (ch && pts.length > 2 && ch.dataset.n !== String(pts.length)) {
    ch.dataset.n = String(pts.length);
    const t = (p) => +T(p[0]), fx = (x) => new Date(x).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });
    ch.innerHTML = sec(X('Baterie (%)', 'Battery (%)'), line(pts.map((p) => [t(p), p[5]]), { color: '#6fd6b8', fx })) + sec(X('Viteză (km/h)', 'Speed (km/h)'), line(pts.map((p) => [t(p), p[3]]), { color: '#7aa8ff', fx }));
  }
}

async function ldTick() {
  if (!ldHere()) { ldStop(); return; }
  let r; try { r = await api('/api/livedrive?car=' + car); } catch (e) { return; }
  if (!ldHere()) return;
  if (!r.active) { ldStop(); LD.idle = Date.now() + 20000; LD.data = null; LD.fit = true; if (LD.layers) { LD.layers.remove(); LD.layers = null; } const h = $('#ldh'); if (h) h.innerHTML = `<small>${X('CURSA S-A TERMINAT', 'DRIVE FINISHED')}</small><h1 style="font-size:23px">${X('Mașina nu mai e în mișcare', 'The car is no longer moving')}</h1><div class="ldsub"><a href="#/drives" style="color:var(--mint)">${X('Vezi cursa în lista de curse ›', 'See the drive in the drives list ›')}</a></div>`; return; }
  LD.data = r; ldFill(r); ldDraw(r);
}

PAGES.live = {
  nav: 'car',
  async render() {
    ldStop();
    let r; try { r = await api('/api/livedrive?car=' + car); } catch (e) { return `<a class="back" href="#/car">‹ ${X('Mașina', 'Car')}</a><div class="empty">${X('Nu pot încărca cursa.', 'Cannot load the drive.')}</div>`; }
    window.__ld = r;
    if (!r.active) return `<a class="back" href="#/car">‹ ${X('Mașina', 'Car')}</a><div class="top"><h1>${X('Nicio cursă în desfășurare', 'No drive in progress')}</h1><small>${X('Pagina se umple singură când mașina pornește la drum.', 'The page fills in by itself when the car sets off.')}</small></div><div class="links"><a href="#/drives">${X('Ultimele curse ›', 'Recent drives ›')}</a></div>`;
    return `<a class="back" href="#/car">‹ ${X('Mașina', 'Car')}</a><div class="top" id="ldh"></div><div class="map big ldmap" id="ldmap" data-ld="1"></div><div id="ldst"></div><div id="ldch"></div>`;
  },
  after() {
    const r = window.__ld; window.__ld = null;
    if (!r || !r.active) return;
    LD.data = r; ldFill(r);
    if (map) { map.remove(); map = null; }
    LD.fit = true; ldMount($('#ldmap'), r.lat, r.lon);
    ldDraw(r);
  },
};

/* Călătorii (#/trips) — curse grupate, cu opriri și încărcări; detaliu cu hartă și reluare */
NAVI.trips = 'M2 12l5-5 4 4 7-7 4 4-11 11-4-4-5 5z';
EXTRA_MENU.push(['trips', 'Călătorii', 'Trips', 'trips']);
let trDays = 90, trTrips = [];
const trDate = (s) => new Date(s + 'Z').toLocaleDateString(LOC(), { weekday: 'short', day: 'numeric', month: 'short' });
const trTime = (s) => new Date(s + 'Z').toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });

PAGES.trips = {
  nav: 'trips',
  async render() {
    let d; try { d = await api('/api/trips?days=' + trDays); } catch (e) { return `<div class="top"><h1>${X('Călătorii', 'Trips')}</h1></div><div class="empty">${X('Nu pot încărca călătoriile.', 'Cannot load the trips.')}</div>`; }
    trTrips = d.trips;
    const cu = CU(), tot = d.trips.reduce((s, t) => ({ km: s.km + t.km, kwh: s.kwh + t.kwh, cost: s.cost + t.charge_cost }), { km: 0, kwh: 0, cost: 0 });
    const cards = d.trips.map((t) => `<a class="item" href="#/tripd/${t.id}"><div class="t"><span>${esc(tr(t.start_name || '—'))}</span><span class="arr">→</span><span>${esc(tr(t.end_name || '—'))}</span></div>
      <div class="m"><span>${trDate(t.start)} ${trTime(t.start)}–${trTime(t.end)}</span><span><b>${nf(t.km, 1)}</b> km</span><span><b>${hm(t.total_min)}</b></span><span><b>${nf(t.kwh, 1)}</b> kWh</span>${t.wh_km ? `<span><b>${t.wh_km}</b> Wh/km</span>` : ''}${t.n_drives > 1 ? `<span>${t.n_drives} ${X('curse', 'drives')}</span>` : ''}${t.n_charges ? `<span>⚡ ${t.n_charges}× · +${nf(t.charge_kwh, 1)} kWh${t.charge_cost ? ' · ' + nf(t.charge_cost, 2) + ' ' + esc(cu) : ''}</span>` : ''}</div>${t.stops.length ? `<div class="m"><span class="mut">${X('Opriri', 'Stops')}: ${t.stops.map((x) => esc(tr(x))).join(', ')}</span></div>` : ''}</a>`).join('');
    return `<div class="top"><h1>${X('Călătorii', 'Trips')}</h1><small>${X('Cursele separate de pauze mai scurte decât pragul de mai jos sunt o singură călătorie. Același prag îl folosește și reluarea traseului.', 'Drives separated by breaks shorter than the threshold below are one trip. The route replay uses the same threshold.')}</small></div>
      <div class="seg">${[30, 90, 365].map((n) => `<button data-trd="${n}" class="${n === trDays ? 'on' : ''}">${n === 365 ? X('1 an', '1 year') : n + X(' zile', ' days')}</button>`).join('')}</div>
      <div class="grid g3" style="margin-top:12px">${stat(X('Călătorii', 'Trips'), nf(d.trips.length))}${stat(X('Distanță', 'Distance'), nf(tot.km), 'km')}${stat(X('Încărcat', 'Charged'), nf(d.trips.reduce((s, t) => s + t.charge_kwh, 0), 1), 'kWh')}</div>
      <div class="card cfg" style="margin-top:12px"><div class="addf"><label>${X('Pauză maximă în aceeași călătorie', 'Max break within one trip')}<select id="tr_gap">${[1, 2, 3, 4, 6, 12].map((h) => `<option value="${h}" ${h === d.gap_h ? 'selected' : ''}>${h} h</option>`).join('')}</select></label></div><div class="toast" aria-live="polite" id="tr_msg" style="display:none"></div></div>
      <div class="list" style="margin-top:14px">${cards || `<div class="empty">${X('Nicio călătorie în perioada aleasă.', 'No trips in the chosen period.')}</div>`}</div>`;
  },
  after() {
    document.querySelectorAll('[data-trd]').forEach((b) => b.onclick = () => { trDays = +b.dataset.trd; render(); });
    const g = $('#tr_gap'); if (g) g.onchange = async () => {
      const [ok, j] = await pinPost('/api/trips/gap', { hours: +g.value }); const m = $('#tr_msg');
      if (ok) render(); else if (m) { m.style.display = ''; m.textContent = '✗ ' + (j.reason || X('Eroare', 'Error')); m.className = 'toast bad'; }
    };
  },
};

PAGES.tripd = {
  nav: 'trips',
  async render(arg) {
    let t = trTrips.find((x) => String(x.id) === String(arg));
    if (!t) { try { t = (await api('/api/trips?days=730')).trips.find((x) => String(x.id) === String(arg)); } catch (e) { /* ignore */ } }
    if (!t) return `<a class="back" href="#/trips">‹ ${X('Călătorii', 'Trips')}</a><div class="empty">${X('Călătoria nu există.', 'Trip not found.')}</div>`;
    const cu = CU();
    return `<a class="back" href="#/trips">‹ ${X('Călătorii', 'Trips')}</a>
      <div class="top"><h1 style="font-size:21px">${esc(tr(t.start_name || '—'))} → ${esc(tr(t.end_name || '—'))}</h1><small>${trDate(t.start)} · ${trTime(t.start)}–${trTime(t.end)}</small></div>
      <a class="play" href="#/trip/${t.id}"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>${X('Reluare traseu', 'Replay route')}</a>
      <div class="map big" id="tmap"></div>
      <div class="grid g3" style="margin-top:12px">${stat(X('Distanță', 'Distance'), nf(t.km, 1), 'km')}${stat(X('Timp total', 'Total time'), hm(t.total_min))}${stat(X('La volan', 'Driving'), hm(t.drive_min))}${stat(X('Energie folosită', 'Energy used'), nf(t.kwh, 1), 'kWh')}${stat(X('Consum', 'Consumption'), t.wh_km ? t.wh_km : '—', 'Wh/km')}${stat(X('Viteză max', 'Top speed'), nf(t.speed_max), 'km/h')}</div>
      ${t.n_charges ? `<div class="grid" style="margin-top:10px">${stat(X('Încărcări pe drum', 'Charges on the way'), t.n_charges + '×  +' + nf(t.charge_kwh, 1), 'kWh')}${stat(X('Cost încărcări', 'Charging cost'), nf(t.charge_cost, 2), esc(cu))}</div>` : ''}
      <h2>${X('Cursele din călătorie', 'Drives in this trip')} (${t.n_drives})</h2><div class="list">${t.drive_ids.map((id) => `<a class="item" href="#/drive/${id}"><div class="t"><span>${X('Cursa', 'Drive')} #${id}</span><span class="arr">→</span></div></a>`).join('')}</div>`;
  },
  after(arg) {
    setTimeout(async () => {
      const el = $('#tmap'); if (!el || !window.L) return;
      let d; try { d = await api('/api/trips/detail?id=' + encodeURIComponent(arg)); } catch (e) { el.innerHTML = `<div class="empty">${X('Harta nu e disponibilă.', 'The map is not available.')}</div>`; return; }
      if (map) { map.remove(); map = null; }
      map = window.L.map(el, { zoomControl: false }).setView([44.4, 26.1], 8);
      window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
      const col = (v) => v < 30 ? '#7aa8ff' : v < 70 ? '#6fd6b8' : v < 110 ? '#d9ba80' : '#ef7a7a', all = [];
      d.segments.forEach((s) => s.points.forEach((p, i, a) => { all.push([p[1], p[2]]); if (i) window.L.polyline([[a[i - 1][1], a[i - 1][2]], [p[1], p[2]]], { color: col(p[3] || 0), weight: 5, opacity: .95, lineCap: 'round' }).addTo(map); }));
      d.stops.forEach((s) => window.L.circleMarker([s.lat, s.lon], { radius: 8, color: '#0b0d10', weight: 3, fillColor: s.kind === 'charge' ? '#d9ba80' : '#9aa4af', fillOpacity: 1 }).addTo(map).bindTooltip(s.kind === 'charge' ? `⚡ ${esc(s.name || '')} +${nf(s.kwh, 1)} kWh` : esc(s.name || '—')));
      if (all.length > 1) map.fitBounds(all, { padding: [24, 24] });
    }, 0);
  },
};

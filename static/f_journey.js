/* Vedere de ansamblu pe harta (#/journey/<mod>): traseu + incarcari + opriri pentru o calatorie, un interval, curse alese sau un tag.
   Plus selectia de curse/incarcari din liste si editarea tag-urilor. */
NAVI.journey = 'M20.5 3l-.16.03L15 5.1 9 3 3.36 4.9c-.21.07-.36.25-.36.48V20.5c0 .28.22.5.5.5l.16-.03L9 18.9l6 2.1 5.64-1.9c.21-.07.36-.25.36-.48V3.5c0-.28-.22-.5-.5-.5zM15 19l-6-2.11V5l6 2.11V19z';

const JCOL = (i, n) => `hsl(${Math.round(200 - (n > 1 ? i / (n - 1) : 0) * 190)}, 85%, 60%)`;       // albastru -> portocaliu in ordinea cronologica
const jmod = (arg) => { const m = String(arg || '').match(/^(trip|ids|tag|range|filter):?(.*)$/); return m ? [m[1], decodeURIComponent(m[2])] : ['filter', '']; };

function jQuery(arg) {
  const [m, v] = jmod(arg);
  if (m === 'trip') return '&trip=' + encodeURIComponent(v);
  if (m === 'ids') return '&ids=' + encodeURIComponent(v);
  if (m === 'tag') return '&tag=' + encodeURIComponent(v);
  if (m === 'range') {
    const [a, b] = v.split('..');
    return (a ? '&from=' + encodeURIComponent(new Date(a + 'T00:00:00').toISOString()) : '') + (b ? '&to=' + encodeURIComponent(new Date(+new Date(b + 'T00:00:00') + 864e5).toISOString()) : '');
  }
  return lfQuery('drives');                                                                         // "filter": cum sunt setate filtrele listei de curse
}
const jDay = (s) => fdate(T(s), { day: 'numeric', month: 'short' }) + ' ' + tm(s);

PAGES.journey = {
  nav: 'drives',
  async render(arg) {
    await lfLoadTags();
    const [m, v] = jmod(arg), f = lfGet('drives');
    const rg = m === 'range' ? v.split('..') : ['', ''];
    const head = `<a class="back" href="#/drives">‹ ${X('Curse', 'Drives')}</a><div class="top"><h1>${X('Vedere de ansamblu', 'Journey overview')}</h1><small>${X('Traseul, încărcările și opririle pe hartă: pentru o călătorie, un interval, curse alese sau un tag.', 'The route, charges and stops on a map: for a trip, a date range, picked drives or a tag.')}</small></div>
      <div class="card cfg"><div class="addf"><label>${X('De la', 'From')}<input type="date" id="jr_from" value="${esc(rg[0])}"></label><label>${X('Până la', 'To')}<input type="date" id="jr_to" value="${esc(rg[1])}"></label>
      ${LF_TAGS.length ? `<label>${X('sau tag', 'or tag')}<select id="jr_tag"><option value="">—</option>${LF_TAGS.map((t) => `<option value="${esc(t.name)}" ${m === 'tag' && v === t.name ? 'selected' : ''}>${esc(t.name)} (${t.n})</option>`).join('')}</select></label>` : ''}</div>
      <div class="links"><a href="#" id="jr_go">${X('Arată pe hartă', 'Show on map')}</a></div></div>`;
    let d;
    try { d = await api('/api/journey?car=' + car + jQuery(arg)); } catch (e) { return head + `<div class="empty">${X('Nu pot încărca datele.', 'Cannot load the data.')}</div>`; }
    if (!d.drives.length && !d.charges.length) return head + `<div class="empty">${X('Nicio cursă pentru această alegere.', 'No drives for this choice.')}</div>`;
    window.__jd = { arg: arg || '', d };                                           // after() reutilizeaza raspunsul (pana la 300 de curse cu puncte)
    const s = d.summary, cu = esc(CU());
    const ev = [];
    d.drives.forEach((x, i) => ev.push({ t: x.start, h: `<a class="item" href="#/drive/${x.id}"><div class="t"><i class="jdot" style="background:${JCOL(i, d.drives.length)}"></i><span>${esc(x.from_)}</span><span class="arr">→</span><span>${esc(x.to)}</span></div><div class="m"><span><b>${nf(x.km, 1)}</b> km</span><span>${jDay(x.start)}</span></div></a>` }));
    d.charges.forEach((x) => ev.push({ t: x.start, h: `<a class="item" href="#/charge/${x.id}"><div class="t"><span>⚡ ${esc(x.name)}</span><span class="badge ${x.dc ? 'dc' : 'ac'}">${x.dc ? 'DC' : 'AC'}</span></div><div class="m"><span><b>+${nf(x.kwh, 1)}</b> kWh</span>${x.cost != null ? `<span><b>${nf(x.cost, 2)}</b> ${cu}</span>` : ''}<span>${jDay(x.start)}</span></div></a>` }));
    d.stops.forEach((x) => ev.push({ t: x.start, h: `<div class="item" style="cursor:default"><div class="t"><span>⏸ ${esc(x.name || '—')}</span></div><div class="m"><span><b>${hm(x.min)}</b> ${X('oprire', 'stop')}</span><span>${jDay(x.start)}</span></div></div>` }));
    ev.sort((a, b) => (a.t < b.t ? -1 : 1));
    return head + `<div class="map big" id="jmap" style="height:56vh;min-height:320px"></div>
      <div class="jlegend"><span><i class="jdot" style="background:${JCOL(0, 2)}"></i>${X('început', 'start')}</span><span><i class="jdot" style="background:${JCOL(1, 2)}"></i>${X('sfârșit', 'end')}</span><span>⚡ ${X('încărcare', 'charge')}</span><span>⏸ ${X('oprire', 'stop')}</span></div>
      <h2>${X('Rezumat', 'Summary')}</h2><div class="grid g3">${stat(X('Distanță', 'Distance'), nf(s.km, 1), 'km')}${stat(X('Timp la volan', 'Driving time'), hm(s.drive_min))}${stat(X('Consum', 'Used'), nf(s.kwh, 1), 'kWh')}${stat(X('Curse', 'Drives'), nf(s.drives))}${stat(X('Încărcări', 'Charges'), nf(s.charges))}${stat(X('Energie încărcată', 'Charged'), nf(s.charged_kwh, 1), 'kWh')}${stat(X('Cost încărcări', 'Charging cost'), nf(s.cost, 2), CU())}${stat(X('Opriri', 'Stops'), nf(s.stops))}${stat(X('Perioadă', 'Period'), s.start ? fdate(T(s.start), { day: 'numeric', month: 'short' }) + ' – ' + fdate(T(s.end), { day: 'numeric', month: 'short' }) : '—')}</div>
      ${d.truncated ? `<p class="note">${X('Am afișat primele 300 de curse din perioadă. Restrânge intervalul pentru restul.', 'Showing the first 300 drives of the period. Narrow the range for the rest.')}</p>` : ''}
      <h2>${X('Pe scurt, în ordine', 'In order')}</h2>${ev.map((x) => x.h).join('')}`;
  },
  after(arg) {
    const go = $('#jr_go');
    if (go) go.onclick = (e) => {
      e.preventDefault();
      const tag = $('#jr_tag') && $('#jr_tag').value, a = $('#jr_from').value, b = $('#jr_to').value;
      location.hash = tag ? '#/journey/tag:' + encodeURIComponent(tag) : (a || b) ? '#/journey/range:' + a + '..' + b : '#/journey/filter';
    };
    (window.__jd && window.__jd.arg === (arg || '') ? Promise.resolve(window.__jd.d) : api('/api/journey?car=' + car + jQuery(arg))).then((d) => {
      const el = $('#jmap'); if (!el || !window.L || (!d.drives.length && !d.charges.length)) return;
      if (map) { map.remove(); map = null; }
      map = window.L.map(el, { zoomControl: false }).setView([45.9, 25], 6);
      window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
      const all = [];
      d.drives.forEach((x, i) => {
        const ll = x.pts.map((p) => [p[0], p[1]]); all.push(...ll);
        if (ll.length > 1) window.L.polyline(ll, { color: JCOL(i, d.drives.length), weight: 5, opacity: .95, lineCap: 'round', lineJoin: 'round' }).bindPopup(`<b>${esc(x.from_)} → ${esc(x.to)}</b><br>${nf(x.km, 1)} km · ${jDay(x.start)}<br><a href="#/drive/${x.id}">${X('Detalii', 'Details')}</a>`).addTo(map);
      });
      const dot = (ll, c) => window.L.circleMarker(ll, { radius: 8, color: '#0b0d10', weight: 3, fillColor: c, fillOpacity: 1 }).addTo(map);
      if (d.drives[0] && d.drives[0].pts.length) { const p = d.drives[0].pts[0]; dot([p[0], p[1]], JCOL(0, 2)); }
      const last = d.drives[d.drives.length - 1]; if (last && last.pts.length) { const p = last.pts[last.pts.length - 1]; dot([p[0], p[1]], JCOL(1, 2)); }
      const icon = (emoji, bg) => window.L.divIcon({ className: '', html: `<div class="jpin" style="background:${bg}">${emoji}</div>`, iconSize: [30, 30], iconAnchor: [15, 15] });
      d.charges.forEach((c) => { all.push([c.lat, c.lon]); window.L.marker([c.lat, c.lon], { icon: icon('⚡', c.dc ? '#ffb15c' : '#6fd6b8') }).bindPopup(`<b>${esc(c.name)}</b><br>+${nf(c.kwh, 1)} kWh${c.cost != null ? ' · ' + nf(c.cost, 2) + ' ' + esc(CU()) : ''}<br>${jDay(c.start)}<br><a href="#/charge/${c.id}">${X('Detalii', 'Details')}</a> · ${gmLink(c.lat, c.lon, 'Google Maps')}`).addTo(map); });
      d.stops.forEach((s) => window.L.marker([s.lat, s.lon], { icon: icon('⏸', '#9aa5b1') }).bindPopup(`<b>${esc(s.name || '—')}</b><br>${hm(s.min)} ${X('oprire', 'stop')}<br>${jDay(s.start)}`).addTo(map));
      if (all.length) map.fitBounds(all, { padding: [30, 30] });
    }).catch(() => {});
  },
};

/* ---------- selectie in liste + tag-uri ---------- */
const SEL = { on: false, kind: '', ids: new Set() };
function selKind(k) { return k === 'drives' ? 'drive' : 'charge'; }
function lfSelBar(k) { return `<div class="links" style="margin:10px 2px"><a href="#" id="lf_sel">${SEL.on && SEL.kind === k ? '✕ ' + X('Ieși din selecție', 'Leave selection') : '☑ ' + X('Selectează', 'Select')}</a>${k === 'drives' ? `<a href="#/journey/filter">🗺 ${X('Vezi perioada pe hartă', 'Show the period on the map')}</a>` : ''}</div>`; }
function lfSelBind(k) {
  const tg = $('#lf_sel');
  if (tg) tg.onclick = (e) => { e.preventDefault(); if (SEL.on && SEL.kind === k) { SEL.on = false; SEL.ids.clear(); } else { SEL.on = true; SEL.kind = k; SEL.ids.clear(); } selDraw(k); };
  document.querySelectorAll('.item[data-id]').forEach((a) => {
    a.classList.toggle('picked', SEL.on && SEL.kind === k && SEL.ids.has(+a.dataset.id));
    a.addEventListener('click', (e) => { if (!(SEL.on && SEL.kind === k)) return; e.preventDefault(); const id = +a.dataset.id; if (SEL.ids.has(id)) SEL.ids.delete(id); else SEL.ids.add(id); a.classList.toggle('picked'); selBar(k); });
  });
  selBar(k);
}
function selDraw(k) { const t = $('#lf_sel'); if (t) t.innerHTML = SEL.on ? '✕ ' + X('Ieși din selecție', 'Leave selection') : '☑ ' + X('Selectează', 'Select'); document.querySelectorAll('.item[data-id]').forEach((a) => a.classList.toggle('picked', SEL.on && SEL.ids.has(+a.dataset.id))); selBar(k); }
function selBar(k) {
  let b = $('#selbar');
  if (!SEL.on || SEL.kind !== k) { if (b) b.remove(); return; }
  if (!b) { b = document.createElement('div'); b.id = 'selbar'; document.body.appendChild(b); }
  const n = SEL.ids.size, ids = [...SEL.ids], typed = ($('#sb_tag') || {}).value || '';
  b.innerHTML = `<div class="row"><b>${n} ${X('selectate', 'selected')}</b><div class="sp"></div>${k === 'drives' ? `<a href="#/journey/ids:${ids.join(',')}" class="${n ? '' : 'off'}" id="sb_map">🗺 ${X('Hartă', 'Map')}</a>` : ''}<a href="#" id="sb_all">${X('Toate de pe pagină', 'All on page')}</a></div>
    <div class="addf" style="margin-top:8px"><label>${X('Tag', 'Tag')}<input id="sb_tag" list="sb_tags" maxlength="30" placeholder="${X('ex. Vacanță Grecia', 'e.g. Greece trip')}"><datalist id="sb_tags">${LF_TAGS.map((t) => `<option value="${esc(t.name)}">`).join('')}</datalist></label></div>
    <div class="links" style="margin-top:8px"><a href="#" id="sb_add">${X('Adaugă tag', 'Add tag')}</a><a href="#" id="sb_rem">${X('Scoate tag', 'Remove tag')}</a></div><div class="toast" id="sb_msg" style="display:none"></div>`;
  if (typed) $('#sb_tag').value = typed;                                          // tag-ul scris nu se pierde cand alegi alt element
  const map_ = $('#sb_map'); if (map_) map_.onclick = (e) => { if (!n) e.preventDefault(); };
  $('#sb_all').onclick = (e) => { e.preventDefault(); document.querySelectorAll('.item[data-id]').forEach((a) => { SEL.ids.add(+a.dataset.id); a.classList.add('picked'); }); selBar(k); };
  const send = async (add) => {
    const name = $('#sb_tag').value.trim(), m = $('#sb_msg');
    if (!n || !name) { m.style.display = ''; m.textContent = X('Alege cel puțin un element și scrie un tag.', 'Pick at least one item and type a tag.'); m.className = 'toast bad'; return; }
    const [ok, j] = await pinPost('/api/tags/set', { kind: selKind(k), ids, [add ? 'add' : 'remove']: [name] });
    m.style.display = ''; m.textContent = ok ? '✓ ' + X('Salvat', 'Saved') : '✗ ' + (j.reason || X('Eroare', 'Error')); m.className = 'toast ' + (ok ? 'ok' : 'bad');
    if (ok) { SEL.on = false; SEL.ids.clear(); setTimeout(() => { b.remove(); render(); }, 700); }
  };
  $('#sb_add').onclick = (e) => { e.preventDefault(); send(true); };
  $('#sb_rem').onclick = (e) => { e.preventDefault(); send(false); };
}
window.addEventListener('hashchange', () => { const b = $('#selbar'); if (b) b.remove(); SEL.on = false; SEL.ids.clear(); });

/* tag-urile unei curse / incarcari, pe pagina ei */
function tagsCard(kind, id, tags) {
  return `<h2>${X('Tag-uri', 'Tags')}</h2><div class="card"><div class="tgrow">${(tags || []).map((t) => `<span class="tg big">${esc(t)} <a href="#" data-tgdel="${esc(t)}" aria-label="${X('șterge', 'remove')}">✕</a></span>`).join('') || `<span class="mut" style="font-size:13px">${X('Fără tag-uri.', 'No tags.')}</span>`}</div>
    <div class="addf" style="margin-top:8px"><label>${X('Adaugă', 'Add')}<input id="tg_new" list="tg_all" maxlength="30" placeholder="${X('ex. Vacanță Grecia', 'e.g. Greece trip')}"><datalist id="tg_all">${LF_TAGS.map((t) => `<option value="${esc(t.name)}">`).join('')}</datalist></label></div>
    <div class="links"><a href="#" id="tg_add">${X('Adaugă tag', 'Add tag')}</a></div><div class="toast" id="tg_msg" style="display:none"></div></div>`;
}
function tagsBind(kind, id) {
  const say = (t, c) => { const m = $('#tg_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + c; } };
  const send = async (body) => { const [ok, j] = await pinPost('/api/tags/set', Object.assign({ kind, ids: [id] }, body)); if (ok) render(); else say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad'); };
  const a = $('#tg_add'); if (a) a.onclick = (e) => { e.preventDefault(); const v = $('#tg_new').value.trim(); if (v) send({ add: [v] }); };
  document.querySelectorAll('[data-tgdel]').forEach((x) => x.onclick = (e) => { e.preventDefault(); send({ remove: [x.dataset.tgdel] }); });
}

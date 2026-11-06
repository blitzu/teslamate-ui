/* Comparare calatorii (#/compare/<id>,<id>,<id>) si Timeline interactiv (#/timeline/<id>).
   Ambele pornesc de la /api/trip/<id> (cursele unei calatorii + opririle dintre ele) si folosesc aceeasi cronologie: puncte GPS cu timp real,
   distanta, energia consumata/recuperata si incarcarea cumulate; opririle sunt puncte "tinute pe loc" ca timpul scurs sa fie cel real. */
NAVI.compare = 'M10 3H4a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h6v-2H5V5h5V3zm4 0v2h5v14h-5v2h6a1 1 0 0 0 1-1V4a1 1 0 0 0-1-1h-6zm-2 4v10l-4-5 4-5z';

const CT_COL = ['#4c8dff', '#ff9a3c', '#b45be0'];                                     // principala, comparatia 1, comparatia 2
const ctClock = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); return s >= 3600 ? Math.floor(s / 3600) + 'h ' + String(Math.floor(s % 3600 / 60)).padStart(2, '0') + 'm' : Math.floor(s / 60) + 'm ' + String(s % 60).padStart(2, '0') + 's'; };
const ctTod = (ms) => new Date(ms).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });
let CT_TRIPS = null;
async function ctTripList() {
  if (!CT_TRIPS) { try { CT_TRIPS = (await api('/api/trips?days=730&car=' + car)).trips; } catch (e) { CT_TRIPS = []; } }
  return CT_TRIPS;
}

/* cronologia unei calatorii: [{t, lat, lon, v, soc, ele, dist, used, regen, chg, st}] ; st = starea intervalului care se TERMINA in acest punct: d (la drum), s (oprire), c (incarcare) */
function ctBuild(data) {
  const segs = (data.segments || []).filter((s) => s.points.length > 1);
  const tl = []; let dist = 0, used = 0, regen = 0, chg = 0, prev = null;
  segs.forEach((sg, si) => {
    if (si > 0 && prev) {
      const st = (data.stops || [])[si - 1] || {}, ch = st.kind === 'charge', t1 = +T(sg.points[0][0]);
      if (t1 > prev.t) {
        if (ch) chg += st.kwh || 0;
        prev = Object.assign({}, prev, { t: prev.t + 1, v: 0, st: 'd' }); tl.push(prev);                  // mașina stă pe loc: viteza scade imediat la 0
        prev = Object.assign({}, prev, { t: Math.max(prev.t + 1, t1 - 1), soc: ch && st.s1 != null ? st.s1 : prev.soc, chg, st: ch ? 'c' : 's' }); tl.push(prev);
      }
    }
    sg.points.forEach((p, i) => {
      const e = { t: +T(p[0]), lat: p[1], lon: p[2], v: p[3] || 0, soc: p[5] ?? prev?.soc ?? 0, ele: p[6] ?? prev?.ele ?? 0, st: 'd' };
      if (prev && !(si > 0 && i === 0)) {
        dist += hav(prev.lat, prev.lon, e.lat, e.lon);
        const en = (p[4] || 0) * (e.t - prev.t) / 3.6e6; if (en > 0) used += en; else regen -= en;
      }
      Object.assign(e, { dist, used, regen, chg });
      if (prev && e.t <= prev.t) e.t = prev.t + 1;
      tl.push(e); prev = e;
    });
  });
  const d0 = segs[0]?.drive || {}, d1 = segs[segs.length - 1]?.drive || {};
  return { tl, t0: tl[0]?.t || 0, t1: tl[tl.length - 1]?.t || 0, km: dist, from: d0.start_name, to: d1.end_name, stops: data.stops || [], n: segs.length };
}
const CT_NUM = ['lat', 'lon', 'v', 'soc', 'ele', 'dist', 'used', 'regen', 'chg'];
function ctAt(tl, t) {
  if (!tl.length) return null;
  if (t <= tl[0].t) return Object.assign({ hd: 0 }, tl[0]);
  if (t >= tl[tl.length - 1].t) return Object.assign({ hd: tl[tl.length - 1].hd || 0 }, tl[tl.length - 1]);
  let lo = 0, hi = tl.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (tl[m].t <= t) lo = m; else hi = m; }
  const a = tl[lo], b = tl[hi], f = (t - a.t) / Math.max(1, b.t - a.t), o = { t, st: b.st, i: lo, hd: brg(a.lat, a.lon, b.lat, b.lon) };
  CT_NUM.forEach((k) => { o[k] = a[k] + (b[k] - a[k]) * f; });
  return o;
}
/* statistici pe intervalul [a, b] (ms) */
function ctStats(tl, a, b) {
  const A = ctAt(tl, a), B = ctAt(tl, b);
  const s = { dur: b - a, dist: B.dist - A.dist, used: B.used - A.used, regen: B.regen - A.regen, chg: B.chg - A.chg, soc0: A.soc, soc1: B.soc, vmax: Math.max(A.v, B.v), move: 0, stops: 0, emin: Math.min(A.ele, B.ele), emax: Math.max(A.ele, B.ele), up: 0, down: 0,
    roll: 0, idle: 0, pause: 0, chgT: 0, idleN: 0, idleMax: 0 };
  let last = A, inStop = false, run = 0;
  const endRun = () => { if (run >= 15000) { s.idleN++; s.idleMax = Math.max(s.idleMax, run); } run = 0; };            // o oprire in trafic = cel putin 15 s pe loc in timpul cursei
  const step = (p) => {
    const dt = Math.min(p.t, b) - Math.max(last.t, a);
    if (dt > 0) {
      if (p.st === 'd') {
        s.move += dt;
        const vi = (p.dist - last.dist) / (dt / 3.6e6);                                      // viteza pe interval din distanta (nu din vitezometru): rezista la esantionare rara
        if (vi < 3) { s.idle += dt; run += dt; } else { s.roll += dt; endRun(); }
      } else { endRun(); s.pause += dt; if (p.st === 'c') s.chgT += dt; if (!inStop) { s.stops++; inStop = true; } }
    }
    if (p.st === 'd') inStop = false;
    const d = p.ele - last.ele; if (d > 0) s.up += d; else s.down -= d;
    s.vmax = Math.max(s.vmax, p.v); s.emin = Math.min(s.emin, p.ele); s.emax = Math.max(s.emax, p.ele);
    last = p;
  };
  tl.forEach((p) => { if (p.t > a && p.t < b) step(p); });
  step(Object.assign({}, B, { st: B.st }));
  endRun();
  s.net = s.used - s.regen; s.vavg = s.roll > 0 ? s.dist / (s.roll / 3.6e6) : (s.move > 0 ? s.dist / (s.move / 3.6e6) : 0); s.vtot = s.dur > 0 ? s.dist / (s.dur / 3.6e6) : 0; s.pct = s.dur > 0 ? s.roll / s.dur * 100 : 0; s.wh = s.dist > .2 ? s.net * 1000 / s.dist : null;
  return s;
}
const ctName = (c) => `${tr(c.from || '—')} → ${tr(c.to || '—')}`;
const ctDate = (c) => new Date(c.t0).toLocaleDateString(LOC(), { day: 'numeric', month: 'short' }) + ' ' + ctTod(c.t0);
const ctDot = (c) => `<i class="ct-dot" style="background:${c}"></i>`;
/* buton "ecran complet" pe harta: Fullscreen API unde exista; altfel (iOS Safari nu il are pe elemente obisnuite) elementul acopera singur tot ecranul. Escape il inchide in ambele moduri. */
function fsSet(host, on, btn, m) {
  host.classList.toggle('fs-on', on);
  for (let p = host.parentElement; p && p.id !== 'view' && p !== document.body; p = p.parentElement) p.classList.toggle('fs-par', on);          // pasi parintii izolati (z-index) ca sa nu acopere ecranul complet
  document.body.classList.toggle('fs-lock', !!document.querySelector('.fs-on'));
  if (btn) { btn.textContent = on ? '✕' : '⛶'; btn.setAttribute('aria-label', on ? X('Ieși din ecranul complet', 'Exit fullscreen') : X('Ecran complet', 'Fullscreen')); }
  if (on && host.requestFullscreen) host.requestFullscreen().catch(() => {});
  if (!on && document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {});
  [60, 350].forEach((ms) => setTimeout(() => { try { m.invalidateSize(); } catch (e) { /* harta nu mai exista */ } }, ms));
}
function fsControl(m, target) {
  if (!window.L || !m || m.__fs) return;
  m.__fs = true;
  const host = target || m.getContainer();
  const Ctl = window.L.Control.extend({
    options: { position: 'topright' },
    onAdd() {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'fsb'; b.textContent = '⛶'; b.setAttribute('aria-label', X('Ecran complet', 'Fullscreen'));
      window.L.DomEvent.disableClickPropagation(b);
      b.onclick = (e) => { e.preventDefault(); fsSet(host, !host.classList.contains('fs-on'), b, m); };
      return b;
    },
  });
  new Ctl().addTo(m);
}
const fsClear = () => { document.querySelectorAll('.fs-on,.fs-par').forEach((h) => h.classList.remove('fs-on', 'fs-par')); document.body.classList.remove('fs-lock'); document.querySelectorAll('.fsb').forEach((b) => { if (b.textContent === '✕') b.textContent = '⛶'; }); };
addEventListener('keydown', (e) => { if (e.key === 'Escape') fsClear(); });
document.addEventListener('fullscreenchange', () => { if (!document.fullscreenElement) fsClear(); });
function ctMap(el, view, fsTarget) {
  if (map) { map.remove(); map = null; }
  map = window.L.map(el, { zoomControl: false, attributionControl: true }).setView(view || [45.9, 25], 7);
  mapBase(map);
  fsControl(map, fsTarget);
  return map;
}
const ctLive = (hash) => location.hash.startsWith(hash);

/* sugestii: calatorii cu plecare si sosire apropiate de ale celei principale (features/similar.py), cu insigne acelasi drum / alt drum, sens invers, perioada anului si temperatura */
const CTS = { f: 'all' };
function ctSugRows(j, ids) {
  const all = (j.suggestions || []).filter((s) => !ids.includes(s.id));
  const nOther = all.filter((s) => s.same_road === false).length, nSame = all.filter((s) => s.same_road === true).length;
  const shown = all.filter((s) => CTS.f === 'all' || (CTS.f === 'other' ? s.same_road === false : s.same_road === true));
  const chip = (k, t, n) => `<button class="pchip ${CTS.f === k ? 'on' : ''}" data-ctsf="${k}">${t} <small>${n}</small></button>`;
  const rows = shown.map((s) => {
    const dt0 = new Date(T(s.start)).toLocaleDateString(LOC(), { day: 'numeric', month: 'short', year: '2-digit' });
    const season = s.season_days <= 20 ? X('aceeași perioadă a anului', 'same time of year') : '±' + s.season_days + ' ' + X('zile față de perioada ta', 'days from your time of year');
    const road = s.same_road === true ? `<span class="tg">${X('același drum', 'same road')}</span>` : s.same_road === false ? `<span class="tg" style="background:#ff9a3c33">${X('alt drum', 'other road')} · ${s.overlap}% ${X('suprapus', 'shared')}</span>` : '';
    return `<a class="item" href="#" data-ctadd="${s.id}"><div class="t"><span>${esc(dt0)}${s.year_ago >= 1 ? ' · ' + X('acum ' + s.year_ago + (s.year_ago === 1 ? ' an' : ' ani'), s.year_ago + (s.year_ago === 1 ? ' year ago' : ' years ago')) : ''}</span><span class="arr">·</span><span>${esc(tr(s.start_name || '—'))} → ${esc(tr(s.end_name || '—'))}</span>${road}${s.reverse ? `<span class="tg">${X('sens invers', 'reverse')}</span>` : ''}</div>
      <div class="m"><span><b>${nf(s.km, 1)}</b> km <small>(${s.dkm > 0 ? '+' : ''}${nf(s.dkm, 0)}%)</small></span>${s.wh_km != null ? `<span><b>${nf(s.wh_km)}</b> Wh/km</span>` : ''}<span><b>${hm(s.total_min)}</b></span>${s.temp != null ? `<span><b>${nf(s.temp, 0)}°</b>${s.dtemp != null ? ' <small>(' + (s.dtemp > 0 ? '+' : '') + nf(s.dtemp, 0) + '°)</small>' : ''}</span>` : ''}<span>${season}</span>${s.n_charges ? `<span>${s.n_charges} ${X('încărcări', 'charges')}</span>` : ''}</div></a>`;
  }).join('');
  return `<div class="pchips">${chip('all', X('Toate', 'All'), all.length)}${chip('other', X('Alt drum', 'Other road'), nOther)}${chip('same', X('Același drum', 'Same road'), nSame)}</div>${rows || `<p class="note">${X('Nimic pentru filtrul ales.', 'Nothing for this filter.')}</p>`}`;
}
async function ctSuggest(mainId, ids, pick, quiet) {
  const box = document.getElementById('ct_sim');
  if (!box || !(mainId > 0)) return;
  box.innerHTML = quiet ? '' : `<p class="note">${X('Caut călătorii similare…', 'Looking for similar trips…')}</p>`;
  let j; try { j = await api('/api/trips/similar?id=' + mainId + '&car=' + car); } catch (e) { box.innerHTML = ''; return; }
  if (document.getElementById('ct_sim') !== box) return;                          // s-a schimbat pagina intre timp
  if (!(j.suggestions || []).length) { box.innerHTML = quiet ? '' : `<p class="note">${X('Nicio călătorie similară (plecare și sosire la sub ' + nf(j.radius_km || 1, 1) + ' km, distanța ±20%).', 'No similar trip (start and end within ' + nf(j.radius_km || 1, 1) + ' km, distance ±20%).')}</p>`; return; }
  const draw = () => {
    box.innerHTML = `<h2>${X('Călătorii similare', 'Similar trips')}</h2><div class="card" style="padding:8px 12px"><p class="note" style="margin:0 0 6px">${X('Aceeași plecare și sosire (și în sens invers), distanță apropiată; cele din aceeași perioadă a anului sunt primele. Atinge una ca s-o compari.', 'Same start and end (and the reverse), similar distance; the ones from the same time of year come first. Tap one to compare it.')}${j.total > j.suggestions.length ? ' ' + X('Primele ' + j.suggestions.length + ' din ' + j.total + '.', 'First ' + j.suggestions.length + ' of ' + j.total + '.') : ''}</p>${ctSugRows(j, ids)}</div>`;
    box.querySelectorAll('[data-ctsf]').forEach((b) => b.onclick = () => { CTS.f = b.dataset.ctsf; draw(); });
    box.querySelectorAll('[data-ctadd]').forEach((a) => a.onclick = (e) => { e.preventDefault(); pick(+a.dataset.ctadd); });
  };
  draw();
}

/* ================= COMPARE ================= */
const CMP = { raf: 0 };
PAGES.compare = {
  nav: 'trips',
  async render(arg) {
    cancelAnimationFrame(CMP.raf);
    const ids = String(arg || '').split(',').map((x) => parseInt(x, 10)).filter((x, i, a) => x > 0 && a.indexOf(x) === i).slice(0, 3);
    const head = `<a class="back" href="#/trips">‹ ${X('Călătorii', 'Trips')}</a><div class="top"><h1>${X('Compară călătorii', 'Compare trips')}</h1><small>${X('Până la trei călătorii pe aceeași hartă. Mașinile pornesc împreună și le vezi unde erau după același timp de la plecare.', 'Up to three trips on one map. The cars start together so you see where each was after the same time since departure.')}</small></div>`;
    const list = await ctTripList();
    let trips = [];
    if (ids.length) {
      try { trips = await Promise.all(ids.map(async (id) => Object.assign(ctBuild(await api('/api/trip/' + id + '?car=' + car)), { id }))); } catch (e) { return head + `<div class="empty">${X('Nu pot încărca călătoriile.', 'Cannot load the trips.')}</div>`; }
      trips = trips.filter((c) => c.tl.length > 1);
    }
    window.__cmp = { ids, trips };
    const opts = list.filter((t) => !ids.includes(t.id)).slice(0, 200).map((t) => `<option value="${t.id}">${esc(new Date(T(t.start)).toLocaleDateString(LOC(), { day: 'numeric', month: 'short', year: '2-digit' }))} · ${esc(tr(t.start_name || '—'))} → ${esc(tr(t.end_name || '—'))} · ${nf(t.km)} km</option>`).join('');
    const chips = trips.map((c, i) => `<div class="ct-trip">${ctDot(CT_COL[i])}<div><b>${i === 0 ? X('Principală', 'Main trip') : X('Comparația ', 'Comparison ') + i}</b><small>${esc(ctName(c))} · ${esc(ctDate(c))}</small></div><a href="#" data-ctrm="${c.id}" aria-label="${X('Scoate', 'Remove')}">✕</a></div>`).join('');
    const picker = ids.length < 3 ? `<div class="addf" style="margin-top:10px"><label>${ids.length ? X('Adaugă o comparație', 'Add a comparison') : X('Alege călătoria principală', 'Pick the main trip')}<select id="ct_add"><option value="">—</option>${opts}</select></label></div>` : '';
    if (!trips.length) return head + `<div class="card cfg">${picker}</div>`;
    return head + `<div class="card cfg" style="padding:10px 14px">${chips}${picker}</div>${ids.length < 3 ? '<div id="ct_sim"></div>' : ''}
      <div id="ctfs"><div class="map big" id="ctmap" style="height:52vh;margin-top:12px"></div>
      <div class="card ct-ctl"><div class="row"><button class="ct-play" id="ct_play" aria-label="play">❚❚</button><input type="range" id="ct_sl" min="0" max="1000" value="0" style="flex:1"><b id="ct_t" class="ct-clk">0m 00s</b></div>
        <div class="seg ct-spd" style="margin:8px 0 0">${[1, 2, 4, 8].map((n) => `<button data-ctsp="${n}" class="${n === 1 ? 'on' : ''}">${n}×</button>`).join('')}</div></div></div>
      <h2>${X('Statistici', 'Statistics')}</h2><div class="card" style="overflow-x:auto;padding:8px 6px"><table class="ct-tab" id="ct_tab"></table></div>`;
  },
  after() {
    const sel = document.getElementById('ct_add');
    const go = (ids) => { location.hash = '#/compare' + (ids.length ? '/' + ids.join(',') : ''); };
    if (sel) sel.onchange = () => { if (sel.value) go([...window.__cmp.ids, +sel.value]); };
    document.querySelectorAll('[data-ctrm]').forEach((a) => a.onclick = (e) => { e.preventDefault(); go(window.__cmp.ids.filter((x) => x !== +a.dataset.ctrm)); });
    ctSuggest((window.__cmp.ids || [])[0], window.__cmp.ids, (id) => { location.hash = '#/compare/' + [...window.__cmp.ids, id].join(','); });
    const trips = window.__cmp.trips, el = document.getElementById('ctmap');
    if (!el || !window.L || !trips.length) return;
    const hash = location.hash, m = ctMap(el, null, document.getElementById('ctfs'));
    const allPts = [];
    const dur = Math.max(...trips.map((c) => c.t1 - c.t0)), dd = trips.map((c) => c.t1 - c.t0);
    const mks = trips.map((c, i) => {
      const ll = c.tl.map((p) => [p.lat, p.lon]); allPts.push(...ll);
      window.L.polyline(ll, { color: CT_COL[i], weight: 4, opacity: .28 }).addTo(m);
      const done = window.L.polyline([], { color: CT_COL[i], weight: 6, opacity: .95, lineCap: 'round', lineJoin: 'round', className: 'glow' }).addTo(m);
      const mk = window.L.marker(ll[0], { icon: window.L.divIcon({ className: '', iconSize: [0, 0], html: `<div class="ct-car" style="--c:${CT_COL[i]}"><u></u><div class="ct-lb p${i}"></div></div>` }), zIndexOffset: 500 - i }).addTo(m);
      return { mk, done, lb: null, ar: null };
    });
    m.fitBounds(allPts, { padding: [30, 30] });
    mks.forEach((o) => { const root = o.mk.getElement(); o.lb = root.querySelector('.ct-lb'); o.ar = root.querySelector('u'); });
    const sl = document.getElementById('ct_sl'), clk = document.getElementById('ct_t'), pb = document.getElementById('ct_play');
    let e = 0, playing = true, sp = 1, last = performance.now();
    const base = dur / 45000;                                                    // implicit: toata comparatia dureaza ~45 s
    const draw = () => {
      trips.forEach((c, i) => {
        const p = ctAt(c.tl, c.t0 + Math.min(e, dd[i])), o = mks[i], el2 = Math.min(e, dd[i]);
        o.mk.setLatLng([p.lat, p.lon]);
        if (p.v > 1 || p.hd) o.ar.style.transform = `rotate(${Math.round(p.hd || 0)}deg)`;
        const pts = c.tl.slice(0, p.i != null ? p.i + 1 : c.tl.length).map((q) => [q.lat, q.lon]); pts.push([p.lat, p.lon]); o.done.setLatLngs(pts);
        o.lb.innerHTML = `<b>${i === 0 ? X('Principală', 'Main') : X('Comparația ', 'Comparison ') + i}${e >= dd[i] ? ' ✓' : ''}</b><span>${nf(p.v)} km/h · ${nf(p.dist, 1)} km</span><span>${ctClock(el2)}</span><span>${nf(p.soc)}% · ${X('net', 'net')} ${nf(p.used - p.regen, 1)} kWh</span>`;
      });
      sl.value = Math.round(e / dur * 1000); clk.textContent = ctClock(e);
    };
    const frame = (now) => {
      if (!ctLive(hash) || !document.getElementById('ctmap')) return;
      if (playing) { e = Math.min(dur, e + (now - last) * base * sp); if (e >= dur) { playing = false; pb.textContent = '↻'; } }
      last = now; draw(); CMP.raf = requestAnimationFrame(frame);
    };
    sl.oninput = () => { e = sl.value / 1000 * dur; draw(); };
    pb.onclick = () => { if (e >= dur) e = 0; playing = !playing || e === 0 ? true : false; pb.textContent = playing ? '❚❚' : '▶'; };
    document.querySelectorAll('[data-ctsp]').forEach((b) => b.onclick = () => { sp = +b.dataset.ctsp; document.querySelectorAll('[data-ctsp]').forEach((x) => x.classList.toggle('on', x === b)); });
    const S = trips.map((c) => ctStats(c.tl, c.t0, c.t1));
    const rows = [
      [X('Distanță', 'Distance'), (s) => nf(s.dist, 1) + ' km'], [X('Durată totală', 'Total time'), (s) => ctClock(s.dur)],
      [X('În mișcare (rulând)', 'Moving (rolling)'), (s) => ctClock(s.roll)], [X('Staționar în trafic (semafoare, cozi)', 'Stationary in traffic (lights, queues)'), (s) => ctClock(s.idle)],
      [X('Oprit între curse (opriri, încărcare)', 'Stopped between drives (stops, charging)'), (s) => ctClock(s.pause)], [X('Din timp, în mișcare', 'Share of time moving'), (s) => nf(s.pct) + '%'],
      [X('Opriri în trafic (peste 15 s)', 'Traffic stops (over 15 s)'), (s) => nf(s.idleN)], [X('Cea mai lungă oprire în trafic', 'Longest traffic stop'), (s) => s.idleMax ? ctClock(s.idleMax) : '—'],
      [X('Viteză medie în mișcare', 'Avg speed while moving'), (s) => nf(s.vavg) + ' km/h'], [X('Viteză medie totală (cu opriri)', 'Avg speed overall (with stops)'), (s) => nf(s.vtot) + ' km/h'], [X('Viteză maximă', 'Top speed'), (s) => nf(s.vmax) + ' km/h'],
      [X('Consum net', 'Net used'), (s) => nf(s.net, 1) + ' kWh'], [X('Eficiență', 'Efficiency'), (s) => s.wh != null ? nf(s.wh) + ' Wh/km' : '—'],
      [X('Recuperat', 'Regen'), (s) => nf(s.regen, 1) + ' kWh'], [X('Încărcat pe drum', 'Charged on the way'), (s) => nf(s.chg, 1) + ' kWh'],
      [X('Baterie', 'Battery'), (s) => nf(s.soc0) + '→' + nf(s.soc1) + '%'], [X('Opriri', 'Stops'), (s) => nf(s.stops)],
    ];
    document.getElementById('ct_tab').innerHTML = `<tr><th></th>${trips.map((c, i) => `<th>${ctDot(CT_COL[i])}${i === 0 ? X('Principală', 'Main') : i}</th>`).join('')}</tr>` + rows.map(([l, f]) => `<tr><td>${l}</td>${S.map((s) => `<td>${f(s)}</td>`).join('')}</tr>`).join('');
    draw(); CMP.raf = requestAnimationFrame(frame);
  },
};

/* ================= TIMELINE ================= */
PAGES.timeline = {
  nav: 'trips',
  async render(arg) {
    const id = parseInt(arg, 10);
    if (!(id > 0)) { location.replace('#/trips'); return ''; }
    let c;
    try { c = Object.assign(ctBuild(await api('/api/trip/' + id + '?car=' + car)), { id }); } catch (e) { c = null; }
    const back = `<a class="back" href="#/tripd/${id}">‹ ${X('Călătorie', 'Trip')}</a>`;
    if (!c || c.tl.length < 2) return back + `<div class="empty">${X('Nu există puncte GPS pentru această călătorie.', 'No GPS points for this trip.')}</div>`;
    window.__tl = c;
    return back + `<div class="top"><h1 style="font-size:21px">${esc(ctName(c))}</h1><small>${esc(ctDate(c))} · ${nf(c.km, 1)} km · ${ctClock(c.t1 - c.t0)}</small></div>
      <div class="map big" id="tlmap" style="height:38vh"></div>
      <div class="ct-sw"><div class="ct-cards" id="tl_cards"><div class="ct-c cur" id="tl_cur"></div><div class="ct-c" id="tl_gen"></div><div class="ct-c" id="tl_alt"></div><div class="ct-c" id="tl_en"></div></div><div class="ct-dots" id="tl_dots"><i class="on"></i><i></i><i></i><i></i></div></div>
      <div class="card ct-chart"><div class="ct-top"><b id="tl_d"></b><b id="tl_e"></b><a href="#" id="tl_reset">${X('Toată călătoria', 'Whole trip')}</a></div>
        <div class="ct-plot" id="tl_plot"><svg viewBox="0 0 1000 200" preserveAspectRatio="none" id="tl_svg"></svg><div class="ct-out l" id="tl_ol"></div><div class="ct-out r" id="tl_or"></div><div class="ct-sel" id="tl_sel"><i class="ct-h l" id="tl_hl"></i><i class="ct-h r" id="tl_hr"></i></div><div class="ct-cursor" id="tl_cs"></div></div>
        <div class="ct-ax"><span id="tl_a0"></span><span id="tl_a1"></span></div>
        <div class="ct-leg"><span style="--c:#b69bff">${X('Altitudine', 'Altitude')}</span><span style="--c:#ff9a3c">${X('Baterie', 'Battery')}</span><span style="--c:#8f99a4">${X('Staționare', 'Stationary')}</span><span style="--c:#6fd6b8">${X('Încărcare', 'Charging')}</span></div></div>
      <div class="toast" aria-live="polite">${X('Trage mânerele ca să alegi o porțiune; atinge graficul ca să muți cursorul. Cardurile se pot trage lateral.', 'Drag the handles to choose a section; touch the chart to move the cursor. The cards swipe sideways.')}</div>`;
  },
  after() {
    const c = window.__tl, el = document.getElementById('tlmap');
    if (!c || !el || !window.L) return;
    const hash = location.hash, tl = c.tl, span = c.t1 - c.t0, L = window.L, m = ctMap(el);
    const ll = tl.map((p) => [p.lat, p.lon]);
    L.polyline(ll, { color: '#8f99a4', weight: 5, opacity: .5 }).addTo(m);
    const hi = L.polyline(ll, { color: '#2f9e78', weight: 6, opacity: .95, lineCap: 'round' }).addTo(m);
    m.fitBounds(ll, { padding: [24, 24] });
    c.stops.forEach((s) => { if (s.lat != null) L.circleMarker([s.lat, s.lon], { radius: 8, color: '#0b0d10', weight: 2, fillColor: s.kind === 'charge' ? '#6fd6b8' : '#8f99a4', fillOpacity: 1 }).bindTooltip((s.kind === 'charge' ? '⚡ ' : '⏸ ') + tr(s.name || '')).addTo(m); });
    const cur = L.circleMarker(ll[0], { radius: 9, color: '#fff', weight: 3, fillColor: '#4c8dff', fillOpacity: 1 }).addTo(m);
    // grafic: altitudine + baterie (fiecare pe scara ei), benzi pentru opriri / incarcari
    const W = 1000, H = 200, x = (t) => (t - c.t0) / span * W;
    const rng = (k) => { let a = Infinity, b = -Infinity; tl.forEach((p) => { a = Math.min(a, p[k]); b = Math.max(b, p[k]); }); return [a, Math.max(b, a + 1)]; };
    const [e0, e1] = rng('ele'), path = (k, lo, hiV) => tl.map((p, i) => (i ? 'L' : 'M') + x(p.t).toFixed(1) + ' ' + (H - 8 - (p[k] - lo) / (hiV - lo) * (H - 16)).toFixed(1)).join('');
    let bands = '';
    tl.forEach((p, i) => { if (i && p.st !== 'd') bands += `<rect x="${x(tl[i - 1].t).toFixed(1)}" y="0" width="${Math.max(1.5, x(p.t) - x(tl[i - 1].t)).toFixed(1)}" height="${H}" fill="${p.st === 'c' ? '#6fd6b8' : '#8f99a4'}" opacity="${p.st === 'c' ? .28 : .2}"/>`; });
    document.getElementById('tl_svg').innerHTML = bands + `<path d="${path('ele', e0, e1)}" fill="none" stroke="#b69bff" stroke-width="2.2" vector-effect="non-scaling-stroke"/><path d="${path('soc', 0, 100)}" fill="none" stroke="#ff9a3c" stroke-width="2.6" vector-effect="non-scaling-stroke"/>`;
    const q = (id) => document.getElementById(id), plot = q('tl_plot'), cu = esc(CU());
    let fa = 0, fb = 1, fc = 0;                                                  // selectia [fa, fb] si cursorul fc (fractii din durata)
    const tAt = (f) => c.t0 + f * span;
    const row = (l, v) => `<div class="ct-kv"><i>${l}</i><b>${v}</b></div>`;
    const sub = (a, b) => ll.filter((_, i) => tl[i].t >= a && tl[i].t <= b);
    function cards() {
      const a = tAt(fa), b = tAt(fb), s = ctStats(tl, a, b), p = ctAt(tl, tAt(fc));
      q('tl_d').textContent = nf(s.dist, 1) + ' km'; q('tl_e').textContent = ctClock(s.dur);
      q('tl_a0').textContent = ctTod(a); q('tl_a1').textContent = ctTod(b);
      q('tl_cur').innerHTML = `<h3>${X('La cursor', 'At cursor')}<small>${ctTod(p.t)}</small></h3><div class="ct-g">${row(X('Viteză', 'Speed'), nf(p.v) + ' km/h')}${row(X('Altitudine', 'Altitude'), nf(p.ele) + ' m')}${row(X('Baterie', 'Battery'), nf(p.soc) + '%')}${row(X('Distanță', 'Distance'), nf(p.dist, 1) + ' km')}${row(X('Consum net', 'Net used'), nf(p.used - p.regen, 1) + ' kWh')}${row(X('Încărcat', 'Charged'), nf(p.chg, 1) + ' kWh')}</div>`;
      q('tl_gen').innerHTML = `<h3>${X('General', 'General')}<small>${X('selecție', 'selection')}</small></h3><div class="ct-g">${row(X('Viteză medie', 'Average speed'), nf(s.vavg, 1) + ' km/h')}${row(X('Viteză maximă', 'Top speed'), nf(s.vmax, 1) + ' km/h')}${row(X('Opriri', 'Stops'), nf(s.stops))}${row(X('În mișcare', 'Moving time'), ctClock(s.roll))}${row(X('Staționar în trafic', 'Stationary in traffic'), ctClock(s.idle))}${row(X('Opriri în trafic', 'Traffic stops'), nf(s.idleN) + (s.idleMax ? ' · ' + ctClock(s.idleMax) : ''))}${row(X('Distanță', 'Distance'), nf(s.dist, 1) + ' km')}${row(X('Durată', 'Duration'), ctClock(s.dur))}</div>`;
      q('tl_alt').innerHTML = `<h3>${X('Altitudine', 'Altitude')}<small>${X('selecție', 'selection')}</small></h3><div class="ct-g">${row(X('Minimă', 'Minimum'), nf(s.emin) + ' m')}${row(X('Maximă', 'Maximum'), nf(s.emax) + ' m')}${row(X('Urcare', 'Ascent'), '↑ ' + nf(s.up) + ' m')}${row(X('Coborâre', 'Descent'), '↓ ' + nf(s.down) + ' m')}</div>`;
      q('tl_en').innerHTML = `<h3>${X('Energie', 'Energy')}<small>${X('selecție', 'selection')}</small></h3><div class="ct-g">${row(X('Consum net', 'Net used'), nf(s.net, 1) + ' kWh')}${row(X('Recuperat', 'Regen'), nf(s.regen, 1) + ' kWh')}${row(X('Încărcat', 'Charged'), nf(s.chg, 1) + ' kWh')}${row(X('Eficiență', 'Efficiency'), s.wh != null ? nf(s.wh) + ' Wh/km' : '—')}${row(X('Baterie', 'Battery'), nf(s.soc0) + '→' + nf(s.soc1) + '%')}</div>`;
    }
    function layout(fit) {
      q('tl_sel').style.cssText = `left:${fa * 100}%;width:${(fb - fa) * 100}%`;
      q('tl_ol').style.width = fa * 100 + '%'; q('tl_or').style.width = (1 - fb) * 100 + '%';
      q('tl_cs').style.left = fc * 100 + '%';
      const a = tAt(fa), b = tAt(fb), A = ctAt(tl, a), B = ctAt(tl, b), pts = [[A.lat, A.lon], ...sub(a, b), [B.lat, B.lon]];
      hi.setLatLngs(pts); const p = ctAt(tl, tAt(fc)); cur.setLatLng([p.lat, p.lon]);
      if (fit && pts.length > 1) m.fitBounds(pts, { padding: [24, 24] });
      cards();
    }
    const frac = (ev) => { const r = plot.getBoundingClientRect(); return Math.min(1, Math.max(0, (ev.clientX - r.left) / Math.max(1, r.width))); };
    const MIN = Math.max(.02, 120000 / span);
    const drag = (which) => (ev) => {
      ev.preventDefault(); ev.stopPropagation(); const t = ev.currentTarget; try { t.setPointerCapture(ev.pointerId); } catch (e) { /* ignore */ }
      const mv = (e2) => {
        const f = frac(e2);
        if (which === 'l') fa = Math.min(f, fb - MIN); else fb = Math.max(f, fa + MIN);
        fc = Math.min(fb, Math.max(fa, fc)); layout(false);
      };
      const up = () => { t.removeEventListener('pointermove', mv); t.removeEventListener('pointerup', up); t.removeEventListener('pointercancel', up); layout(true); };
      t.addEventListener('pointermove', mv); t.addEventListener('pointerup', up); t.addEventListener('pointercancel', up);
    };
    q('tl_hl').onpointerdown = drag('l'); q('tl_hr').onpointerdown = drag('r');
    const setCur = (ev) => { fc = Math.min(fb, Math.max(fa, frac(ev))); layout(false); };
    plot.onpointerdown = (ev) => { setCur(ev); const mv = (e2) => setCur(e2), up = () => { plot.removeEventListener('pointermove', mv); plot.removeEventListener('pointerup', up); }; plot.addEventListener('pointermove', mv); plot.addEventListener('pointerup', up); };
    plot.onmousemove = (ev) => { if (!ev.buttons) setCur(ev); };
    q('tl_reset').onclick = (ev) => { ev.preventDefault(); fa = 0; fb = 1; layout(true); };
    const cs = q('tl_cards'), dots = q('tl_dots').children;
    cs.onscroll = () => { const k = Math.round(cs.scrollLeft / Math.max(1, cs.clientWidth * .86)); [...dots].forEach((d, i) => d.classList.toggle('on', i === Math.min(dots.length - 1, k))); };
    layout(false);
    if (!ctLive(hash)) return;
  },
};

'use strict';
/* Clima, control incarcare, HomeLink, notificari si reluarea animata a traseului.
   Se incarca inainte de app.js; foloseste din app.js (la momentul apelului): $, api, S, car, cur, nf, T, tr, esc, hm, tm, ico, getPin, setHtml, LANG, LOC, view. */
const X = (ro, en) => LANG === 'en' ? en : ro;
const EN2 = {
  'Clima': 'Climate', 'Poartă': 'Gate', 'Notificări': 'Notifications', 'Control încărcare': 'Charging control', 'Reluare traseu': 'Replay route',
  'Cablu conectat': 'Cable connected', 'Încărcare terminată': 'Charging complete', 'Ușă / portbagaj deschise': 'Door / trunk open', 'Trimite test': 'Send test',
  'Nicio notificare încă.': 'No notifications yet.', 'Deschizi poarta (HomeLink)?': 'Open the gate (HomeLink)?', 'Temperatură': 'Temperature',
  'Scaune încălzite': 'Heated seats', 'Volan încălzit': 'Heated steering wheel', 'Dezgheață (max)': 'Defrost (max)', 'Protecție supraîncălzire habitaclu': 'Cabin overheat protection',
};

/* ---------- comune ---------- */
const toast = (id, t, cls) => { const m = document.getElementById(id); if (m) { m.textContent = t; m.className = 'toast ' + (cls || ''); } };
async function fire(name, label, arg, msgId) {
  if (S.public_demo) { toast(msgId, X('Demonstrație — comenzile sunt dezactivate.', 'Demo — commands are disabled.'), 'bad'); return null; }
  const pin = getPin(); if (!pin) return null;
  toast(msgId, label + '…', 'busy');
  try {
    const r = await fetch('/api/cmd/' + name, { method: 'POST', headers: { 'X-Pin': pin, 'Content-Type': 'application/json' }, body: JSON.stringify({ car, arg }) });
    const j = await r.json();
    if (r.status === 403) { localStorage.removeItem('pin'); toast(msgId, tr('PIN greșit.'), 'bad'); return null; }
    toast(msgId, j.ok ? '✓ ' + label : '✗ ' + label + (j.reason ? ' — ' + j.reason : ''), j.ok ? 'ok' : 'bad');
    return j;
  } catch (e) { toast(msgId, '✗ ' + label + ' — ' + e.message, 'bad'); return null; }
}
const hhmm = (m) => String(Math.floor(m / 60) % 24).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
const toMin = (s) => { const [h, m] = (s || '0:0').split(':'); return (+h || 0) * 60 + (+m || 0); };
const DAYN = [[1, 'D', 'Sun'], [2, 'L', 'Mon'], [4, 'M', 'Tue'], [8, 'M', 'Wed'], [16, 'J', 'Thu'], [32, 'V', 'Fri'], [64, 'S', 'Sat']];
const daysTxt = (m) => m === 127 ? X('Zilnic', 'Daily') : m === 62 ? X('Luni–Vineri', 'Weekdays') : m === 65 ? X('Weekend', 'Weekend') : DAYN.filter((d) => m & d[0]).map((d) => X(d[1], d[2])).join(' ');
const sw = (id, on, label) => `<label class="sw"><span>${label}</span><input type="checkbox" id="${id}" ${on ? 'checked' : ''}><i></i></label>`;
const lsGet = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } };
const lsSet = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ignore */ } };

/* ---------- CLIMA ---------- */
const SEATS = [[0, 'seat_heater_left', 'fl'], [1, 'seat_heater_right', 'fr'], [2, 'seat_heater_rear_left', 'rl'], [4, 'seat_heater_rear_center', 'rc'], [5, 'seat_heater_rear_right', 'rr']];
let CL = {};
function pageClimate() {
  return `<div class="top row"><div><h1>Clima</h1><small id="clsub"></small></div><div class="sp"></div><span class="pill" id="clpill"></span></div>
  <div id="cl"><div class="empty">…</div></div>`;
}
async function afterClimate() {
  const c = cur(); if (!c) return;
  const L = c.live || {};
  let vd = {}; try { vd = await api('/api/vdata?car=' + c.id); } catch (e) { /* ignore */ }
  const cs = vd.climate_state || {}, saved = lsGet('cl_' + c.id, {});
  const has = cs.driver_temp_setting != null;
  CL = {
    on: L.is_climate_on, temp: has ? cs.driver_temp_setting : (saved.temp ?? 21),
    seats: Object.fromEntries(SEATS.map(([i, k]) => [i, has ? (cs[k] || 0) : (saved.seats?.[i] || 0)])),
    wheel: has ? !!cs.steering_wheel_heater : !!saved.wheel, defrost: has ? !!cs.is_front_defroster_on : !!saved.defrost,
    cop: has ? (cs.cabin_overheat_protection || 'Off') : (saved.cop || 'Off'), copT: has ? (cs.cop_activation_temperature || 'High') : (saved.copT || 'High'),
  };
  const sub = $('#clsub'), pill = $('#clpill');
  if (sub) sub.textContent = nf(L.inside_temp, 1) + '° ' + X('în mașină', 'inside') + ' · ' + nf(L.outside_temp, 1) + '° ' + X('afară', 'outside');
  if (pill) { pill.className = 'pill ' + (L.is_climate_on ? 'ok' : ''); pill.textContent = L.is_climate_on ? tr('Climatizare pornită') : tr('Climatizare oprită'); }
  const note = vd.asleep && !has ? `<p class="note">${X('Mașina doarme: nu cunosc setările curente (arăt ultimele folosite din aplicație). Orice comandă o trezește.', 'The car is asleep: current settings unknown (showing the last ones used here). Any command wakes it.')}</p>` : '';
  const seatBtn = ([i, , pos]) => `<button class="seat ${pos} l${CL.seats[i]}" data-seat="${i}" aria-label="seat ${pos}"><span>${[0, 1, 2, 3].map((n) => `<i class="${n < CL.seats[i] ? 'on' : ''}"></i>`).join('')}</span></button>`;
  const segB = (key, opts, cur2) => `<div class="seg" data-seg="${key}">${opts.map(([v, l]) => `<button data-v="${v}" class="${v === cur2 ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  setHtml($('#cl'), `${note}
  <div class="card cl-hero">
    <div class="row"><button class="act ${L.is_climate_on ? 'on' : ''}" id="clpow" style="min-height:0;flex-direction:row;padding:12px 16px;width:auto">${ico('climate')}<b>${L.is_climate_on ? tr('Oprește clima') : tr('Pornește clima')}</b></button><div class="sp"></div>
      <div class="tstep"><button id="tm">−</button><div><b id="tv">${nf(CL.temp, 1)}</b><small>°C</small></div><button id="tp">+</button></div></div>
  </div>
  <h2>${tr('Scaune încălzite')}</h2>
  <div class="card seats"><img src="/car.png" alt="">${SEATS.map(seatBtn).join('')}</div>
  <div class="card" style="margin-top:10px">${sw('wheel', CL.wheel, tr('Volan încălzit'))}${sw('defrost', CL.defrost, tr('Dezgheață (max)'))}</div>
  <h2>${tr('Protecție supraîncălzire habitaclu')}</h2>
  <div class="card">${segB('cop', [['Off', X('Oprit', 'Off')], ['FanOnly', X('Doar ventilator', 'Fan only')], ['On', X('Pornit', 'On')]], CL.cop)}
    <div class="lim-title" style="margin:12px 4px 0"><span>${X('Se activează peste', 'Activates above')}</span></div>
    ${segB('copT', [['Low', '30°'], ['Medium', '35°'], ['High', '40°']], CL.copT)}</div>
  <div class="toast" id="climsg">${tr('Comenzile pot trezi mașina (durează câteva secunde).')}</div>`);
  const save = () => lsSet('cl_' + c.id, { temp: CL.temp, seats: CL.seats, wheel: CL.wheel, defrost: CL.defrost, cop: CL.cop, copT: CL.copT });
  const M = 'climsg';
  $('#clpow').onclick = async () => { const j = await fire(L.is_climate_on ? 'climate_off' : 'climate_on', L.is_climate_on ? tr('Oprește clima') : tr('Pornește clima'), undefined, M); if (j?.ok) { L.is_climate_on = !L.is_climate_on; afterClimate(); } };
  let tt = null;
  const stepT = (d) => { CL.temp = Math.max(15, Math.min(28, Math.round((CL.temp + d) * 2) / 2)); $('#tv').textContent = nf(CL.temp, 1); save(); clearTimeout(tt); tt = setTimeout(() => fire('set_temps', X('Temperatură ', 'Temperature ') + nf(CL.temp, 1) + '°', { driver: CL.temp }, M), 1100); };
  $('#tm').onclick = () => stepT(-.5); $('#tp').onclick = () => stepT(.5);
  view.querySelectorAll('[data-seat]').forEach((b) => b.onclick = async () => {
    const i = +b.dataset.seat, lv = (CL.seats[i] + 1) % 4;
    const j = await fire('seat_heater', X('Scaun ', 'Seat ') + lv, { seat: i, level: lv }, M);
    if (j?.ok) { CL.seats[i] = lv; save(); b.className = 'seat ' + SEATS.find((s) => s[0] === i)[2] + ' l' + lv; b.querySelectorAll('i').forEach((e, n) => e.classList.toggle('on', n < lv)); }
  });
  $('#wheel').onchange = async (e) => { const j = await fire('steering_heater', tr('Volan încălzit'), { on: e.target.checked }, M); if (j?.ok) { CL.wheel = e.target.checked; save(); } else e.target.checked = !e.target.checked; };
  $('#defrost').onchange = async (e) => { const j = await fire('defrost', tr('Dezgheață (max)'), { on: e.target.checked }, M); if (j?.ok) { CL.defrost = e.target.checked; save(); } else e.target.checked = !e.target.checked; };
  view.querySelectorAll('[data-seg] button').forEach((b) => b.onclick = async () => {
    const key = b.parentNode.dataset.seg, v = b.dataset.v;
    const j = key === 'cop' ? await fire('cop', tr('Protecție supraîncălzire habitaclu'), { on: v !== 'Off', fan_only: v === 'FanOnly' }, M)
                            : await fire('cop_temp', tr('Protecție supraîncălzire habitaclu'), { level: ['Low', 'Medium', 'High'].indexOf(v) }, M);
    if (j?.ok) { CL[key] = v; save(); b.parentNode.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b)); }
  });
}

/* ---------- CONTROL INCARCARE (pe pagina Incarcari) ---------- */
function chargeCtlShell() { return '<div id="chctl"></div>'; }
async function afterCharges() {
  const box = $('#chctl'); if (!box) return;
  const c = cur(); if (!c) return;
  let vd = {}; try { vd = await api('/api/vdata?car=' + c.id); } catch (e) { /* ignore */ }
  const st = vd.charge_state || {}, max = st.charge_current_request_max || 32, now = st.charge_current_request || max;
  const asleep = vd.asleep && !vd.charge_state;
  const schedRow = (s, kind) => `<div class="row srow"><div><b>${kind === 'c' ? hhmm(s.start_time ?? 0) + (s.end_enabled ? ' → ' + hhmm(s.end_time ?? 0) : '') : hhmm(s.precondition_time ?? 0)}</b>
      <small>${esc(s.name || '')} ${daysTxt(s.days_of_week ?? 127)}${s.one_time ? ' · ' + X('o dată', 'once') : ''}${s.enabled === false ? ' · ' + X('oprit', 'off') : ''}</small></div><div class="sp"></div>
      <button class="x" data-del="${kind}" data-id="${s.id}" aria-label="delete">✕</button></div>`;
  const dayOpts = `<option value="ALL">${X('Zilnic', 'Daily')}</option><option value="WEEKDAYS">${X('Luni–Vineri', 'Weekdays')}</option><option value="SAT,SUN">${X('Weekend', 'Weekend')}</option>`;
  setHtml(box, `<h2>${tr('Control încărcare')}</h2>
  ${asleep ? `<div class="card"><p class="note" style="margin:0">${X('Mașina doarme — nu pot citi programările fără s-o trezesc.', 'The car is asleep — I cannot read the schedules without waking it.')}</p><div class="links"><a href="#" id="wake">${X('Trezește și citește', 'Wake and read')}</a></div></div>` : `
  <div class="card"><div class="lim-title" style="margin:0 0 8px"><span>${X('Curent de încărcare', 'Charging current')}</span><b id="ampv">${nf(now)} A</b></div>
    <input type="range" id="amps" min="5" max="${max}" value="${Math.min(max, now)}" class="rng-in"><div class="row" style="margin-top:8px"><small class="mut">5 A</small><div class="sp"></div><small class="mut">${max} A</small></div>
    <div class="links"><a href="#" id="ampgo">${X('Aplică curentul', 'Apply current')}</a></div></div>
  <h2>${X('Încărcare programată', 'Scheduled charging')}</h2>
  <div class="card">${(vd.charge_schedules || []).map((s) => schedRow(s, 'c')).join('') || `<div class="mut" style="font-size:13px">${X('Niciun program.', 'No schedules.')}</div>`}
    <div class="addf"><label>${X('Pornește', 'Start')}<input type="time" id="cs0" value="01:00"></label>
      <label>${X('Oprește', 'Stop')}<input type="time" id="cs1" value="06:00"></label>
      <label>${X('Zile', 'Days')}<select id="csd">${dayOpts}</select></label></div>
    ${sw('cs1on', false, X('Folosește și ora de oprire', 'Also use the stop time'))}
    <div class="links"><a href="#" id="csadd">${X('Adaugă program', 'Add schedule')}</a></div></div>
  <h2>${X('Plecare programată (preîncălzire)', 'Scheduled departure (preconditioning)')}</h2>
  <div class="card">${(vd.precondition_schedules || []).map((s) => schedRow(s, 'p')).join('') || `<div class="mut" style="font-size:13px">${X('Niciun program.', 'No schedules.')}</div>`}
    <div class="addf"><label>${X('Plecare la', 'Depart at')}<input type="time" id="ps0" value="07:30"></label><label>${X('Zile', 'Days')}<select id="psd">${dayOpts}</select></label></div>
    <div class="links"><a href="#" id="psadd">${X('Adaugă plecare', 'Add departure')}</a></div></div>`}
  <div class="toast" id="chmsg">${tr('Comenzile pot trezi mașina (durează câteva secunde).')}</div>`);
  const M = 'chmsg', reload = () => setTimeout(afterCharges, 1500);
  const on = (id, fn) => { const e = $('#' + id); if (e) e.onclick = (ev) => { ev.preventDefault(); fn(); }; };
  const amps = $('#amps'); if (amps) amps.oninput = () => { $('#ampv').textContent = amps.value + ' A'; };
  on('wake', async () => { const j = await fire('wake', X('Trezire', 'Wake'), undefined, M); if (j?.ok) afterCharges(); });
  on('ampgo', async () => { await fire('charging_amps', X('Curent ', 'Current ') + amps.value + ' A', { amps: +amps.value }, M); });
  on('csadd', async () => { const j = await fire('charge_schedule_add', X('Program încărcare', 'Charge schedule'), { days: $('#csd').value, start: toMin($('#cs0').value), end: toMin($('#cs1').value), end_on: $('#cs1on').checked, start_on: true }, M); if (j?.ok) reload(); });
  on('psadd', async () => { const j = await fire('precond_add', X('Plecare programată', 'Scheduled departure'), { days: $('#psd').value, time: toMin($('#ps0').value) }, M); if (j?.ok) reload(); });
  box.querySelectorAll('[data-del]').forEach((b) => b.onclick = async () => {
    if (!confirm(X('Ștergi programul?', 'Delete this schedule?'))) return;
    const j = await fire(b.dataset.del === 'c' ? 'charge_schedule_del' : 'precond_del', X('Ștergere program', 'Delete schedule'), { id: b.dataset.id }, M); if (j?.ok) reload();
  });
}

/* ---------- NOTIFICARI (pe pagina Masina) ---------- */
function notifShell() { return `<h2>${tr('Notificări')}</h2><div id="notif"></div>`; }
async function afterNotif() {
  const box = $('#notif'); if (!box || S.public_demo) { if (box) box.innerHTML = ''; return; }
  let n; try { n = await api('/api/notify'); } catch (e) { return; }
  const st = n.settings || {};
  setHtml(box, `<div class="card">${sw('n_plugged', st.plugged, tr('Cablu conectat'))}${sw('n_charge_done', st.charge_done, tr('Încărcare terminată'))}${sw('n_door', st.door, tr('Ușă / portbagaj deschise'))}
    ${n.hook ? '' : `<p class="note" style="margin:8px 0 0">${X('Telefonul nu e legat încă (lipsește NOTIFY_WEBHOOK) — notificările apar doar aici.', 'Phone not linked yet (NOTIFY_WEBHOOK missing) — notifications only show here.')}</p>`}
    <div class="links"><a href="#" id="ntest">${tr('Trimite test')}</a></div>
    <div id="nlist">${(n.events || []).slice(0, 8).map((e) => `<div class="row nrow"><div><b>${esc(e.title)}</b><small>${esc(e.msg)}</small></div><div class="sp"></div><span class="mut" style="font-size:11.5px">${ago(e.t)}</span></div>`).join('') || `<p class="note" style="margin:8px 0 0">${tr('Nicio notificare încă.')}</p>`}</div></div>`);
  ['plugged', 'charge_done', 'door'].forEach((k) => { const e = $('#n_' + k); if (e) e.onchange = () => fetch('/api/notify/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [k]: e.checked }) }); });
  const t = $('#ntest'); if (t) t.onclick = async (ev) => { ev.preventDefault(); await fetch('/api/notify/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); setTimeout(afterNotif, 400); };
}

/* ---------- RELUARE TRASEU (animatie 3D) ---------- */
let RP = null;
const hav = (a, b, c, d) => { const r = Math.PI / 180, x = (c - a) * r, y = (d - b) * r, h = Math.sin(x / 2) ** 2 + Math.cos(a * r) * Math.cos(c * r) * Math.sin(y / 2) ** 2; return 12742 * Math.asin(Math.min(1, Math.sqrt(h))); };
const brg = (a, b, c, d) => { const r = Math.PI / 180, y = Math.sin((d - b) * r) * Math.cos(c * r), x = Math.cos(a * r) * Math.sin(c * r) - Math.sin(a * r) * Math.cos(c * r) * Math.cos((d - b) * r); return (Math.atan2(y, x) / r + 360) % 360; };
const angd = (a, b) => ((b - a + 540) % 360) - 180;
const dur = (s) => { s = Math.round(s); return s >= 3600 ? Math.floor(s / 3600) + ' h ' + String(Math.floor(s % 3600 / 60)).padStart(2, '0') + ' m' : s >= 60 ? Math.floor(s / 60) + 'm ' + String(s % 60).padStart(2, '0') + 's' : s + 's'; };

function loadMapLibre() {
  if (window.maplibregl) return Promise.resolve();
  return new Promise((res, rej) => {
    const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = 'https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.min.css'; document.head.appendChild(l);
    const s = document.createElement('script'); s.src = 'https://cdnjs.cloudflare.com/ajax/libs/maplibre-gl/4.7.1/maplibre-gl.min.js'; s.onload = res; s.onerror = () => rej(new Error('MapLibre')); document.head.appendChild(s);
  });
}

function buildTL(tr2) {
  const segs = tr2.segments.filter((s) => s.points.length > 1);
  let km = 0; segs.forEach((s) => s.points.forEach((p, i) => { if (i) km += hav(s.points[i - 1][1], s.points[i - 1][2], p[1], p[2]); }));
  // timpul animatiei ~ timpul real (comprimat constant) => viteza masinii pe ecran urmeaza viteza reala; opririle scurte la semafor sunt limitate la 40 s
  let realS = 0; segs.forEach((s) => s.points.forEach((p, i) => { if (i) realS += Math.min(40, (+T(p[0]) - +T(s.points[i - 1][0])) / 1000); }));
  const kT = Math.min(200, Math.max(55, km * 2.2)) / Math.max(realS, 1);
  const tl = [], stops = [];
  let pt = 0, dist = 0, used = 0, regen = 0, chg = 0, prev = null;
  segs.forEach((sg, si) => {
    if (si > 0 && prev) {
      const st = tr2.stops[si - 1] || {}, ch = st.kind === 'charge', real1 = +T(sg.points[0][0]);
      const dw = ch ? 3.6 : 2.6, e = Object.assign({}, prev);
      pt += dw; chg += ch ? (st.kwh || 0) : 0;
      Object.assign(e, { pt, rt: real1, soc: ch && st.s1 != null ? st.s1 : prev.soc, chg, dw: true });
      stops.push({ pt0: prev.pt, pt1: pt, lat: prev.lat, lon: prev.lon, kind: ch ? 'charge' : 'stop', sec: (real1 - prev.rt) / 1000, kwh: st.kwh, dc: st.dc, name: st.name, s0: st.s0, s1: st.s1 });
      tl.push(e); prev = e;
    }
    sg.points.forEach((p, i) => {
      const e = { rt: +T(p[0]), lat: p[1], lon: p[2], v: p[3] || 0, soc: p[5] ?? prev?.soc ?? 0, ele: p[6] ?? prev?.ele ?? 0, si };
      if (prev) {
        const first = si > 0 && i === 0, d = first ? 0 : hav(prev.lat, prev.lon, e.lat, e.lon);
        dist += d; pt += Math.max(.015, first ? 0 : Math.min(40, (e.rt - prev.rt) / 1000) * kT);
        if (!first) { const en = (p[4] || 0) * (e.rt - prev.rt) / 3.6e6; if (en > 0) used += en; else regen -= en; }
      }
      Object.assign(e, { pt, dist, used, regen, chg }); tl.push(e); prev = e;
    });
  });
  // traseu neted: spline Hermite (chord-length) intre punctele GPS, ~10 m intre puncte -> fara miscare sacadata
  const dense = [];
  const okN = (x, a) => x && x.si === a.si && !x.dw;
  for (let i = 0; i < tl.length; i++) {
    const a = tl[i], b = tl[i + 1];
    dense.push(a);
    if (!b || a.si !== b.si || a.dw || b.dw) continue;
    const d12 = hav(a.lat, a.lon, b.lat, b.lon); if (d12 < .012) continue;
    const p0 = okN(tl[i - 1], a) ? tl[i - 1] : a, p3 = okN(tl[i + 2], a) ? tl[i + 2] : b, cs = Math.cos(a.lat * Math.PI / 180);
    const P = (e) => [e.lon * cs, e.lat], A = P(p0), B = P(a), C = P(b), D = P(p3);
    const dd = (u, v) => Math.hypot(v[0] - u[0], v[1] - u[1]) || 1e-12, d01 = dd(A, B), dm = dd(B, C), d23 = dd(C, D);
    const m1 = [0, 1].map((k) => (C[k] - A[k]) * dm / (d01 + dm)), m2 = [0, 1].map((k) => (D[k] - B[k]) * dm / (dm + d23));
    const n = Math.min(16, Math.max(1, Math.ceil(d12 * 1000 / 10)));
    for (let j = 1; j < n; j++) {
      const t = j / n, t2 = t * t, t3 = t2 * t, h00 = 2 * t3 - 3 * t2 + 1, h10 = t3 - 2 * t2 + t, h01 = -2 * t3 + 3 * t2, h11 = t3 - t2;
      const x = h00 * B[0] + h10 * m1[0] + h01 * C[0] + h11 * m2[0], y = h00 * B[1] + h10 * m1[1] + h01 * C[1] + h11 * m2[1];
      const e = { lat: y, lon: x / cs, si: a.si };
      ['rt', 'v', 'soc', 'ele', 'pt', 'dist', 'used', 'regen', 'chg'].forEach((k) => { e[k] = a[k] + (b[k] - a[k]) * t; });
      dense.push(e);
    }
  }
  const coords = []; let cd = 0, last = null;
  dense.forEach((e) => { if (!e.dw) { if (last) cd += hav(last.lat, last.lon, e.lat, e.lon); coords.push([e.lon, e.lat]); last = e; } e.cd = cd; e.ci = coords.length; });
  for (let i = dense.length - 1; i >= 0; i--) {                              // directia deplasarii (cu privire in fata ~40 m)
    let h = dense[i + 1]?.hd ?? 0;
    for (let j = i + 1; j < Math.min(dense.length, i + 40); j++) if (hav(dense[i].lat, dense[i].lon, dense[j].lat, dense[j].lon) > .04) { h = brg(dense[i].lat, dense[i].lon, dense[j].lat, dense[j].lon); break; }
    dense[i].hd = h;
  }
  return { tl: dense, stops, coords, km, vAvg: Math.max(km / Math.max(realS / 3600, 1e-6), 10), cdTotal: Math.max(cd, 1e-6), drives: segs.map((s) => s.drive), end: dense[dense.length - 1].pt };
}
function atPh(tl, ph) {
  let lo = 0, hi = tl.length - 1;
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (tl[m].pt <= ph) lo = m; else hi = m; }
  const a = tl[lo], b = tl[hi], f = b.pt > a.pt ? Math.min(1, Math.max(0, (ph - a.pt) / (b.pt - a.pt))) : 0, g = (k) => a[k] + (b[k] - a[k]) * f;
  return { i: lo, ci: a.ci, f, hd: a.hd, si: a.si, lat: g('lat'), lon: g('lon'), rt: g('rt'), v: g('v'), soc: g('soc'), ele: g('ele'), dist: g('dist'), used: g('used'), regen: g('regen'), chg: g('chg'), cd: g('cd') };
}
const WX = (c, day) => c === 0 ? [day ? '☀️' : '🌙', X('Senin', 'Clear')] : c <= 2 ? [day ? '🌤️' : '☁️', X('Parțial noros', 'Partly cloudy')] : c === 3 ? ['☁️', X('Noros', 'Overcast')] : c <= 48 ? ['🌫️', X('Ceață', 'Fog')] :
  c <= 57 ? ['🌦️', X('Burniță', 'Drizzle')] : c <= 67 ? ['🌧️', X('Ploaie', 'Rain')] : c <= 77 ? ['🌨️', X('Ninsoare', 'Snow')] : c <= 82 ? ['🌧️', X('Averse', 'Showers')] : c <= 86 ? ['🌨️', X('Averse de ninsoare', 'Snow showers')] : ['⛈️', X('Furtună', 'Thunderstorm')];
async function fetchWx(lat, lon, t0) {
  const d = new Date(t0), day = d.toISOString().slice(0, 10), old = Date.now() - t0 > 80 * 864e5;
  const u = (old ? 'https://archive-api.open-meteo.com/v1/archive' : 'https://api.open-meteo.com/v1/forecast') + `?latitude=${lat.toFixed(1)}&longitude=${lon.toFixed(1)}&hourly=temperature_2m,weather_code,is_day&start_date=${day}&end_date=${new Date(t0 + 864e5).toISOString().slice(0, 10)}&timezone=auto`;
  const r = await fetch(u); if (!r.ok) throw new Error(r.status); return r.json();
}
function wxAt(w, rt) {
  if (!w?.hourly) return null;
  const k = new Date(rt + (w.utc_offset_seconds || 0) * 1000).toISOString().slice(0, 13) + ':00', i = w.hourly.time.indexOf(k);
  return i < 0 ? null : { t: w.hourly.temperature_2m[i], c: w.hourly.weather_code[i], day: w.hourly.is_day[i] === 1 };
}
const GRAD = (p) => { p = Math.min(.9995, Math.max(.0003, p)); return ['interpolate', ['linear'], ['line-progress'], 0, 'rgba(76,194,160,.5)', p, '#0a6b3a', Math.min(.9999, p + .0002), 'rgba(10,107,58,0)', 1, 'rgba(10,107,58,0)']; };

async function startReplay(id) {
  stopReplay();
  const root = document.createElement('div'); root.id = 'rp';
  root.innerHTML = `<div id="rpmap"></div><div class="rp-top"><button class="rp-btn" id="rpx" aria-label="close">✕</button><div class="rp-clock"><b id="rpt">--:--</b><small id="rpd"></small></div><div class="rp-wx" id="rpw"></div></div>
  <div class="rp-intro" id="rpi"><div class="rp-card"><small>${X('Traseu', 'Route')}</small><h2 id="rpit">…</h2><p id="rpid"></p><span class="rp-load" id="rpl">${X('Se încarcă harta…', 'Loading map…')}</span></div></div>
  <div class="rp-zoom"><button class="rp-btn" id="rpzi" aria-label="zoom in">＋</button><button class="rp-btn" id="rpzo" aria-label="zoom out">−</button><button class="rp-btn fo" id="rpfo" aria-label="follow">◎</button></div>
  <div class="rp-ctl"><button class="rp-btn" id="rpp" aria-label="play">❚❚</button><input type="range" id="rps" min="0" max="1000" value="0"><button class="rp-btn wide" id="rpv">1×</button></div>
  <div class="rp-end" id="rpe"></div>`;
  document.body.appendChild(root);
  const done = () => { stopReplay(); location.hash = '#/drive/' + id; };
  root.querySelector('#rpx').onclick = done;
  let data;
  try { [data] = await Promise.all([api('/api/trip/' + id + '?car=' + car), loadMapLibre()]); } catch (e) { root.querySelector('#rpl').textContent = '✗ ' + e.message; return; }
  if (!document.getElementById('rp')) return;
  if (!data.segments.some((s) => s.points.length > 1)) { root.querySelector('#rpl').textContent = X('Nu există puncte GPS pentru această cursă.', 'No GPS points for this drive.'); return; }
  const T0 = buildTL(data), tl = T0.tl;
  const drv = T0.drives, first = drv[0], last = drv[drv.length - 1];
  const names = [first.start_name, ...data.stops.map((s) => s.name), last.end_name].filter((x, i, a) => x && x !== '—' && a.indexOf(x) === i).slice(0, 4).map((x) => tr(x));
  const t0 = +T(first.start_date), t1 = +T(last.end_date);
  root.querySelector('#rpit').textContent = names.join(' • ') || X('Cursă', 'Drive');
  root.querySelector('#rpid').textContent = new Date(t0).toLocaleDateString(LOC(), { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) + ' · ' + nf(T0.km, 1) + ' km';
  const ml = window.maplibregl;
  const map2 = new ml.Map({ container: 'rpmap', interactive: true, keyboard: false, attributionControl: { compact: true }, center: [tl[0].lon, tl[0].lat], zoom: 12, pitch: 0, fadeDuration: 0, maxPitch: 70,
    style: { version: 8, sources: { osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 19, attribution: '© OpenStreetMap' } },
             layers: [{ id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-saturation': -.25, 'raster-contrast': .05, 'raster-fade-duration': 0 } }] } });
  // zoom de baza: ~230 px/s deplasare pe ecran indiferent cat de lunga e calatoria (nivelul de zoom coboara pe trasee lungi)
  const vg = T0.km / Math.max(T0.end - T0.stops.reduce((s, x) => s + (x.pt1 - x.pt0), 0), 1);
  const zb = Math.max(11.8, Math.min(16.2, Math.log2(156543 * Math.cos(tl[0].lat * Math.PI / 180) * 190 / Math.max(vg * 1000, 1))));
  RP = { root, map: map2, tl, T0, ph: 0, end: T0.end, playing: false, speed: 1, stage: 'intro', last: 0, cb: 0, hd: tl[0].hd, chd: tl[0].hd, zb, z: zb, wx: {}, stopEls: [], follow: true, zoff: 0, zo: 0, freeze: 0, raf: 0, id, t0, t1 };
  const bounds = new ml.LngLatBounds(); T0.coords.forEach((c) => bounds.extend(c));
  const cw = innerWidth < 520 ? 104 : 136;
  map2.once('load', () => {
    root.querySelector('#rpl').remove();
    map2.fitBounds(bounds, { padding: 70, duration: 0 });
    map2.addSource('full', { type: 'geojson', lineMetrics: true, data: { type: 'Feature', geometry: { type: 'LineString', coordinates: T0.coords } } });
    map2.addLayer({ id: 'full-c', type: 'line', source: 'full', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#ffffff', 'line-width': 10, 'line-opacity': .75 } });
    map2.addLayer({ id: 'full-l', type: 'line', source: 'full', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#2f6f4f', 'line-width': 4, 'line-opacity': .3 } });
    map2.addLayer({ id: 'done-l', type: 'line', source: 'full', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-width': 8, 'line-gradient': GRAD(0) } });
    const mk = (cls, html) => { const el = document.createElement('div'); el.className = cls; el.innerHTML = html; return el; };
    const tfmt = (ms) => new Date(ms).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });
    const flag = (cls, txt, lat, lon) => { const el = mk('rp-pin ' + cls, `<i>${cls === 'end' ? '🏁' : '⚑'}</i><span>${txt}</span>`); new ml.Marker({ element: el, anchor: 'bottom' }).setLngLat([lon, lat]).addTo(map2); return el; };
    RP.startEl = flag('start', X('Start ', 'Start ') + tfmt(t0), tl[0].lat, tl[0].lon);
    flag('end', X('Sosire ', 'Arrived ') + tfmt(t1), tl[tl.length - 1].lat, tl[tl.length - 1].lon);
    T0.stops.forEach((s) => {
      const el = mk('rp-pin stop ' + s.kind, `<i>${s.kind === 'charge' ? '⚡' : '⏸'}</i><span>${s.kind === 'charge' ? X('Încărcare ', 'Charging ') + dur(s.sec) + (s.kwh ? ' · +' + nf(s.kwh, 1) + ' kWh' : '') : X('Oprit ', 'Stopped ') + dur(s.sec)}</span>`);
      new ml.Marker({ element: el, anchor: 'bottom' }).setLngLat([s.lon, s.lat]).addTo(map2); RP.stopEls.push([s, el]);
    });
    RP.carEl = mk('rp-car', '<img src="/car.png" alt="">');
    RP.car = new ml.Marker({ element: RP.carEl, rotationAlignment: 'map', pitchAlignment: 'map', rotation: tl[0].hd }).setLngLat([tl[0].lon, tl[0].lat]).addTo(map2);
    // carduri de informatii lipite de masina (ca in filmulet): stanga distanta+altitudine, dreapta baterie+consum
    RP.cardL = mk('rp-fc l', `<i>${X('Distanță', 'Distance')}</i><b id="rkm">0,0<small> km</small></b><span id="rel">0 m</span><em id="rv"></em>`);
    RP.cardR = mk('rp-fc r', `<i>${X('Baterie', 'Battery')}</i><b id="rsoc">—<small>%</small></b><div class="rp-bar"><div id="rbar"></div></div>
      <div class="rp-en"><span><u class="n"></u>${X('Net', 'Net')} <b id="ren">0</b></span><span><u class="g"></u>${X('Recup.', 'Regen')} <b id="rrg">0</b></span><span id="rchw"><u class="c"></u>${X('Încărcat', 'Charged')} <b id="rch">0</b></span></div>`);
    [RP.cardL, RP.cardR].forEach((el) => { el.style.width = cw + 'px'; });
    RP.mL = new ml.Marker({ element: RP.cardL, anchor: 'center', offset: [-(cw / 2 + 34), -6] }).setLngLat([tl[0].lon, tl[0].lat]).addTo(map2);
    RP.mR = new ml.Marker({ element: RP.cardR, anchor: 'center', offset: [cw / 2 + 34, -6] }).setLngLat([tl[0].lon, tl[0].lat]).addTo(map2);
    drv.forEach((d, si) => { const p = data.segments.filter((s) => s.points.length > 1)[si].points[0]; fetchWx(p[1], p[2], +T(p[0])).then((w) => { RP.wx[si] = w; }).catch(() => {}); });
    map2.on('movestart', (e) => { if (e.originalEvent && RP && RP.stage === 'play' && RP.follow) { RP.follow = false; root.querySelector('#rpfo').classList.add('show'); } });
    map2.on('click', onPick);
    root.querySelector('#rpi').classList.add('show');
    RP.introT = setTimeout(flyStart, 3200);
    root.querySelector('#rpi').onclick = flyStart;
    RP.raf = requestAnimationFrame(frame);
  });
  function flyStart() {
    if (!RP || RP.stage !== 'intro') return;
    clearTimeout(RP.introT); RP.stage = 'fly'; root.querySelector('#rpi').classList.remove('show');
    map2.setPadding({ top: Math.round(innerHeight * .3), bottom: 0, left: 0, right: 0 });
    map2.flyTo({ center: [tl[0].lon, tl[0].lat], zoom: RP.zb, pitch: 62, bearing: tl[0].hd, duration: 2800, essential: true, curve: 1.2 });
    map2.once('moveend', () => { if (RP) { RP.stage = 'play'; RP.playing = true; RP.last = performance.now(); RP.z = RP.zb; RP.chd = tl[0].hd; setPlayBtn(); } });
  }
  const clearPop = () => { if (RP.pop) { RP.pop.remove(); RP.pop = null; } if (RP.dot) { RP.dot.remove(); RP.dot = null; } };
  function setFollow() {
    RP.follow = true; root.querySelector('#rpfo').classList.remove('show'); RP.freeze = performance.now() + 700;
    const p = atPh(tl, RP.ph); map2.easeTo({ center: [p.lon, p.lat], zoom: RP.z, bearing: RP.chd, pitch: 62, duration: 650 });
  }
  root.querySelector('#rpfo').onclick = setFollow;
  const zoomBy = (d) => { if (RP.stage === 'play' && RP.follow) RP.zoff = Math.max(-4, Math.min(3.5, RP.zoff + d)); else map2.easeTo({ zoom: map2.getZoom() + d, duration: 250 }); };
  root.querySelector('#rpzi').onclick = () => zoomBy(.7);
  root.querySelector('#rpzo').onclick = () => zoomBy(-.7);
  function onPick(e) {
    if (!RP || (RP.stage !== 'play' && RP.stage !== 'end')) return;
    let best = null, bd = 1e9;
    for (let i = 0; i < tl.length; i += 1) { const q = tl[i]; if (q.dw) continue; const s = map2.project([q.lon, q.lat]), d = (s.x - e.point.x) ** 2 + (s.y - e.point.y) ** 2; if (d < bd) { bd = d; best = q; } }
    if (!best || bd > 90 * 90) return;
    clearPop();
    const q = best, net = Math.max(0, q.used - q.regen);
    RP.dot = new ml.Marker({ element: Object.assign(document.createElement('div'), { className: 'rp-dot' }) }).setLngLat([q.lon, q.lat]).addTo(map2);
    RP.pop = new ml.Popup({ closeButton: true, closeOnClick: false, offset: 14, className: 'rp-pop', maxWidth: '230px' }).setLngLat([q.lon, q.lat])
      .setHTML(`<div class="rp-pk"><b>${tfmt2(q.rt)}</b><small>${new Date(q.rt).toLocaleDateString(LOC(), { weekday: 'short', day: 'numeric', month: 'short' })}</small>
        <div><span>${X('Viteză', 'Speed')}</span><b>${nf(q.v)} km/h</b></div><div><span>${X('Baterie', 'Battery')}</span><b>${nf(q.soc)}%</b></div>
        <div><span>${X('Altitudine', 'Elevation')}</span><b>${nf(q.ele)} m</b></div><div><span>${X('Distanță', 'Distance')}</span><b>${nf(q.dist, 1)} km</b></div>
        <div><span>${X('Consum net', 'Net used')}</span><b>${nf(net, 1)} kWh</b></div><a href="#" class="rp-go">▶ ${X('Redă de aici', 'Play from here')}</a></div>`).addTo(map2);
    RP.pop.on('close', () => { if (RP && RP.dot) { RP.dot.remove(); RP.dot = null; } });
    RP.pop.getElement().querySelector('.rp-go').onclick = (ev) => {
      ev.preventDefault(); clearPop();
      if (RP.stage === 'end') { RP.stage = 'play'; showCards(true); root.querySelector('#rpe').classList.remove('show'); map2.setPadding({ top: Math.round(innerHeight * .3), bottom: 0, left: 0, right: 0 }); }
      RP.ph = q.pt; RP.playing = true; setPlayBtn(); RP.follow = true; root.querySelector('#rpfo').classList.remove('show'); RP.freeze = 0; draw(.016, true);
    };
  }
  const setPlayBtn = () => { root.querySelector('#rpp').textContent = RP.playing ? '❚❚' : '▶'; };
  root.querySelector('#rpp').onclick = () => { if (RP.stage === 'end') return restart(); if (RP.stage !== 'play') return; RP.playing = !RP.playing; setPlayBtn(); };
  root.querySelector('#rpv').onclick = (e) => { RP.speed = RP.speed === 1 ? 2 : RP.speed === 2 ? 4 : 1; e.target.textContent = RP.speed + '×'; };
  const sl = root.querySelector('#rps');
  sl.oninput = () => { if (RP.stage === 'intro' || RP.stage === 'fly') return; RP.playing = false; if (RP.stage === 'end') { map2.setPadding({ top: Math.round(innerHeight * .3), bottom: 0, left: 0, right: 0 }); } RP.stage = 'play'; showCards(true); root.querySelector('#rpe').classList.remove('show'); RP.ph = sl.value / 1000 * RP.end; setPlayBtn(); draw(0.016, true); };
  const showCards = (on) => { [RP.cardL, RP.cardR].forEach((el) => { el.style.display = on ? '' : 'none'; }); };
  function restart() {
    clearPop(); RP.follow = true; root.querySelector('#rpfo').classList.remove('show'); showCards(true); RP.ph = 0; RP.stage = 'play'; RP.playing = true; RP.last = performance.now(); root.querySelector('#rpe').classList.remove('show');
    map2.setPadding({ top: Math.round(innerHeight * .3), bottom: 0, left: 0, right: 0 });
    map2.jumpTo({ center: [tl[0].lon, tl[0].lat], zoom: RP.zb, pitch: 62, bearing: tl[0].hd }); RP.chd = tl[0].hd; setPlayBtn();
  }
  function finish() {
    RP.stage = 'end'; RP.playing = false; setPlayBtn(); showCards(false);
    const p = atPh(tl, RP.end), net = Math.max(0, p.used - p.regen);
    root.querySelector('#rpe').innerHTML = `<div class="rp-card"><small>${X('Sosit', 'Arrived')} · ${tfmt2(t1)}</small><h2>${esc(names[names.length - 1] || '')}</h2>
      <div class="rp-sum"><div><b>${nf(T0.km, 1)}</b><small>km</small></div><div><b>${dur((t1 - t0) / 1000)}</b><small>${X('durată totală', 'total time')}</small></div><div><b>${nf(net, 1)}</b><small>kWh ${X('consum net', 'net used')}</small></div>
      <div><b>${nf(p.regen, 1)}</b><small>kWh ${X('recuperat', 'regenerated')}</small></div>${p.chg ? `<div><b>${nf(p.chg, 1)}</b><small>kWh ${X('încărcat', 'charged')}</small></div>` : ''}</div>
      <button class="rp-cx" id="rphide" aria-label="hide">✕</button>
      <div class="links"><a href="#" id="rpre">↻ ${X('Reia', 'Replay')}</a><a href="#" id="rpclose" style="background:#ffffff14;color:#fff">${X('Închide', 'Close')}</a></div></div>`;
    root.querySelector('#rpe').classList.add('show');
    root.querySelector('#rpre').onclick = (e) => { e.preventDefault(); restart(); };
    root.querySelector('#rpclose').onclick = (e) => { e.preventDefault(); done(); };
    root.querySelector('#rphide').onclick = () => root.querySelector('#rpe').classList.remove('show');
    map2.setPadding({ top: 0, bottom: 0, left: 0, right: 0 });
    map2.fitBounds(bounds, { padding: 90, pitch: 0, bearing: 0, duration: 2400 });
  }
  const tfmt2 = (ms) => new Date(ms).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });
  function draw(dtS, force) {
    const p = atPh(tl, RP.ph), kd = (tau) => force ? 1 : 1 - Math.exp(-dtS / tau);
    RP.car.setLngLat([p.lon, p.lat]); RP.mL.setLngLat([p.lon, p.lat]); RP.mR.setLngLat([p.lon, p.lat]);
    RP.hd = (RP.hd + angd(RP.hd, p.hd) * kd(.25) + 360) % 360;
    RP.chd = (RP.chd + angd(RP.chd, p.hd) * kd(.9) + 360) % 360;
    RP.car.setRotation(RP.hd);
    RP.zo += (RP.zoff - RP.zo) * kd(.25);
    if (RP.stage === 'play' && RP.follow && performance.now() > RP.freeze) {
      RP.z += (RP.zb - Math.max(-1.2, Math.min(1.3, .6 * Math.log2(Math.max(p.v, 10) / T0.vAvg))) - RP.z) * kd(1.2);
      map2.jumpTo({ center: [p.lon, p.lat], bearing: RP.chd, pitch: 62, zoom: RP.z + RP.zo });
    }
    if ((RP.cb++ % 3) === 0 || force) {
      map2.setPaintProperty('done-l', 'line-gradient', GRAD(p.cd / T0.cdTotal));
      $('#rpt').textContent = tfmt2(p.rt);
      $('#rpd').textContent = new Date(p.rt).toLocaleDateString(LOC(), { weekday: 'short', day: 'numeric', month: 'short' });
      $('#rkm').innerHTML = nf(p.dist, 1) + '<small> km</small>';
      $('#rel').textContent = '▲ ' + nf(p.ele) + ' m';
      $('#rv').textContent = p.v > 1 ? nf(p.v) + ' km/h' : '';
      $('#rsoc').innerHTML = nf(p.soc) + '<small>%</small>';
      $('#rbar').style.width = Math.max(0, Math.min(100, p.soc)) + '%'; $('#rbar').className = p.soc < 20 ? 'low' : p.soc < 45 ? 'mid' : '';
      $('#ren').textContent = nf(Math.max(0, p.used - p.regen), 1) + ' kWh'; $('#rrg').textContent = nf(p.regen, 1) + ' kWh';
      $('#rchw').style.display = p.chg > 0 ? '' : 'none'; $('#rch').textContent = nf(p.chg, 1) + ' kWh';
      const w = wxAt(RP.wx[p.si], p.rt), we = $('#rpw');
      if (w) { const [ic, tx] = WX(w.c, w.day); we.innerHTML = `<b>${ic} ${nf(w.t)}°C</b><small>${tx} · ${X('estimat', 'estimated')}</small><small class="cr">Open-Meteo</small>`; we.classList.add('show'); }
      RP.stopEls.forEach(([s, el]) => el.classList.toggle('seen', RP.ph >= s.pt0));
      RP.startEl.classList.toggle('gone', RP.ph > 6);
      $('#rps').value = Math.round(RP.ph / RP.end * 1000);
    }
  }
  function frame(ts) {
    if (!RP) return;
    const dtS = Math.min(.08, Math.max(.001, (ts - RP.last) / 1000));
    if (RP.playing && RP.stage === 'play') {
      RP.ph += dtS * RP.speed;
      if (RP.ph >= RP.end) { RP.ph = RP.end; draw(dtS); finish(); }
    }
    RP.last = ts;
    if (RP.stage === 'play' || RP.stage === 'end' || RP.stage === 'fly') draw(dtS);
    RP.raf = requestAnimationFrame(frame);
  }
}
function stopReplay() {
  if (!RP) { document.getElementById('rp')?.remove(); return; }
  cancelAnimationFrame(RP.raf); clearTimeout(RP.introT);
  try { RP.map.remove(); } catch (e) { /* ignore */ }
  RP.root.remove(); RP = null; document.getElementById('rp')?.remove();
}

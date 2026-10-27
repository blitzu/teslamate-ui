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
  const pin = await getPin(); if (!pin) return null;
  toast(msgId, label + '…', 'busy');
  try {
    const r = await fetch('/api/cmd/' + name, { method: 'POST', headers: { 'X-Pin': pin, 'Content-Type': 'application/json' }, body: JSON.stringify({ car, arg }) });
    const j = await r.json();
    if (r.status === 403 && /PIN/i.test(j.reason || '')) { pinClear(); toast(msgId, tr('PIN greșit.'), 'bad'); return null; }
    toast(msgId, j.ok ? '✓ ' + label + (j.via === 'ble' ? ' · BLE' : '') : '✗ ' + label + (j.reason ? ' — ' + j.reason : ''), j.ok ? 'ok' : 'bad');
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
  const caps = vd.caps || {}, SEATS_SHOWN = SEATS.filter(([i]) => i <= 1 || caps.rear_seats !== false);
  const seatBtn = ([i, , pos]) => `<button class="seat ${pos} l${CL.seats[i]}" data-seat="${i}" aria-label="seat ${pos}"><span>${[0, 1, 2, 3].map((n) => `<i class="${n < CL.seats[i] ? 'on' : ''}"></i>`).join('')}</span></button>`;
  const segB = (key, opts, cur2) => `<div class="seg" data-seg="${key}">${opts.map(([v, l]) => `<button data-v="${v}" class="${v === cur2 ? 'on' : ''}">${l}</button>`).join('')}</div>`;
  setHtml($('#cl'), `${note}
  <div class="card cl-hero">
    <div class="row"><button class="act ${L.is_climate_on ? 'on' : ''}" id="clpow" style="min-height:0;flex-direction:row;padding:12px 16px;width:auto">${ico('climate')}<b>${L.is_climate_on ? tr('Oprește clima') : tr('Pornește clima')}</b></button><div class="sp"></div>
      <div class="tstep"><button id="tm">−</button><div><b id="tv">${nf(CL.temp, 1)}</b><small>°C</small></div><button id="tp">+</button></div></div>
  </div>
  <h2>${tr('Scaune încălzite')}</h2>
  <div class="card seats"><div class="seatimg"><img src="/car.png" alt="">${SEATS_SHOWN.map(seatBtn).join('')}</div></div>${caps.rear_seats === undefined ? `<p class="note" style="margin:6px 4px">${X('Dotările (ex. bancheta încălzită) se detectează automat când mașina e online; până atunci arăt toate scaunele.', 'Equipment (e.g. heated rear seat) is detected automatically when the car is online; until then all seats are shown.')}</p>` : ''}
  <div class="card" style="margin-top:10px">${caps.wheel_heater === false ? '' : sw('wheel', CL.wheel, tr('Volan încălzit'))}${sw('defrost', CL.defrost, tr('Dezgheață (max)'))}</div>
  <h2>${tr('Protecție supraîncălzire habitaclu')}</h2>
  <div class="card">${segB('cop', [['Off', X('Oprit', 'Off')], ['FanOnly', X('Doar ventilator', 'Fan only')], ['On', X('Pornit', 'On')]], CL.cop)}
    <div class="lim-title" style="margin:12px 4px 0"><span>${X('Se activează peste', 'Activates above')}</span></div>
    ${segB('copT', [['Low', '30°'], ['Medium', '35°'], ['High', '40°']], CL.copT)}</div>
  <div class="toast" aria-live="polite" id="climsg">${tr('Comenzile pot trezi mașina (durează câteva secunde).')}</div>`);
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
  if ($('#wheel')) $('#wheel').onchange = async (e) => { const j = await fire('steering_heater', tr('Volan încălzit'), { on: e.target.checked }, M); if (j?.ok) { CL.wheel = e.target.checked; save(); } else e.target.checked = !e.target.checked; };
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
  drawChargeList();
  if (!chRows.length) lfBind('charges', () => render());                              // lista goala: filtrele (perioada/tag) trebuie sa ramana folosibile
  const go = $('#goctl'); if (go) go.onclick = (ev) => { ev.preventDefault(); const t = $('#chctl'); if (t) t.scrollIntoView({ behavior: 'smooth' }); };
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
  <div class="toast" aria-live="polite" id="chmsg">${tr('Comenzile pot trezi mașina (durează câteva secunde).')}</div>`);
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
function notifShell() { return `<h2>${tr('Notificări')}</h2><div id="notif"></div><div class="links"><a href="#/auto">⚙️ ${X('Automatizări', 'Automations')} ›</a><a href="#/sleep">😴 ${X('Somn și repaus', 'Sleep & idle')} ›</a></div>`; }
async function afterNotif() {
  const box = $('#notif'); if (!box || S.public_demo) { if (box) box.innerHTML = ''; return; }
  let n; try { n = await api('/api/notify'); } catch (e) { return; }
  const st = n.settings || {};
  setHtml(box, `<div class="card">${sw('n_plugged', st.plugged, tr('Cablu conectat'))}${sw('n_charge_done', st.charge_done, tr('Încărcare terminată'))}${sw('n_door', st.door, tr('Ușă / portbagaj deschise'))}${sw('n_update', st.update, X('Update software disponibil', 'Software update available'))}${sw('n_low_batt', st.low_batt, X('Baterie sub 20% la parcare', 'Battery below 20% while parked'))}${sw('n_away_only', st.away_only, X('Fără notificări de stare acasă (cablu conectat, uși/frunk deschise, carduri „deschis” și „conectată”) — doar în afara casei', 'No status notifications at home (cable, doors/frunk, "open" and "plugged" cards) — only away from home'))}${sw('n_live', st.live, X('Live Activity pe iPhone (încărcare, ușă deschisă, conectată)', 'iPhone Live Activity (charging, open door, plugged in)'))}${sw('n_live_drive', st.live_drive, X('Live Activity și în timpul condusului', 'Live Activity while driving'))}${sw('n_actions', st.actions, X('Butoane de comandă pe notificări (deblochează cablul, oprește încărcarea, încuie)', 'Command buttons on notifications (release cable, stop charging, lock)'))}${sw('n_app_update', st.app_update, X('Versiune nouă a aplicației', 'New app version'))}
    ${n.hook ? '' : `<p class="note" style="margin:8px 0 0">${X('Telefonul nu e legat încă (lipsește NOTIFY_WEBHOOK) — notificările apar doar aici.', 'Phone not linked yet (NOTIFY_WEBHOOK missing) — notifications only show here.')}</p>`}
    <div class="links"><a href="#" id="ntest">${tr('Trimite test')}</a></div>
    <div id="nlist">${(n.events || []).slice(0, 40).map((e) => `<div class="row nrow"><div><b>${esc(e.title)}</b><small>${esc(e.msg)}</small></div><div class="sp"></div><span class="mut" style="font-size:11.5px">${ago(e.t)}</span></div>`).join('') || `<p class="note" style="margin:8px 0 0">${tr('Nicio notificare încă.')}</p>`}</div></div>`);
  ['plugged', 'charge_done', 'door', 'update', 'low_batt', 'away_only', 'live', 'live_drive', 'actions', 'app_update'].forEach((k) => { const e = $('#n_' + k); if (e) e.onchange = () => fetch('/api/notify/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ [k]: e.checked }) }); });
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
    const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = 'vendor/maplibre-gl.min.css'; document.head.appendChild(l);
    const s = document.createElement('script'); s.src = 'vendor/maplibre-gl.min.js'; s.onload = res; s.onerror = () => rej(new Error('MapLibre')); document.head.appendChild(s);
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
  <div class="rp-zoom"><button class="rp-btn" id="rpzi" aria-label="zoom in">＋</button><button class="rp-btn" id="rpzo" aria-label="zoom out">−</button><button class="rp-btn fo" id="rpfo" aria-label="follow">◎</button><button class="rp-btn vw" id="rptop" aria-label="top view" title="${X('Vedere de sus / înclinată', 'Top view / tilted')}">3D</button><button class="rp-btn vw" id="rpnorth" aria-label="north up" title="${X('Nord mereu în sus', 'North always up')}">N</button></div>
  <div class="rp-ctl"><button class="rp-btn" id="rpp" aria-label="play">❚❚</button><input type="range" id="rps" min="0" max="1000" value="0"><button class="rp-btn" id="rpr" aria-label="record" title="Video">⏺</button><button class="rp-btn wide" id="rpv">1×</button></div>
  <div class="rp-end" id="rpe"></div>`;
  document.body.appendChild(root);
  root.querySelector('#rpi').classList.add('show');                     // "Se incarca harta…" vizibil de la inceput
  const done = () => { stopReplay(); location.hash = '#/drive/' + id; };
  root.querySelector('#rpx').onclick = done;
  let data;
  try { [data] = await Promise.all([api('/api/trip/' + id + '?car=' + car), loadMapLibre()]); } catch (e) { root.querySelector('#rpl').textContent = '✗ ' + e.message; root.querySelector('#rpi').classList.add('show'); return; }
  if (!document.getElementById('rp')) return;
  if (!data.segments.some((s) => s.points.length > 1)) { root.querySelector('#rpl').textContent = X('Nu există puncte GPS pentru această cursă.', 'No GPS points for this drive.'); root.querySelector('#rpi').classList.add('show'); return; }
  const T0 = buildTL(data), tl = T0.tl;
  const drv = T0.drives, first = drv[0], last = drv[drv.length - 1];
  const names = [first.start_name, ...data.stops.map((s) => s.name), last.end_name].filter((x, i, a) => x && x !== '—' && a.indexOf(x) === i).slice(0, 4).map((x) => tr(x));
  const t0 = +T(first.start_date), t1 = +T(last.end_date);
  root.querySelector('#rpit').textContent = names.join(' • ') || X('Cursă', 'Drive');
  root.querySelector('#rpid').textContent = new Date(t0).toLocaleDateString(LOC(), { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) + ' · ' + nf(T0.km, 1) + ' km';
  const ml = window.maplibregl;
  const map2 = new ml.Map({ container: 'rpmap', interactive: true, keyboard: false, attributionControl: { compact: true }, center: [tl[0].lon, tl[0].lat], zoom: 12, pitch: 0, fadeDuration: 0, maxPitch: 70, preserveDrawingBuffer: true,
    style: { version: 8, sources: { osm: { type: 'raster', tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'], tileSize: 256, maxzoom: 19, attribution: '© OpenStreetMap' } },
             layers: [{ id: 'osm', type: 'raster', source: 'osm', paint: { 'raster-saturation': -.25, 'raster-contrast': .05, 'raster-fade-duration': 0 } }] } });
  // zoom de baza: ~230 px/s deplasare pe ecran indiferent cat de lunga e calatoria (nivelul de zoom coboara pe trasee lungi)
  const vg = T0.km / Math.max(T0.end - T0.stops.reduce((s, x) => s + (x.pt1 - x.pt0), 0), 1);
  const zb = Math.max(11.8, Math.min(16.2, Math.log2(156543 * Math.cos(tl[0].lat * Math.PI / 180) * 190 / Math.max(vg * 1000, 1))));
  const VW = (() => { try { return JSON.parse(localStorage.getItem('rp_view') || '{}'); } catch (e) { return {}; } })();
  RP = { top: !!VW.top, north: !!VW.north, root, map: map2, tl, T0, ph: 0, end: T0.end, playing: false, speed: 1, stage: 'intro', last: 0, cb: 0, hd: tl[0].hd, chd: tl[0].hd, zb, z: zb, wx: {}, stopEls: [], follow: true, zoff: 0, zo: 0, freeze: 0, raf: 0, id, t0, t1 };
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
    map2.setPadding(padV());
    map2.flyTo({ center: [tl[0].lon, tl[0].lat], zoom: RP.zb, pitch: pitchV(), bearing: bearV(tl[0].hd), duration: 2800, essential: true, curve: 1.2 });
    map2.once('moveend', () => { if (RP) { RP.stage = 'play'; RP.playing = true; RP.last = performance.now(); RP.z = RP.zb; RP.chd = tl[0].hd; setPlayBtn(); } });
  }
  const clearPop = () => { if (RP.pop) { RP.pop.remove(); RP.pop = null; } if (RP.dot) { RP.dot.remove(); RP.dot = null; } };
  function setFollow() {
    RP.follow = true; root.querySelector('#rpfo').classList.remove('show'); RP.freeze = performance.now() + 700;
    const p = atPh(tl, RP.ph); map2.easeTo({ center: [p.lon, p.lat], zoom: RP.z, bearing: bearV(RP.chd), pitch: pitchV(), duration: 650 });
  }
  root.querySelector('#rpfo').onclick = setFollow;
  const pitchV = () => (RP.top ? 0 : RP.rec ? 50 : 58), bearV = (hd) => (RP.north ? 0 : hd);
  const padV = () => ({ top: RP.top ? 0 : Math.round(innerHeight * .3), bottom: 0, left: 0, right: 0 });
  function applyView(animate) {
    const bt = root.querySelector('#rptop'), bn = root.querySelector('#rpnorth');
    bt.textContent = RP.top ? '2D' : '3D'; bt.classList.toggle('on', RP.top); bn.classList.toggle('on', RP.north);
    map2.setMaxPitch(RP.top ? 0 : 70);
    if (RP.north) { map2.dragRotate.disable(); map2.touchZoomRotate.disableRotation(); } else { map2.dragRotate.enable(); map2.touchZoomRotate.enableRotation(); }
    try { localStorage.setItem('rp_view', JSON.stringify({ top: RP.top, north: RP.north })); } catch (e) { /* ignore */ }
    if (RP.stage === 'play' || RP.stage === 'fly') map2.setPadding(padV());
    if (animate && (RP.stage === 'play' || RP.stage === 'end')) {
      const o = { duration: 600 };
      if (RP.stage === 'play' && RP.follow) { const p = atPh(tl, RP.ph); Object.assign(o, { center: [p.lon, p.lat], pitch: pitchV(), bearing: bearV(RP.chd) }); RP.freeze = performance.now() + 700; }
      else Object.assign(o, { pitch: RP.top ? 0 : map2.getPitch(), bearing: RP.north ? 0 : map2.getBearing() });
      map2.easeTo(o);
    }
  }
  root.querySelector('#rptop').onclick = () => { RP.top = !RP.top; applyView(true); };
  root.querySelector('#rpnorth').onclick = () => { RP.north = !RP.north; applyView(true); };
  applyView(false);
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
      .setHTML(`<div class="rp-pk"><b>${tfmt2(q.rt)}</b><small>${fdate(new Date(q.rt), { weekday: 'short', day: 'numeric', month: 'short' })}</small>
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
  root.querySelector('#rpv').onclick = (e) => { RP.speed = RP.speed === 1 ? 2 : RP.speed === 2 ? 4 : RP.speed === 4 ? .5 : 1; e.target.textContent = RP.speed + '×'; };
  const sl = root.querySelector('#rps');
  sl.oninput = () => { if (RP.stage === 'intro' || RP.stage === 'fly') return; RP.playing = false; if (RP.stage === 'end') { map2.setPadding({ top: Math.round(innerHeight * .3), bottom: 0, left: 0, right: 0 }); } RP.stage = 'play'; showCards(true); root.querySelector('#rpe').classList.remove('show'); RP.ph = sl.value / 1000 * RP.end; setPlayBtn(); draw(0.016, true); };
  const showCards = (on) => { [RP.cardL, RP.cardR].forEach((el) => { el.style.display = on ? '' : 'none'; }); };
  function restart() {
    clearPop(); root.querySelector('#rpe').classList.remove('show'); RP.follow = true; root.querySelector('#rpfo').classList.remove('show'); showCards(true); RP.ph = 0; RP.stage = 'play'; RP.playing = true; RP.last = performance.now(); root.querySelector('#rpe').classList.remove('show');
    map2.setPadding({ top: Math.round(innerHeight * .3), bottom: 0, left: 0, right: 0 });
    map2.jumpTo({ center: [tl[0].lon, tl[0].lat], zoom: RP.zb, pitch: pitchV(), bearing: bearV(tl[0].hd) }); RP.chd = tl[0].hd; setPlayBtn();
  }
  function finish() {
    RP.stage = 'end'; RP.playing = false; setPlayBtn(); showCards(false); stopRecord();
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
    RP.chd = (RP.chd + angd(RP.chd, p.hd) * kd(RP.rec ? 1.6 : .9) + 360) % 360;
    RP.car.setRotation(RP.hd);
    RP.zo += (RP.zoff - RP.zo) * kd(.25);
    if (RP.stage === 'play' && RP.follow && performance.now() > RP.freeze) {
      RP.z += (RP.zb - Math.max(-1.2, Math.min(1.3, .6 * Math.log2(Math.max(p.v, 10) / T0.vAvg))) - RP.z) * kd(1.2);
      map2.jumpTo({ center: [p.lon, p.lat], bearing: bearV(RP.chd), pitch: pitchV(), zoom: RP.z + RP.zo + (RP.rec ? .45 : 0) });
    }
    if ((RP.cb++ % 3) === 0 || force) {
      map2.setPaintProperty('done-l', 'line-gradient', GRAD(p.cd / T0.cdTotal));
      $('#rpt').textContent = tfmt2(p.rt);
      $('#rpd').textContent = fdate(new Date(p.rt), { weekday: 'short', day: 'numeric', month: 'short' });
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

  /* ---------- export video: compune harta + cardurile intr-un canvas si il inregistreaza ---------- */
  const rrect = (c, x, y, w, h, r) => { c.beginPath(); if (c.roundRect) c.roundRect(x, y, w, h, r); else c.rect(x, y, w, h); };
  function compose() {
    const R = RP.rec, c = R.ctx, mc = map2.getCanvas(), W = R.cv.width, H = R.cv.height, k = W / mc.clientWidth, p = atPh(tl, RP.ph);
    c.drawImage(mc, 0, 0, W, H);
    const P = (lon, lat) => { const q = map2.project([lon, lat]); return [q.x * k, q.y * k]; };
    const pill = (txt, x, y, col) => { c.font = `700 ${12 * k}px system-ui,sans-serif`; const w = c.measureText(txt).width + 24 * k; rrect(c, x, y - 12 * k, w, 24 * k, 8 * k); c.fillStyle = '#0b0d10e6'; c.fill(); c.fillStyle = '#fff'; c.textBaseline = 'middle'; c.fillText(txt, x + 12 * k, y); if (col) { c.fillStyle = col; } };
    const disc = (x, y, col, ic) => { c.beginPath(); c.arc(x, y, 14 * k, 0, 7); c.fillStyle = col; c.fill(); c.lineWidth = 2 * k; c.strokeStyle = '#fff'; c.stroke(); c.font = `${14 * k}px system-ui`; c.textAlign = 'center'; c.textBaseline = 'middle'; c.fillStyle = '#fff'; c.fillText(ic, x, y + 1 * k); c.textAlign = 'left'; };
    // optiuni de pe traseu
    const [sx, sy] = P(tl[0].lon, tl[0].lat); if (RP.ph < 6) { disc(sx, sy - 18 * k, '#0b0d10', '⚑'); }
    RP.stopEls.forEach(([st]) => { if (RP.ph >= st.pt0) { const [x, y] = P(st.lon, st.lat); disc(x, y - 18 * k, st.kind === 'charge' ? '#2f8f69' : '#e8943a', st.kind === 'charge' ? '⚡' : '⏸'); pill((st.kind === 'charge' ? X('Încărcare ', 'Charging ') : X('Oprit ', 'Stopped ')) + dur(st.sec), x + 20 * k, y - 18 * k); } });
    // masina
    const [cx, cy] = P(p.lon, p.lat), img = RP.carEl.querySelector('img');
    c.save(); c.translate(cx, cy); c.rotate((RP.hd - map2.getBearing()) * Math.PI / 180); c.scale(1, Math.max(.45, Math.cos(map2.getPitch() * Math.PI / 180))); if (img && img.complete) c.drawImage(img, -17 * k, -36 * k, 34 * k, 72 * k); c.restore();
    // carduri lipite de masina
    const cw = (innerWidth < 520 ? 104 : 136) * k, ch = 84 * k, card = (x, lines, title) => { rrect(c, x, cy - ch / 2 - 6 * k, cw, ch, 14 * k); c.fillStyle = '#0b0d10e6'; c.fill(); c.fillStyle = '#8f99a4'; c.font = `800 ${9 * k}px system-ui`; c.textBaseline = 'top'; c.fillText(title.toUpperCase(), x + 11 * k, cy - ch / 2 + 2 * k); lines.forEach((l, i) => { c.fillStyle = l[1]; c.font = `${i === 0 ? 800 : 700} ${(i === 0 ? 22 : 11.5) * k}px system-ui`; c.fillText(l[0], x + 11 * k, cy - ch / 2 + (i === 0 ? 16 : 42 + (i - 1) * 15) * k); }); };
    if (RP.stage !== 'end') card(cx - cw - 34 * k, [[nf(p.dist, 1) + ' km', '#fff'], ['▲ ' + nf(p.ele) + ' m', '#cfd5db'], [p.v > 1 ? nf(p.v) + ' km/h' : '', '#6fd6b8']], X('Distanță', 'Distance'));
    if (RP.stage !== 'end') card(cx + 34 * k, [[nf(p.soc) + '%', '#fff'], [X('Net ', 'Net ') + nf(Math.max(0, p.used - p.regen), 1) + ' kWh', '#ff9a5c'], [X('Recup. ', 'Regen ') + nf(p.regen, 1), '#6fd6b8'], p.chg > 0 ? [X('Încărcat ', 'Charged ') + nf(p.chg, 1), '#7aa8ff'] : ['', '#fff']], X('Baterie', 'Battery'));
    // ceas + vreme
    c.textAlign = 'center'; c.textBaseline = 'top'; c.font = `800 ${46 * k}px system-ui`; c.lineWidth = 6 * k; c.strokeStyle = '#fffd'; c.fillStyle = '#0b0d10'; const t1s = tfmt2(p.rt); c.strokeText(t1s, W / 2, 14 * k); c.fillText(t1s, W / 2, 14 * k);
    c.font = `800 ${13 * k}px system-ui`; const d1s = fdate(new Date(p.rt), { weekday: 'short', day: 'numeric', month: 'short' }).toUpperCase(); c.strokeText(d1s, W / 2, 64 * k); c.fillText(d1s, W / 2, 64 * k); c.textAlign = 'left';
    const w = wxAt(RP.wx[p.si], p.rt); if (w) { const [ic, tx] = WX(w.c, w.day); rrect(c, W - 150 * k, 12 * k, 138 * k, 54 * k, 14 * k); c.fillStyle = '#0b0d10e6'; c.fill(); c.fillStyle = '#fff'; c.textBaseline = 'top'; c.font = `800 ${16 * k}px system-ui`; c.fillText(ic + ' ' + nf(w.t) + '°C', W - 140 * k, 18 * k); c.fillStyle = '#aab3bd'; c.font = `700 ${10.5 * k}px system-ui`; c.fillText(tx + ' · ' + X('estimat', 'est.'), W - 140 * k, 40 * k); c.fillText('Open-Meteo', W - 140 * k, 53 * k); }
  }
  async function startRecord() {
    if (!window.MediaRecorder) { alert(X('Browserul nu suportă înregistrarea video.', 'This browser does not support video recording.')); return; }
    if (RP.stage === 'intro') flyStart();
    const mc = map2.getCanvas(), k = Math.min(1, 1280 / mc.width), cv = document.createElement('canvas'); cv.width = Math.round(mc.width * k); cv.height = Math.round(mc.height * k);
    const mime = ['video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm'].find((m) => MediaRecorder.isTypeSupported(m)) || '';
    const rec = new MediaRecorder(cv.captureStream(30), mime ? { mimeType: mime, videoBitsPerSecond: 5e6 } : { videoBitsPerSecond: 5e6 }), chunks = [];
    rec.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = () => { const type = rec.mimeType || 'video/webm', ext = type.includes('mp4') ? 'mp4' : 'webm', a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(chunks, { type })); a.download = 'traseu-' + new Date(t0).toISOString().slice(0, 10) + '.' + ext; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 20000); root.classList.remove('recording'); };
    RP.rec = { cv, ctx: cv.getContext('2d'), rec }; root.classList.add('recording'); RP.speed = 1; root.querySelector('#rpv').textContent = '1×'; clearPop();
    if (RP.stage !== 'fly') restart();
    else map2.once('moveend', () => {});
    rec.start(250);
  }
  function stopRecord() { if (!RP.rec) return; const r = RP.rec.rec; RP.rec = null; setTimeout(() => { try { r.stop(); } catch (e) { root.classList.remove('recording'); } }, 1200); }
  root.querySelector('#rpr').onclick = () => { if (RP.rec) return; if (confirm(X('Înregistrez animația ca video (durează cât animația). Continui?', 'Record the animation as a video (takes as long as the animation). Continue?'))) startRecord(); };
  function frame(ts) {
    if (!RP) return;
    const dtS = Math.min(.08, Math.max(.001, (ts - RP.last) / 1000));
    if (RP.playing && RP.stage === 'play') {
      RP.ph += dtS * RP.speed * (RP.rec ? .6 : 1);
      if (RP.ph >= RP.end) { RP.ph = RP.end; draw(dtS); finish(); }
    }
    RP.last = ts;
    if (RP.stage === 'play' || RP.stage === 'end' || RP.stage === 'fly') draw(dtS);
    if (RP.rec) compose();
    RP.raf = requestAnimationFrame(frame);
  }
}
function stopReplay() {
  if (!RP) { document.getElementById('rp')?.remove(); return; }
  cancelAnimationFrame(RP.raf); clearTimeout(RP.introT);
  try { RP.map.remove(); } catch (e) { /* ignore */ }
  RP.root.remove(); RP = null; document.getElementById('rp')?.remove();
}

/* ---------- SOMN si consum in repaus (#/sleep) ---------- */
let sleepDays = 7;
async function pageSleep() {
  const z = await api('/api/sleep?car=' + car + '&days=' + sleepDays);
  const now = Date.now(), span = 48 * 3600e3, t0 = now - span;
  const W = 340, H = 46, x = (ms) => 6 + Math.max(0, Math.min(1, (ms - t0) / span)) * (W - 12);
  const rects = z.runs.map((r) => { const a = +T(r.start), b = r.end ? +T(r.end) : now; if (b < t0) return ''; return `<rect x="${x(a).toFixed(1)}" y="${r.s === 'sleep' ? 8 : 18}" width="${Math.max(1, x(b) - x(Math.max(a, t0))).toFixed(1)}" height="${r.s === 'sleep' ? 20 : 10}" rx="2" fill="${r.s === 'sleep' ? '#7aa8ff' : '#d9ba80'}"/>`; }).join('');
  const ticks = [0, 12, 24, 36, 48].map((h) => { const ms = t0 + h * 3600e3; return `<text x="${x(ms)}" y="${H - 2}" text-anchor="middle">${new Date(ms).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' })}</text>`; }).join('');
  const tl = `<svg viewBox="0 0 ${W} ${H}">${rects}${ticks}</svg><div class="legend"><span><i style="background:#7aa8ff"></i>${X('Doarme', 'Asleep')}</span><span><i style="background:#d9ba80"></i>${X('Trează', 'Awake')}</span></div>`;
  const hint = z.short_wakes >= 4 ? `<div class="card hint"><b>${X('Tipar de treziri scurte', 'Short-wake pattern')}</b><p>${X(`${z.short_wakes} treziri de ~${z.short_med} min în ${z.days} zile (între 8 și 16 min). Treziri periodice regulate arată de obicei un client care „bătătorește" mașina (BLE, telemetrie, o aplicație sau un accesoriu) — nu mașina singură.`, `${z.short_wakes} wakes of ~${z.short_med} min in ${z.days} days (8–16 min). Regular periodic wakes usually mean a client polling the car (BLE, telemetry, an app or an accessory) rather than the car itself.`)}</p></div>` : '';
  const idle = z.idle.map((i) => `<div class="item" style="cursor:default"><div class="t"><span>${esc(i.place || '—')}</span></div><div class="m"><span>${fdate(new Date(T(i.start)), { day: 'numeric', month: 'short' })} ${tm(i.start)} → ${tm(i.end)}</span></div>
    <div class="m"><span><b>${hm(i.hours * 60)}</b></span><span>${X('somn ', 'sleep ')}<b>${i.pct_sleep}%</b></span><span><b>${i.drop > 0 ? '−' : '+'}${nf(Math.abs(i.drop))}%</b></span><span>${i.kwh != null ? '<b>' + nf(i.kwh, 1) + '</b> kWh' : ''}</span><span>${nf(i.per_h * 100 / 100, 2)} %/h</span></div></div>`).join('') || `<div class="mut" style="font-size:13px;padding:8px 0">${X('Nicio perioadă în repaus în acest interval.', 'No idle periods in this range.')}</div>`;
  return `<div class="top"><h1>${X('Staționări', 'Parked')}</h1><small>${X('offline din TeslaMate = adormită', 'TeslaMate offline = asleep')}</small></div>
  <div class="seg">${[3, 7, 14, 30].map((n) => `<button data-sd="${n}" class="${n === sleepDays ? 'on' : ''}">${n} ${X('zile', 'days')}</button>`).join('')}</div>
  <h2>${X('Rezumat', 'Summary')}</h2><div class="grid">${stat(X('Somn', 'Sleep'), nf(z.sleep_pct, 1), '%')}${stat(X('Ore dormite', 'Hours asleep'), nf(z.sleep_h, 1), 'h')}${stat(X('Treziri', 'Wakes'), nf(z.wakes))}${stat(X('Consum în repaus', 'Idle drain'), z.per_h != null ? nf(z.per_h, 2) : '—', '%/h')}${stat(X('Energie în repaus', 'Idle energy'), z.kwh_day != null ? nf(z.kwh_day, 2) : '—', 'kWh/' + X('zi', 'day'))}${stat(X('Pierdut total', 'Total lost'), nf(z.idle_drop), '%')}</div>
  ${hint}
  <h2>${X('Ultimele 48 de ore', 'Last 48 hours')}</h2><div class="card chart">${tl}</div>
  ${sec(X('Somn pe zi (%)', 'Sleep per day (%)'), bars(z.by_day.map((d) => ({ l: new Date(d.day + 'T00:00:00').toLocaleDateString(LOC(), { day: 'numeric', month: 'short' }), v: d.pct })), { color: '#7aa8ff' }))}
  <h2>${X('Perioade în repaus (între curse/încărcări)', 'Idle periods (between drives/charges)')}</h2>${idle}`;
}
function afterSleep() { view.querySelectorAll('[data-sd]').forEach((b) => b.onclick = () => { sleepDays = +b.dataset.sd; render(); }); }

/* ---------- SANATATE BATERIE (pe Statistici) ---------- */
function healthShell() { return `<h2>${X('Sănătatea bateriei', 'Battery health')}</h2><div id="bhealth"><div class="mut" style="font-size:13px">…</div></div>`; }
async function afterHealth() {
  const box = $('#bhealth'); if (!box) return;
  let h; try { h = await api('/api/health_battery?car=' + car); } catch (e) { return; }
  const COL = ['#6fd6b8', '#7aa8ff', '#d9ba80', '#ef7a7a', '#b69bff', '#8fd3ff'];
  let cv = '';
  if (h.curves.length) {
    const Wd = 340, Hd = 130, pl = 30, pt = 8, pb = 18, mx = Math.max(10, ...h.curves.flatMap((c) => c.pts.map((p) => p[1])));
    const X0 = (s) => pl + s / 100 * (Wd - pl - 6), Y0 = (v) => pt + (1 - v / mx) * (Hd - pt - pb);
    cv = `<svg viewBox="0 0 ${Wd} ${Hd}"><path d="M${pl} ${Y0(0)}H${Wd - 6}M${pl} ${Y0(mx / 2)}H${Wd - 6}M${pl} ${Y0(mx)}H${Wd - 6}" stroke="#ffffff10"/>
      ${h.curves.map((c, i) => `<path d="${c.pts.map((p, k) => (k ? 'L' : 'M') + X0(p[0]).toFixed(1) + ' ' + Y0(p[1]).toFixed(1)).join('')}" fill="none" stroke="${COL[i % 6]}" stroke-width="2" stroke-linejoin="round"/>`).join('')}
      <text x="${pl - 5}" y="${Y0(mx) + 3}" text-anchor="end">${nf(mx)}</text><text x="${pl - 5}" y="${Y0(0) + 3}" text-anchor="end">0</text><text x="${pl}" y="${Hd - 3}">0%</text><text x="${Wd - 6}" y="${Hd - 3}" text-anchor="end">100%</text></svg>
      <div class="legend" style="flex-wrap:wrap">${h.curves.map((c, i) => `<span><i style="background:${COL[i % 6]}"></i>${new Date(T(c.date)).toLocaleDateString(LOC(), { day: 'numeric', month: 'short' })} ${c.dc ? 'DC' : 'AC'}</span>`).join('')}</div>`;
  }
  const lab = (k) => k + '°';
  setHtml(box, `<div class="grid">${stat(X('Capacitate utilizabilă', 'Usable capacity'), h.cap_now != null ? nf(h.cap_now, 1) : '—', 'kWh')}${stat(X('Degradare estimată', 'Estimated degradation'), h.degradation != null ? nf(h.degradation, 1) : '—', '%')}</div>
    <p class="note" style="margin:6px 4px">${X('Estimată din energia adăugată pe sesiune / procentul încărcat (sesiuni de minim 15%). Mediană pe ultimele 8 sesiuni vs primele 8.', 'Estimated from energy added per session / percentage charged (sessions of at least 15%). Median of the last 8 sessions vs the first 8.')}</p>
    ${sec(X('Capacitate estimată (kWh)', 'Estimated capacity (kWh)'), line(h.capacity.map((c) => [+T(c.date), c.cap]), { color: '#6fd6b8', dec: 1 }))}
    ${sec(X('Curbe de încărcare (kW după nivel baterie)', 'Charging curves (kW by battery level)'), cv || `<div class="mut" style="font-size:13px;padding:10px 0">${X('Prea puține date', 'Not enough data')}</div>`)}
    ${sec(X('Consum după temperatura exterioară (Wh/km)', 'Consumption by outside temperature (Wh/km)'), bars(h.by_temp.map((x) => ({ l: lab(x.x), v: x.wh })), { color: '#d9ba80' }))}
    ${sec(X('Consum după viteza medie (Wh/km)', 'Consumption by average speed (Wh/km)'), bars(h.by_speed.map((x) => ({ l: x.x + '+', v: x.wh })), { color: '#7aa8ff' }))}`);
}

/* ---------- CURSA: scor + evenimente, grafice interactive legate de harta ---------- */
function driveEvents(ev) {
  if (!ev) return '';
  const cls = ev.score >= 85 ? 'ok' : ev.score >= 65 ? 'warn' : 'bad';
  return `<h2>${X('Stil de condus', 'Driving style')}</h2><div class="grid g3"><div class="st"><i>${X('Scor', 'Score')}</i><b><span class="pill ${cls}" style="font-size:19px">${ev.score}</span></b></div>${stat(X('Frânări bruște', 'Hard braking'), nf(ev.hard_brake))}${stat(X('Accelerări bruște', 'Hard accel.'), nf(ev.hard_accel))}${stat(X('Recuperat', 'Regenerated'), nf(ev.regen_kwh, 1), 'kWh')}</div>
  <p class="note" style="margin:6px 4px">${X('Scor = 100 − 5 × frânări bruște − 3 × accelerări bruște (peste ~3 m/s², măsurate pe 1,5 s); la cursele de peste 30 km penalizarea e micșorată proporțional. Indicativ, calculat din punctele GPS.', 'Score = 100 − 5 × hard braking − 3 × hard acceleration (above ~3 m/s², measured over 1.5 s); drives longer than 30 km get the penalty scaled down. Indicative, computed from GPS samples.')}</p>`;
}
function driveHover(pts, lmap) {
  if (!pts || pts.length < 3 || !window.L || !lmap) return;
  const svgs = view.querySelectorAll('.chart svg');
  let dot = null, tip = $('#dtip');
  const t = (p) => +T(p[0]), t0 = t(pts[0]), t1 = t(pts[pts.length - 1]);
  svgs.forEach((svg) => {
    const line2 = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line2.setAttribute('y1', 6); line2.setAttribute('y2', 92); line2.setAttribute('stroke', '#fff'); line2.setAttribute('stroke-opacity', '.5'); line2.style.display = 'none'; svg.appendChild(line2);
    const move = (e) => {
      const r = svg.getBoundingClientRect(), vb = svg.viewBox.baseVal, xv = (e.clientX - r.left) / r.width * vb.width;
      const f = Math.max(0, Math.min(1, (xv - 30) / (vb.width - 36))), tt = t0 + f * (t1 - t0);
      let i = 0; while (i < pts.length - 1 && t(pts[i + 1]) <= tt) i++;
      const p = pts[i];
      svgs.forEach((s2) => { const l2 = s2.querySelector('line:last-child'); if (l2) { l2.setAttribute('x1', 30 + f * (vb.width - 36)); l2.setAttribute('x2', 30 + f * (vb.width - 36)); l2.style.display = ''; } });
      if (dot) dot.setLatLng([p[1], p[2]]); else dot = window.L.circleMarker([p[1], p[2]], { radius: 8, color: '#fff', weight: 3, fillColor: '#6fd6b8', fillOpacity: 1 }).addTo(lmap);
      if (tip) tip.textContent = tm(p[0]) + ' · ' + nf(p[3]) + ' km/h · ' + nf(p[4]) + ' kW · ' + nf(p[5]) + '% · ' + nf(p[6]) + ' m';
    };
    svg.style.touchAction = 'pan-y';
    svg.addEventListener('pointermove', move); svg.addEventListener('pointerdown', move);
  });
}

/* ---------- AUTOMATIZARI (#/auto) ---------- */
async function pageAuto() {
  const d = await api('/api/rules');
  const nm = (r) => r.type === 'arrive_gate' ? X('La sosirea în „', 'On arriving at “') + esc(r.geofence) + X('” deschide poarta (HomeLink)', '” open the gate (HomeLink)')
    : r.type === 'plug_limit' ? X('La conectarea cablului', 'When the cable is plugged in') + (r.geofence ? X(' la „', ' at “') + esc(r.geofence) + '”' : '') + X(': limită ', ': limit ') + r.limit + '%'
    : X('Pornește clima la ', 'Start climate at ') + esc(r.time) + ' · ' + (r.days === 'WEEKDAYS' ? X('Luni–Vineri', 'Weekdays') : r.days === 'WEEKEND' ? 'Weekend' : X('zilnic', 'daily'));
  const list = d.rules.map((r) => `<div class="row srow"><div><b style="font-size:14px">${nm(r)}</b><small>${r.enabled ? X('activă', 'on') : X('oprită', 'off')}</small></div><div class="sp"></div>
    <label class="sw" style="padding:0"><input type="checkbox" data-rt="${r.id}" ${r.enabled ? 'checked' : ''}><i></i></label><button class="x" data-rd="${r.id}" style="margin-left:10px">✕</button></div>`).join('') || `<div class="mut" style="font-size:13px">${X('Nicio automatizare încă.', 'No automations yet.')}</div>`;
  const fg = d.geofences.map((g) => `<option>${esc(g)}</option>`).join('');
  const log = d.log.map((l) => `<div class="row nrow"><div><b style="color:${l.ok ? 'var(--mint)' : '#ffb3b3'}">${esc(l.msg)}</b></div><div class="sp"></div><span class="mut" style="font-size:11.5px">${ago(l.t)}</span></div>`).join('') || `<p class="note" style="margin:0">${X('Nicio execuție încă.', 'No runs yet.')}</p>`;
  return `<div class="top"><h1>${X('Automatizare', 'Automation')}</h1><small>${X('Rulează pe server, fără PIN — activează doar ce vrei. Comenzile merg prin BLE când e disponibil, altfel prin Tesla.', 'Run on the server without a PIN — enable only what you want. Commands go via BLE when available, otherwise via Tesla.')}</small></div>
  <div class="card">${list}</div>
  <h2>${X('Adaugă', 'Add')}</h2>
  <div class="card"><div class="addf"><label>${X('Tip', 'Type')}<select id="rtype"><option value="arrive_gate">${X('Deschide poarta la sosire', 'Open gate on arrival')}</option><option value="plug_limit">${X('Limită la conectarea cablului', 'Charge limit when plugging in')}</option><option value="depart_climate">${X('Clima înainte de plecare', 'Pre-departure climate')}</option></select></label></div>
    <div class="addf" id="rfields"></div>
    <div class="links"><a href="#" id="radd">${X('Adaugă automatizarea', 'Add automation')}</a></div></div>
  <div class="toast" aria-live="polite" id="rmsg">${X('Poarta și deschiderile cer prudență: GPS-ul poate „sări”. Fiecare regulă are pauză de 10 minute între declanșări.', 'Gates and openings need care: GPS can jitter. Each rule has a 10-minute cooldown between triggers.')}</div>
  <h2>${X('Ultimele execuții', 'Recent runs')}</h2><div class="card">${log}</div>
  <script type="application/json" id="rgf">${JSON.stringify(d.geofences).replace(/</g, '\\u003c')}</script>`;
}
function afterAuto() {
  const gf = JSON.parse(document.getElementById('rgf')?.textContent || '[]'), opt = gf.map((g) => `<option>${esc(g)}</option>`).join('');
  const fields = () => {
    const t = $('#rtype').value;
    $('#rfields').innerHTML = t === 'arrive_gate' ? `<label>${X('Loc (geofence TeslaMate)', 'Place (TeslaMate geofence)')}<select id="rgfn">${opt}</select></label>`
      : t === 'plug_limit' ? `<label>${X('Loc (opțional)', 'Place (optional)')}<select id="rgfn"><option value="">—</option>${opt}</select></label><label>${X('Limită %', 'Limit %')}<input type="number" id="rlim" min="50" max="100" value="80"></label>`
      : `<label>${X('Ora', 'Time')}<input type="time" id="rtime" value="07:30"></label><label>${X('Zile', 'Days')}<select id="rdays"><option value="ALL">${X('Zilnic', 'Daily')}</option><option value="WEEKDAYS">${X('Luni–Vineri', 'Weekdays')}</option><option value="WEEKEND">Weekend</option></select></label>`;
  };
  $('#rtype').onchange = fields; fields();
  const post = async (body) => {
    const pin = await getPin(); if (!pin) return;
    let r, j;
    try { r = await fetch('/api/rules', { method: 'POST', headers: { 'X-Pin': pin, 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); j = await r.json(); } catch (e) { toast('rmsg', '✗ ' + e.message, 'bad'); return; }
    if (r.status === 403) { if (/PIN/i.test(j.reason || '')) pinClear(); toast('rmsg', j.reason || tr('PIN greșit.'), 'bad'); return; }
    if (j.ok === false || j.error) { toast('rmsg', '✗ ' + (j.reason || j.error), 'bad'); return; }
    render();
  };
  $('#radd').onclick = (e) => { e.preventDefault(); const t = $('#rtype').value;
    if (t === 'arrive_gate' && !confirm(X('Poarta se va deschide automat la sosire. Continui?', 'The gate will open automatically on arrival. Continue?'))) return;
    post({ type: t, geofence: $('#rgfn')?.value, limit: $('#rlim')?.value, time: $('#rtime')?.value, days: $('#rdays')?.value }); };
  view.querySelectorAll('[data-rt]').forEach((b) => b.onchange = () => post({ toggle: b.dataset.rt }));
  view.querySelectorAll('[data-rd]').forEach((b) => b.onclick = () => { if (confirm(X('Ștergi automatizarea?', 'Delete this automation?'))) post({ delete: b.dataset.rd }); });
}

/* ---------- Sursa energiei pe pagina unei incarcari ---------- */
async function afterChargeSolar(id) {
  const box = $('#chsolar'); if (!box) return;
  let d; try { d = await api('/api/charge_solar/' + id); } catch (e) { return; }
  if (!d.available) { box.remove(); return; }
  const sh = d.solar_share, cur = S.currency ?? 'lei';
  setHtml(box, `<h2>${X('Sursa energiei (estimat)', 'Energy source (estimate)')}</h2><div class="card"><div class="row"><div class="pct" style="font-size:40px">${sh != null ? sh : '—'}<small>%</small></div><div class="rng">${X('din soare / baterie casă', 'from solar / home battery')}</div></div>
    <div class="bar"><div class="fill" style="width:${sh || 0}%"></div></div>
    <div class="grid" style="margin-top:12px">${stat(X('Din rețea (import)', 'From grid (import)'), nf(d.grid_kwh, 1), 'kWh')}${stat(X('Consumat de mașină', 'Used by the car'), nf(d.car_kwh, 1), 'kWh')}
      ${stat(X('Cost TeslaMate (tarif fix)', 'TeslaMate cost (flat tariff)'), d.cost_tm != null ? nf(d.cost_tm, 2) : '—', cur)}${stat(X('Cost real estimat', 'Estimated real cost'), d.cost_real != null ? nf(d.cost_real, 2) : '—', cur)}</div>
    <p class="note" style="margin:8px 0 0">${X('TeslaMate calculează costul ca energie × tariful fix al locației' + (d.price ? ' (' + nf(d.price, 2) + ' ' + cur + '/kWh)' : '') + ', fără să știe de unde a venit energia. „Cost real” = doar energia importată din rețea × tarif; energia din soare/baterie casă e considerată gratuită. Tariful îl poți seta în Setări → Afișare.', 'TeslaMate computes cost as energy × the location’s flat tariff' + (d.price ? ' (' + nf(d.price, 2) + ' ' + cur + '/kWh)' : '') + ', without knowing where the energy came from. “Real cost” = only the energy imported from the grid × tariff; solar/home-battery energy counts as free. Set the tariff in Settings → Display.')}</p>
    <p class="note" style="margin:8px 0 0">${X('Estimare: importul din rețea al invertorului în timpul încărcării, comparat cu energia consumată de mașină. Consumul casei din rețea în acel interval poate umfla partea „din rețea”.', 'Estimate: the inverter’s grid import during the charge versus the energy the car used. House load drawn from the grid in that window can inflate the “from grid” part.')}</p></div>`);
}

/* ---------- SETARI (#/settings): configurare din aplicatie, fara scripturi ---------- */
async function pageSettings() {
  const lang = `<h2>${X('Limbă', 'Language')}</h2><div class="seg"><button data-lang="ro" class="${LANG === 'ro' ? 'on' : ''}">Română</button><button data-lang="en" class="${LANG === 'en' ? 'on' : ''}">English</button></div>`;
  if (S.public_demo) return `<div class="top"><h1>${X('Setări', 'Settings')}</h1></div>${lang}<p class="note">${X('Setările sunt dezactivate în demonstrație.', 'Settings are disabled in the demo.')}</p>`;
  let c; try { c = await api('/api/config'); } catch (e) { return `<div class="top"><h1>${X('Setări', 'Settings')}</h1></div>${lang}<div class="empty">${X('Setările pot fi schimbate doar de administrator.', 'Only the administrator can change settings.')}</div>`; }
  if (c.error) return `<div class="top"><h1>${X('Setări', 'Settings')}</h1></div>${lang}<div class="empty">${X('Setările pot fi schimbate doar de administrator.', 'Only the administrator can change settings.')}</div>`;
  const f = (label, id, val, o = {}) => `<label class="cf">${label}<input id="${id}" type="${o.secret ? 'password' : (o.type || 'text')}" value="${o.secret ? '' : esc(val ?? '')}" placeholder="${o.secret ? (o.set ? X('••••••  (setat — lasă gol ca să-l păstrezi)', '••••••  (set — leave empty to keep)') : (o.ph || '')) : (o.ph || '')}" autocomplete="off" ${o.attrs || ''}></label>${o.hint ? `<small class="ch">${o.hint}</small>` : ''}`;
  const sec2 = (title, body, save, extra = '') => `<h2>${title}</h2><div class="card cfg">${body}<div class="links"><a href="#" data-save="${save}">${X('Salvează', 'Save')}</a>${extra}</div><div class="toast" aria-live="polite" id="cm-${save}" style="display:none"></div></div>`;
  const fl = c.fleet, ha = c.ha, ac = c.access, dp = c.display, up = c.update || {};
  let ver = {}; try { ver = await api('/api/version'); } catch (x) { /* ignore */ }
  let cl = []; try { cl = await api('/api/changelog?limit=6'); } catch (x) { /* ignore */ }
  const extBy = {};
  for (const x of SETTINGS_EXT.slice().sort((a, b) => (a.order || 9) - (b.order || 9))) { try { const h = await x.render(); if (h) extBy[x.cat || 'data'] = (extBy[x.cat || 'data'] || '') + h; } catch (err) { /* ignore */ } }
  const ext = (cat) => extBy[cat] || '';
  const G = (cat) => `</div><div class="scat" data-cat="${cat}">`;
  const cats = [['general', X('General', 'General')], ['notif', X('Notificări', 'Notifications')], ['conn', X('Conexiuni', 'Connections')], ['security', X('Securitate', 'Security')], ['data', X('Date și funcții', 'Data & features')]];
  if (!cats.some((x) => x[0] === setCat)) setCat = 'general';
  window.__pinSet = fl.pin_set; window.__haSet = ha.token_set && !!ha.url;
  return `<div class="top"><h1>${X('Setări', 'Settings')}</h1><small>${X('Totul se salvează pe server și se aplică imediat. Câmpurile secrete nu se mai afișează după salvare.', 'Everything is saved on the server and applies immediately. Secret fields are never shown again after saving.')}</small></div>
  <div class="seg scats">${cats.map(([k, l]) => `<button data-scat="${k}" class="${k === setCat ? 'on' : ''}">${l}</button>`).join('')}</div>
  <div class="scat" data-cat="general">${lang}
  ${G('security')}${sec2(X('PIN comenzi', 'Command PIN'), f(fl.pin_set ? X('PIN nou (lasă gol ca să-l păstrezi)', 'New PIN (leave empty to keep)') : X('Setează un PIN (min. 6 caractere)', 'Set a PIN (min. 6 characters)'), 'pin', '', { secret: true, set: false, attrs: 'inputmode="numeric"' }) + `<small class="ch">${fl.pin_set ? X('PIN-ul e setat. Orice schimbare cere PIN-ul actual.', 'A PIN is set. Any change asks for the current PIN.') : X('Fără PIN nu se pot trimite comenzi. Prima setare se face doar din rețeaua locală.', 'No commands without a PIN. The first setup must be done on the local network.')}</small>`, 'pin')}
  ${G('conn')}${sec2('Tesla Fleet API', f('Client ID', 'fleet_id', fl.id) + f('Client Secret', 'fleet_secret', '', { secret: true, set: fl.secret_set }) + f(X('Domeniu public (fără https://)', 'Public domain (without https://)'), 'fleet_domain', fl.domain, { ph: 'tesla.example.com' })
    + `<label class="cf">${X('Regiune', 'Region')}<select id="fleet_base"><option value="https://fleet-api.prd.eu.vn.cloud.tesla.com" ${fl.base.includes('.eu.') ? 'selected' : ''}>Europa / Orientul Mijlociu / Africa</option><option value="https://fleet-api.prd.na.vn.cloud.tesla.com" ${fl.base.includes('.na.') ? 'selected' : ''}>America de Nord / Asia-Pacific</option><option value="https://fleet-api.prd.cn.vn.cloud.tesla.cn" ${fl.base.includes('.cn.') ? 'selected' : ''}>China</option></select></label>`
    + `<small class="ch">${X('După salvare, pașii (înregistrare domeniu, conectare cont, cheie virtuală) apar în cardul „Comenzi” din pagina Mașină.', 'After saving, the steps (register domain, connect account, virtual key) appear in the “Controls” card on the Car page.')} <a href="https://github.com/blitzu/teslamate-ui/blob/main/docs/fleet-api.md" target="_blank" rel="noopener" style="color:var(--gold)">${X('Ghid complet', 'Full guide')}</a></small>`, 'fleet')}
  ${sec2('Home Assistant (BLE + energie)', f('URL Home Assistant', 'ha_url', ha.url, { ph: 'http://192.168.1.10:8123' }) + f(X('Token de acces (long-lived)', 'Long-lived access token'), 'ha_token', '', { secret: true, set: ha.token_set })
    + f(X('Prefix entități ESP32 BLE', 'ESP32 BLE entity prefix'), 'ha_prefix', ha.prefix, { ph: 'tesla_ble' }) + sw('ha_ble', ha.ble, X('Comenzi locale prin BLE când e disponibil', 'Local BLE commands when available'))
    + f(X('Senzor import rețea (W) — opțional', 'Grid import sensor (W) — optional'), 'ha_grid', ha.grid, { ph: 'sensor.invertor_grid_import_power', attrs: 'list="ha_sens"', hint: `${X('Puterea (în W) trasă din rețea; pozitivă când imporți. Se completează automat după ce legi Home Assistant.', 'Power (W) drawn from the grid; positive when importing. Filled automatically once Home Assistant is linked.')}<span id="sg-ha_grid"></span>` }) + f(X('Senzor putere fotovoltaică (W) — opțional', 'PV power sensor (W) — optional'), 'ha_pv', ha.pv, { ph: 'sensor.invertor_pv_power', attrs: 'list="ha_sens"', hint: `${X('Puterea totală produsă de panouri (W).', 'Total power produced by the panels (W).')}<span id="sg-ha_pv"></span>` }) + '<datalist id="ha_sens"></datalist>', 'ha', `<a href="#" data-test="ha">${X('Testează conexiunea', 'Test connection')}</a>`)}
  ${G('notif')}${ext('notif')}${sec2(X('Webhook (Home Assistant)', 'Webhook (Home Assistant)'), f('Webhook (POST JSON: title, message, kind)', 'notify_webhook', '', { secret: true, set: c.notify.webhook_set, ph: 'http://homeassistant:8123/api/webhook/…' }), 'notify', `<a href="#" data-test="notify">${X('Trimite test', 'Send test')}</a>`)}
  ${G('conn')}${sec2(X('Import din Tessie', 'Import from Tessie'), f(X('Token API Tessie', 'Tessie API token'), 'tessie_token', '', { secret: true, set: c.tessie.token_set, hint: X('Tokenul de acces din contul tău Tessie (vezi developer.tessie.com). Se folosește doar pentru a citi istoricul tău.', 'The access token from your Tessie account (see developer.tessie.com). Used only to read your history.') })
    + `<label class="cf">${X('Ce se importă', 'What to import')}<select id="imp_mode"><option value="gaps">${X('Tot ce lipsește din TeslaMate (în orice perioadă)', 'Everything missing from TeslaMate (any period)')}</option><option value="older">${X('Doar ce e mai vechi decât prima înregistrare TeslaMate', 'Only what is older than the first TeslaMate record')}</option></select></label>`
    + `<small class="ch">${X('„Tot ce lipsește” aduce din Tessie orice cursă sau încărcare care nu se suprapune cu una existentă în TeslaMate: înainte, între și după datele tale. Se poate rula de mai multe ori.', '“Everything missing” brings every Tessie drive or charge that does not overlap an existing TeslaMate one: before, between and after your data. You can run it more than once.')}</small>`
    + `<div id="timp" class="note" style="margin:12px 2px 0"></div>`, 'tessie', `<a href="#" data-imp="check">${X('Verifică', 'Check')}</a><a href="#" data-imp="dry">${X('Test (fără scriere)', 'Test (no writes)')}</a><a href="#" data-imp="run">${X('Importă', 'Import')}</a><a href="#" data-imp="undo">${X('Anulează importul', 'Undo import')}</a>`)}
  ${G('security')}${S.lan_open ? `<div class="card" style="border:1px solid #ef7a7a66"><b style="color:#ffb3b3">${X('Rețeaua locală nu are parolă', 'The local network has no password')}</b><p class="note" style="margin:6px 0 0">${X('Oricine din Wi-Fi-ul tău poate vedea și comanda mașina. Setează mai jos o parolă (min. 12 caractere): după salvare, și accesul din rețeaua locală va cere autentificare (o singură dată pe dispozitiv, 30 de zile).', 'Anyone on your Wi-Fi can see and control the car. Set a password below (min. 12 characters): once saved, local network access also asks you to sign in (once per device, 30 days).')}</p></div>` : ''}
  ${sec2(X('Acces din internet și roluri', 'Internet access & roles'), f(X('Parolă pentru acces din internet (min. 12 caractere)', 'Password for internet access (min. 12 characters)'), 'app_password', '', { secret: true, set: ac.password_set })
    + f('Cloudflare Access — team domain', 'acc_team', ac.team, { ph: 'echipa.cloudflareaccess.com' }) + f('Cloudflare Access — AUD tag', 'acc_aud', ac.aud) + f(X('E-mail administrator', 'Administrator e-mail'), 'acc_email', ac.email)
    + f(X('Roluri (email:rol, separate prin virgulă; roluri: admin, family, viewer)', 'Roles (email:role, comma-separated; roles: admin, family, viewer)'), 'roles', ac.roles, { ph: 'sotia@example.com:family' })
    + (ac.password_set ? `<button type="button" class="btn" id="logout_all" style="margin-top:10px">${X('Deconectează toate dispozitivele', 'Sign out all devices')}</button><small class="ch">${X('Sesiunile cu parolă de pe telefoane și calculatoare expiră imediat; se cere din nou parola.', 'Password sessions on phones and computers end immediately; the password is asked again.')}</small>` : ''), 'access')}
  ${G('data')}${ext('data')}
  ${G('general')}${sec2(X('Afișare', 'Display'), f(X('Adresa aplicației (se deschide la atingerea notificării)', 'App address (opened when you tap a notification)'), 'app_url', dp.app_url, { ph: 'https://car.example.com' }) + f(X('Consum mașină termică de comparație (l/100 km)', 'Comparison ICE car consumption (l/100 km)'), 'ice_l100', dp.ice_l100, { ph: '7.5' }) + `<label class="cf">${X('Combustibil pentru comparație', 'Fuel for comparison')}<select id="fuel_type"><option value="euro95" ${dp.fuel_type === 'euro95' ? 'selected' : ''}>${X('Benzină (Euro 95) — preț automat zilnic', 'Petrol (Euro 95) — automatic daily price')}</option><option value="diesel" ${dp.fuel_type === 'diesel' ? 'selected' : ''}>${X('Motorină — preț automat zilnic', 'Diesel — automatic daily price')}</option><option value="manual" ${dp.fuel_type === 'manual' ? 'selected' : ''}>${X('Preț manual', 'Manual price')}</option></select></label>` + f(X('Preț manual combustibil (pe litru)', 'Manual fuel price (per litre)'), 'fuel_price', dp.fuel_price, { ph: '7.50' }) + f(X('Țara pentru prețul automat (fuel-prices.eu)', 'Country for the automatic price (fuel-prices.eu)'), 'fuel_country', dp.fuel_country, { ph: 'Romania' }) + f(X('Monedă (lângă costul încărcărilor)', 'Currency (next to charging cost)'), 'currency', dp.currency) + f(X('Preț energie din rețea / kWh (opțional)', 'Grid energy price / kWh (optional)'), 'price_grid', dp.price_grid, { ph: '1.10', hint: X('Folosit pentru „Cost real estimat”. Gol = tariful locației din TeslaMate.', 'Used for “Estimated real cost”. Empty = the location tariff from TeslaMate.') }) + f('URL TeslaMate', 'link_tm', dp.teslamate, { ph: 'http://…:4000' }) + f('URL Grafana', 'link_gf', dp.grafana, { ph: 'http://…:3000' }), 'display')}
  ${sec2(X('Versiune și actualizări', 'Version & updates'),
    `<div class="grid">${stat(X('Versiune instalată', 'Installed version'), 'v' + esc(ver.version || '?') + (ver.commit ? ' · ' + esc(ver.commit) : ''))}${stat(X('Ultima versiune', 'Latest version'), ver.private ? X('build local', 'local build') : (ver.latest ? 'v' + esc(ver.latest) : '—'))}</div>`
    + (ver.newer ? `<div class="card" style="border:1px solid #6fd6b866;margin-top:10px"><b style="color:var(--mint)">${X('Versiune nouă disponibilă', 'New version available')}: v${esc(ver.latest)}</b><pre class="notes">${esc(ver.notes || '')}</pre>
      <p class="note" style="margin:6px 0">${X('Actualizare manuală', 'Manual update')}: <code>docker compose pull &amp;&amp; docker compose up -d</code> ${X('(sau', '(or')} <code>git pull &amp;&amp; docker compose up -d --build</code>)</p>${ver.url ? `<div class="links"><a href="${esc(safeUrl(ver.url))}" target="_blank" rel="noopener">${X('Notele versiunii', 'Release notes')}</a></div>` : ''}</div>` : '')
    + (ver.error ? `<p class="note">${X('Ultima verificare a eșuat: ', 'Last check failed: ')}${esc(ver.error)}</p>` : (ver.checked ? `<p class="note">${X('Ultima verificare: ', 'Last checked: ')}${esc(new Date(ver.checked * 1000).toLocaleString(LOC()))}</p>` : ''))
    + (cl.length ? `<details class="cl"><summary>${X('Ce s-a schimbat', 'What changed')}</summary>${cl.map((x) => `<h3 class="sub">v${esc(x.version)}${x.date ? ' · ' + esc(x.date) : ''}</h3><pre class="notes">${esc(x.notes)}</pre>`).join('')}</details>` : '')
    + `<p class="note" style="margin:10px 2px 0">${ver.private ? '' : (ver.can_apply ? '✓ ' + (ver.builtin_updater ? X('Updater-ul inclus e activ: „Actualizează acum” descarcă și repornește aplicația dintr-un click.', 'The built-in updater is active: “Update now” downloads and restarts the app in one click.') : X('Updater extern configurat: „Actualizează acum” îl apelează.', 'External updater configured: “Update now” calls it.')) : X('Nu ai niciun updater activ: când apare o versiune nouă vezi mai sus comenzile pentru actualizare manuală. „Verifică acum” caută oricând versiuni noi.', 'No updater is active: when a new version appears the manual update commands are shown above. “Check now” looks for new versions any time.'))}</p>`
    + sw('update_check', up.check, X('Verifică automat versiuni noi (o cerere către GitHub, de două ori pe zi)', 'Check for new versions automatically (one request to GitHub, twice a day)'))
    + f(X('Adresa updater-ului (cel inclus: http://updater:8080/update; Watchtower: http://watchtower:8080/v1/update) — opțional', 'Updater address (the built-in one: http://updater:8080/update; Watchtower: http://watchtower:8080/v1/update) — optional'), 'update_webhook', up.webhook, { ph: 'http://watchtower:8080/v1/update' })
    + f(X('Token updater', 'Updater token'), 'update_token', '', { secret: true, set: up.token_set })
    + `<p class="note">${X('Cu un updater configurat apare butonul „Actualizează acum”. Aplicația nu are acces la Docker și nu își poate înlocui singură containerul.', 'With an updater configured an “Update now” button appears. The app has no Docker access and cannot replace its own container.')}</p>`,
    'updates', `<a href="#" data-upd="check">${X('Verifică acum', 'Check now')}</a>${ver.can_apply ? `<a href="#" data-upd="apply">${X('Actualizează acum', 'Update now')}</a>` : ''}`)}
  </div>`;
}
function afterSettings() {
  const showCat = (k) => { setCat = k; try { localStorage.setItem('setcat', k); } catch (x) { /* ignore */ } view.querySelectorAll('.scat').forEach((d) => d.classList.toggle('on', d.dataset.cat === k)); view.querySelectorAll('[data-scat]').forEach((b) => b.classList.toggle('on', b.dataset.scat === k)); };
  view.querySelectorAll('[data-scat]').forEach((b) => b.onclick = () => { showCat(b.dataset.scat); scrollTo(0, 0); });
  showCat(setCat);
  SETTINGS_EXT.forEach((x) => { try { if (x.after) x.after(); } catch (err) { /* ignore */ } });
  view.querySelectorAll('[data-lang]').forEach((b) => b.onclick = () => { LANG = b.dataset.lang; try { localStorage.setItem('lang', LANG); } catch (x) { /* ignore */ } document.documentElement.lang = LANG; render(); });
  if (window.__haSet) api('/api/config/ha_entities').then((d) => {
    if (!d.ok || !d.entities) return;
    const dl = document.getElementById('ha_sens'); if (dl) dl.innerHTML = d.entities.map((e) => `<option value="${esc(e.id)}">${esc(e.name)} (${esc(String(e.state))} W)</option>`).join('');
    [['ha_grid', d.grid], ['ha_pv', d.pv]].forEach(([id, sug]) => {
      const el = document.getElementById(id), box = document.getElementById('sg-' + id); if (!el || !box || !sug) return;
      if (!el.value) { el.value = sug; box.innerHTML = ` <b style="color:var(--mint)">${X('Detectat automat — apasă Salvează', 'Auto-detected — press Save')}</b>`; }
      else if (el.value !== sug) box.innerHTML = ` ${X('Sugestie: ', 'Suggestion: ')}<a href="#" data-sug="${id}|${esc(sug)}" style="color:var(--gold)">${esc(sug)}</a>`;
      box.querySelectorAll('[data-sug]').forEach((a) => a.onclick = (ev) => { ev.preventDefault(); el.value = sug; });
    });
  }).catch(() => {});
  const FIELDS = { pin: ['pin'], fleet: ['fleet_id', 'fleet_secret', 'fleet_domain', 'fleet_base'], ha: ['ha_url', 'ha_token', 'ha_prefix', 'ha_grid', 'ha_pv'], notify: ['notify_webhook'],
    access: ['app_password', 'acc_team', 'acc_aud', 'acc_email', 'roles'], tessie: ['tessie_token'], updates: ['update_webhook', 'update_token'], display: ['app_url', 'ice_l100', 'fuel_type', 'fuel_price', 'fuel_country', 'currency', 'price_grid', 'link_tm', 'link_gf'] };
  const say = (k, t, cls) => { const m = document.getElementById('cm-' + k); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
  const call = async (path, body, k) => {
    const pinSet = (window.__pinSet !== false);
    let pin = pinGet();
    if (!pin && pinSet) pin = await getPin();
    let r, j;
    try { r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Pin': pin || '' }, body: JSON.stringify(body) }); j = await r.json(); }
    catch (err) { return [false, { reason: X('Fără conexiune la server.', 'No connection to the server.') }]; }
    if (r.status === 403 && /PIN/.test(j.reason || '')) { pinClear(); }
    return [r.ok, j];
  };
  const lo = document.getElementById('logout_all');
  if (lo) lo.onclick = async () => {
    if (!confirm(X('Deconectez toate dispozitivele (inclusiv acesta)?', 'Sign out all devices (including this one)?'))) return;
    const [ok, j] = await call('/api/logout_all', {}, 'access');
    if (ok) location.href = '/login'; else say('access', (j && j.reason) || X('Nu am reușit.', 'Failed.'), 'bad');
  };
  view.querySelectorAll('[data-upd]').forEach((b) => b.onclick = async (ev) => {
    ev.preventDefault();
    const apply = b.dataset.upd === 'apply';
    if (apply && !confirm(X('Actualizez aplicația acum? Se repornește câteva zeci de secunde.', 'Update the app now? It restarts for a few tens of seconds.'))) return;
    say('updates', X('Se lucrează…', 'Working…'), 'busy');
    const [ok, j] = await call(apply ? '/api/update/apply' : '/api/update/check', {}, 'updates');
    if (apply && ok && j.ok) {
      say('updates', X('Se descarcă versiunea nouă și aplicația se repornește (circa un minut). Pagina se reîncarcă singură.', 'Downloading the new version and restarting the app (about a minute). The page reloads by itself.'), 'busy');
      const oldBuild = S && S.app && S.app.build; let n = 0;
      if (window.__updTimer) clearInterval(window.__updTimer);
      const t = window.__updTimer = setInterval(async () => {
        n += 1;
        try { const r = await fetch('/api/state', { cache: 'no-store' }); if (r.ok) { const d = await r.json(); if (oldBuild && d.app && d.app.build && d.app.build !== oldBuild) { clearInterval(t); say('updates', '✓ ' + X('Gata, se reîncarcă…', 'Done, reloading…'), 'ok'); setTimeout(() => location.reload(), 800); return; } } } catch (e) { /* aplicatia se reporneste */ }
        if (n >= 75) { clearInterval(t); say('updates', '✗ ' + X('Nu am văzut versiunea nouă după 5 minute. Verifică jurnalul updater-ului (docker logs tessie-updater) sau reîncarcă pagina.', 'I did not see the new version after 5 minutes. Check the updater log (docker logs tessie-updater) or reload the page.'), 'bad'); }
      }, 4000);
    } else if (apply) say('updates', '✗ ' + (j.reason || X('Eroare', 'Error')), 'bad');
    else { say('updates', ok && j.ok ? '✓ ' + (j.newer ? X('Versiune nouă: v', 'New version: v') + j.latest : X('Ești la zi.', 'You are up to date.')) : '✗ ' + (j.reason || X('Eroare', 'Error')), ok && j.ok ? 'ok' : 'bad'); if (ok && j.ok) setTimeout(render, 1200); }
  });
  view.querySelectorAll('[data-save]').forEach((b) => b.onclick = async (e) => {
    e.preventDefault(); const k = b.dataset.save, body = {};
    FIELDS[k].forEach((id) => { const el = document.getElementById(id); if (el) body[id] = el.value; });
    if (k === 'ha') body.ha_ble = document.getElementById('ha_ble').checked ? '1' : '0';
    if (k === 'updates') body.update_check = document.getElementById('update_check').checked ? '1' : '0';
    say(k, X('Se salvează…', 'Saving…'), 'busy');
    const [ok, j] = await call('/api/config', body, k);
    if (ok && j.ok) { if (k === 'pin' && body.pin) pinSave(body.pin, false); say(k, '✓ ' + X('Salvat', 'Saved'), 'ok'); setTimeout(render, 900); }
    else say(k, '✗ ' + (j.reason || j.error || X('Eroare', 'Error')), 'bad');
  });
  const impBox = () => document.getElementById('timp');
  const impSay = (h) => { const b = impBox(); if (b) b.innerHTML = h; };
  const impMode = () => (document.getElementById('imp_mode') || {}).value || 'gaps';
  const imp = async (action, extra = {}) => (await call('/api/import/tessie', Object.assign({ action, car, mode: impMode() }, extra)))[1];
  let impT = null;
  const impPoll = () => { clearInterval(impT); impT = setInterval(async () => {
    if (!impBox()) { clearInterval(impT); return; }
    const st = await api('/api/import/tessie/status');
    if (st.running) { const pc = st.total ? Math.round(st.done / st.total * 100) : 0; impSay(`⏳ ${esc(st.phase)} · ${pc}%<div class="bar" style="margin:8px 0 0"><div class="fill" style="width:${pc}%"></div></div>`); return; }
    clearInterval(impT);
    if (st.error) impSay(`<span style="color:#ffb3b3">✗ ${esc(st.error)}</span>`);
    else if (st.result) { const r = st.result; impSay(`<b style="color:var(--mint)">✓ ${r.dry_run ? X('Test reușit (nu s-a scris nimic)', 'Test passed (nothing written)') : X('Import terminat', 'Import finished')}</b> — ${r.drives} ${X('curse', 'drives')}, ${r.charges} ${X('încărcări', 'charges')}, ${r.positions} ${X('puncte GPS', 'GPS points')}.${r.dry_run ? '' : ' ' + X('Poți anula oricând cu „Anulează importul”.', 'You can undo it anytime with “Undo import”.')}`); }
  }, 1200); };
  view.querySelectorAll('[data-imp]').forEach((b) => b.onclick = async (e) => {
    e.preventDefault(); const k = b.dataset.imp; impSay('…');
    if (k === 'check') {
      const v = await imp('vehicles'); if (!v.ok) { impSay(`<span style="color:#ffb3b3">✗ ${esc(v.reason || 'eroare')}</span>`); return; }
      const j = await imp('preview'); if (!j.ok) { impSay(`<span style="color:#ffb3b3">✗ ${esc(j.reason || 'eroare')}</span>`); return; }
      const dd = (ts) => ts ? new Date(ts * 1000).toLocaleDateString(LOC(), { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
      const w = (o) => o.before + o.between + o.after ? ` (${o.before ? o.before + ' ' + X('înainte', 'before') : ''}${o.before && (o.between || o.after) ? ', ' : ''}${o.between ? o.between + ' ' + X('între', 'between') : ''}${o.between && o.after ? ', ' : ''}${o.after ? o.after + ' ' + X('după datele TeslaMate', 'after your TeslaMate data') : ''})` : '';
      impSay(`${X('Tessie are', 'Tessie has')} <b>${j.tessie_drives}</b> ${X('curse și', 'drives and')} <b>${j.tessie_charges}</b> ${X('încărcări', 'charges')}; ${X('în TeslaMate există deja', 'TeslaMate already has')} ${j.already_in_teslamate.drives} + ${j.already_in_teslamate.charges}. ${X('De importat', 'To import')}: <b>${j.to_import_drives}</b> ${X('curse', 'drives')}${w(j.drives_where)} (${nf(j.km)} km), <b>${j.to_import_charges}</b> ${X('încărcări', 'charges')}${w(j.charges_where)} (${nf(j.kwh, 1)} kWh)${j.first ? ' · ' + dd(j.first) + ' – ' + dd(j.last) : ''}.${j.already ? '<br>' + X('Există deja date aduse de un import anterior; noul import le completează, iar „Anulează importul” le scoate pe toate.', 'Data from an earlier import exists; the new import adds to it and “Undo import” removes all of it.') : ''}`);
    } else if (k === 'dry' || k === 'run') {
      if (k === 'run' && !confirm(X('Importul ADAUGĂ curse, încărcări și puncte GPS în baza TeslaMate (nu șterge și nu modifică nimic existent) și poate fi anulat. Ai făcut o copie de siguranță a bazei de date?', 'The import ADDS drives, charges and GPS points to the TeslaMate database (it never deletes or changes existing data) and can be undone. Have you backed up the database?'))) { impSay(''); return; }
      const j = await imp(k, { confirm: true }); if (!j.ok) { impSay(`<span style="color:#ffb3b3">✗ ${esc(j.reason || 'eroare')}</span>`); return; } impPoll();
    } else if (k === 'undo') {
      if (!confirm(X('Șterg exact datele adăugate de import (după jurnalul lui). Continui?', 'Delete exactly the data added by the import (per its ledger). Continue?'))) { impSay(''); return; }
      const j = await imp('undo'); impSay(j.ok ? `<b style="color:var(--mint)">✓ ${X('Anulat', 'Undone')}</b> — ${j.undone.drives} ${X('curse', 'drives')}, ${j.undone.charges} ${X('încărcări', 'charges')}, ${j.undone.positions} ${X('puncte', 'points')}.` : `<span style="color:#ffb3b3">✗ ${esc(j.reason || 'eroare')}</span>`);
    }
  });
  view.querySelectorAll('[data-test]').forEach((b) => b.onclick = async (e) => {
    e.preventDefault(); const k = b.dataset.test; say(k, X('Se testează…', 'Testing…'), 'busy');
    const [ok, j] = await call('/api/config/test', { what: k }, k);
    say(k, (j.ok ? '✓ ' : '✗ ') + (j.msg || j.reason || ''), j.ok ? 'ok' : 'bad');
  });
}

/* ---------- MENIU (ca in Tessie) + pagini noi: Activitate, Starea bateriei, Notificari, Profiler ---------- */
const NAVI = {
  car: 'M5 11l1.6-4.4A2 2 0 0 1 8.5 5.3h7a2 2 0 0 1 1.9 1.3L19 11M4 11h16v6H4zM7 17v2M17 17v2M7.5 14h.01M16.5 14h.01',
  route: 'M6 20a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM8 18h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7',
  bolt: 'M13 3L5 14h6l-1 7 8-11h-6z',
  parking: 'M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zM10 17V8h3a2.6 2.6 0 0 1 0 5.2h-3',
  history: 'M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7.5V12l3 2',
  heart: 'M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.6-7 10-7 10zM7 12.5h3l1.5-3 2 5 1.5-2H17',
  wand: 'M15 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1zM4 20L14 10M12.5 8.5l3 3M5 6l.7 1.3L7 8l-1.3.7L5 10l-.7-1.3L3 8l1.3-.7z',
  bell: 'M6 17v-6a6 6 0 0 1 12 0v6l2 2H4zM10 21h4',
  gauge: 'M4 18a9 9 0 1 1 16 0M12 14l4-5M12 18h.01',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 11v5M12 8h.01',
  gear: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z',
};
let setCat = (() => { try { return localStorage.getItem('setcat') || 'general'; } catch (x) { return 'general'; } })();
const SETTINGS_EXT = [];     // sectiuni de Setari adaugate de module: { render: async () => html, after: () => {} }
const PAGES = {};            // pagini adaugate de module: PAGES.cheie = { render: async (arg) => html, after: (arg) => {} }
const EXTRA_MENU = [];       // [cheie, ro, en, icon] adaugate de module
const MENU = [['car', 'Bord', 'Dashboard', 'car'], ['drives', 'Trasee', 'Drives', 'route'], ['charges', 'Încărcări', 'Charges', 'bolt'], ['parked', 'Staționări', 'Parked', 'parking'],
  ['activity', 'Activitate', 'Activity', 'history'], ['battery', 'Starea bateriei', 'Battery health', 'heart'], ['auto', 'Automatizare', 'Automation', 'wand'],
  ['notifications', 'Notificări', 'Notifications', 'bell'], ['profiler', 'Profiler', 'Profiler', 'gauge']];
const nicon = (k) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${NAVI[k]}"/></svg>`;
function carLabel(c) { if (!c) return 'Tesla'; const mn = String(c.marketing_name || ''); return (/model|cyber|semi/i.test(mn) ? mn : 'Model ' + (c.model || '')).replace(/\s*(Highland|Juniper).*/i, '').trim() || 'Tesla'; }
function drawNav(active) {
  const c = cur();
  const nav2 = document.getElementById('nav'); if (!nav2) return;
  nav2.innerHTML = `<div class="sb-top"><div class="sb-logo"><svg viewBox="0 0 24 24"><path d="${NAVI.car}"/></svg><span>TESLAMATE UI</span></div></div>
    <button class="sb-car" id="sbcar" title="${X('Detalii mașină', 'Car details')}"><span>${esc(carLabel(c))}</span>${nicon('info')}</button>
    ${S.cars.length > 1 ? `<select id="sbcarsel" aria-label="${X('Alege mașina', 'Choose car')}">${S.cars.map((x) => `<option value="${x.id}" ${x.id === car ? 'selected' : ''}>${esc(carLabel(x))}${x.name ? ' · ' + esc(x.name) : ''}</option>`).join('')}</select>` : ''}
    <div class="sb-menu">${MENU.concat(EXTRA_MENU).map(([k, ro, en, ic]) => `<a href="#/${k}" class="${active === k ? 'on' : ''}">${nicon(ic)}<span>${X(ro, en)}</span></a>`).join('')}</div>
    <div class="sb-foot"><a href="#/settings" class="${active === 'settings' ? 'on' : ''}">${nicon('gear')}<span>${X('Setări', 'Settings')}</span></a>
      ${S.app ? `<a href="#/settings" class="sb-ver">v${esc(S.app.version)}${S.app.latest ? ` · <b>${X('nou', 'new')} v${esc(S.app.latest)}</b>` : ''}</a>` : ''}<div class="sb-lang"><button data-lang="ro" class="${LANG === 'ro' ? 'on' : ''}">RO</button><button data-lang="en" class="${LANG === 'en' ? 'on' : ''}">EN</button></div></div>`;
  nav2.querySelectorAll('[data-lang]').forEach((b) => b.onclick = () => { LANG = b.dataset.lang; try { localStorage.setItem('lang', LANG); } catch (x) { /* ignore */ } document.documentElement.lang = LANG; render(); });
  nav2.querySelectorAll('a').forEach((a) => a.addEventListener('click', () => document.body.classList.remove('nav-open')));
  const sc = document.getElementById('sbcar'); if (sc) sc.onclick = carInfo;
  const sel = document.getElementById('sbcarsel'); if (sel) sel.onchange = () => { car = +sel.value; try { localStorage.setItem('car', String(car)); } catch (x) { /* ignore */ } document.body.classList.remove('nav-open'); render(); };
  const tt = document.getElementById('tbtitle'), cur2 = MENU.find((m) => m[0] === active);
  if (tt) tt.textContent = cur2 ? X(cur2[1], cur2[2]) : (active === 'settings' ? X('Setări', 'Settings') : carLabel(c));
}
function carInfo() {
  const c = cur(); if (!c) return; const L = c.live || {};
  const row = (k, v) => v == null || v === '' ? '' : `<div class="row" style="padding:7px 0;border-bottom:1px solid var(--line)"><span class="mut">${k}</span><div class="sp"></div><b>${esc(String(v))}</b></div>`;
  const m = document.createElement('div'); m.className = 'modal';
  m.innerHTML = `<div class="modal-card"><button class="rp-cx" aria-label="close">✕</button><h2 style="margin:0 0 8px;text-transform:none;letter-spacing:0;font-size:20px;color:var(--tx)">${esc(c.name || carLabel(c))}</h2>
    ${row(X('Model', 'Model'), c.marketing_name || ('Model ' + (c.model || '')))}${row(X('Versiune', 'Trim'), c.trim)}${row(X('Culoare', 'Colour'), c.color)}${row(X('Jante', 'Wheels'), c.wheel_type)}
    ${row('VIN', c.vin ? '…' + String(c.vin).slice(-8) : '')}${row('Software', L.version)}${row(X('Odometru', 'Odometer'), L.odometer != null ? nf(L.odometer) + ' km' : '')}${row(X('Eficiență de referință', 'Reference efficiency'), c.efficiency != null ? nf(c.efficiency * 1000) + ' Wh/km' : '')}</div>`;
  m.onclick = (e) => { if (e.target === m || e.target.classList.contains('rp-cx')) m.remove(); };
  document.body.appendChild(m);
}

/* ---------- Activitate (cronologie + statistici) ---------- */
let actMode = 'feed';
async function pageActivity() {
  const head = `<div class="top"><h1>${X('Activitate', 'Activity')}</h1></div><div class="seg"><button data-am="feed" class="${actMode === 'feed' ? 'on' : ''}">${X('Cronologie', 'Timeline')}</button><button data-am="stats" class="${actMode === 'stats' ? 'on' : ''}">${X('Statistici', 'Statistics')}</button></div>`;
  if (actMode === 'stats') return head + await statsBody(true);
  const ev = await api('/api/activity?car=' + car + '&days=30&limit=150');
  const ICN = { drive: ['route', '#7aa8ff'], charge: ['bolt', '#d9ba80'], parked: ['parking', '#8f99a4'], update: ['info', '#b69bff'], app: ['bell', '#6fd6b8'] };
  let last = '', html = '';
  ev.forEach((e) => {
    const k = dayKey(e.t); if (k !== last) { html += `<div class="day"><span>${dayLabel(k)}</span><span></span></div>`; last = k; }
    const [ic, col] = ICN[e.type] || ICN.app;
    const meta = e.type === 'drive' ? `${nf(e.km, 1)} km · ${nf(e.kwh, 1)} kWh · ${nf(e.soc0)}% → ${nf(e.soc1)}% · ${tm(e.t)}–${tm(e.end)}`
      : e.type === 'charge' ? `+${nf(e.kwh, 1)} kWh · ${nf(e.soc0)}% → ${nf(e.soc1)}% · ${e.dc ? 'DC' : 'AC'} · ${tm(e.t)}–${tm(e.end)}${e.cost != null ? ' · ' + nf(e.cost, 2) + ' ' + CU() : ''}`
      : e.type === 'parked' ? `${hm(e.hours * 60)} · ${X('somn', 'sleep')} ${e.sleep_pct}% · ${e.drop > 0 ? '−' : '+'}${nf(Math.abs(e.drop))}% · ${tm(e.t)}–${tm(e.end)}`
      : e.type === 'update' ? X('Actualizare software instalată', 'Software update installed') : esc(e.msg || '');
    const href = e.type === 'drive' ? `#/drive/${e.id}` : e.type === 'charge' ? `#/charge/${e.id}` : e.type === 'parked' ? '#/parked' : '#/activity';
    html += `<a class="item act-i" href="${href}"><div class="t"><span class="ai" style="color:${col}">${nicon(ic)}</span><span>${esc(e.title)}</span></div><div class="m"><span>${meta}</span></div></a>`;
  });
  return head + (html || `<div class="empty">${X('Nimic înregistrat încă.', 'Nothing recorded yet.')}</div>`);
}
function afterActivity() { view.querySelectorAll('[data-am]').forEach((b) => b.onclick = () => { actMode = b.dataset.am; render(); }); view.querySelectorAll('[data-d]').forEach((b) => b.onclick = () => { days = +b.dataset.d; render(); }); view.querySelectorAll('[data-ice]').forEach((b) => b.onclick = (ev) => { ev.preventDefault(); iceActions(b); }); }

/* ---------- Starea bateriei ---------- */
async function pageBattery() {
  const b = await api('/api/battery?car=' + car);
  return `<div class="top"><h1>${X('Starea bateriei', 'Battery health')}</h1></div>
  ${healthShellBody()}
  <h2>${X('Autonomie la 100%', 'Range at 100%')}</h2>${sec(X('Autonomie estimată la 100% (km)', 'Estimated range at 100% (km)'), line(b.range100.map((x) => [+new Date(x.week), x.range100]), { color: '#6fd6b8', dec: 0 }))}
  <p class="note" style="margin-top:6px">${X('Calculată din autonomia ideală raportată la nivelul bateriei; scăderea lentă în timp indică degradarea.', 'Computed from ideal range reported against battery level; a slow decline over time indicates degradation.')}</p>
  ${b.updates.length ? `<h2>${X('Actualizări software', 'Software updates')}</h2><div class="card">${b.updates.map((u) => `<div class="row" style="padding:5px 0"><b>${esc(u.version)}</b><div class="sp"></div><span class="mut">${T(u.start_date).toLocaleDateString(LOC(), { day: 'numeric', month: 'long', year: 'numeric' })}</span></div>`).join('')}</div>` : ''}`;
}
function healthShellBody() { return `<div id="bhealth"><div class="mut" style="font-size:13px">…</div></div>`; }

/* ---------- Notificari ---------- */
function pageNotif() { return `<div class="top"><h1>${X('Notificări', 'Notifications')}</h1><small>${X('Evenimente trimise pe telefon (webhook) și păstrate aici.', 'Events sent to your phone (webhook) and kept here.')}</small></div><div id="notif" style="margin-top:12px"></div>`; }

/* ---------- PROFILER ---------- */
let PFS = null, PFES = null, PFSEL = 'charging', PFMIN = 10, PFFILTER = '', PFOPEN = new Set(), PFTICK = 0;
const pfDescAll = () => ({ performance: X('Viteză, accelerație, motoare, cuplu, temperaturi invertor', 'Speed, acceleration, motors, torque, inverter temperatures'), charging: X('Putere, tensiune, curent, celule, temperatură baterie', 'Power, voltage, current, cells, battery temperature'),
  climate: X('Temperaturi, HVAC, scaune, dezghețare', 'Temperatures, HVAC, seats, defrost'), body: X('Uși, geamuri, lumini, port de încărcare', 'Doors, windows, lights, charge port'), safety: X('Sentry, centuri, presiune roți, avertizări', 'Sentry, belts, tyre pressure, warnings'),
  nav: X('GPS, traseu, destinație, media', 'GPS, route, destination, media'), turbo: X('Toate semnalele, flux rapid', 'All signals, fast feed') });
const pfLabel = (n) => n.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/^Di /, 'DI ').replace(/\bFl\b/, 'FL').replace(/\bFr\b/, 'FR').replace(/\bRl\b/, 'RL').replace(/\bRr\b/, 'RR');
function pfFmt(n, v) {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? X('Da', 'Yes') : X('Nu', 'No');
  if (typeof v === 'number') return nf(v, Math.abs(v) >= 100 ? 1 : 2);
  if (typeof v === 'object') return Object.entries(v).map(([k, x]) => k + ' ' + (typeof x === 'number' ? nf(x, 5) : x)).join(' · ');
  let s = String(v); const stem = n.replace(/State$/, ''); if (s.startsWith(n)) s = s.slice(n.length); else if (s.startsWith(stem)) s = s.slice(stem.length); s = s.replace(/^State(?=[A-Z])/, ''); return s || String(v);
}
function spark(h, unit) {
  const W = 150, H = 44, pl = 24;
  if (!h || h.length < 2) return `<svg viewBox="0 0 ${W} ${H}" class="pf-sp"><path d="M${pl} ${H / 2}H${W}" stroke="#2b6cb0" stroke-width="1.4" stroke-dasharray="1 7" stroke-linecap="round"/></svg>`;
  const mn = Math.min(...h), mx = Math.max(...h), r = mx - mn || Math.max(1, Math.abs(mx) * .02), lo = mn - r * .1, hi = mx + r * .1;
  const X0 = (i) => pl + i / (h.length - 1) * (W - pl - 2), Y0 = (y) => 5 + (1 - (y - lo) / (hi - lo)) * (H - 14);
  const f = (v) => nf(v, Math.abs(v) >= 100 ? 0 : 1) + (unit ? ' ' + unit : '');
  return `<svg viewBox="0 0 ${W} ${H}" class="pf-sp"><text x="0" y="10">${f(hi)}</text><text x="0" y="${H - 2}">${f(lo)}</text>
    <path d="${h.map((y, i) => (i ? 'L' : 'M') + X0(i).toFixed(1) + ' ' + Y0(y).toFixed(1)).join('')}" fill="none" stroke="#3b82f6" stroke-width="1.3"/>
    ${h.length < 60 ? h.map((y, i) => `<circle cx="${X0(i).toFixed(1)}" cy="${Y0(y).toFixed(1)}" r="1.7" fill="#3b82f6"/>`).join('') : ''}</svg>`;
}
const PF_SUFFIX = /(RearLeft|RearRight|RearCenter|FrontLeft|FrontRight|REL|RER|Fl|Fr|Rl|Rr|Left|Right|F|R|L|0|1|2|3)$/;
function pfGroupKey(n) { return n.replace(PF_SUFFIX, '') || n; }
const PF_ICO = { 'A': 'M5 18V9M10 18V5M15 18v-7M20 18v-3', 'V': 'M13 3L5 14h6l-1 7 8-11h-6z', 'Nm': 'M4 18a8 8 0 1 1 16 0M12 14l3-4', 'rpm': 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', '°C': 'M10 14V5a2 2 0 1 1 4 0v9a4 4 0 1 1-4 0z', 'kW': 'M13 3L5 14h6l-1 7 8-11h-6z', 'km/h': 'M4 18a8 8 0 1 1 16 0M12 14l4-5', 'bar': 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', '%': 'M5 18L19 6M7 8h.01M17 16h.01' };
function pfClose() { if (PFES) { PFES.close(); PFES = null; } }
async function pageProfiler() {
  let d; try { d = await api('/api/profiler'); } catch (e) { return `<div class="empty">${esc(e.message)}</div>`; }
  PFS = { meta: d.meta, values: d.values || {}, hist: d.hist || {}, status: d };
  const cats = { perf: X('Performanță', 'Performance'), charge: X('Încărcare', 'Charging'), climate: X('Climă', 'Climate'), body: X('Caroserie', 'Body'), safety: X('Siguranță', 'Safety'), nav: X('Navigație', 'Navigation'), other: X('Altele', 'Other') };
  PFS.cats = cats;
  return `<div class="top row"><div><h1>Profiler</h1><small>${X('Date live de la mașină (Fleet Telemetry) — pe sesiuni scurte', 'Live data from the car (Fleet Telemetry) — in short sessions')}</small></div><div class="sp"></div><span class="pill" id="pfst"></span></div>
  <div id="pfctl"></div><div id="pftiles" class="grid g3" style="margin-top:14px"></div>
  <div class="row" style="margin-top:14px;gap:8px"><input id="pfq" class="pf-q" placeholder="${X('Caută semnal…', 'Search signal…')}" value="${esc(PFFILTER)}"><a class="pf-dl" href="/api/profiler/export.csv">⬇ CSV</a></div>
  <div id="pflist"></div>`;
}
async function pfDiag() {
  const box = $('#pfdiag'); if (!box || !PFS) return;
  if (!PFS.status.session) {                       // fara sesiune: arata ce configuratie de telemetrie are acum masina (verificare ca s-a revenit la normal)
    try { const dg = await api('/api/profiler/diag'); if (dg.ok && !dg.sim) { const normal = dg.normal !== undefined ? dg.normal : dg.fields <= 1; box.innerHTML = (normal && dg.synced ? '✓ ' : normal ? '… ' : '⚠ ') + X(normal ? 'Configurația mașinii: normală (cea de bază, ' + dg.fields + ' semnale)' + (dg.synced ? ' — aplicată pe mașină.' : ' — așteaptă să fie preluată de mașină.') : 'Mașina trimite încă ' + dg.fields + ' semnale — nu a revenit la normal!', normal ? 'Car configuration: normal (the base one, ' + dg.fields + ' signals)' + (dg.synced ? ' — applied on the car.' : ' — waiting for the car to fetch it.') : 'The car is still streaming ' + dg.fields + ' signals — it has not reverted!'); } else if (dg.sim) box.innerHTML = ''; } catch (e) { /* ignore */ }
    return;
  }
  const st = PFS.status, se = st.session, now = Date.now() / 1000;
  const age = st.last_rx ? Math.round(now - st.last_rx) : null, cn = st.conn;
  let line = [];
  if (se.sim) { box.innerHTML = ''; return; }
  if (se.waking) line.push('⏳ ' + X('Trezesc mașina…', 'Waking the car…'));
  if (cn) line.push((cn.status === 'CONNECTED' ? '🟢 ' : '⚪ ') + X('Mașina ' + (cn.status === 'CONNECTED' ? 'e conectată la serverul de telemetrie' : 'nu e conectată acum') + (cn.net ? ' (' + esc(cn.net) + ')' : '') + ', acum ' + Math.round(now - cn.at) + ' s', 'Car ' + (cn.status === 'CONNECTED' ? 'is connected to the telemetry server' : 'is not connected now') + (cn.net ? ' (' + esc(cn.net) + ')' : '') + ', ' + Math.round(now - cn.at) + ' s ago'));
  line.push(age == null ? X('Nu am primit încă nicio dată.', 'No data received yet.') : X('Ultimul pachet: acum ' + age + ' s', 'Last packet: ' + age + ' s ago'));
  try { const dg = await api('/api/profiler/diag'); if (dg.ok && !dg.sim) line.push((dg.synced ? '✓ ' : '… ') + X('Configurația ' + (dg.synced ? 'e aplicată pe mașină' : 'așteaptă să fie preluată de mașină (trebuie să fie trează și online)'), 'Configuration ' + (dg.synced ? 'is applied on the car' : 'is waiting for the car to fetch it (it must be awake and online)'))); } catch (e) { /* ignore */ }
  if ((age == null || age > 20) && Date.now() / 1000 - se.started > 25) line.push('<a href="#" id="pfwake" style="color:var(--gold)">' + X('Trezește mașina', 'Wake the car') + '</a>');
  box.innerHTML = line.join('<br>');
  const w = $('#pfwake'); if (w) w.onclick = async (e) => { e.preventDefault(); w.textContent = '…'; const pin = await getPin(); if (!pin) return; await fetch('/api/cmd/wake', { method: 'POST', headers: { 'X-Pin': pin, 'Content-Type': 'application/json' }, body: JSON.stringify({ car }) }); };
}
let pfDiagT = 0;
function pfRenderCtl() {
  const box = $('#pfctl'); if (!box || !PFS) return; const st = PFS.status, se = st.session;
  const left = se ? Math.max(0, Math.round((se.until * 1000 - Date.now()) / 1000)) : 0;
  const pill = $('#pfst'); if (pill) { pill.className = 'pill ' + (se ? 'ok' : ''); pill.textContent = se ? (se.sim ? X('Simulare · ', 'Simulation · ') : '● ') + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0') : X('Inactiv', 'Idle'); }
  const key = (se ? se.started : 0) + PFSEL + PFMIN;
  if (box.dataset.k === key) return;
  box.dataset.k = key;
  const cards = Object.entries(st.profiles).map(([k, p]) => `<button class="pf-card ${PFSEL === k ? 'on' : ''}" data-pf="${k}" ${se ? 'disabled' : ''}><b>${LANG === 'en' ? p.en : p.ro}</b><small>${p.count} ${X('semnale', 'signals')}</small><span>${pfDescAll()[k] || ''}</span></button>`).join('');
  setHtml(box, se ? `<div class="card"><div class="row"><div><b>${LANG === 'en' ? st.profiles[se.profile].en : st.profiles[se.profile].ro}</b><small class="mut" style="display:block">${se.fields} ${X('semnale · se oprește automat', 'signals · stops automatically')}</small></div><div class="sp"></div><button class="pf-btn stop" id="pfstop">${X('Oprește', 'Stop')}</button>${(se.stop_fails || window.__pfStopFail) ? `<button class="pf-btn" id="pfforce" title="${X('Închide sesiunea fără să mai restabilesc configurația mașinii', 'Close the session without restoring the car configuration')}">${X('Forțează', 'Force')}</button>` : ''}</div>
      <div class="note" id="pfdiag" style="margin:8px 0 0"></div>
      ${(se.dropped || []).length ? `<p class="note" style="margin:8px 0 0">${X('Omise (lipsește permisiunea de locație vehicle_location sau nu sunt acceptate): ', 'Skipped (missing vehicle_location scope or not accepted): ')}${esc(se.dropped.slice(0, 8).join(', '))}${se.dropped.length > 8 ? '…' : ''}</p>` : ''}</div>`
    : `<div class="pf-cards">${cards}</div><div class="card" style="margin-top:10px"><div class="row"><label class="cf" style="margin:0;flex:1">${X('Durată', 'Duration')}<select id="pfmin" style="width:100%">${[5, 10, 15, 30].map((m) => `<option value="${m}" ${m === PFMIN ? 'selected' : ''}>${m} min</option>`).join('')}</select></label><button class="pf-btn" id="pfgo" style="margin-top:14px">${X('Pornește sesiunea', 'Start session')}</button></div>
      <p class="note" style="margin:8px 0 0">${X('Mașina trebuie să fie trează și conectată; cât durează sesiunea NU adoarme. Alerta Sentry rămâne activă. La final revine automat la configurația normală. Tesla poate taxa semnalele de telemetrie.', 'The car must be awake and connected; it will NOT sleep during the session. Sentry alerts stay active. At the end it automatically reverts to the normal configuration. Tesla may bill telemetry signals.')}</p></div>
      <div class="note" id="pfdiag" style="margin:10px 2px 0"></div><div class="toast" aria-live="polite" id="pfmsg" style="display:none"></div>`);
  pfDiag();
  box.querySelectorAll('[data-pf]').forEach((b) => b.onclick = () => { PFSEL = b.dataset.pf; pfRenderCtl(); });
  const m = $('#pfmin'); if (m) m.onchange = () => { PFMIN = +m.value; };
  const go = $('#pfgo'); if (go) go.onclick = async () => {
    const pin = S.public_demo ? '' : await getPin(); if (!pin && !S.public_demo) return; const msg = $('#pfmsg'); msg.style.display = ''; msg.className = 'toast busy'; msg.textContent = X('Se configurează mașina…', 'Configuring the car…');
    try { const r = await fetch('/api/profiler/start', { method: 'POST', headers: { 'X-Pin': pin, 'Content-Type': 'application/json' }, body: JSON.stringify({ car, profile: PFSEL, minutes: PFMIN }) }); const j = await r.json();
      if (r.status === 403) pinClear();
      if (j.ok || S.public_demo) { PFS.status = await api('/api/profiler'); pfRenderCtl(); } else { msg.className = 'toast bad'; msg.textContent = '✗ ' + (j.reason || j.error || 'eroare'); } } catch (e) { msg.className = 'toast bad'; msg.textContent = '✗ ' + e.message; }
  };
  const sp = $('#pfstop'); if (sp) sp.onclick = async () => { const pin = await getPin(); if (!pin && !S.public_demo) return; const r = await fetch('/api/profiler/stop', { method: 'POST', headers: { 'X-Pin': pin || '', 'Content-Type': 'application/json' }, body: '{}' }); const jr = await r.json(); window.__pfStopFail = !jr.ok; PFS.status = await api('/api/profiler'); box.dataset.k = ''; pfRenderCtl(); };
  const pfo = $('#pfforce'); if (pfo) pfo.onclick = async () => { if (!confirm(X('Închid sesiunea FĂRĂ să restabilesc configurația mașinii (Sentry)? Verifică după aceea telemetria.', 'Close the session WITHOUT restoring the car configuration (Sentry)? Check the telemetry afterwards.'))) return; const pin = await getPin(); if (!pin) return; const r = await fetch('/api/profiler/stop', { method: 'POST', headers: { 'X-Pin': pin, 'Content-Type': 'application/json' }, body: JSON.stringify({ force: true }) }); const jr = await r.json(); window.__pfStopFail = false; if (jr.warning) alert(jr.warning); PFS.status = await api('/api/profiler'); box.dataset.k = ''; pfRenderCtl(); };
}
function pfRenderData() {
  if (!PFS) return; const q2 = (PFFILTER || '').toLowerCase(), fav = lsGet('pf_fav', []);
  const T0 = PFS.values, v = (n) => (T0[n] ? T0[n][0] : null);
  const names = Object.keys(T0).filter((n) => !q2 || n.toLowerCase().includes(q2) || pfLabel(n).toLowerCase().includes(q2));
  const tiles = [[X('Viteză', 'Speed'), v('VehicleSpeed'), 'km/h'], [X('Baterie', 'Battery'), v('BatteryLevel') ?? v('Soc'), '%'], [X('Putere încărcare', 'Charging power'), v('DCChargingPower') || v('ACChargingPower'), 'kW'], [X('Tensiune pachet', 'Pack voltage'), v('PackVoltage'), 'V'], [X('Curent pachet', 'Pack current'), v('PackCurrent'), 'A'], [X('Temp. interior', 'Inside temp'), v('InsideTemp'), '°C']].filter((t) => t[1] != null);
  const tl = $('#pftiles'); if (tl) tl.innerHTML = tiles.map((t) => `<div class="st"><i>${t[0]}</i><b>${esc(pfFmt('', t[1]))}<small>${esc(t[2])}</small></b></div>`).join('');
  const box = $('#pflist'); if (!box) return;
  if (!names.length) { box.innerHTML = `<div class="empty">${PFS.status.session ? X('Aștept date de la mașină… (mașina trebuie să fie trează și online)', 'Waiting for data from the car… (the car must be awake and online)') : X('Pornește o sesiune ca să vezi semnalele live.', 'Start a session to see live signals.')}</div>`; return; }
  // grupuri ca in Tessie: semnale inrudite (ex. DiMotorCurrentF/R/REL/RER) intr-un rand de celule; restul pe categorii
  const byKey = {}; names.forEach((n) => { (byKey[pfGroupKey(n)] = byKey[pfGroupKey(n)] || []).push(n); });
  const groups = [], singles = {};
  const favs = names.filter((n) => fav.includes(n)); if (favs.length) groups.push([X('Favorite', 'Favorites'), favs, 'pf-fv']);
  Object.entries(byKey).forEach(([k, arr]) => { if (arr.length >= 2) groups.push([pfLabel(k), arr.sort(), PFS.meta[arr[0]]?.unit || '']); else (singles[PFS.meta[arr[0]]?.cat || 'other'] = singles[PFS.meta[arr[0]]?.cat || 'other'] || []).push(arr[0]); });
  groups.sort((a, b) => (a[2] === 'pf-fv' ? -1 : b[2] === 'pf-fv' ? 1 : 0));
  Object.keys(PFS.cats).forEach((c) => { if (singles[c]) groups.push([PFS.cats[c], singles[c].sort(), '']); });
  const now = Date.now() / 1000;
  const cell = (n) => { const [val, ts] = T0[n], m = PFS.meta[n] || {}, h = PFS.hist[n], age = now - ts, num = typeof val === 'number';
    return `<div class="pf-c ${age > 30 ? 'old' : ''}" data-n="${esc(n)}"><div class="pf-cn"><span>${esc(n)}</span><button class="pf-s ${fav.includes(n) ? 'on' : ''}" data-fav="${esc(n)}" aria-label="favorite">★</button></div><div class="pf-cv">${esc(pfFmt(n, val))}${m.unit && num ? '<small> ' + m.unit + '</small>' : ''}</div>${num ? spark(h, m.unit) : ''}</div>`; };
  box.innerHTML = `<div class="pf-panel">${groups.map(([title, arr, unit]) => `<section class="pf-g"><h3><svg viewBox="0 0 24 24"><path d="${PF_ICO[unit] || PF_ICO.bar}"/></svg>${esc(title)}</h3><div class="pf-gr">${arr.map(cell).join('')}</div></section>`).join('')}</div>`;
  box.querySelectorAll('[data-fav]').forEach((b) => b.onclick = (e) => { e.stopPropagation(); const f = lsGet('pf_fav', []), i = f.indexOf(b.dataset.fav); if (i < 0) f.push(b.dataset.fav); else f.splice(i, 1); lsSet('pf_fav', f); pfRenderData(); });
}
function afterProfiler() {
  pfClose(); pfRenderCtl(); pfRenderData();
  const q3 = $('#pfq'); if (q3) q3.oninput = () => { PFFILTER = q3.value; pfRenderData(); };
  PFES = new EventSource('/api/profiler/stream');
  PFES.onmessage = (e) => {
    const m = JSON.parse(e.data); if (!PFS) return;
    if (m.status) { PFS.status = m.status; $('#pfctl') && ($('#pfctl').dataset.k = ''); pfRenderCtl(); return; }
    Object.entries(m.d || {}).forEach(([k, v]) => { PFS.values[k] = [v, m.t]; if (typeof v === 'number') { const h = (PFS.hist[k] = PFS.hist[k] || []); h.push(v); if (h.length > 120) h.shift(); } });
    const now = performance.now(); if (now - PFTICK > 700) { PFTICK = now; pfRenderData(); }
  };
  clearInterval(window.__pfT); window.__pfT = setInterval(async () => { if (location.hash.startsWith('#/profiler')) { pfRenderCtl(); if (Date.now() - pfDiagT > 4000) { pfDiagT = Date.now(); try { PFS.status = Object.assign(PFS.status, await api('/api/profiler').then((d) => ({ last_rx: d.last_rx, conn: d.conn, session: d.session, active: d.active }))); } catch (e) { /* ignore */ } pfDiag(); } } else { clearInterval(window.__pfT); pfClose(); } }, 1000);
}


/* ---------- Deschideri animate pe poza masinii (usi, frunk, portbagaj, geamuri) ---------- */
function openState(L, o) {
  o = o || {};
  const d = { fl: !!o.df, rl: !!o.dr, fr: !!o.pf, rr: !!o.pr };                       // df/dr = sofer (stanga) fata/spate, pf/pr = pasager (dreapta)
  const known = Object.keys(o).length > 0 && ['df', 'dr', 'pf', 'pr'].some((k) => o[k] !== undefined && o[k] !== null);
  return { doors: d, doorsKnown: known, anyDoor: known ? Object.values(d).some(Boolean) : !!L.doors_open, frunk: !!(L.frunk_open || o.ft), trunk: !!(L.trunk_open || o.rt),
    windows: !!(L.windows_open || o.fd_window || o.fp_window || o.rd_window || o.rp_window) };
}
function openOverlay(L, o) {
  const st = openState(L, o);
  if (!(st.anyDoor || st.frunk || st.trunk || st.windows)) return '<svg class="ovl" viewBox="0 0 640 1400"></svg>';
  const door = (x, y, hinge, cls, flip) => `<rect class="od ${cls}" x="${x}" y="${y}" width="78" height="285" rx="22" style="transform-origin:${hinge}px ${y}px"/>`;
  let g = '';
  if (st.doorsKnown) {
    if (st.doors.fl) g += door(40, 520, 58, 'l');
    if (st.doors.rl) g += door(40, 815, 58, 'l');
    if (st.doors.fr) g += door(522, 520, 582, 'r');
    if (st.doors.rr) g += door(522, 815, 582, 'r');
  } else if (st.anyDoor) g += '<rect class="og" x="36" y="520" width="84" height="580" rx="30"/><rect class="og" x="520" y="520" width="84" height="580" rx="30"/>';
  if (st.frunk) g += '<path class="og" d="M130 60C250 22 390 22 510 60L535 330H105Z"/>';
  if (st.trunk) g += '<path class="og" d="M120 1130H520L500 1320C400 1350 240 1350 140 1320Z"/>';
  if (st.windows) g += '<path class="ow" d="M62 540V1090M578 540V1090"/>';
  return `<svg class="ovl" viewBox="0 0 640 1400" aria-hidden="true">${g}</svg>`;
}
function openChips(L, o) {
  const st = openState(L, o), t = [];
  const nm = { fl: X('Ușă stânga față', 'Front left door'), rl: X('Ușă stânga spate', 'Rear left door'), fr: X('Ușă dreapta față', 'Front right door'), rr: X('Ușă dreapta spate', 'Rear right door') };
  if (st.doorsKnown) Object.entries(st.doors).forEach(([k, v]) => { if (v) t.push(nm[k]); }); else if (st.anyDoor) t.push(X('Ușă deschisă', 'Door open'));
  if (st.frunk) t.push('Frunk'); if (st.trunk) t.push(X('Portbagaj', 'Trunk')); if (st.windows) t.push(X('Geam deschis', 'Window open'));
  return t.map((x) => `<span class="chip alert"><i></i>${x}</span>`).join('');
}
let openBusy = false;
async function refreshOpenings(c) {
  const L = c.live || {};
  if (!(L.doors_open || L.trunk_open || L.frunk_open || L.windows_open) || openBusy || S.demo) return;
  openBusy = true;
  try {
    const d = await api('/api/vdata?car=' + c.id); S.opens = S.opens || {};
    const n = JSON.stringify(d.openings || {});
    if (d.openings && n !== JSON.stringify(S.opens[c.id] || {})) {
      S.opens[c.id] = d.openings;
      const pp = document.getElementById('pp'); if (pp) pp.outerHTML = openPhoto(L, d.openings);
      const ch = document.getElementById('openchips'); if (ch) ch.innerHTML = openChips(L, d.openings);
    }
  } catch (e) { /* ignore */ } finally { openBusy = false; }
}

/* ---------- Vedere laterala a masinii cu elementele deschise (ca pe ecranul masinii) ---------- */
function sideSvg(side, f) {
  // side: 'L' (partea soferului, botul spre stanga) sau 'R' (oglindit); f = { fd, rd, hood, trunk, win, half }
  const id = 'sv' + side, op = (b, c) => (b ? ' ' + c + (f.half ? ' half' : '') : '');
  const wheel = (cx) => `<g><circle cx="${cx}" cy="214" r="50" fill="#0c0d0f"/><circle cx="${cx}" cy="214" r="35" fill="url(#${id}r)"/><g stroke="#69717c" stroke-width="3.4" stroke-linecap="round">${[0, 72, 144, 216, 288].map((a) => `<path d="M${cx} 214L${(cx + 28 * Math.cos((a - 90) * Math.PI / 180)).toFixed(1)} ${(214 + 28 * Math.sin((a - 90) * Math.PI / 180)).toFixed(1)}"/>`).join('')}</g><circle cx="${cx}" cy="214" r="7" fill="#454c55"/></g>`;
  const FD = 'M258 116H410V232H262L255 164Z', RD = 'M412 116H590L584 172Q574 198 552 214L546 232H412Z';
  return `<svg class="sv ${side === 'R' ? 'mir' : ''}" viewBox="0 0 800 300" role="img" aria-label="${X('Mașina din lateral', 'Car side view')}">
<defs><linearGradient id="${id}b" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset=".5" stop-color="#eef1f4"/><stop offset="1" stop-color="#c2c9d0"/></linearGradient>
<linearGradient id="${id}g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3a4552"/><stop offset="1" stop-color="#10151b"/></linearGradient>
<radialGradient id="${id}r"><stop offset="0" stop-color="#e1e5ea"/><stop offset="1" stop-color="#8b939d"/></radialGradient></defs>
<ellipse cx="400" cy="266" rx="352" ry="10" fill="#000" opacity=".5"/>
<path d="M258 116C272 94 302 70 342 59C386 48 468 46 518 57C558 66 588 88 606 110L600 118H258Z" fill="url(#${id}g)"/>
<path class="bdy" fill="url(#${id}b)" stroke="#a6aeb8" stroke-width="1.3" d="M58 238C50 226 48 206 54 192C62 172 100 152 150 142L262 116L590 116L600 108L722 118C738 120 746 132 748 150V226C748 234 744 238 736 238H658.8A58 58 0 1 0 553.2 238H227.8A58 58 0 1 0 122.2 238H66C60 238 58 238 58 238Z"/>
<path d="M258 116L262 114C300 80 330 66 360 60L404 56V116Z" fill="url(#${id}g)" opacity="0"/>
<path d="${FD}" fill="#13161a"/><path d="${RD}" fill="#13161a"/>
<g class="fd${op(f.fd, 'open')}" style="transform-origin:258px 176px"><path class="win${f.win ? ' dn' : ''}" d="M262 114C288 84 316 68 346 62C372 58 392 57 404 57V114Z" fill="url(#${id}g)"/><path d="${FD}" fill="url(#${id}b)" stroke="#a6aeb8" stroke-width="1.3"/><rect x="362" y="150" width="30" height="7" rx="3.5" fill="#aab2bb"/></g>
<g class="rd${op(f.rd, 'open')}" style="transform-origin:588px 176px"><path class="win${f.win ? ' dn' : ''}" d="M416 57C462 57 512 59 546 70C570 80 590 98 600 114H416Z" fill="url(#${id}g)"/><path d="${RD}" fill="url(#${id}b)" stroke="#a6aeb8" stroke-width="1.3"/><rect x="426" y="150" width="30" height="7" rx="3.5" fill="#aab2bb"/></g>
<path d="M404 57H416V232H404Z" fill="#1b1f24"/>
<g class="hood${op(f.hood, 'open')}" style="transform-origin:262px 118px"><path d="M58 188C70 168 104 152 150 142L262 116L266 126L152 154C112 162 84 176 70 198Z" fill="url(#${id}b)" stroke="#a6aeb8" stroke-width="1.3"/></g>
<g class="tr${op(f.trunk, 'open')}" style="transform-origin:600px 112px"><path d="M600 108L722 118C738 120 746 132 748 150L740 152C738 138 732 130 720 128L600 118Z" fill="url(#${id}b)" stroke="#a6aeb8" stroke-width="1.3"/></g>
<rect x="56" y="196" width="22" height="9" rx="4.5" fill="#e6eef8" opacity=".95"/><rect x="728" y="170" width="19" height="10" rx="5" fill="#e5483f"/>
<path d="M120 238H66M740 238H664" stroke="#b9c0c8" stroke-width="3" opacity=".5"/>
${wheel(175)}${wheel(606)}
</svg>`;
}
function sideView(L, o) {
  const st = openState(L, o);
  if (!(st.anyDoor || st.frunk || st.trunk || st.windows)) return '';
  const half = !st.doorsKnown && st.anyDoor;
  const left = st.doorsKnown ? (st.doors.fl || st.doors.rl) : half, right = st.doorsKnown && (st.doors.fr || st.doors.rr);
  const views = [];
  const both = { hood: st.frunk, trunk: st.trunk, win: st.windows };
  if (left || !right) views.push(sideSvg('L', Object.assign({ fd: st.doors.fl || half, rd: st.doors.rl || half, half }, both)));
  if (right) views.push(sideSvg('R', Object.assign({ fd: st.doors.fr, rd: st.doors.rr }, left ? { win: st.windows } : both)));
  return `<div class="sideview ${views.length > 1 ? 'two' : ''}">${views.join('')}</div>`;
}


/* ---------- Deschideri realiste: portiuni din POZA REALA a masinii se rotesc/se ridica (nu desen) ---------- */
const CARPOLY = {"fl": [[6.7, 32.5], [2.2, 33.9], [0.0, 35.3], [0.2, 36.8], [6.6, 38.2], [6.4, 39.6], [6.4, 41.0], [6.2, 42.5], [6.2, 43.9], [6.1, 45.3], [6.1, 46.8], [5.9, 48.2], [5.9, 49.6], [5.8, 51.0], [5.8, 52.5], [5.8, 53.9], [5.8, 55.3], [18.1, 55.3], [18.1, 53.9], [18.1, 52.5], [18.1, 51.0], [18.3, 49.6], [18.3, 48.2], [18.4, 46.8], [18.4, 45.3], [18.6, 43.9], [18.6, 42.5], [18.8, 41.0], [18.8, 39.6], [18.9, 38.2], [12.5, 36.8], [12.3, 35.3], [14.5, 33.9], [19.1, 32.5]], "rl": [[5.8, 55.4], [5.8, 56.8], [5.8, 58.2], [5.9, 59.7], [5.9, 61.1], [5.9, 62.5], [5.9, 64.0], [5.9, 65.4], [5.9, 66.8], [5.8, 68.2], [5.6, 69.7], [5.3, 71.1], [5.0, 72.5], [4.8, 73.9], [4.7, 75.4], [4.7, 75.7], [17.0, 75.7], [17.0, 75.4], [17.2, 73.9], [17.3, 72.5], [17.7, 71.1], [18.0, 69.7], [18.1, 68.2], [18.3, 66.8], [18.3, 65.4], [18.3, 64.0], [18.3, 62.5], [18.3, 61.1], [18.3, 59.7], [18.1, 58.2], [18.1, 56.8], [18.1, 55.4]], "fr": [[93.1, 32.5], [97.7, 33.9], [99.7, 35.3], [99.5, 36.8], [93.1, 38.2], [93.3, 39.6], [93.3, 41.0], [93.4, 42.5], [93.6, 43.9], [93.6, 45.3], [93.8, 46.8], [93.8, 48.2], [93.8, 49.6], [93.8, 51.0], [93.9, 52.5], [93.9, 53.9], [93.9, 55.3], [81.6, 55.3], [81.6, 53.9], [81.6, 52.5], [81.4, 51.0], [81.4, 49.6], [81.4, 48.2], [81.4, 46.8], [81.2, 45.3], [81.2, 43.9], [81.1, 42.5], [80.9, 41.0], [80.9, 39.6], [80.8, 38.2], [87.2, 36.8], [87.3, 35.3], [85.3, 33.9], [80.8, 32.5]], "rr": [[93.9, 55.4], [93.9, 56.8], [93.9, 58.2], [93.9, 59.7], [93.8, 61.1], [93.8, 62.5], [93.8, 64.0], [93.8, 65.4], [93.8, 66.8], [93.9, 68.2], [94.2, 69.7], [94.5, 71.1], [94.7, 72.5], [95.0, 73.9], [95.0, 75.4], [95.0, 75.7], [82.7, 75.7], [82.7, 75.4], [82.7, 73.9], [82.3, 72.5], [82.2, 71.1], [81.9, 69.7], [81.6, 68.2], [81.4, 66.8], [81.4, 65.4], [81.4, 64.0], [81.4, 62.5], [81.4, 61.1], [81.6, 59.7], [81.6, 58.2], [81.6, 56.8], [81.6, 55.4]], "hood": [[27.8, 3.4], [22.7, 4.9], [18.8, 6.3], [16.6, 7.7], [15.0, 9.1], [13.9, 10.6], [13.1, 12.0], [12.7, 13.4], [14.7, 14.8], [14.5, 16.3], [14.4, 17.7], [14.2, 19.1], [14.2, 20.6], [14.2, 22.0], [14.2, 23.3], [85.5, 23.3], [85.5, 22.0], [85.5, 20.6], [85.5, 19.1], [85.3, 17.7], [85.2, 16.3], [85.2, 14.8], [87.0, 13.4], [86.7, 12.0], [85.9, 10.6], [84.7, 9.1], [83.3, 7.7], [81.1, 6.3], [77.2, 4.9], [71.9, 3.4]], "trunk": [[13.3, 80.2], [13.3, 81.7], [13.4, 83.1], [13.8, 84.5], [14.1, 85.9], [14.5, 87.4], [15.6, 88.8], [16.7, 90.2], [18.0, 91.6], [19.2, 93.1], [20.8, 94.5], [21.9, 95.2], [74.8, 95.2], [77.5, 94.5], [80.3, 93.1], [81.9, 91.6], [83.0, 90.2], [84.2, 88.8], [85.2, 87.4], [85.8, 85.9], [86.1, 84.5], [86.2, 83.1], [86.4, 81.7], [86.4, 80.2]], "hinge": {"fl": [8.0, 38.5], "rl": [6.1, 75.5], "fr": [91.7, 38.5], "rr": [93.6, 75.5], "hood": [50.0, 23.3], "trunk": [50.0, 80.2]}};
const polyStr = (k) => CARPOLY[k].map((q) => q[0] + '% ' + q[1] + '%').join(',');
const hingeStr = (k) => CARPOLY.hinge[k][0] + '% ' + CARPOLY.hinge[k][1] + '%';
function openPhoto(L, o) {
  const st = openState(L, o);
  const any = st.anyDoor || st.frunk || st.trunk || st.windows;
  if (!any) return `<div class="pp" id="pp">${carFx(L)}</div>`;
  const bg = "background-image:url('/car.png')";
  const piece = (k, cls) => `<div class="ppu${k === 'hood' || k === 'trunk' ? ' sf' : ''}" style="clip-path:polygon(${polyStr(k)})"></div><div class="ppc ${cls}" style="${bg};clip-path:polygon(${polyStr(k)});transform-origin:${hingeStr(k)}"></div>`;
  let h = '';
  if (st.doorsKnown) {
    if (st.doors.fl) h += piece('fl', 'dl');
    if (st.doors.rl) h += piece('rl', 'dl2');
    if (st.doors.fr) h += piece('fr', 'dr');
    if (st.doors.rr) h += piece('rr', 'dr2');
  } else if (st.anyDoor) h += '<div class="pg" style="left:3%;top:33%;width:22%;height:48%"></div><div class="pg" style="left:75%;top:33%;width:22%;height:48%"></div>';
  if (st.frunk) h += piece('hood', 'hd');
  if (st.trunk) h += piece('trunk', 'tk');
  if (st.windows) h += '<svg class="pw" viewBox="0 0 640 1400"><path d="M62 540V1090M578 540V1090"/></svg>';
  return `<div class="pp" id="pp">${carFx(L)}${h}</div>`;
}


/* ---------- Incarcari: filtru pe furnizor + totaluri, cost editabil, comparatie cu o masina termica ---------- */
const CU = () => { const c = S.currency; return tr(!c || /^(lei|ron)$/i.test(c) ? 'lei' : c); };       // "LEI"/"RON" se afiseaza ca "lei"
let chF = { p: null, d: 0 }, chRows = [], chKeys = [];
async function pinPost(path, body) {
  let pin = pinGet();
  if (!pin && window.__pinSet !== false) pin = await getPin();
  try {
    const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Pin': pin || '' }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (r.status === 403 && /PIN/.test(j.reason || '')) { pinClear(); }
    return [r.ok && j.ok !== false, j];
  } catch (e) { return [false, { reason: e.message || 'offline' }]; }                // offline / PIN cu caractere speciale: mesajul de "se salveaza" nu ramane blocat
}
function chCost(c) {
  const cu = esc(CU()), tmc = c.cost != null ? nf(c.cost, 2) : '—';
  if (c.cost_manual != null) return `<span title="${X('Cost introdus manual · TeslaMate: ', 'Manually entered cost · TeslaMate: ')}${tmc}"><b>${nf(c.cost_manual, 2)}</b> ${cu} <small style="color:var(--mut)">(${X('manual', 'manual')})</small></span>`;
  if (c.cost_manual == null && c.cost_real == null && c.cost_place != null) return `<span title="${X('Preț salvat pentru ', 'Saved price for ')}${esc(c.place_name)}: ${nf(c.place_price, 3)} ${cu}/kWh · TeslaMate: ${tmc}"><b>${nf(c.cost_place, 2)}</b> ${cu} <small style="color:var(--mut)">(${nf(c.place_price, 2)}/kWh)</small></span>`;
  if (c.cost_real != null) return `<span title="${X('Cost real estimat (doar energia din rețea) · TeslaMate: ', 'Estimated real cost (grid energy only) · TeslaMate: ')}${tmc}"><b>${nf(c.cost_real, 2)}</b> ${cu} <small style="color:var(--mut)">(TM ${tmc})</small></span>`;
  return c.cost != null ? `<span><b>${nf(c.cost, 2)}</b> ${cu}</span>` : '';
}
async function fetchAll(kind, qs = '') {
  let all = [], off = 0;
  for (;;) {
    const r = await api('/api/' + kind + '?car=' + car + '&limit=200&offset=' + off + qs);
    all = all.concat(r);
    if (r.length < 200 || all.length >= 1000) break;
    off += 200;
  }
  return all;
}
const fetchCharges = () => fetchAll('charges', lfQuery('charges'));
async function pageCharges() {
  await lfLoadTags();
  chRows = await fetchCharges();
  const head = `<div class="top"><h1>${tr('Încărcări')}</h1></div>`;
  if (!chRows.length) return `${head}<div id="chfilt">${lfBar('charges')}</div><div class="empty">${X('Nimic în perioada aleasă.', 'Nothing in the chosen period.')}</div>${chargeCtlShell()}`;
  if (chF.p !== null && !chRows.some((r) => (r.provider || '') === chF.p)) chF.p = null;
  return `${head}<div class="links" style="margin:0 2px"><a href="#/chstats">📊 ${X('Statistici încărcări', 'Charging stats')}</a><a href="#" id="goctl">${X('Control încărcare ↓', 'Charging control ↓')}</a></div><div id="chfilt"></div><div id="chlist"></div>${chargeCtlShell()}`;
}
function chFiltered() {
  return chRows.filter((r) => chF.p === null || (r.provider || '') === chF.p);
}
function drawChargeList() {
  const fb = $('#chfilt'), lb = $('#chlist'); if (!fb || !lb) return;
  const cu = CU();
  const inPeriod = chRows;
  const by = {};                                                  // furnizor -> { n, kwh }
  inPeriod.forEach((r) => { const k = r.provider || ''; const x = by[k] = by[k] || { n: 0, kwh: 0 }; x.n++; x.kwh += r.charge_energy_added || 0; });
  chKeys = Object.keys(by).sort((a, b) => by[b].kwh - by[a].kwh);
  const nm = (k) => k || X('Nespecificat', 'Unspecified');
  fb.innerHTML = lfBar('charges') + `
  <div class="pchips"><button class="pchip ${chF.p === null ? 'on' : ''}" data-cp="-1">${X('Toți furnizorii', 'All providers')} <small>${inPeriod.length}</small></button>${chKeys.map((k, i) => `<button class="pchip ${chF.p === k ? 'on' : ''}" data-cp="${i}">${esc(nm(k))} <small>${by[k].n}</small></button>`).join('')}</div>`;
  const rows = chFiltered();
  const kwh = rows.reduce((s, x) => s + (x.charge_energy_added || 0), 0), cost = rows.reduce((s, x) => s + (x.cost_eff || 0), 0);
  const nocost = rows.filter((x) => x.cost_eff == null).length;
  const kwhC = rows.filter((x) => x.cost_eff != null).reduce((s, x) => s + (x.charge_energy_added || 0), 0);   // pretul mediu = cost / kWh doar din sesiunile care au cost
  let html = `<h2>${chF.p === null ? X('Total', 'Total') : esc(nm(chF.p))}</h2><div class="grid">${stat(X('Sesiuni', 'Sessions'), nf(rows.length))}${stat(X('Energie încărcată', 'Energy charged'), nf(kwh, 1), 'kWh')}${stat(X('Cost total', 'Total cost'), nf(cost, 2), cu)}${stat(X('Cost mediu', 'Average cost'), kwhC > 0 ? nf(cost / kwhC, 2) : '—', cu + '/kWh')}</div>`;
  if (nocost) html += `<p class="note" style="margin:8px 2px 0">${nocost} ${X('sesiuni fără cost înregistrat (nu intră în total). Poți introduce costul din pagina fiecărei încărcări.', 'sessions without a recorded cost (not in the total). You can enter the cost on each charge’s page.')}</p>`;
  if (!rows.length) html += `<div class="empty">${X('Nicio încărcare pentru filtrul ales.', 'No charges for this filter.')}</div>`;
  const agg = {}, nShow = lfGet('charges').n, shown = rows.slice(0, nShow);
  shown.forEach((r) => { const k = dayKey(r.start_date); (agg[k] = agg[k] || []).push(r); });
  Object.keys(agg).sort().reverse().forEach((k) => {
    const g = agg[k], dk = g.reduce((s, x) => s + (x.charge_energy_added || 0), 0), dc = g.reduce((s, x) => s + (x.cost_eff || 0), 0);
    html += `<div class="day"><span>${dayLabel(k)}</span><span>+${nf(dk, 1)} kWh${dc ? ' · ' + nf(dc, 2) + ' ' + cu : ''}</span></div>` + g.map(chargeItem).join('');
  });
  if (rows.length > shown.length) html += `<div class="links" style="margin:14px 2px"><a href="#" data-lfmore="${nShow}">${X('Afișează încă ', 'Show ')}${Math.min(nShow, rows.length - shown.length)}${X('', ' more')} <small>(${shown.length}/${rows.length})</small></a></div>`;
  lb.innerHTML = lfSelBar('charges') + html;
  lfBind('charges', () => render());
  lfSelBind('charges');
  fb.querySelectorAll('[data-cp]').forEach((b) => b.onclick = () => { const i = +b.dataset.cp; chF.p = i < 0 ? null : chKeys[i]; drawChargeList(); });
}
async function afterChargeEdit() {
  const box = $('#chedit'), c = window.__chrow; if (!box || !c) return;
  if (!chRows.length) { try { chRows = await fetchCharges(); } catch (x) { /* ignore */ } }
  const cu = esc(CU()), provs = [...new Set(chRows.map((r) => r.provider).filter(Boolean))].sort();
  const eff = c.cost_real ?? c.cost;
  setHtml(box, `<h2>${X('Cost și furnizor', 'Cost & provider')}</h2><div class="card">
    <div class="addf"><label>${X('Cost total', 'Total cost')} (${cu})<input id="ce_cost" type="number" inputmode="decimal" step="0.01" min="0" value="${c.cost_manual ?? ''}" placeholder="${eff != null ? nf(eff, 2) : ''}"></label>
      <label>${X('Furnizor', 'Provider')}<input id="ce_prov" list="ce_provs" maxlength="40" value="${esc(c.provider_set ? c.provider : '')}" placeholder="${esc(c.provider || 'ex. Ionity')}"><datalist id="ce_provs">${provs.map((p) => `<option value="${esc(p)}">`).join('')}</datalist></label></div>
    <div class="links"><a href="#" id="ce_save">${X('Salvează', 'Save')}</a>${c.cost_manual != null || c.provider_set ? `<a href="#" id="ce_clear">${X('Șterge modificările', 'Clear changes')}</a>` : ''}</div>
    <div class="toast" aria-live="polite" id="ce_msg">${X('Costul introdus înlocuiește costul TeslaMate și estimarea, în listă și în statistici. Se salvează doar în această aplicație, nu în TeslaMate. Lasă gol ca să revii la cost automat.', 'The cost you enter replaces the TeslaMate cost and the estimate in the list and in the statistics. It is stored only in this app, not in TeslaMate. Leave empty to go back to the automatic cost.')}</div></div>`);
  const say = (t, cls) => { const m = $('#ce_msg'); if (m) { m.textContent = t; m.className = 'toast ' + (cls || ''); } };
  const send = async (body) => {
    say(X('Se salvează…', 'Saving…'), 'busy');
    const [ok, j] = await pinPost('/api/charge/meta', Object.assign({ id: c.id }, body));
    if (ok) { say('✓ ' + X('Salvat', 'Saved'), 'ok'); setTimeout(render, 600); } else say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad');
  };
  const sv = $('#ce_save'); if (sv) sv.onclick = (ev) => { ev.preventDefault(); send({ cost: $('#ce_cost').value, provider: $('#ce_prov').value }); };
  const cl = $('#ce_clear'); if (cl) cl.onclick = (ev) => { ev.preventDefault(); send({ cost: '', provider: '' }); };
}
function costStats(ch, d) {
  const cu = CU(), eff = ch.cost_eff ?? ch.cost ?? 0, tmc = ch.cost || 0;
  let h = stat(X('Cost total', 'Total cost'), nf(eff, 2), cu);
  if (Math.abs(eff - tmc) > 0.005) h += stat(X('Cost TeslaMate', 'TeslaMate cost'), nf(tmc, 2), cu);
  h += stat(X('Cost încărcări / 100 km', 'Charging cost / 100 km'), d.km > 0 && eff != null ? nf(eff / d.km * 100, 2) : '—', cu);
  if (eff < tmc - 0.005) h += stat(X('Economie față de TeslaMate', 'Saved vs TeslaMate'), nf(tmc - eff, 2), cu);
  if (ch.manual_n) h += stat(X('Sesiuni cu cost manual', 'Sessions with manual cost'), nf(ch.manual_n));
  return h;
}
function iceBlock(o) {
  const ic = o.ice || {}, cu = CU(), on = !!ic.enabled;
  const last = (ic.prices || []).slice(-1)[0];
  let body = '';
  if (!on) body += `<p class="note" style="margin:0">${X('Introdu consumul unei mașini termice comparabile (l/100 km) și vezi cât ai fi cheltuit pe combustibil pentru aceiași kilometri. Prețul combustibilului se preia automat în fiecare zi și se stochează.', 'Enter the consumption of a comparable petrol/diesel car (l/100 km) to see what you would have spent on fuel for the same kilometres. The fuel price is fetched automatically every day and stored.')}</p>`;
  else {
    body += `<div class="grid">${stat(X('Cost combustibil (termică)', 'Fuel cost (ICE car)'), nf(ic.cost, 2), cu)}${stat(X('Cost electric (estimat)', 'Electric cost (estimated)'), ic.ev_cost != null ? nf(ic.ev_cost, 2) : '—', cu)}
      ${stat(X('Economie', 'Saved'), ic.saving != null ? nf(ic.saving, 2) : '—', cu)}${stat(X('Litri evitați', 'Litres avoided'), nf(ic.liters, 1), 'l')}
      ${stat(X('Preț mediu combustibil', 'Average fuel price'), ic.avg_price != null ? nf(ic.avg_price, 2) : '—', cu + '/l')}${stat(X('Cost / 100 km: termică vs electric (energia consumată)', 'Cost / 100 km: ICE vs electric (energy used)'), (ic.per100_ice != null ? nf(ic.per100_ice, 1) : '—') + ' vs ' + (ic.per100_ev != null ? nf(ic.per100_ev, 1) : '—'), cu)}</div>`;
    body += `<h3 class="sub">${X('Prețul combustibilului pe zile', 'Fuel price per day')} (${cu}/l)${last ? ' · ' + X('azi ', 'now ') + nf(last.price, 2) : ''}</h3>`
      + ((ic.prices || []).length > 1 ? '<div class="chart">' + line(ic.prices.map((p) => [+new Date(p.day + 'T12:00:00'), p.price]), { color: '#d9ba80', dec: 2 }) + '</div>' : `<div class="mut" style="padding:8px 0;font-size:13px">${X('Prețul se stochează în fiecare zi; graficul apare după a doua zi de citire.', 'The price is stored every day; the chart appears after the second day of readings.')}</div>`);
    body += `<p class="note" style="margin:8px 0 0">${X('Litri = km/100 × consum, la prețul din fiecare zi', 'Litres = km/100 × consumption, at that day’s price')} (${ic.type === 'diesel' ? X('motorină', 'diesel') : ic.type === 'manual' ? X('preț manual', 'manual price') : X('benzină Euro 95', 'Euro 95 petrol')}).
      ${ic.est_days ? ` ${ic.est_days} ${X('din', 'of')} ${(ic.days || []).length} ${X('zile folosesc ultimul preț cunoscut (stocarea zilnică a început de curând).', 'days use the latest known price (daily storage only started recently).')}` : ''}
      ${ic.missing_days ? ` ${ic.missing_days} ${X('zile fără preț — setează un preț manual.', 'days without a price — set a manual price.')}` : ''}
      ${X('Sursa prețului: media națională de pe fuel-prices.eu (pentru România, din Monitorul Prețurilor Carburanților).', 'Price source: the national average from fuel-prices.eu (for Romania, the official fuel price monitor).')}</p>`;
  }
  const dp = (window.__fuelCfg = window.__fuelCfg || {});
  const sel = ic.type || 'euro95';
  body += `<div class="addf"><label>${X('Consum termică (l/100 km)', 'ICE consumption (l/100 km)')}<input id="ic_l100" type="number" inputmode="decimal" step="0.1" min="0" max="60" value="${on ? ic.l100 : ''}" placeholder="ex. 7.5"></label>
    <label>${X('Combustibil', 'Fuel')}<select id="ic_type"><option value="euro95" ${sel === 'euro95' ? 'selected' : ''}>${X('Benzină (Euro 95)', 'Petrol (Euro 95)')}</option><option value="diesel" ${sel === 'diesel' ? 'selected' : ''}>${X('Motorină', 'Diesel')}</option><option value="manual" ${sel === 'manual' ? 'selected' : ''}>${X('Preț manual', 'Manual price')}</option></select></label>
    <label>${X('Preț manual', 'Manual price')} (${cu}/l)<input id="ic_price" type="number" inputmode="decimal" step="0.01" min="0" value="${dp.manual ?? ''}" placeholder="${X('opțional', 'optional')}"></label></div>
    <div class="links"><a href="#" data-ice="save">${X('Salvează', 'Save')}</a><a href="#" data-ice="refresh">${X('Actualizează prețul acum', 'Refresh price now')}</a></div><div class="toast" aria-live="polite" id="ic_msg" style="display:none"></div>`;
  api('/api/fuel').then((f) => { window.__fuelCfg = { manual: f.manual }; const pi = $('#ic_price'); if (pi && f.manual != null && !pi.value) pi.value = f.manual; }).catch(() => {});
  return `<h2>${X('Comparație cu o mașină termică', 'Compared with a petrol/diesel car')}</h2><div class="card">${body}</div>`;
}
async function iceActions(b) {
  const say = (t, cls) => { const m = $('#ic_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
  if (b.dataset.ice === 'refresh') {
    say(X('Se citește prețul…', 'Reading the price…'), 'busy');
    const [ok, j] = await pinPost('/api/fuel/refresh', {});
    if (ok) { say('✓ ' + X('Preț actualizat', 'Price updated'), 'ok'); setTimeout(render, 700); } else say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad');
    return;
  }
  say(X('Se salvează…', 'Saving…'), 'busy');
  const [ok, j] = await pinPost('/api/config', { ice_l100: $('#ic_l100').value || '__clear__', fuel_type: $('#ic_type').value, fuel_price: $('#ic_price').value || '__clear__' });
  if (ok) { say('✓ ' + X('Salvat', 'Saved'), 'ok'); setTimeout(render, 1200); } else say('✗ ' + (j.reason || j.error || X('Eroare', 'Error')), 'bad');
}

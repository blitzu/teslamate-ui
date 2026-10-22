'use strict';
const $ = (s) => document.querySelector(s);
const view = $('#view'), nav = $('#nav');

/* ---------- limba (RO / EN) ---------- */
let LANG = 'ro';
try { LANG = localStorage.getItem('lang') || ((navigator.language || 'ro').toLowerCase().startsWith('ro') ? 'ro' : 'en'); } catch (e) { /* ignore */ }
const LOC = () => LANG === 'ro' ? 'ro-RO' : 'en-GB';
const EN = {
  'Mașină': 'Car', 'Curse': 'Drives', 'Încărcări': 'Charges', 'Statistici': 'Stats', 'Setări': 'Settings',
  'Azi': 'Today', 'Ieri': 'Yesterday', 'Prea puține date': 'Not enough data', 'Nicio mașină': 'No car',
  'Doarme': 'Asleep', 'Se încarcă': 'Charging', 'În mișcare': 'Driving', 'Suspendată': 'Suspended', 'Se actualizează': 'Updating',
  'Blocată': 'Locked', 'Deblocată': 'Unlocked', 'Sentry activ': 'Sentry on', 'Sentry oprit': 'Sentry off',
  'Climatizare pornită': 'Climate on', 'Climatizare oprită': 'Climate off', 'Conectată la priză': 'Plugged in', 'Neconectată': 'Unplugged',
  'Ceva e deschis': 'Something is open', 'Conexiune TeslaMate instabilă': 'TeslaMate connection unstable',
  'Odometru': 'Odometer', 'Temperatură': 'Temperature', 'int': 'in', 'ext': 'out', 'Putere': 'Power', 'Locație': 'Location', 'În drum': 'On the road',
  'Timp până la plin': 'Time to full', 'Software': 'Software', 'Energie adăugată': 'Energy added', 'Autonomie nominală': 'Rated range',
  'Tensiune · curent': 'Voltage · current', 'Viteză': 'Speed', 'Baterie utilizabilă': 'Usable battery', 'km autonomie': 'km range',
  'Față stânga': 'Front left', 'Față dreapta': 'Front right', 'Spate stânga': 'Rear left', 'Spate dreapta': 'Rear right',
  'Comenzi': 'Controls', 'Detalii': 'Details', 'Ultima cursă · ultima încărcare': 'Last drive · last charge',
  'Încă nu există curse sau încărcări': 'No drives or charges yet', 'Nimic înregistrat încă.': 'Nothing recorded yet.',
  'Rezumat': 'Summary', 'Distanță': 'Distance', 'Durată': 'Duration', 'Consum': 'Consumption', 'Eficiență': 'Efficiency', 'Viteză max': 'Top speed',
  'Putere max': 'Max power', 'Baterie': 'Battery', 'Temp. ext.': 'Outside temp.', 'Urcare': 'Ascent',
  'Viteză (km/h)': 'Speed (km/h)', 'Putere (kW)': 'Power (kW)', 'Baterie (%)': 'Battery (%)', 'Altitudine (m)': 'Altitude (m)',
  '‹ Curse': '‹ Drives', '‹ Încărcări': '‹ Charges', 'Adăugat': 'Added', 'Consumat din rețea': 'Drawn from grid', 'Cost': 'Cost', 'lei': 'RON',
  'Putere de încărcare (kW)': 'Charging power (kW)', 'Nivel baterie (%)': 'Battery level (%)', 'Energie adăugată (kWh)': 'Energy added (kWh)',
  'Conducere': 'Driving', 'Timp la volan': 'Time driving', 'Consum mediu': 'Average consumption', 'Energie folosită': 'Energy used', 'Viteză maximă': 'Top speed',
  'Kilometri pe zi': 'Kilometres per day', 'Încărcare': 'Charging', 'Cost total': 'Total cost', 'Cost / 100 km': 'Cost / 100 km',
  'kWh încărcați pe zi': 'kWh charged per day', 'Autonomie estimată la 100% (km)': 'Estimated range at 100% (km)',
  'Calculată din autonomia ideală raportată la nivelul bateriei; scăderea lentă în timp indică degradarea.': 'Calculated from ideal range reported against battery level; a slow decline over time indicates degradation.',
  'Stare mașină (ultimele 30 de zile)': 'Car state (last 30 days)', 'Actualizări software': 'Software updates',
  'Comenzile apar după ce mașina e conectată în TeslaMate și contul Tesla e autorizat.': 'Controls appear once the car is connected in TeslaMate and the Tesla account is authorised.',
  'Aplicație Tesla (client id/secret) și domeniu configurate': 'Tesla app (client id/secret) and domain configured',
  'Cheie publică generată': 'Public key generated', 'Cont Tesla autorizat': 'Tesla account authorised', 'PIN setat': 'PIN set',
  'Conectează contul Tesla': 'Connect Tesla account',
  'Oprește Sentry': 'Turn Sentry off', 'Pornită': 'On', 'Oprită': 'Off', 'Activ': 'On', 'Oprit': 'Off', 'Deschis': 'Open', 'Închis': 'Closed', 'Deschise': 'Open', 'Închise': 'Closed',
  'Conectată': 'Plugged in', 'Limită încărcare': 'Charge limit', 'Comenzile pot trezi mașina (durează câteva secunde).': 'Commands may wake the car (takes a few seconds).', 'Domeniu înregistrat la Tesla': 'Domain registered with Tesla', 'Înregistrează domeniul la Tesla': 'Register domain with Tesla',
  'Instalează cheia virtuală în mașină': 'Install virtual key in the car', 'Se înregistrează…': 'Registering…', 'Domeniu înregistrat.': 'Domain registered.',
  'Deblochează': 'Unlock', 'Blochează': 'Lock', 'Oprește clima': 'Stop climate', 'Pornește clima': 'Start climate',
  'Oprește încărcarea': 'Stop charging', 'Începe încărcarea': 'Start charging', 'Deschide portul': 'Open port', 'Pornește Sentry': 'Turn Sentry on',
  'Portbagaj': 'Trunk', 'Aerisește': 'Vent windows', 'Închide geamuri': 'Close windows', 'Faruri': 'Flash lights', 'Claxon': 'Honk',
  'Limita de încărcare · comenzile pot trezi mașina (durează câteva secunde).': 'Charge limit · commands may wake the car (takes a few seconds).',
  'Deblochezi mașina?': 'Unlock the car?', 'Deschizi frunk-ul?': 'Open the frunk?', 'Deschizi portbagajul?': 'Open the trunk?',
  'Aerisești geamurile?': 'Vent the windows?', 'Claxonezi?': 'Honk the horn?', 'PIN aplicație:': 'App PIN:', 'PIN greșit.': 'Wrong PIN.',
  'Limită ': 'Limit ', 'Limită': 'Limit', ' zile': ' days', '1 an': '1 year', 'Eroare la încărcare: ': 'Failed to load: ',
  'Online': 'Online', 'Offline': 'Offline', 'Update disponibil': 'Update available',
  'Acasă': 'Home', 'Birou': 'Office', 'Părinți': 'Parents', 'Aeroport': 'Airport', 'Benzinărie Petrom': 'Petrom gas station',
  'Piața Centrală': 'Central Market', 'Sala de sport': 'Gym',
};
if (typeof EN2 !== 'undefined') Object.assign(EN, EN2);
const tr = (s) => LANG === 'en' ? (EN[s] ?? s) : s;
function i18nDom(root) {
  if (LANG !== 'en' || !root) return;
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (w.nextNode()) nodes.push(w.currentNode);
  nodes.forEach((n) => {
    const v = n.nodeValue, k = v.trim();
    if (k && EN[k] !== undefined) n.nodeValue = v.replace(k, EN[k]);
  });
}
const setHtml = (el, html) => { if (el) { el.innerHTML = html; i18nDom(el); } };
let S = { demo: false, cars: [], links: {} };
let car = 1, map = null, route = '', cache = {};

/* ---------- helpers ---------- */
const nf = (v, d = 0) => v === null || v === undefined || isNaN(v) ? '—' : Number(v).toLocaleString(LOC(), { minimumFractionDigits: d, maximumFractionDigits: d });
const T = (s) => s instanceof Date ? s : new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + 'Z');
const hm = (min) => { min = Math.round(min || 0); return min >= 60 ? Math.floor(min / 60) + ' h ' + String(min % 60).padStart(2, '0') + ' min' : min + ' min'; };
const tm = (s) => T(s).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });
const dayKey = (s) => { const d = T(s); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
const dayLabel = (k) => {
  const d = new Date(k + 'T00:00:00'), t = new Date(); t.setHours(0, 0, 0, 0);
  const diff = Math.round((t - d) / 864e5);
  return diff === 0 ? 'Azi' : diff === 1 ? 'Ieri' : d.toLocaleDateString(LOC(), { weekday: 'long', day: 'numeric', month: 'long' });
};
const ago = (s) => {
  const m = Math.max(0, Math.round((Date.now() - T(s).getTime()) / 60000));
  if (LANG === 'en') return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : m < 1440 ? Math.floor(m / 60) + ' h ago' : Math.floor(m / 1440) + ' days ago';
  return m < 1 ? 'chiar acum' : m < 60 ? 'acum ' + m + ' min' : m < 1440 ? 'acum ' + Math.floor(m / 60) + ' h' : 'acum ' + Math.floor(m / 1440) + ' zile';
};
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const api = async (p) => { const r = await fetch(p, { cache: 'no-store' }); if (!r.ok) throw new Error(r.status); return r.json(); };
const stat = (l, v, u = '') => `<div class="st"><i>${l}</i><b>${v}${u ? '<small>' + u + '</small>' : ''}</b></div>`;
const socCls = (s) => s < 20 ? 'low' : s < 45 ? 'mid' : '';

/* ---------- charts ---------- */
function line(pts, o = {}) {
  pts = pts.filter((p) => p[1] !== null && p[1] !== undefined && !isNaN(p[1]));
  if (pts.length < 2) return '<div class="mut" style="padding:20px 0;font-size:13px">Prea puține date</div>';
  const W = 340, H = o.h || 110, pl = 30, pr = 6, pt = 8, pb = 18;
  const xs = pts.map((p) => +p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  let y0 = o.min ?? Math.min(...ys), y1 = o.max ?? Math.max(...ys);
  if (y0 === y1) { y0 -= 1; y1 += 1; }
  const X = (x) => pl + (x - x0) / (x1 - x0 || 1) * (W - pl - pr), Y = (y) => pt + (1 - (y - y0) / (y1 - y0)) * (H - pt - pb);
  const d = pts.map((p, i) => (i ? 'L' : 'M') + X(+p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1)).join('');
  const id = 'g' + Math.random().toString(36).slice(2, 7), c = o.color || '#6fd6b8';
  const fmtX = o.fx || ((x) => new Date(x).toLocaleDateString(LOC(), { day: 'numeric', month: 'short' }));
  return `<svg viewBox="0 0 ${W} ${H}"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c}" stop-opacity=".35"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></linearGradient></defs>
  <path d="M${pl} ${Y(y0)}H${W - pr}M${pl} ${Y((y0 + y1) / 2)}H${W - pr}M${pl} ${Y(y1)}H${W - pr}" stroke="#ffffff10"/>
  <path d="${d}L${X(x1)} ${Y(y0)}L${X(x0)} ${Y(y0)}Z" fill="url(#${id})"/><path d="${d}" fill="none" stroke="${c}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
  <text x="${pl - 5}" y="${Y(y1) + 3}" text-anchor="end">${nf(y1, o.dec || 0)}</text><text x="${pl - 5}" y="${Y(y0) + 3}" text-anchor="end">${nf(y0, o.dec || 0)}</text>
  <text x="${pl}" y="${H - 3}">${fmtX(x0)}</text><text x="${W - pr}" y="${H - 3}" text-anchor="end">${fmtX(x1)}</text></svg>`;
}
function bars(items, o = {}) {
  if (!items.length) return '<div class="mut" style="padding:20px 0;font-size:13px">Prea puține date</div>';
  const W = 340, H = o.h || 110, pb = 18, mx = Math.max(...items.map((i) => i.v), 1);
  const bw = (W - 8) / items.length;
  const b = items.map((it, i) => { const h = (it.v / mx) * (H - pb - 14); return `<rect x="${4 + i * bw + bw * .12}" y="${H - pb - h}" width="${Math.max(1.5, bw * .76)}" height="${Math.max(h, it.v > 0 ? 1.5 : 0)}" rx="${Math.min(4, bw * .3)}" fill="${o.color || '#6fd6b8'}"/>`; }).join('');
  return `<svg viewBox="0 0 ${W} ${H}">${b}<text x="4" y="${H - 3}">${esc(items[0].l)}</text><text x="${W - 4}" y="${H - 3}" text-anchor="end">${esc(items[items.length - 1].l)}</text><text x="${W - 4}" y="10" text-anchor="end">max ${nf(mx, o.dec || 0)}</text></svg>`;
}

/* ---------- car svg ---------- */
function carSvg(L) {
  const tp = (x, y, k) => { const v = L['tpms_pressure_' + k]; return `<text class="tp ${v != null && v < 2.5 ? 'low' : ''}" x="${x}" y="${y}" text-anchor="middle">${v == null ? '—' : nf(v, 1)}</text><text class="tpu" x="${x}" y="${y + 9}" text-anchor="middle">bar</text>`; };
  const charging = L.charging_state === 'Charging' || L.state === 'charging', plug = L.plugged_in;
  const hot = (L.outside_temp ?? 15) <= 22 ? '' : 'cold';
  return `<svg viewBox="0 0 300 480" role="img" aria-label="Tesla">
<defs><linearGradient id="bd" x1="0" x2="1"><stop offset="0" stop-color="#cfd5db"/><stop offset=".22" stop-color="#f4f6f8"/><stop offset=".5" stop-color="#fff"/><stop offset=".78" stop-color="#f1f3f5"/><stop offset="1" stop-color="#c4cad1"/></linearGradient>
<linearGradient id="gl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2b3540"/><stop offset=".55" stop-color="#10151b"/><stop offset="1" stop-color="#1b232c"/></linearGradient>
<radialGradient id="fl"><stop offset="0" stop-color="#6fd6b8" stop-opacity=".22"/><stop offset="1" stop-color="#6fd6b8" stop-opacity="0"/></radialGradient>
<radialGradient id="sh"><stop offset="0" stop-color="#000" stop-opacity=".75"/><stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient></defs>
<ellipse cx="150" cy="250" rx="150" ry="235" fill="url(#fl)" opacity="${charging || plug ? 1 : .35}"/>
${L.sentry_mode ? '<g transform="translate(150 240)"><ellipse class="radar r1" rx="104" ry="228"/><ellipse class="radar r2" rx="104" ry="228"/><ellipse class="radar r3" rx="104" ry="228"/></g>' : ''}
<ellipse cx="150" cy="258" rx="108" ry="232" fill="url(#sh)"/>
<g transform="translate(50 0)">
<rect x="14" y="82" width="18" height="50" rx="8" fill="#0b0d10"/><rect x="168" y="82" width="18" height="50" rx="8" fill="#0b0d10"/><rect x="15" y="328" width="18" height="52" rx="8" fill="#0b0d10"/><rect x="167" y="328" width="18" height="52" rx="8" fill="#0b0d10"/>
<path d="M100 14C132 14 160 30 166 70C170 110 174 160 175 220C176 300 174 380 168 420C164 448 134 466 100 466C66 466 36 448 32 420C26 380 24 300 25 220C26 160 30 110 34 70C40 30 68 14 100 14Z" fill="url(#bd)" stroke="#9aa3ad" stroke-width=".8"/>
<path d="M72 30C86 24 114 24 128 30C136 60 138 96 134 124L66 124C62 96 64 60 72 30Z" fill="none" stroke="#c4cad1" stroke-width=".9"/>
<path d="M64 124C74 112 126 112 136 124L141 190L59 190Z" fill="url(#gl)"/><path d="M59 190L141 190L145 318L55 318Z" fill="#0d1116"/><path d="M59 190L141 190L145 318L55 318Z" fill="url(#gl)" opacity=".35"/>
<path d="M55 318L145 318C141 340 136 354 128 366L72 366C64 354 59 340 55 318Z" fill="url(#gl)"/>
<path d="M46 150L54 196L54 312L46 330M154 150L146 196L146 312L154 330" fill="none" stroke="#1b232c" stroke-width="5" stroke-linecap="round" opacity=".85"/>
<path d="M30 232H46M154 232H170" stroke="#aeb6bf"/><path d="M62 124H138" stroke="#d6dbe0" stroke-width=".8"/>
<ellipse cx="26" cy="152" rx="9" ry="5" transform="rotate(-28 26 152)" fill="#f1f3f5" stroke="#9aa3ad" stroke-width=".7"/><ellipse cx="174" cy="152" rx="9" ry="5" transform="rotate(28 174 152)" fill="#f1f3f5" stroke="#9aa3ad" stroke-width=".7"/>
<path d="M42 46C50 38 64 32 80 29L82 36C68 40 56 46 49 55ZM158 46C150 38 136 32 120 29L118 36C132 40 144 46 151 55Z" fill="#dfeeff"/>
<path d="M44 438C52 446 66 452 84 454L84 447C70 446 58 441 49 432ZM156 438C148 446 134 452 116 454L116 447C130 446 142 441 151 432Z" fill="#e5483f"/><path d="M84 452H116" stroke="#e5483f" stroke-width="2"/>
<circle class="${plug || charging ? 'glow' : ''}" cx="38" cy="428" r="5" fill="${plug || charging ? '#6fd6b8' : '#7f8994'}"/>
${L.frunk_open ? '<path d="M72 30C86 24 114 24 128 30C136 60 138 96 134 124L66 124C62 96 64 60 72 30Z" fill="#ffb15c" fill-opacity=".35" stroke="#ffb15c" stroke-dasharray="4 3"/>' : ''}
${L.trunk_open ? '<path d="M70 366H130L136 440C120 452 80 452 64 440Z" fill="#ffb15c" fill-opacity=".35" stroke="#ffb15c" stroke-dasharray="4 3"/>' : ''}
${L.doors_open ? '<rect x="22" y="150" width="14" height="168" rx="6" fill="#ffb15c" fill-opacity=".4" stroke="#ffb15c"/><rect x="164" y="150" width="14" height="168" rx="6" fill="#ffb15c" fill-opacity=".4" stroke="#ffb15c"/>' : ''}
${L.windows_open ? '<path d="M50 200L50 300M150 200L150 300" stroke="#8fd3ff" stroke-width="3" stroke-linecap="round" stroke-dasharray="2 6"/>' : ''}
${L.is_climate_on ? `<path class="heat ${hot}" d="M78 226q10-10 22 0t22 0"/><path class="heat h2 ${hot}" d="M78 246q10-10 22 0t22 0"/><path class="heat h3 ${hot}" d="M78 266q10-10 22 0t22 0"/>` : ''}
</g>${tp(24, 104, 'fl')}${tp(276, 104, 'fr')}${tp(24, 352, 'rl')}${tp(276, 352, 'rr')}</svg>`;
}

/* ---------- pages ---------- */
function cur() { return S.cars.find((c) => c.id === car) || S.cars[0]; }
const STATE = { online: 'Online', asleep: 'Doarme', offline: 'Offline', charging: 'Se încarcă', driving: 'În mișcare', suspended: 'Suspendată', updating: 'Se actualizează' };

function pageCar() {
  const c = cur(); if (!c) return '<div class="empty">Nicio mașină</div>';
  const L = c.live || {};
  const driving = L.state === 'driving' || (L.shift_state && L.shift_state !== 'P');
  const charging = L.state === 'charging' || L.charging_state === 'Charging';
  const soc = L.usable_battery_level ?? L.battery_level, lim = L.charge_limit_soc;
  const range = L.est_battery_range_km ?? L.ideal_battery_range_km ?? L.rated_battery_range_km;
  const st = driving ? 'În mișcare' : charging ? 'Se încarcă' : (STATE[L.state] || L.state || '—');
  const pc = charging || (!driving && L.state === 'online') ? 'ok' : driving ? 'warn' : '';
  const chip = (t, on, alert) => `<span class="chip ${on ? 'on' : ''} ${alert ? 'alert' : ''}"><i></i>${t}</span>`;
  const chips = [
    L.locked != null ? chip(L.locked ? 'Blocată' : 'Deblocată', L.locked, !L.locked) : '',
    L.sentry_mode != null ? chip(L.sentry_mode ? 'Sentry activ' : 'Sentry oprit', L.sentry_mode) : '',
    L.is_climate_on != null ? chip(L.is_climate_on ? 'Climatizare pornită' : 'Climatizare oprită', L.is_climate_on) : '',
    L.plugged_in != null ? chip(L.plugged_in ? 'Conectată la priză' : 'Neconectată', L.plugged_in) : '',
    (L.doors_open || L.windows_open || L.trunk_open || L.frunk_open) ? `<span id="openchips">${openChips(L, (S.opens || {})[c.id]) || chip('Ceva e deschis', false, true)}</span>` : '',
    L.update_available ? chip(tr('Update disponibil') + (L.update_version ? ' ' + esc(L.update_version) : ''), false) : '',
    L.healthy === false ? chip('Conexiune TeslaMate instabilă', false, true) : '',
  ].join('');
  const tl = L.time_to_full_charge;
  const age = c.live_age != null ? (c.live_age < 90 ? 'live' : ago(new Date(Date.now() - c.live_age * 1000))) : (L.since ? ago(L.since) : '');
  const stats = [
    stat('Odometru', nf(L.odometer), 'km'),
    stat('Temperatură', nf(L.inside_temp) + '° <small>int</small> · ' + nf(L.outside_temp) + '° <small>ext</small>'),
    charging ? stat('Putere', nf(L.charger_power, 1), 'kW') : stat('Locație', esc(L.geofence || (driving ? 'În drum' : '—'))),
    charging ? stat('Timp până la plin', tl ? hm(tl * 60) : '—') : stat('Software', esc(L.version || '—')),
    charging ? stat('Energie adăugată', nf(L.charge_energy_added, 1), 'kWh') : stat('Autonomie nominală', nf(L.rated_battery_range_km), 'km'),
    charging ? stat('Tensiune · curent', nf(L.charger_voltage) + ' V · ' + nf(L.charger_actual_current) + ' A') : stat(driving ? 'Viteză' : 'Baterie utilizabilă', nf(driving ? L.speed : L.usable_battery_level), driving ? 'km/h' : '%'),
  ].join('');
  return `
<div class="top row"><div><h1>${esc(c.name || L.display_name || 'Tesla')}</h1><small>${esc(c.marketing_name || ('Model ' + (c.model || '')))}${c.trim && !/^\d+$/.test(c.trim) ? ' · ' + esc(c.trim) : ''}${age ? ' · ' + age : ''}</small></div><div class="sp"></div>${S.demo ? '<span class="pill demo">DEMO</span>' : ''}<span class="pill ${pc}">${st}</span></div>
<div class="card" style="margin-top:12px">
  <div id="sidev">${sideView(L, (S.opens || {})[c.id])}</div>
  <div class="stage photo ${c.image === '/car.png' ? 'top' : ''} ${charging ? 'chg' : ''}" id="stage">${c.image ? `<div class="cw"><img src="${esc(c.image)}" alt=""></div>` : carSvg(L)}${c.image === '/car.png' ? ['fl', 'fr', 'rl', 'rr'].map((k) => { const v = L['tpms_pressure_' + k]; return `<span class="tw ${k} ${v != null && v < 2.5 ? 'low' : ''}">${v == null ? '—' : nf(v, 1)}<small>bar</small></span>`; }).join('') : ''}</div>
  <div class="tpr ${c.image === '/car.png' ? 'hide' : ''}">${['fl', 'fr', 'rl', 'rr'].map((k, i) => { const v = L['tpms_pressure_' + k]; return `<span class="${v != null && v < 2.5 ? 'low' : ''}"><i>${['Față stânga', 'Față dreapta', 'Spate stânga', 'Spate dreapta'][i]}</i><b>${v == null ? '—' : nf(v, 1)}</b> bar</span>`; }).join('')}</div>
  <div class="row" style="align-items:flex-end;margin-top:4px"><div class="pct">${nf(soc)}<small>%</small></div><div class="rng"><b>${nf(range)}</b> km autonomie</div></div>
  <div class="bar"><div class="fill ${socCls(soc)} ${charging ? 'chg' : ''}" style="width:${Math.max(0, Math.min(100, soc || 0))}%"></div>${lim ? `<div class="lim" style="left:calc(${Math.min(100, lim)}% - 1px)"></div>` : ''}</div>
  <div class="sub"><span>${charging ? tr('Se încarcă') + (L.charger_power ? ' · ' + nf(L.charger_power, 1) + ' kW' : '') : ''}</span><span>${lim ? tr('Limită ') + nf(lim) + '%' : ''}</span></div>
  <div class="chips">${chips}</div>
  ${sleepBlock(c)}
</div>
<h2>Comenzi</h2><div id="cmds"></div>
<h2>Locație</h2><div id="map"></div>
<h2>Detalii</h2><div class="grid">${stats}</div>
<h2>Ultima cursă · ultima încărcare</h2><div id="last"></div>
<div class="links"><a href="#/climate">🌡 ${X('Clima', 'Climate')} ›</a></div>
${S.links && S.links.teslamate ? `<div class="links"><a href="${esc(S.links.teslamate)}" target="_blank" rel="noopener">TeslaMate</a><a href="${esc(S.links.grafana)}" target="_blank" rel="noopener">Grafana</a></div>` : ''}
${S.public_demo ? '<p class="note">' + (LANG === 'en' ? 'Demo with sample data - no real vehicle is connected.' : 'Demonstrație cu date fictive - nicio mașină reală nu este conectată.') + '</p>' : S.demo ? '<p class="note">' + (LANG === 'en' ? 'Demo data. Connect your Tesla account in TeslaMate (' + esc(S.links.teslamate) + ') and every page fills in with real data.' : 'Date demonstrative. Conectează contul Tesla în TeslaMate (' + esc(S.links.teslamate) + ') și toate paginile se umplu singure cu datele reale.') + '</p>' : ''}
${S.db_error ? '<p class="note">' + (LANG === 'en' ? 'The TeslaMate database is not responding right now.' : 'Baza de date TeslaMate nu răspunde momentan.') + '</p>' : ''}`;
}

function sleepBlock(c) {
  const z = c.sleep; if (!z) return '';
  const L = c.live || {}, since = T(z.since), mins = Math.max(0, Math.round((Date.now() - since.getTime()) / 60000));
  const asleep = L.state ? (L.state === 'asleep' || L.state === 'offline') : z.state === 'asleep';
  const d = (m) => hm(m), t = (x) => tm(x), from = X(' · din ', ' · since ') + t(since);
  const l1 = asleep ? X('😴 Doarme de ', '😴 Asleep for ') + d(mins) + from : X('Trează de ', 'Awake for ') + d(mins) + from;
  const l2 = z.last ? (asleep ? X('Somnul anterior: ', 'Previous sleep: ') : X('Ultimul somn: ', 'Last sleep: ')) + d((T(z.last.end) - T(z.last.start)) / 60000) + ' (' + t(z.last.start) + '–' + t(z.last.end) + ')' : X('Niciun somn înregistrat încă', 'No sleep recorded yet');
  const pc = Math.round((z.sec24 || 0) / 864);
  return `<a class="sleepc" href="#/parked" style="display:block;text-decoration:none;color:inherit"><b>${l1}</b><span>${l2}</span><span>${X('Somn în ultimele 24 h: ', 'Sleep in the last 24 h: ')}${hm((z.sec24 || 0) / 60)} (${pc}%)</span><span style="color:var(--mint)">${X('Detalii somn și consum în repaus ›', 'Sleep & idle drain details ›')}</span></a>`;
}

function drawMap(el, L) {
  if (!window.L || !el) return;
  if (map) { map.remove(); map = null; }
  const lat = L.latitude ?? 44.4268, lon = L.longitude ?? 26.1025;
  map = window.L.map(el, { zoomControl: false, attributionControl: true }).setView([lat, lon], 14);
  window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
  window.L.marker([lat, lon], { icon: window.L.divIcon({ className: '', html: '<div class="pin"></div>', iconSize: [18, 18], iconAnchor: [9, 9] }) }).addTo(map);
}

async function afterCar() {
  const c = cur(); if (!c) return;
  drawMap($('#map'), c.live || {});
  renderCmds();
  refreshOpenings(c);
  const im = $('#stage img');
  if (im) im.onerror = () => { $('#stage').classList.remove('photo'); $('#stage').innerHTML = carSvg(c.live || {}); };
  try {
    const [d, ch] = await Promise.all([api('/api/drives?car=' + c.id + '&limit=1'), api('/api/charges?car=' + c.id + '&limit=1')]);
    const parts = [];
    if (d[0]) parts.push(driveItem(d[0]));
    if (ch[0]) parts.push(chargeItem(ch[0]));
    setHtml($('#last'), parts.join('') || '<div class="empty">Încă nu există curse sau încărcări</div>');
  } catch (e) { /* ignore */ }
}

function driveItem(d) {
  const wh = d.distance > 0 && d.kwh != null ? d.kwh * 1000 / d.distance : null;
  return `<a class="item" href="#/drive/${d.id}"><div class="t"><span>${esc(d.start_name)}</span><span class="arr">→</span><span>${esc(d.end_name)}</span></div>
  <div class="m"><span><b>${nf(d.distance, 1)}</b> km</span><span><b>${hm(d.duration_min)}</b></span><span><b>${nf(d.kwh, 1)}</b> kWh</span><span><b>${nf(wh)}</b> Wh/km</span><span>${tm(d.start_date)}–${tm(d.end_date)}</span><span class="soc">${nf(d.start_soc)}% → ${nf(d.end_soc)}%</span></div></a>`;
}
function chargeItem(c) {
  return `<a class="item" href="#/charge/${c.id}"><div class="t"><span>${esc(c.name)}</span><span class="badge ${c.dc ? 'dc' : 'ac'}">${c.dc ? 'DC' : 'AC'}</span></div>
  <div class="m"><span><b>+${nf(c.charge_energy_added, 1)}</b> kWh</span><span><b>${hm(c.duration_min)}</b></span><span>max <b>${nf(c.power_max)}</b> kW</span>${c.cost_real != null ? `<span title="${X('Cost real estimat (doar energia din rețea) · TeslaMate: ', 'Estimated real cost (grid energy only) · TeslaMate: ')}${nf(c.cost, 2)}"><b>${nf(c.cost_real, 2)}</b> ${esc(S.currency ?? '€')} <small style="color:var(--mut)">(TM ${nf(c.cost, 2)})</small></span>` : (c.cost ? `<span><b>${nf(c.cost, 2)}</b> ${esc(S.currency ?? '€')}</span>` : '')}<span>${tm(c.start_date)}–${tm(c.end_date)}</span><span class="soc">${nf(c.start_soc)}% → ${nf(c.end_soc)}%</span></div></a>`;
}

async function pageList(kind) {
  const rows = await api('/api/' + kind + '?car=' + car + '&limit=120');
  const ctl = kind === 'charges' ? chargeCtlShell() : '';
  if (!rows.length) return `<div class="top"><h1>${kind === 'drives' ? 'Curse' : 'Încărcări'}</h1></div>${ctl}<div class="empty">Nimic înregistrat încă.</div>`;
  let last = '', html = '', agg = {};
  rows.forEach((r) => { const k = dayKey(r.start_date); (agg[k] = agg[k] || []).push(r); });
  Object.keys(agg).sort().reverse().forEach((k) => {
    const g = agg[k];
    const sum = kind === 'drives' ? nf(g.reduce((s, x) => s + (x.distance || 0), 0), 1) + ' km' : '+' + nf(g.reduce((s, x) => s + (x.charge_energy_added || 0), 0), 1) + ' kWh';
    html += `<div class="day"><span>${dayLabel(k)}</span><span>${sum}</span></div>` + g.map(kind === 'drives' ? driveItem : chargeItem).join('');
  });
  return `<div class="top"><h1>${kind === 'drives' ? 'Curse' : 'Încărcări'}</h1></div>${ctl}` + html;
}

function sec(title, inner) { return `<h2>${title}</h2><div class="card chart">${inner}</div>`; }

async function pageDrive(id) {
  const rows = await api('/api/drives?car=' + car + '&limit=200');
  const d = rows.find((r) => r.id == id) || rows[0];
  const dd = await api('/api/drive/' + id), pts = dd.points;
  const wh = d && d.distance > 0 && d.kwh != null ? d.kwh * 1000 / d.distance : null;
  const t = (p) => +T(p[0]);
  const html = `<a class="back" href="#/drives">‹ Curse</a>
  <div class="top"><h1 style="font-size:21px">${esc(tr(d?.start_name))} → ${esc(tr(d?.end_name))}</h1><small>${d ? T(d.start_date).toLocaleDateString(LOC(), { weekday: 'long', day: 'numeric', month: 'long' }) + ' · ' + tm(d.start_date) + '–' + tm(d.end_date) : ''}</small></div>
  <a class="play" href="#/trip/${id}"><svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>${X('Reluare traseu', 'Replay route')}</a>
  <div class="map big" id="dmap"></div>
  <h2>Rezumat</h2><div class="grid g3">${stat('Distanță', nf(d?.distance, 1), 'km')}${stat('Durată', hm(d?.duration_min))}${stat('Consum', nf(d?.kwh, 1), 'kWh')}${stat('Eficiență', nf(wh), 'Wh/km')}${stat('Viteză max', nf(d?.speed_max), 'km/h')}${stat('Putere max', nf(d?.power_max), 'kW')}${stat('Baterie', nf(d?.start_soc) + '→' + nf(d?.end_soc), '%')}${stat('Temp. ext.', nf(d?.outside_temp_avg, 1), '°C')}${stat('Urcare', nf(d?.ascent), 'm')}</div>
  ${driveEvents(dd.events)}
  <div class="toast" id="dtip">${X('Atinge un grafic ca să vezi punctul pe hartă.', 'Touch a chart to see the point on the map.')}</div>
  ${sec('Viteză (km/h)', line(pts.map((p) => [t(p), p[3]]), { color: '#7aa8ff', fx: (x) => new Date(x).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' }) }))}
  ${sec('Putere (kW)', line(pts.map((p) => [t(p), p[4]]), { color: '#d9ba80', fx: (x) => new Date(x).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' }) }))}
  ${sec('Baterie (%)', line(pts.map((p) => [t(p), p[5]]), { color: '#6fd6b8', fx: (x) => new Date(x).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' }) }))}
  ${sec('Altitudine (m)', line(pts.map((p) => [t(p), p[6]]), { color: '#b69bff', fx: (x) => new Date(x).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' }) }))}`;
  setTimeout(() => {
    const el = $('#dmap'); if (!el || !window.L || pts.length < 2) return;
    if (map) { map.remove(); map = null; }
    map = window.L.map(el, { zoomControl: false }).setView([pts[0][1], pts[0][2]], 13);
    window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(map);
    const col = (v) => v < 30 ? '#7aa8ff' : v < 70 ? '#6fd6b8' : v < 110 ? '#d9ba80' : '#ef7a7a';
    for (let i = 1; i < pts.length; i++) window.L.polyline([[pts[i - 1][1], pts[i - 1][2]], [pts[i][1], pts[i][2]]], { color: col(pts[i][3] || 0), weight: 5, opacity: .95, lineCap: 'round' }).addTo(map);
    const dot = (p, c) => window.L.circleMarker([p[1], p[2]], { radius: 7, color: '#0b0d10', weight: 3, fillColor: c, fillOpacity: 1 }).addTo(map);
    dot(pts[0], '#6fd6b8'); dot(pts[pts.length - 1], '#ef7a7a');
    map.fitBounds(pts.map((p) => [p[1], p[2]]), { padding: [24, 24] });
    driveHover(pts, map);
  }, 0);
  return html;
}

async function pageCharge(id) {
  const rows = await api('/api/charges?car=' + car + '&limit=200');
  const c = rows.find((r) => r.id == id) || rows[0];
  const pts = (await api('/api/charge/' + id)).points, t = (p) => +T(p[0]);
  const fx = (x) => new Date(x).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' });
  return `<a class="back" href="#/charges">‹ Încărcări</a>
  <div class="top row"><div><h1 style="font-size:21px">${esc(c?.name)}</h1><small>${c ? T(c.start_date).toLocaleDateString(LOC(), { weekday: 'long', day: 'numeric', month: 'long' }) + ' · ' + tm(c.start_date) + '–' + tm(c.end_date) : ''}</small></div><div class="sp"></div><span class="badge ${c?.dc ? 'dc' : 'ac'}">${c?.dc ? 'DC' : 'AC'}</span></div>
  <h2>Rezumat</h2><div class="grid g3">${stat('Adăugat', nf(c?.charge_energy_added, 1), 'kWh')}${stat('Durată', hm(c?.duration_min))}${stat('Putere max', nf(c?.power_max), 'kW')}${stat('Baterie', nf(c?.start_soc) + '→' + nf(c?.end_soc), '%')}${stat('Consumat din rețea', nf(c?.charge_energy_used, 1), 'kWh')}${stat('Cost', c?.cost ? nf(c.cost, 2) : '—', (S.currency ?? '€'))}</div>
  <div id="chsolar"></div>
  ${sec('Putere de încărcare (kW)', line(pts.map((p) => [t(p), p[1]]), { color: '#d9ba80', fx }))}
  ${sec('Nivel baterie (%)', line(pts.map((p) => [t(p), p[2]]), { color: '#6fd6b8', fx, min: 0, max: 100 }))}
  ${sec('Energie adăugată (kWh)', line(pts.map((p) => [t(p), p[5]]), { color: '#7aa8ff', fx, dec: 1 }))}`;
}

let days = 30;
async function statsBody(embed) {
  const [o, b] = await Promise.all([api('/api/overview?car=' + car + '&days=' + days), api('/api/battery?car=' + car)]);
  const d = o.drives, ch = o.charges;
  const wh = d.km > 0 ? d.kwh * 1000 / d.km : null;
  const SM = { online: ['Online', '#6fd6b8'], asleep: ['Doarme', '#7aa8ff'], offline: ['Offline', '#7f8994'] };
  const tot = b.states.reduce((s, x) => s + x.hours, 0) || 1;
  const stateBar = b.states.length ? `<div style="display:flex;height:16px;border-radius:99px;overflow:hidden;margin-top:6px">${b.states.map((x) => `<div title="${x.s}" style="width:${x.hours / tot * 100}%;background:${(SM[x.s] || ['', '#555'])[1]}"></div>`).join('')}</div>
    <div class="legend">${b.states.map((x) => `<span><i style="background:${(SM[x.s] || ['', '#555'])[1]}"></i>${(SM[x.s] || [x.s])[0]} ${nf(x.hours / tot * 100)}%</span>`).join('')}</div>` : '<div class="mut" style="font-size:13px;padding:10px 0">Prea puține date</div>';
  const lab = (k) => new Date(k + 'T00:00:00').toLocaleDateString(LOC(), { day: 'numeric', month: 'short' });
  return `${embed ? '' : '<div class="top"><h1>Statistici</h1></div>'}
  <div class="seg" style="margin-top:12px">${[7, 30, 90, 365].map((n) => `<button data-d="${n}" class="${n === days ? 'on' : ''}">${n === 365 ? tr('1 an') : n + tr(' zile')}</button>`).join('')}</div>
  <h2>Conducere</h2><div class="grid">${stat('Distanță', nf(d.km), 'km')}${stat('Curse', nf(d.n))}${stat('Timp la volan', hm(d.minutes))}${stat('Consum mediu', nf(wh), 'Wh/km')}${stat('Energie folosită', nf(d.kwh), 'kWh')}${stat('Viteză maximă', nf(d.vmax), 'km/h')}</div>
  ${sec('Kilometri pe zi', bars(o.by_day.map((x) => ({ l: lab(x.day), v: x.km })), { color: '#7aa8ff' }))}
  <h2>Încărcare</h2><div class="grid">${stat('Încărcări', nf(ch.n))}${stat('Energie adăugată', nf(ch.kwh), 'kWh')}${ch.cost_real != null ? stat(X('Cost TeslaMate', 'TeslaMate cost'), nf(ch.cost, 2), (S.currency ?? '€')) + stat(X('Cost real estimat', 'Estimated real cost'), nf(ch.cost_real, 2), (S.currency ?? '€')) + stat(X('Cost real / 100 km', 'Real cost / 100 km'), d.km > 0 ? nf(ch.cost_real / d.km * 100, 2) : '—', (S.currency ?? '€')) + stat(X('Economie (soare/baterie)', 'Saved (solar/battery)'), nf(Math.max(0, ch.cost - ch.cost_real), 2), (S.currency ?? '€')) : stat('Cost total', nf(ch.cost, 2), (S.currency ?? '€')) + stat('Cost / 100 km', d.km > 0 && ch.cost ? nf(ch.cost / d.km * 100, 2) : '—', (S.currency ?? '€'))}</div>
  ${sec('kWh încărcați pe zi', bars(o.charge_by_day.map((x) => ({ l: lab(x.day), v: x.kwh })), { color: '#d9ba80' }))}
  <h2>Stare mașină (ultimele 30 de zile)</h2><div class="card">${stateBar}</div>`;
}


/* ---------- comenzi (Tesla Fleet API prin backend) ---------- */
const getPin = (force) => { let p = localStorage.getItem('pin'); if (!p || force) { p = prompt(tr('PIN aplicație:')) || ''; if (p) localStorage.setItem('pin', p); } return p; };
const IC = {
  lock: 'M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm-6 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zm3.1-9H8.9V6c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2z',
  unlock: 'M12 17c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm6-9h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6h1.9c0-1.71 1.39-3.1 3.1-3.1 1.71 0 3.1 1.39 3.1 3.1v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zm0 12H6V10h12v10z',
  climate: 'M15 13V5c0-1.66-1.34-3-3-3S9 3.34 9 5v8c-1.21.91-2 2.37-2 4 0 2.76 2.24 5 5 5s5-2.24 5-5c0-1.63-.79-3.09-2-4zm-4-8c0-.55.45-1 1-1s1 .45 1 1h-1v1h1v2h-1v1h1v2h-2V5z',
  bolt: 'M11 21h-1l1-7H7.5c-.58 0-.57-.32-.38-.66.19-.34.05-.08.07-.12C8.48 10.94 10.42 7.54 13 3h1l-1 7h3.5c.49 0 .56.33.47.51l-.07.15C12.96 17.55 11 21 11 21z',
  plug: 'M16 9v4.66l-3.5 3.51V19h-1v-1.83L8 13.65V9h8m0-6h-2v4h-4V3H8v4h-.01C6.9 6.99 6 7.89 6 8.98v5.52L9.5 18v3h5v-3l3.5-3.51V9c0-1.1-.9-2-2-2V3z',
  eye: 'M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z',
  car: 'M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z',
  window: 'M3 3v18h18V3H3zm8 16H5v-6h6v6zm0-8H5V5h6v6zm8 8h-6v-6h6v6zm0-8h-6V5h6v6z',
  light: 'M9 21c0 .55.45 1 1 1h4c.55 0 1-.45 1-1v-1H9v1zm3-19C8.14 2 5 5.14 5 9c0 2.38 1.19 4.47 3 5.74V17c0 .55.45 1 1 1h6c.55 0 1-.45 1-1v-2.26c1.81-1.27 3-3.36 3-5.74 0-3.86-3.14-7-7-7z',
  gate: 'M12 3 2 8v13h20V8L12 3zm8 16H4V9.1l8-4 8 4V19zM6 11h12v2H6zm0 4h12v2H6z',
  horn: 'M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z',
};
const ico = (k) => `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${IC[k]}"/></svg>`;
async function sendCmd(name, label, arg, tile) {
  if (S.public_demo) return;
  const pin = getPin(); if (!pin) return;
  label = tr(label);
  const msg = (t, cls) => { const m = $('#cmdmsg'); if (m) { m.textContent = t; m.className = 'toast ' + (cls || ''); } };
  msg(label + '…', 'busy'); if (tile) tile.classList.add('busy');
  try {
    const r = await fetch('/api/cmd/' + name, { method: 'POST', headers: { 'X-Pin': pin, 'Content-Type': 'application/json' }, body: JSON.stringify({ car, arg }) });
    const j = await r.json();
    if (r.status === 403) { localStorage.removeItem('pin'); msg(tr('PIN greșit.'), 'bad'); return; }
    msg(j.ok ? '✓ ' + label + (j.via === 'ble' ? ' · BLE' : '') : '✗ ' + label + (j.reason ? ' — ' + j.reason : ''), j.ok ? 'ok' : 'bad');
  } catch (e) { msg('✗ ' + label + ' — ' + e.message, 'bad'); }
  finally { if (tile) tile.classList.remove('busy'); }
}
async function renderCmds() {
  const box = $('#cmds'); if (!box) return;
  if (S.demo && !S.public_demo) { setHtml(box, '<div class="note">Comenzile apar după ce mașina e conectată în TeslaMate și contul Tesla e autorizat.</div>'); return; }
  let f; if (S.public_demo) f = { ready: true }; else { try { f = await api('/api/fleet/status'); } catch (e) { return; } }
  const L = (cur() || {}).live || {};
  if (!(f.ready || f.ble)) {
    setHtml(box, `<div class="card"><p class="note" style="margin:0">${X('Comenzile nu sunt configurate încă. Completează Tesla Fleet API (și PIN-ul) în Setări; apoi urmează pașii de aici.', 'Commands are not configured yet. Fill in the Tesla Fleet API (and PIN) in Settings, then follow the steps here.')}</p><div class="links"><a href="#/settings">⚙ ${tr('Setări')}</a></div></div>`);
    if (!f.configured || !f.pin) return;
    const step = (ok, t) => `<div class="row" style="padding:5px 0"><span style="width:22px">${ok ? '✓' : '○'}</span><span class="${ok ? '' : 'mut'}">${t}</span></div>`;
    setHtml(box, `<div class="card">${step(f.configured, 'Aplicație Tesla (client id/secret) și domeniu configurate')}${step(f.key, 'Cheie publică generată')}${step(f.pin, 'PIN setat')}${step(f.registered, 'Domeniu înregistrat la Tesla')}${step(f.authorized, 'Cont Tesla autorizat')}
      <div class="links" style="flex-wrap:wrap">
        ${f.configured && f.pin && !f.registered ? '<a href="#" id="fl-reg">Înregistrează domeniul la Tesla</a>' : ''}
        ${f.configured && f.registered && !f.authorized ? '<a href="/api/fleet/login">Conectează contul Tesla</a>' : ''}
        ${f.configured && f.authorized ? `<a href="https://tesla.com/_ak/${esc(f.domain)}" target="_blank" rel="noopener">Instalează cheia virtuală în mașină</a>` : ''}
      </div><p class="note" id="fl-msg"></p></div>`);
const rg = $('#fl-reg');
  if (rg) rg.onclick = async (e) => {
    e.preventDefault();
    const pin = getPin(); if (!pin) return;
    const m = $('#fl-msg'); if (m) m.textContent = tr('Se înregistrează…');
    try {
      const r = await fetch('/api/fleet/register', { method: 'POST', headers: { 'X-Pin': pin, 'Content-Type': 'application/json' }, body: '{}' });
      const j = await r.json();
      if (r.status === 403) { localStorage.removeItem('pin'); if (m) m.textContent = tr('PIN greșit.'); return; }
      if (m) m.textContent = j.ok ? tr('Domeniu înregistrat.') : ('✗ ' + (j.step || '') + ' ' + (j.code || '') + ' ' + JSON.stringify(j.detail || '').slice(0, 240));
      if (j.ok) setTimeout(renderCmds, 800);
    } catch (x) { if (m) m.textContent = '✗ ' + x.message; }
  };
    return;
  }
  let caps = {}; try { caps = await api('/api/caps?car=' + car); } catch (e) { /* ignore */ }
  const charging = L.state === 'charging' || L.charging_state === 'Charging';
  const tile = (o) => `<button class="act ${o.on ? 'on' : ''} ${o.alert ? 'alert' : ''}" ${S.public_demo ? 'disabled' : ''} data-cmd="${o.cmd}" data-label="${o.label}" data-arg="${o.arg || ''}" data-ask="${o.ask || ''}">
    <small class="sts">${o.status}</small>${ico(o.icon)}<b>${o.label}</b></button>`;
  const kw = L.charger_power ? ' · ' + nf(L.charger_power, 1) + ' kW' : '';
  const tiles = [
    L.locked ? tile({ cmd: 'unlock', icon: 'lock', label: 'Deblochează', status: 'Blocată', on: true, ask: 'Deblochezi mașina?' })
             : tile({ cmd: 'lock', icon: 'unlock', label: 'Blochează', status: 'Deblocată', alert: true }),
    L.is_climate_on ? tile({ cmd: 'climate_off', icon: 'climate', label: 'Oprește clima', status: 'Pornită', on: true })
                    : tile({ cmd: 'climate_on', icon: 'climate', label: 'Pornește clima', status: 'Oprită' }),
    L.plugged_in ? (charging ? tile({ cmd: 'charge_stop', icon: 'bolt', label: 'Oprește încărcarea', status: tr('Se încarcă') + kw, on: true })
                             : tile({ cmd: 'charge_start', icon: 'bolt', label: 'Începe încărcarea', status: 'Conectată' }))
                 : tile({ cmd: 'port_open', icon: 'plug', label: 'Deschide portul', status: L.charge_port_door_open ? 'Deschis' : 'Închis', alert: !!L.charge_port_door_open }),
    L.sentry_mode ? tile({ cmd: 'sentry_off', icon: 'eye', label: 'Oprește Sentry', status: 'Activ', on: true })
                  : tile({ cmd: 'sentry_on', icon: 'eye', label: 'Pornește Sentry', status: 'Oprit' }),
    tile({ cmd: 'frunk', icon: 'car', label: 'Frunk', status: L.frunk_open ? 'Deschis' : 'Închis', alert: !!L.frunk_open, ask: 'Deschizi frunk-ul?' }),
    tile({ cmd: 'trunk', icon: 'car', label: 'Portbagaj', status: L.trunk_open ? 'Deschis' : 'Închis', alert: !!L.trunk_open, ask: 'Deschizi portbagajul?' }),
    L.windows_open ? tile({ cmd: 'close_windows', icon: 'window', label: 'Închide geamuri', status: 'Deschise', alert: true })
                   : tile({ cmd: 'vent', icon: 'window', label: 'Aerisește', status: 'Închise', ask: 'Aerisești geamurile?' }),
    caps.homelink === false ? '' : tile({ cmd: 'homelink', icon: 'gate', label: 'Poartă', status: 'HomeLink', ask: 'Deschizi poarta (HomeLink)?' }),
    tile({ cmd: 'flash', icon: 'light', label: 'Faruri', status: '—' }),
    tile({ cmd: 'honk', icon: 'horn', label: 'Claxon', status: '—', ask: 'Claxonezi?' }),
  ].join('');
  setHtml(box, `<div class="acts">${tiles}</div>
    <div class="lim-title"><span>Limită încărcare</span><b>${L.charge_limit_soc != null ? nf(L.charge_limit_soc) + '%' : '—'}</b></div>
    <div class="seg" style="margin-top:6px">${[70, 80, 90, 100].map((n) => `<button ${S.public_demo ? 'disabled' : ''} data-cmd="charge_limit" data-label="${tr('Limită')} ${n}%" data-arg="${n}" class="${L.charge_limit_soc === n ? 'on' : ''}">${n}%</button>`).join('')}</div>
    <div class="toast" id="cmdmsg">Comenzile pot trezi mașina (durează câteva secunde).</div>`);
  box.querySelectorAll('[data-cmd]').forEach((el) => el.onclick = () => {
    if (el.dataset.ask && !confirm(tr(el.dataset.ask))) return;
    sendCmd(el.dataset.cmd, el.dataset.label, el.dataset.arg ? +el.dataset.arg : undefined, el);
  });
}

/* ---------- router ---------- */
const ICON = {
  car: 'M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z',
  drives: 'M19 15.18V7c0-2.21-1.79-4-4-4s-4 1.79-4 4v10c0 1.1-.9 2-2 2s-2-.9-2-2V8.82C8.16 8.4 9 7.3 9 6c0-1.66-1.34-3-3-3S3 4.34 3 6c0 1.3.84 2.4 2 2.82V17c0 2.21 1.79 4 4 4s4-1.79 4-4V7c0-1.1.9-2 2-2s2 .9 2 2v8.18c-1.16.41-2 1.51-2 2.82 0 1.66 1.34 3 3 3s3-1.34 3-3c0-1.3-.84-2.4-2-2.82z',
  charges: 'M11 21h-1l1-7H7.5c-.58 0-.57-.32-.38-.66.19-.34.05-.08.07-.12C8.48 10.94 10.42 7.54 13 3h1l-1 7h3.5c.49 0 .56.33.47.51l-.07.15C12.96 17.55 11 21 11 21z',
  climate: IC.climate,
  settings: 'M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58a.49.49 0 00.12-.61l-1.92-3.32a.488.488 0 00-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54a.484.484 0 00-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58a.49.49 0 00-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z',
  stats: 'M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z',
};
const TABS = [['car', 'Mașină'], ['climate', 'Clima'], ['drives', 'Curse'], ['charges', 'Încărcări'], ['stats', 'Statistici'], ['settings', 'Setări']];
function renderNav(active) { drawNav(active); }
let renderSeq = 0;
async function render() {
  const h = location.hash.replace(/^#\/?/, '') || 'car';
  const [p, arg] = h.split('/');
  route = p;
  if (typeof RP !== 'undefined' && RP && p !== 'trip') stopReplay();
  if (p !== 'profiler' && typeof pfClose === 'function') pfClose();
  renderNav(['drive', 'trip'].includes(p) ? 'drives' : p === 'charge' ? 'charges' : p === 'sleep' ? 'parked' : p === 'stats' ? 'activity' : p === 'climate' ? 'car' : p);
  const seq = ++renderSeq;
  let html = '';
  try {
    if (p === 'car') html = pageCar();
    else if (p === 'drives') html = await pageList('drives');
    else if (p === 'charges') html = await pageList('charges');
    else if (p === 'drive') html = await pageDrive(arg);
    else if (p === 'charge') html = await pageCharge(arg);
    else if (p === 'stats') { actMode = 'stats'; html = await pageActivity(); }
    else if (p === 'activity') html = await pageActivity();
    else if (p === 'parked' || p === 'sleep') html = await pageSleep();
    else if (p === 'battery') html = await pageBattery();
    else if (p === 'notifications') html = pageNotif();
    else if (p === 'profiler') html = await pageProfiler();
    else if (p === 'auto') html = await pageAuto();
    else if (p === 'settings') html = await pageSettings();
    else if (p === 'climate') html = pageClimate();
    else if (p === 'trip') html = '';
    else html = pageCar();
  } catch (e) { html = `<div class="empty">${tr('Eroare la încărcare: ')}${esc(e.message)}</div>`; }
  if (seq !== renderSeq) return;
  if (map && p !== 'car' && p !== 'drive') { map.remove(); map = null; }
  const y = scrollY;
  setHtml(view, html);
  document.documentElement.lang = LANG;
  if (p === 'car') afterCar();
  if (p === 'climate') afterClimate();
  if (p === 'charges') afterCharges();
  if (p === 'trip') startReplay(arg);
  if (p === 'sleep' || p === 'parked') afterSleep();
  if (p === 'activity' || p === 'stats') afterActivity();
  if (p === 'battery') afterHealth();
  if (p === 'notifications') afterNotif();
  if (p === 'profiler') afterProfiler();
  if (p === 'auto') afterAuto();
  if (p === 'settings') afterSettings();
  if (p === 'charge') afterChargeSolar(arg);
  if (p === 'car') scrollTo(0, y); else if (seq === renderSeq && !window.__keep) scrollTo(0, 0);
}
addEventListener('hashchange', render);

/* ---------- live ---------- */
let t = null;
function live() {
  const es = new EventSource('/api/stream');
  es.onmessage = (e) => {
    const m = JSON.parse(e.data), c = S.cars.find((x) => x.id === m.car);
    if (!c || S.demo) return;
    c.live = c.live || {}; c.live[m.k] = m.v; c.live_age = 0;
    if (route === 'car') { clearTimeout(t); t = setTimeout(() => { const y = scrollY; setHtml(view, pageCar()); drawMap($('#map'), c.live); afterCar(); scrollTo(0, y); }, 400); }
  };
}
async function boot() {
  try { S = await api('/api/state'); car = S.cars[0]?.id || 1; } catch (e) { /* ignore */ }
  document.title = (S.cars[0]?.name || 'Tesla') + (S.demo ? ' · demo' : '');
  render();
  live();
  setInterval(async () => { try { const n = await api('/api/state'); if (!n.demo && !S.demo) return; S = n; if (route === 'car') render(); } catch (e) { /* ignore */ } }, 60000);
}
document.getElementById('burger')?.addEventListener('click', () => document.body.classList.toggle('nav-open'));
document.getElementById('backdrop')?.addEventListener('click', () => document.body.classList.remove('nav-open'));
boot();

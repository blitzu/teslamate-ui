/* Întreținere, anvelope și software (#/service) */
NAVI.service = 'M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z';
EXTRA_MENU.push(['service', 'Întreținere', 'Maintenance', 'service']);
let svTab = 'maint';
const SV_PRESETS = [
  ['Rotire anvelope', 'Tyre rotation', 10000, null], ['Filtru aer cabină', 'Cabin air filter', null, 24], ['Test lichid de frână', 'Brake fluid test', null, 48],
  ['Curățare/gresare etriere', 'Clean & lubricate calipers', 20000, 12], ['Schimb anvelope sezonier', 'Seasonal tyre change', null, 6],
  ['ITP', 'Periodic inspection (ITP)', null, 24], ['Asigurare RCA', 'RCA insurance', null, 12], ['Rovinietă', 'Road toll (rovinietă)', null, 12], ['CASCO', 'CASCO insurance', null, 12],
];
const svDay = (s) => s ? new Date(s + 'T12:00:00').toLocaleDateString(LOC(), { day: 'numeric', month: 'short', year: 'numeric' }) : '—';
const svFld = (id, label, val = '', type = 'text', extra = '') => `<label>${label}<input id="${id}" type="${type}" value="${esc(val)}" ${extra}></label>`;
const SV_COL = { overdue: '#ef7a7a', soon: '#ffb15c', ok: '#6fd6b8', unknown: '#7f8994' };

PAGES.service = {
  nav: 'service',
  async render() {
    const tabs = `<div class="seg">${[['maint', X('Întreținere', 'Maintenance')], ['tires', X('Anvelope', 'Tyres')], ['soft', 'Software']].map(([k, l]) => `<button data-svt="${k}" class="${svTab === k ? 'on' : ''}">${l}</button>`).join('')}</div>`;
    let body = '';
    try { body = svTab === 'maint' ? await svMaint() : svTab === 'tires' ? await svTires() : await svSoft(); } catch (e) { body = `<div class="empty">${X('Nu pot încărca datele.', 'Cannot load the data.')} ${esc(e.message)}</div>`; }
    return `<div class="top"><h1>${X('Întreținere', 'Maintenance')}</h1></div>${tabs}${body}`;
  },
  after() {
    document.querySelectorAll('[data-svt]').forEach((b) => b.onclick = () => { svTab = b.dataset.svt; render(); });
    const post = async (path, body, msg) => { const [ok, j] = await pinPost(path, body); if (ok) { render(); } else { const m = $('#svmsg'); if (m) { m.style.display = ''; m.textContent = '✗ ' + (j.reason || X('Eroare', 'Error')); m.className = 'toast bad'; } } return ok; };
    const v = (id) => (document.getElementById(id) || {}).value;
    // --- întreținere
    document.querySelectorAll('[data-pre]').forEach((b) => b.onclick = (e) => { e.preventDefault(); const p = SV_PRESETS[+b.dataset.pre]; $('#mi_name').value = X(p[0], p[1]); $('#mi_km').value = p[2] || ''; $('#mi_mo').value = p[3] || ''; });
    const add = $('#mi_add'); if (add) add.onclick = (e) => { e.preventDefault(); post('/api/service/item', { name: v('mi_name'), interval_km: v('mi_km'), interval_months: v('mi_mo'), last_date: v('mi_date') || new Date().toISOString().slice(0, 10), last_km: v('mi_lkm') }); };
    document.querySelectorAll('[data-del-item]').forEach((b) => b.onclick = (e) => { e.preventDefault(); if (confirm(X('Ștergi elementul?', 'Delete the item?'))) post('/api/service/item', { delete: true, id: b.dataset.delItem }); });
    document.querySelectorAll('[data-done]').forEach((b) => b.onclick = (e) => { e.preventDefault(); const f = document.getElementById('dn' + b.dataset.done); if (f) f.style.display = f.style.display === 'none' ? '' : 'none'; });
    document.querySelectorAll('[data-done-save]').forEach((b) => b.onclick = (e) => { e.preventDefault(); const i = b.dataset.doneSave; post('/api/service/done', { id: i, date: v('dd' + i), odometer: v('do' + i), cost: v('dc' + i), notes: v('dn_' + i) }); });
    const la = $('#sl_add'); if (la) la.onclick = (e) => { e.preventDefault(); post('/api/service/log', { description: v('sl_desc'), date: v('sl_date'), odometer: v('sl_odo'), cost: v('sl_cost'), category: v('sl_cat') }); };
    document.querySelectorAll('[data-del-log]').forEach((b) => b.onclick = (e) => { e.preventDefault(); if (confirm(X('Ștergi intrarea?', 'Delete the entry?'))) post('/api/service/log', { delete: true, id: b.dataset.delLog }); });
    // --- anvelope
    const ts = $('#ts_add'); if (ts) ts.onclick = (e) => { e.preventDefault(); post('/api/tires/set', { action: 'add', name: v('ts_name'), kind: v('ts_kind'), brand: v('ts_brand'), size: v('ts_size') }); };
    document.querySelectorAll('[data-tset]').forEach((b) => b.onclick = (e) => { e.preventDefault(); const [act, id] = b.dataset.tset.split(':'); if (act === 'delete' && !confirm(X('Ștergi setul și măsurătorile lui?', 'Delete the set and its measurements?'))) return; post('/api/tires/set', { action: act, id }); });
    document.querySelectorAll('[data-tcheck]').forEach((b) => b.onclick = (e) => { e.preventDefault(); const i = b.dataset.tcheck; post('/api/tires/check', { set_id: i, d_fl: v('tc_fl' + i), d_fr: v('tc_fr' + i), d_rl: v('tc_rl' + i), d_rr: v('tc_rr' + i) }); });
  },
};

async function svMaint() {
  const d = await api('/api/service'), cu = CU();
  const st = { overdue: X('Scadent', 'Overdue'), soon: X('În curând', 'Soon'), ok: 'OK', unknown: X('Setează ultima dată', 'Set the last date') };
  const items = d.items.map((i) => {
    const left = [i.km_left != null ? (i.km_left >= 0 ? nf(i.km_left) + ' km' : X('depășit cu ', 'over by ') + nf(-i.km_left) + ' km') : '', i.days_left != null ? (i.days_left >= 0 ? i.days_left + X(' zile', ' days') : X('depășit cu ', 'over by ') + (-i.days_left) + X(' zile', ' days')) : ''].filter(Boolean).join(' · ');
    return `<div class="card"><div class="row"><div><b>${esc(i.name)}</b><small class="mut" style="display:block">${i.interval_km ? nf(i.interval_km) + ' km ' : ''}${i.interval_km && i.interval_months ? X('sau ', 'or ') : ''}${i.interval_months ? i.interval_months + X(' luni', ' months') : ''} · ${X('ultima dată', 'last done')}: ${svDay(i.last_date)}${i.last_km != null ? ' · ' + nf(i.last_km) + ' km' : ''}</small></div><div class="sp"></div><span class="chip" style="color:${SV_COL[i.status]}"><i style="background:${SV_COL[i.status]}"></i>${st[i.status]}</span></div>
      <div class="bar" style="margin:10px 0 6px"><div class="fill" style="width:${Math.min(100, Math.round(i.progress * 100))}%;background:${SV_COL[i.status]}"></div></div>
      <small class="mut">${left || '—'}</small>
      <div class="links"><a href="#" data-done="${i.id}">${X('Făcut', 'Done')}</a><a href="#" data-del-item="${i.id}">${X('Șterge', 'Delete')}</a></div>
      <div class="addf" id="dn${i.id}" style="display:none">${svFld('dd' + i.id, X('Data', 'Date'), new Date().toISOString().slice(0, 10), 'date')}${svFld('do' + i.id, X('Odometru (km)', 'Odometer (km)'), d.odometer ? Math.round(d.odometer) : '', 'number')}${svFld('dc' + i.id, X('Cost', 'Cost') + ' (' + esc(cu) + ')', '', 'number', 'step="0.01"')}${svFld('dn_' + i.id, X('Notițe', 'Notes'))}<div class="links" style="grid-column:1/-1"><a href="#" data-done-save="${i.id}">${X('Salvează', 'Save')}</a></div></div></div>`;
  }).join('');
  const log = d.log.length ? `<div class="card"><table class="bktab"><tr><th>${X('Data', 'Date')}</th><th>km</th><th>${X('Ce s-a făcut', 'What was done')}</th><th>${X('Cost', 'Cost')}</th><th></th></tr>${d.log.map((l) => `<tr><td>${svDay(l.date)}</td><td>${l.odometer != null ? nf(l.odometer) : '—'}</td><td>${esc(l.description)}${l.category && l.category !== l.description ? `<small class="mut" style="display:block">${esc(l.category)}</small>` : ''}</td><td>${l.cost != null ? nf(l.cost, 2) + ' ' + esc(cu) : '—'}</td><td><a href="#" data-del-log="${l.id}" aria-label="delete">✕</a></td></tr>`).join('')}</table></div>` : `<div class="empty">${X('Jurnalul e gol.', 'The log is empty.')}</div>`;
  const total = d.log.reduce((s, l) => s + (l.cost || 0), 0);
  return `<div class="grid" style="margin-top:12px">${stat(X('Odometru', 'Odometer'), d.odometer != null ? nf(d.odometer) : '—', 'km')}${stat(X('Cheltuit pe service (jurnal)', 'Spent on service (log)'), nf(total, 2), esc(cu))}</div>
    <h2>${X('Termene și remindere', 'Schedule & reminders')}</h2>${items || `<div class="empty">${X('Nu ai niciun element. Adaugă din presetări mai jos.', 'No items yet. Add from the presets below.')}</div>`}
    <div class="toast" aria-live="polite" id="svmsg" style="display:none"></div>
    <h2>${X('Adaugă un element', 'Add an item')}</h2><div class="card cfg">
      <div class="chips">${SV_PRESETS.map((p, i) => `<a href="#" class="chip" data-pre="${i}" style="text-decoration:none">${X(p[0], p[1])}</a>`).join('')}</div>
      <div class="addf">${svFld('mi_name', X('Nume', 'Name'))}${svFld('mi_km', X('La fiecare (km)', 'Every (km)'), '', 'number')}${svFld('mi_mo', X('La fiecare (luni)', 'Every (months)'), '', 'number')}${svFld('mi_date', X('Ultima dată', 'Last done'), '', 'date')}${svFld('mi_lkm', X('Odometru atunci (km)', 'Odometer then (km)'), d.odometer ? Math.round(d.odometer) : '', 'number')}</div>
      <div class="links"><a href="#" id="mi_add">${X('Adaugă', 'Add')}</a></div>
      <p class="note">${X('Intervalele de pornire vin din manualul de service Tesla Model 3 (rotire la 10.000 km, filtru de cabină la 2 ani, test lichid de frână la 4 ani, etriere anual) și din obiceiurile din România (ITP, RCA, rovinietă). Verifică-le și ajustează-le pentru mașina ta.', 'The starting intervals come from the Tesla Model 3 service manual (rotation every 10,000 km, cabin filter every 2 years, brake-fluid test every 4 years, calipers yearly) and common Romanian obligations (ITP, RCA, road toll). Check and adjust them for your car.')}</p></div>
    <h2>${X('Jurnal de service', 'Service log')}</h2>${log}
    <div class="card cfg"><div class="addf">${svFld('sl_desc', X('Ce s-a făcut', 'What was done'))}${svFld('sl_cat', X('Categorie', 'Category'))}${svFld('sl_date', X('Data', 'Date'), new Date().toISOString().slice(0, 10), 'date')}${svFld('sl_odo', 'km', d.odometer ? Math.round(d.odometer) : '', 'number')}${svFld('sl_cost', X('Cost', 'Cost') + ' (' + esc(cu) + ')', '', 'number', 'step="0.01"')}</div><div class="links"><a href="#" id="sl_add">${X('Adaugă în jurnal', 'Add to the log')}</a></div></div>`;
}

async function svTires() {
  const [d, p] = await Promise.all([api('/api/tires'), api('/api/tires/pressure?days=60').catch(() => null)]);
  const names = { fl: X('Față stânga', 'Front left'), fr: X('Față dreapta', 'Front right'), rl: X('Spate stânga', 'Rear left'), rr: X('Spate dreapta', 'Rear right') };
  const charts = p && p.series ? `<div class="grid">${['fl', 'fr', 'rl', 'rr'].map((w) => { const pts = (p.series[w] || []).map(([day, val]) => [+new Date(day + 'T12:00:00'), val]); const lk = (p.leaks || {})[w] || {};
    return `<div class="card chart"><small class="mut">${names[w]} (bar, ${X('la 20°C', 'at 20°C')})${lk.leaking ? ' <b style="color:#ef7a7a">⚠ ' + X('scurgere lentă', 'slow leak') + '</b>' : ''}</small>${line(pts, { color: lk.leaking ? '#ef7a7a' : '#7aa8ff', dec: 2, h: 90 })}</div>`; }).join('')}</div><p class="note">${X('Mediana zilnică a presiunii, doar din momentele în care mașina stă pe loc, adusă la 20°C (presiunea scade cu aprox. 0,07 bar la fiecare 10°C). O scădere constantă de peste 0,012 bar/zi e semnalată ca posibilă scurgere.', 'Daily median pressure, only from times when the car is stationary, normalised to 20°C (pressure drops about 0.07 bar per 10°C). A steady drop over 0.012 bar/day is flagged as a possible slow leak.')}</p>` : `<div class="empty">${X('Presiunile apar în TeslaMate doar cât mașina e trează.', 'Pressures show up in TeslaMate only while the car is awake.')}</div>`;
  const sets = d.sets.map((s) => `<div class="card"><div class="row"><div><b>${esc(s.name)}</b><small class="mut" style="display:block">${[s.kind, s.brand, s.size].filter(Boolean).map(esc).join(' · ')}</small></div><div class="sp"></div><span class="chip ${s.active ? 'on' : ''}"><i></i>${s.active ? X('Montat', 'Mounted') : X('În depozit', 'Stored')}</span></div>
      <div class="grid g3" style="margin-top:10px">${stat(X('Parcurși', 'Driven'), s.km != null ? nf(s.km) : '—', 'km')}${stat(X('Montat', 'Mounted'), svDay(s.mounted_date))}${stat(X('Demontat', 'Removed'), svDay(s.removed_date))}</div>
      ${s.checks.length ? `<table class="bktab"><tr><th>${X('Adâncime profil (mm)', 'Tread depth (mm)')}</th><th>FL</th><th>FR</th><th>RL</th><th>RR</th></tr>${s.checks.map((c) => `<tr><td>${svDay(c.date)}${c.odometer != null ? ' · ' + nf(c.odometer) + ' km' : ''}</td><td>${c.d_fl ?? '—'}</td><td>${c.d_fr ?? '—'}</td><td>${c.d_rl ?? '—'}</td><td>${c.d_rr ?? '—'}</td></tr>`).join('')}</table>` : ''}
      <div class="addf">${['fl', 'fr', 'rl', 'rr'].map((w) => svFld('tc_' + w + s.id, w.toUpperCase() + ' mm', '', 'number', 'step="0.1"')).join('')}</div>
      <div class="links"><a href="#" data-tcheck="${s.id}">${X('Salvează măsurătoarea', 'Save measurement')}</a>${s.active ? `<a href="#" data-tset="unmount:${s.id}">${X('Demontează', 'Unmount')}</a>` : `<a href="#" data-tset="mount:${s.id}">${X('Montează acum', 'Mount now')}</a>`}<a href="#" data-tset="delete:${s.id}">${X('Șterge', 'Delete')}</a></div></div>`).join('');
  return `<h2>${X('Presiune în timp', 'Pressure over time')}</h2>${charts}
    <h2>${X('Seturi de anvelope', 'Tyre sets')}</h2>${sets || `<div class="empty">${X('Adaugă seturile tale (vară / iarnă) ca să vezi câți km are fiecare.', 'Add your sets (summer / winter) to see the km of each.')}</div>`}
    <div class="toast" aria-live="polite" id="svmsg" style="display:none"></div>
    <div class="card cfg"><div class="addf">${svFld('ts_name', X('Nume (ex. Iarnă 2026)', 'Name (e.g. Winter 2026)'))}${svFld('ts_kind', X('Tip (vară/iarnă/all-season)', 'Type (summer/winter/all-season)'))}${svFld('ts_brand', X('Marcă', 'Brand'))}${svFld('ts_size', X('Dimensiune', 'Size'), '235/45R18')}</div><div class="links"><a href="#" id="ts_add">${X('Adaugă setul', 'Add the set')}</a></div>
    <p class="note">${X('Kilometrii unui set se calculează din odometrul mașinii între „Montează acum” și „Demontează” (montarea unui set îl demontează automat pe cel activ).', 'A set’s km are computed from the car odometer between “Mount now” and “Unmount” (mounting a set unmounts the active one).')}</p></div>`;
}

async function svSoft() {
  const d = await api('/api/software');
  const cmp = (b, a) => { if (!b || b.wh_km == null || !a || a.wh_km == null) return '—'; const df = a.wh_km - b.wh_km; return `${b.wh_km} → ${a.wh_km} Wh/km <b style="color:${df > 3 ? '#ffb15c' : df < -3 ? '#6fd6b8' : 'inherit'}">(${df > 0 ? '+' : ''}${df})</b>`; };
  const rows = d.updates.map((u) => `<tr><td><b>${esc(u.version)}</b></td><td>${esc(new Date(u.start + 'Z').toLocaleDateString(LOC(), { day: 'numeric', month: 'short', year: 'numeric' }))}</td><td>${u.minutes != null ? hm(u.minutes) : '—'}</td><td>${cmp(u.before, u.after)}<small class="mut" style="display:block">${u.before && u.before.temp != null ? u.before.temp + '°C' : ''}${u.after && u.after.temp != null ? ' → ' + u.after.temp + '°C' : ''}</small></td></tr>`).join('');
  return `<div class="grid" style="margin-top:12px">${stat(X('Versiune curentă', 'Current version'), esc(d.current || '—'))}${stat(X('Update disponibil', 'Update available'), d.update_available ? esc(d.update_available) : X('nu', 'no'))}</div>
    <h2>${X('Istoric versiuni', 'Version history')}</h2><div class="card">${rows ? `<table class="bktab"><tr><th>${X('Versiune', 'Version')}</th><th>${X('Instalată', 'Installed')}</th><th>${X('Durată', 'Duration')}</th><th>${X('Consum 30 zile înainte → după', 'Consumption 30 days before → after')}</th></tr>${rows}</table><p class="note">${X('Compararea nu ține cont de sezon: uită-te și la temperaturile medii de sub cifre. O diferență de câteva Wh/km poate veni doar din vreme.', 'The comparison ignores season: look at the average temperatures under the numbers. A few Wh/km difference can come from the weather alone.')}</p>` : `<div class="mut" style="font-size:13px">${X('Niciun update înregistrat încă.', 'No update recorded yet.')}</div>`}</div>
    ${d.notes && d.notes.text ? `<h2>${X('Note de versiune', 'Release notes')} ${esc(d.notes.version || '')}</h2><div class="card"><pre class="notes">${esc(d.notes.text)}</pre></div>` : ''}`;
}

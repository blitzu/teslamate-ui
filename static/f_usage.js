/* Statistici de consum (#/usage): Wh/km pe ultimele X zile sau ultimii X km, fata de perioada anterioara si de consumul nominal, pe temperatura, viteza si in timp. */
NAVI.usage = 'M20.38 8.57l-1.23 1.85a8 8 0 0 1-.22 7.58H5.07A8 8 0 0 1 15.58 6.85l1.85-1.23A10 10 0 0 0 3.35 19a2 2 0 0 0 1.72 1h13.85a2 2 0 0 0 1.74-1 10 10 0 0 0-.27-10.44zm-9.79 6.84a2 2 0 0 0 2.83 0l5.66-8.49-8.49 5.66a2 2 0 0 0 0 2.83z';
EXTRA_MENU.push(['usage', 'Statistici consum', 'Consumption stats', 'usage']);

const US_KEY = 'usage_sel';
const usGet = () => { try { const v = JSON.parse(localStorage.getItem(US_KEY) || '{}'); return { mode: v.mode === 'km' ? 'km' : 'days', n: +v.n > 0 ? +v.n : (v.mode === 'km' ? 500 : 30) }; } catch (e) { return { mode: 'days', n: 30 }; } };
const usSet = (v) => { try { localStorage.setItem(US_KEY, JSON.stringify(v)); } catch (e) { /* ignore */ } };
const US_PRESETS = { days: [7, 30, 90, 365], km: [100, 500, 1000, 5000] };
const US_COL = '#8fd3ff', US_BAD = '#ef7a7a', US_GOOD = '#6fd6b8';

function usBucketLabel(b, unit) {
  if (b.lo <= -90) return '< ' + b.hi + unit;
  if (b.hi >= 900) return '> ' + b.lo + unit;
  return b.lo + '–' + b.hi + unit;
}
function usTable(rows, unit, head) {
  const some = rows.filter((r) => r.n);
  if (!some.length) return '';
  return `<table class="bktab"><tr><th>${head}</th><th>${X('Curse', 'Drives')}</th><th>km</th><th>Wh/km</th></tr>${rows.filter((r) => r.n).map((r) => `<tr><td>${usBucketLabel(r, unit)}</td><td>${nf(r.n)}</td><td>${nf(r.km, 0)}</td><td><b>${r.wh_km == null ? '—' : nf(r.wh_km)}</b></td></tr>`).join('')}</table>`;
}
function usDriveItem(d) {
  const day = new Date(d.when + 'Z').toLocaleDateString(LOC(), { day: 'numeric', month: 'short' });
  return `<a class="item" href="#/drive/${d.id}"><div class="t"><span>${esc(d.start)}</span><span class="arr">→</span><span>${esc(d.end)}</span></div>
    <div class="m"><span>${esc(day)}</span><span>${nf(d.km, 1)} km</span><span><b>${nf(d.wh_km)}</b> Wh/km</span>${d.speed == null ? '' : `<span>${nf(d.speed)} km/h</span>`}${d.temp == null ? '' : `<span>${nf(d.temp)}°</span>`}</div></a>`;
}

PAGES.usage = {
  nav: 'drives',
  async render() {
    const sel = usGet(), cu = CU();
    const presets = US_PRESETS[sel.mode].map((v) => `<button data-usn="${v}" class="${sel.n === v ? 'on' : ''}">${v} ${sel.mode === 'km' ? 'km' : X('zile', 'days')}</button>`).join('');
    const bar = `<div class="seg lfseg" style="margin-top:12px"><button data-usm="days" class="${sel.mode === 'days' ? 'on' : ''}">${X('Ultimele zile', 'Last days')}</button><button data-usm="km" class="${sel.mode === 'km' ? 'on' : ''}">${X('Ultimii km', 'Last km')}</button></div>
      <div class="seg lfseg" style="margin-top:8px">${presets}</div>
      <div class="addf" style="margin-top:8px"><label>${sel.mode === 'km' ? X('Ultimii … km', 'Last … km') : X('Ultimele … zile', 'Last … days')}<input type="number" id="us_n" min="1" step="1" value="${sel.n}" inputmode="numeric"></label></div>`;
    const head = `<a class="back" href="#/drives">‹ ${X('Curse', 'Drives')}</a><div class="top"><h1>${X('Statistici consum', 'Consumption stats')}</h1><small>${X('Cât consumă mașina în mers (Wh/km), pe ultimele zile sau pe ultimii kilometri, față de perioada dinainte și de consumul nominal.', 'How much the car uses while driving (Wh/km), over the last days or the last kilometres, compared with the period before and with the rated consumption.')}</small></div>${bar}`;
    let d; try { d = await api('/api/usage?car=' + car + '&mode=' + sel.mode + '&n=' + sel.n); } catch (e) { return head + `<div class="empty">${X('Nu pot încărca statisticile.', 'Cannot load the stats.')}</div>`; }
    if (d.empty) return head + `<div class="empty">${X('Pagina cere o mașină reală în TeslaMate (nu merge în demo).', 'This page needs a real car in TeslaMate (not available in the demo).')}</div>`;
    if (d.empty_window || !d.used_drives) return head + `<div class="empty">${X('Nicio cursă cu date de consum în perioada aleasă.', 'No drive with consumption data in the chosen period.')}</div>`;
    const money = (v) => v == null ? '—' : nf(v, 2);
    const vs = d.vs_rated_pct, pv = d.prev || {};
    const verdict = (x, goodLow = true) => x == null ? '' : `<span style="color:${(x <= 0) === goodLow ? US_GOOD : US_BAD}">${x > 0 ? '+' : ''}${nf(x)}%</span>`;
    const stats = `<div class="grid">${stat(X('Consum', 'Consumption'), d.wh_km == null ? '—' : nf(d.wh_km), 'Wh/km')}${stat(X('Pe 100 km', 'Per 100 km'), d.kwh_100 == null ? '—' : nf(d.kwh_100, 1), 'kWh')}${stat(X('Distanță', 'Distance'), nf(d.km, 0), 'km')}${stat(X('Energie', 'Energy'), nf(d.kwh, 1), 'kWh')}${stat(X('Viteză medie', 'Avg speed'), d.avg_speed == null ? '—' : nf(d.avg_speed), 'km/h')}${stat(X('Curse', 'Drives'), nf(d.used_drives))}${d.cost == null ? '' : stat(X('Cost', 'Cost'), money(d.cost), cu)}${d.cost_100 == null ? '' : stat(X('Cost / 100 km', 'Cost / 100 km'), money(d.cost_100), cu)}${d.price_kwh == null ? '' : stat(X('Preț mediu', 'Avg price'), nf(d.price_kwh, 2), cu + '/kWh')}</div>`;
    const cmp = [];
    if (vs != null) cmp.push(`${X('Față de consumul nominal', 'Versus the rated consumption')} (${nf(d.rated_wh_km)} Wh/km): ${verdict(vs)}`);
    if (pv.delta_pct != null) cmp.push(`${d.mode === 'km' ? X('Față de cei', 'Versus the') + ' ' + nf(pv.km, 0) + ' km ' + X('dinainte', 'before') : X('Față de cele', 'Versus the') + ' ' + d.n + ' ' + X('zile dinainte', 'days before')} (${nf(pv.wh_km)} Wh/km): ${verdict(pv.delta_pct)}`);
    const range = `${new Date(d.from_ + 'Z').toLocaleDateString(LOC(), { day: 'numeric', month: 'short', year: 'numeric' })} – ${new Date(d.to + 'Z').toLocaleDateString(LOC(), { day: 'numeric', month: 'short', year: 'numeric' })}`;
    const tr = d.trend || [];
    const trendLabel = (t) => t.day.slice(8) + '.' + t.day.slice(5, 7);
    const tempItems = d.by_temp.filter((r) => r.n).map((r) => ({ l: usBucketLabel(r, '°'), v: [r.wh_km || 0] }));
    const speedItems = d.by_speed.filter((r) => r.n).map((r) => ({ l: usBucketLabel(r, ''), v: [r.wh_km || 0] }));
    return head + `<div class="card" style="margin-top:12px"><small class="mut">${esc(range)} · ${nf(d.span_days)} ${X('zile', 'days')}${d.mode === 'km' ? ' · ' + X('curse întregi, deci ', 'whole drives, so ') + nf(d.km, 0) + ' km' : ''}</small>
        <div style="margin-top:8px">${stats}</div>${cmp.length ? `<p class="note" style="margin:10px 0 0">${cmp.join('<br>')}</p>` : ''}</div>
      ${tr.length > 1 ? sec(X(d.span_days > 45 ? 'Consum pe săptămână (Wh/km)' : 'Consum pe zi (Wh/km)', d.span_days > 45 ? 'Consumption per week (Wh/km)' : 'Consumption per day (Wh/km)'), chBars(tr.map((t) => ({ l: trendLabel(t), v: [t.wh_km || 0] })), [US_COL], { dec: 0, unit: 'Wh/km' })) : ''}
      ${tempItems.length > 1 ? sec(X('După temperatura de afară (Wh/km)', 'By outside temperature (Wh/km)'), chBars(tempItems, [US_COL], { dec: 0, unit: 'Wh/km' })) + usTable(d.by_temp, '°', X('Temperatură', 'Temperature')) : ''}
      ${speedItems.length > 1 ? sec(X('După viteza medie a cursei (Wh/km)', 'By average trip speed (Wh/km)'), chBars(speedItems, [US_COL], { dec: 0, unit: 'Wh/km' })) + usTable(d.by_speed, ' km/h', X('Viteză medie', 'Avg speed')) : ''}
      ${d.best.length ? `<h2>${X('Cele mai economice curse (peste 10 km)', 'Most efficient drives (over 10 km)')}</h2><div class="list">${d.best.map(usDriveItem).join('')}</div>` : ''}
      ${d.worst.length ? `<h2>${X('Cele mai mari consumuri (peste 10 km)', 'Highest consumption (over 10 km)')}</h2><div class="list">${d.worst.map(usDriveItem).join('')}</div>` : ''}
      <p class="note">${X('Energia unei curse e diferența de autonomie ideală dintre început și sfârșit × eficiența mașinii, la fel ca în lista de curse. Cursele sub 1 km sau fără măsurătoare validă nu intră în Wh/km' + (d.skipped ? ` (${d.skipped} omise)` : '') + '. Consumul include încălzirea/clima din timpul mersului, dar nu consumul în staționare (acela e pe pagina „Consum în staționare”). La „ultimii km” se iau curse întregi, începând de la cea mai recentă, până se strâng kilometrii aleși.', 'A drive’s energy is the ideal-range difference between start and end × the car’s efficiency, the same as in the drives list. Drives under 1 km or without a valid measurement are left out of Wh/km' + (d.skipped ? ` (${d.skipped} omitted)` : '') + '. The figure includes heating/climate while driving but not the parked drain (that is on the “Idle energy use” page). For “last km” whole drives are taken, starting from the most recent, until the chosen distance is reached.')}</p>`;
  },
  after() {
    const go = (v) => { usSet(Object.assign(usGet(), v)); render(); };
    document.querySelectorAll('[data-usm]').forEach((b) => b.onclick = () => go({ mode: b.dataset.usm, n: b.dataset.usm === 'km' ? 500 : 30 }));
    document.querySelectorAll('[data-usn]').forEach((b) => b.onclick = () => go({ n: +b.dataset.usn }));
    const inp = document.getElementById('us_n');
    const apply = () => { const v = Math.round(+inp.value); if (v > 0 && v !== usGet().n) go({ n: v }); };
    if (inp) { inp.onchange = apply; inp.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); apply(); } }; }
  },
};

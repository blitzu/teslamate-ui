/* Arhiva Tessie (#/tessie): ce a adus importul din Tessie si TeslaMate nu poate pastra: staționari (consum cat stai parcat), capacitatea bateriei in timp, alerte firmware,
   plus un card cu datele Tessie pe pagina fiecarei curse (autopilot, putere ESTIMATA). Apare in meniu doar dupa un import. */
NAVI.archive = 'M4 5h16v4H4zM5 9h14v10H5zM10 13h4';
EXTRA_MENU.push(['tessie', 'Arhivă Tessie', 'Tessie archive', 'archive']);

const tsDate = (s, o) => fdate(new Date(s * 1000), o || { day: 'numeric', month: 'short' });
const tsMin = (s) => { s = Math.round(s / 60); return s >= 1440 ? Math.floor(s / 1440) + 'd ' + Math.floor(s % 1440 / 60) + 'h' : s >= 60 ? Math.floor(s / 60) + 'h ' + String(s % 60).padStart(2, '0') + 'm' : s + 'm'; };
const tsAlert = (n) => String(n || '').replace(/^[A-Za-z]+_[a-z]?\d+_/, '').replace(/([a-z])([A-Z])/g, '$1 $2');

PAGES.tessie = {
  nav: 'tessie',
  async render() {
    const head = `<div class="top"><h1>${X('Arhivă Tessie', 'Tessie archive')}</h1><small>${X('Ce a adus importul și TeslaMate nu poate păstra', 'What the import brought and TeslaMate cannot keep')}</small></div>`;
    let sm, idl, hl, al;
    try { [sm, idl, hl, al] = await Promise.all(['summary', 'idles?limit=40', 'health', 'alerts'].map((p) => api('/api/tessie/' + p + (p.includes('?') ? '&' : '?') + 'car=' + car))); } catch (e) { return head + `<div class="empty">${X('Nu pot încărca arhiva.', 'Cannot load the archive.')}</div>`; }
    if (!sm.any) return head + `<div class="empty">${X('Nu există date din Tessie pentru această mașină. Importă-le din Setări → Import din Tessie.', 'There is no Tessie data for this car. Import it from Settings → Import from Tessie.')}</div>`;
    const t = idl.total || {}, pts = (hl.points || []).filter((p) => p.capacity);
    const cap = pts.length > 1 ? `${nf(pts[0].capacity, 1)} → ${nf(pts[pts.length - 1].capacity, 1)} kWh (${nf((pts[pts.length - 1].capacity / pts[0].capacity - 1) * 100, 1)}%)` : '—';
    const days = t.secs ? t.secs / 86400 : 0;
    const idleRows = (idl.rows || []).map((r) => `<tr><td>${tsDate(r.started_at, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</td><td>${esc(r.saved || (r.place || '').split(',').slice(0, 2).join(','))}</td><td>${tsMin(r.ended_at - r.started_at)}</td><td>${r.soc0 ?? '—'}→${r.soc1 ?? '—'}%</td><td>${nf(r.energy_used, 2)}</td></tr>`).join('');
    const alRows = (al.kinds || []).slice(0, 25).map((k) => `<details class="tsal"><summary><b>${esc(tsAlert(k.name))}</b> <span class="mut">× ${nf(k.n)} · ${X('ultima', 'last')} ${tsDate(k.last, { day: 'numeric', month: 'short', year: 'numeric' })}</span></summary><p class="note" style="margin:6px 0 10px">${esc(k.description || '')}${k.impact ? ' — ' + esc(k.impact) : ''}<br><code style="font-size:11px">${esc(k.name)}</code></p></details>`).join('');
    return head + `<h2>${X('Rezumat', 'Summary')}</h2><div class="grid g3">${stat(X('Staționări', 'Parked periods'), nf(sm.idles.n))}${stat(X('Starea bateriei', 'Battery measurements'), nf(sm.health.n))}${stat(X('Alerte', 'Alerts'), nf(sm.alerts.n))}</div>
      <h2>${X('Capacitatea bateriei', 'Battery capacity')}</h2>
      <div class="card chart">${pts.length > 1 ? line(pts.map((p) => [p.ts * 1000, p.capacity]), { color: '#6fd6b8', fx: (x) => fdate(new Date(x), { month: 'short', year: '2-digit' }) }) : `<div class="mut" style="padding:16px 0;font-size:13px">${X('Prea puține măsurători', 'Not enough measurements')}</div>`}<p class="note" style="margin:8px 0 0">${cap} · ${X('măsurată de Tessie la încărcări și zilnic (kWh utilizabili)', 'measured by Tessie at charges and daily (usable kWh)')}</p></div>
      <h2>${X('Consum cât stai parcat', 'Drain while parked')}</h2>
      <div class="card"><div class="grid g3">${stat(X('Energie', 'Energy'), nf(t.kwh, 1), 'kWh')}${stat(X('Pe zi parcat', 'Per parked day'), days ? nf(t.kwh / days, 2) : '—', 'kWh')}${stat(X('Cu sentry', 'With sentry'), nf(t.sentry_kwh, 1), 'kWh')}</div>
      <p class="note" style="margin:8px 0 0">${X('Include clima și sentry; „cu sentry” = staționările în care sentry a fost activ mai mult de jumătate din timp.', 'Includes climate and sentry; “with sentry” = periods where sentry was on for more than half of the time.')}</p>
      <table class="bktab" style="margin-top:10px"><tr><th>${X('Început', 'Start')}</th><th>${X('Loc', 'Place')}</th><th>${X('Durată', 'Length')}</th><th>${X('Baterie', 'Battery')}</th><th>kWh</th></tr>${idleRows}</table>
      <p class="note">${X('Ultimele 40 din', 'Last 40 of')} ${nf(t.n)}.</p></div>
      <h2>${X('Alerte de la mașină', 'Alerts from the car')}</h2><div class="card">${alRows || `<div class="mut">${X('Nicio alertă.', 'No alerts.')}</div>`}<p class="note" style="margin:8px 0 0">${X('Mesaje pe care mașina le-a generat (de ex. asistență pentru bandă, frânare automată): foarte multe sunt normale. Se arată cele mai frecvente 25 din', 'Messages the car generated (e.g. lane assist, automatic braking): many are normal. The 25 most frequent of')} ${nf(sm.alerts.kinds)}.</p></div>`;
  },
};

/* card pe pagina unei curse: datele Tessie care nu au loc in TeslaMate (se adauga dupa ce pagina e desenata) */
async function tessieDriveCard(id) {
  if (!S.tessie) return;
  let r; try { r = await api('/api/tessie/drive?car=' + car + '&id=' + id); } catch (e) { return; }
  const box = $('#tdrv'); if (!box || !r.found || !location.hash.startsWith('#/drive/' + id)) return;
  const has = r.est_power_max != null;
  box.innerHTML = `<h2>${X('Date din Tessie', 'Tessie data')}</h2><div class="card"><div class="grid g3">${stat(X('Putere max*', 'Peak power*'), has ? nf(r.est_power_max, 0) : '—', 'kW')}${stat(X('Recuperare max*', 'Peak regen*'), has ? nf(-r.est_power_min, 0) : '—', 'kW')}${stat(X('Viteză medie', 'Average speed'), nf(r.avg_speed, 0), 'km/h')}</div>
    <div class="grid g3" style="margin-top:8px">${stat(X('Energie (Tessie)', 'Energy (Tessie)'), nf(r.energy_used, 2), 'kWh')}${stat(X('Autopilot', 'Autopilot'), nf(r.autopilot_km, 1), 'km')}${stat(X('Autonomie folosită', 'Range used'), nf(r.rated_range_used, 1), 'km')}</div>
    <p class="note" style="margin:8px 0 0">* ${X('Estimat din energia rămasă în baterie, pe ferestre de ~60 s: Tessie nu oferă puterea reală, deci vârfurile scurte nu se văd.', 'Estimated from the energy left in the battery over ~60 s windows: Tessie does not provide real power, so short peaks are not visible.')}</p></div>`;
}

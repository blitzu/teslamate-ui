/* Consum în afara condusului (#/idleuse): cât costă climatizarea / preîncălzirea, încălzirea bateriei, Sentry, mașina trează și somnul, pe perioada aleasă. */
NAVI.idleuse = 'M11 21h-1l1-7H7.5c-.58 0-.57-.32-.38-.66.19-.34.05-.08.07-.12C8.48 10.94 10.42 7.54 13 3h1l-1 7h3.5c.49 0 .56.33.47.51l-.07.15C12.96 17.55 11 21 11 21z';
EXTRA_MENU.push(['idleuse', 'Consum în staționare', 'Idle energy use', 'idleuse']);

const IU_COL = { climate: '#ffb15c', heater: '#ef7a7a', sentry: '#b69bff', awake: '#8fd3ff', sleep: '#5b7bb5' };
const IU_ORDER = ['climate', 'heater', 'sentry', 'awake', 'sleep'];
const iuName = (k) => ({
  climate: X('Climatizare / preîncălzire habitaclu', 'Climate / cabin preheat'),
  heater: X('Încălzirea bateriei', 'Battery heating'),
  sentry: X('Mod Sentry', 'Sentry mode'),
  awake: X('Mașina trează (altceva)', 'Car awake (other)'),
  sleep: X('Somn (consum de fond)', 'Asleep (background drain)'),
})[k];
const iuHelp = (k) => ({
  climate: X('Cât timp clima a fost pornită cu mașina oprită (preîncălzire din aplicație sau programată, dezghețare, ventilație). Intră și scaunele / volanul încălzite.', 'While the climate was on with the car parked (preheat from the app or scheduled, defrost, ventilation). Heated seats and wheel are included.'),
  heater: X('Bateria s-a încălzit singură (frig) cât mașina stătea. Încălzirea din timpul încărcării sau al condusului nu e aici.', 'The battery heated itself (cold) while parked. Heating during charging or driving is not here.'),
  sentry: X('Cât timp Sentry a fost pornit și mașina nu făcea altceva. Sentry ține mașina trează, deci include și consumul de „treaz”.', 'While Sentry was on and the car did nothing else. Sentry keeps the car awake, so this includes the “awake” draw.'),
  awake: X('Mașina era trează fără Sentry sau climă: aplicații, comenzi, actualizări, tu în mașină sau o oră după ce ai oprit.', 'The car was awake without Sentry or climate: apps, commands, updates, you in the car or the hour after you stop.'),
  sleep: X('Intervale lungi în care mașina a dormit (TeslaMate nu mai are poziții). Ăsta e consumul de bază.', 'Long stretches with the car asleep (TeslaMate has no positions). This is the baseline drain.'),
})[k];

/* bare suprapuse pe zile: items [{l, v: {cat: kWh}}] */
function iuBars(days) {
  const W = 340, H = 150, pb = 20, n = days.length;
  const tot = (d) => IU_ORDER.reduce((s, k) => s + Math.max(0, d[k] || 0), 0), mx = Math.max(...days.map(tot), 0.1), bw = (W - 8) / n;
  const bars = days.map((d, i) => {
    let y = H - pb;
    const segs = ['sleep', 'awake', 'sentry', 'heater', 'climate'].map((k) => { const v = Math.max(0, d[k] || 0), h = v / mx * (H - pb - 16); y -= h; return h > 0.4 ? `<rect x="${4 + i * bw + bw * .1}" y="${y.toFixed(1)}" width="${Math.max(1.5, bw * .8).toFixed(1)}" height="${h.toFixed(1)}" fill="${IU_COL[k]}"/>` : ''; }).join('');
    return `<g><title>${esc(d.day)} · ${nf(tot(d), 2)} kWh</title>${segs}</g>`;
  }).join('');
  const every = Math.ceil(n / 8);
  const labs = days.map((d, i) => (i % every === 0 ? `<text x="${4 + i * bw + bw / 2}" y="${H - 5}" text-anchor="middle">${esc(d.day.slice(8) + '.' + d.day.slice(5, 7))}</text>` : '')).join('');
  return `<svg viewBox="0 0 ${W} ${H}">${bars}${labs}<text x="${W - 4}" y="10" text-anchor="end">max ${nf(mx, 1)} kWh</text></svg>
    <div class="legend">${IU_ORDER.map((k) => `<span><i style="background:${IU_COL[k]}"></i>${iuName(k)}</span>`).join('')}</div>`;
}

PAGES.idleuse = {
  nav: 'parked',
  async render() {
    if (!LFS.idleuse) lfSet('idleuse', { p: 30 });
    LF_TAGS = [];                                                  // filtrul pe tag nu are sens aici
    const bar = lfBar('idleuse', { noPage: true });
    const head = `<a class="back" href="#/parked">‹ ${X('Staționări', 'Parked')}</a><div class="top"><h1>${X('Consum în staționare', 'Idle energy use')}</h1><small>${X('Cât costă climatizarea, Sentry și restul funcțiilor care consumă energie cât mașina nu conduce și nu se încarcă.', 'What climate, Sentry and the other functions cost while the car is not driving or charging.')}</small></div>${bar}`;
    let d; try { d = await api('/api/idleuse?car=' + car + lfQuery('idleuse')); } catch (e) { return head + `<div class="empty">${X('Nu pot încărca datele.', 'Cannot load the data.')}</div>`; }
    if (d.empty) return head + `<div class="empty">${X('Pagina cere o mașină reală în TeslaMate (nu merge în demo).', 'This page needs a real car in TeslaMate (not available in the demo).')}</div>`;
    if (!d.kwh && !d.hours) return head + `<div class="empty">${X('Nicio staționare cu date în perioada aleasă.', 'No parked time with data in the chosen period.')}</div>`;
    const cu = CU(), money = (v) => v == null ? '' : nf(v, 2) + ' ' + cu;
    const stats = `<div class="grid">${stat(X('Consum în staționare', 'Parked energy'), nf(d.kwh, 1), 'kWh')}${stat(X('Cost estimat', 'Estimated cost'), d.cost == null ? '—' : nf(d.cost, 2), d.cost == null ? '' : cu)}${stat(X('Din tot consumul', 'Of all energy used'), d.idle_share == null ? '—' : nf(d.idle_share), '%')}${stat(X('Condus', 'Driving'), d.driving_kwh == null ? '—' : nf(d.driving_kwh, 0), 'kWh')}${stat(X('Perioadă acoperită', 'Period covered'), nf(d.days, 1), X('zile', 'days'))}${stat(X('Somn, de bază', 'Asleep, baseline'), d.sleep_kw == null ? '—' : nf(d.sleep_kw * 24, 2), 'kWh/' + X('zi', 'day'))}</div>`;
    const rows = IU_ORDER.map((k) => d.cats.find((c) => c.key === k)).filter((c) => c && (c.kwh > 0 || c.hours > 0)).map((c) => {
      const extra = c.extra_kwh == null ? '' : `<br>${X('Peste ce ar fi consumat dormind: ', 'Beyond what it would use asleep: ')}<b>${nf(c.extra_kwh, 2)} kWh</b>${c.extra_cost == null ? '' : ' ≈ ' + money(c.extra_cost)}`;
      const proj = c.per30_kwh == null ? '' : `<br>${X('La ritmul acesta, 30 de zile: ', 'At this rate, 30 days: ')}<b>${nf(c.per30_kwh, 1)} kWh</b>${c.per30_cost == null ? '' : ' ≈ ' + money(c.per30_cost)}`;
      return `<div class="card" style="margin-top:10px;border-left:4px solid ${IU_COL[c.key]}"><div style="display:flex;justify-content:space-between;gap:10px;align-items:baseline"><b>${iuName(c.key)}</b><span><b style="font-size:20px">${nf(c.kwh, 2)}</b> kWh${c.cost == null ? '' : ' · ' + money(c.cost)}</span></div>
        <div style="height:6px;border-radius:99px;background:#232a31;margin:8px 0"><div style="height:6px;border-radius:99px;width:${Math.max(1, c.pct || 0)}%;background:${IU_COL[c.key]}"></div></div>
        <small class="mut">${c.pct == null ? '' : c.pct + '% · '}${nf(c.hours, 1)} h${c.kw == null ? '' : ' · ' + nf(c.kw, 2) + ' kW ' + X('în medie', 'on average')}${extra}${proj}</small>
        <p class="note" style="margin:6px 0 0">${iuHelp(c.key)}</p></div>`;
    }).join('');
    const days = d.by_day.slice(-90);
    return head + `<h2>${X('Rezumat', 'Summary')}</h2>${stats}<h2>${X('Pe funcții', 'By function')}</h2>${rows}
      ${days.length > 1 ? sec(X('Pe zile (kWh)', 'Per day (kWh)'), iuBars(days)) : ''}
      <p class="note">${X('Mașina nu raportează un consum pentru fiecare funcție, așa că energia e scoasă din ce vede TeslaMate: între două puncte în care mașina nu conducea și nu se încărca, scad autonomia ideală (× eficiența mașinii) și atribui diferența după clima / încălzirea bateriei din acel moment, după intervalele Sentry din jurnal și după cât a stat trează sau adormită. Sunt estimări: autonomia se schimbă în pași mici, deci un interval de 5 minute are zgomot, dar sumele pe zile și săptămâni sunt stabile. Costul folosește prețul mediu al energiei din baterie în perioadă (același calcul ca la costul curselor). Preîncălzirea bateriei dinaintea unui Supercharger se face pe drum, deci intră la condus. La fel, clima pornită în timpul unei încărcări adevărate sau al unei curse nu se poate separa și rămâne la încărcare / condus; o preîncălzire la încărcător, fără energie adăugată în baterie, se numără aici, cu energia venită din rețea.', 'The car does not report a figure per function, so the energy is derived from what TeslaMate sees: between two points where the car was neither driving nor charging I subtract the ideal range (× the car’s efficiency) and assign the difference by the climate / battery heating state at that moment, the Sentry intervals in the log and whether the car was awake or asleep. These are estimates: the range changes in small steps, so a 5-minute interval is noisy, but daily and weekly sums are stable. The cost uses the average price of the energy in the battery over the period (same calculation as the drive cost). Battery preconditioning before a Supercharger happens on the road, so it counts as driving. Likewise, climate running during a real charge or a drive cannot be separated and stays with the charge / drive; a preheat at the charger that adds no energy to the battery is counted here, together with the energy that came from the grid.')}${d.skipped_n ? ' ' + X(`${d.skipped_n} interval(e) cu salt imposibil (${nf(d.skipped_kwh, 1)} kWh) au fost lăsate deoparte.`, `${d.skipped_n} interval(s) with an impossible jump (${nf(d.skipped_kwh, 1)} kWh) were left out.`) : ''}</p>`;
  },
  after() { lfBind('idleuse', () => render()); },
};

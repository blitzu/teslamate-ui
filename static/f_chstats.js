/* Statistici de incarcare (#/chstats): kWh AC vs DC, viteza pe procente de baterie, nivelul la inceput/sfarsit, kWh pe luna */
NAVI.chstats = 'M5 9.2h3V19H5V9.2zM10.6 5h2.8v14h-2.8V5zm5.6 8H19v6h-2.8v-6z';
EXTRA_MENU.push(['chstats', 'Statistici încărcări', 'Charging stats', 'chstats']);

/* bare (eventual suprapuse), cu eticheta sub fiecare: items [{l, v: [a, b?]}] */
function chBars(items, colors, o = {}) {
  if (!items.length || !items.some((i) => i.v.some((x) => x > 0))) return `<div class="mut" style="padding:16px 0;font-size:13px">${X('Prea puține date', 'Not enough data')}</div>`;
  const W = 340, H = o.h || 130, pb = 20, mx = Math.max(...items.map((i) => i.v.reduce((s, x) => s + x, 0)), 1), bw = (W - 8) / items.length;
  const bars = items.map((it, i) => {
    let y = H - pb;
    return it.v.map((v, k) => { const h = (v / mx) * (H - pb - 16); y -= h; return h > 0 ? `<rect x="${4 + i * bw + bw * .12}" y="${y}" width="${Math.max(2, bw * .76)}" height="${Math.max(h, 1.5)}" rx="2" fill="${colors[k]}"/>` : ''; }).join('');
  }).join('');
  const every = items.length > 14 ? Math.ceil(items.length / 10) : 1;
  const labs = items.map((it, i) => (i % every === 0 ? `<text x="${4 + i * bw + bw / 2}" y="${H - 5}" text-anchor="middle">${esc(it.l)}</text>` : '')).join('');
  return `<svg viewBox="0 0 ${W} ${H}">${bars}${labs}<text x="${W - 4}" y="10" text-anchor="end">max ${nf(mx, o.dec || 0)}${o.unit ? ' ' + o.unit : ''}</text></svg>`;
}

PAGES.chstats = {
  nav: 'charges',
  async render() {
    await lfLoadTags();
    const bar = lfBar('chstats', { noPage: true }), head = `<a class="back" href="#/charges">‹ ${X('Încărcări', 'Charges')}</a><div class="top"><h1>${X('Statistici încărcări', 'Charging stats')}</h1><small>${X('AC față de DC, viteza de încărcare pe procente de baterie și nivelul la care încarci. Din datele TeslaMate, pe perioada aleasă.', 'AC versus DC, charging speed by battery level and the level you charge at. From the TeslaMate data, for the chosen period.')}</small></div>${bar}`;
    let d; try { d = await api('/api/chstats?car=' + car + lfQuery('chstats')); } catch (e) { return head + `<div class="empty">${X('Nu pot încărca statisticile.', 'Cannot load the stats.')}</div>`; }
    if (d.empty) return head + `<div class="empty">${X('Statisticile cer o mașină reală în TeslaMate (nu merg în demo).', 'The stats need a real car in TeslaMate (not available in the demo).')}</div>`;
    const ac = d.kinds.ac, dc = d.kinds.dc, none = !ac.n && !dc.n;
    if (none) return head + `<div class="empty">${X('Nicio încărcare în perioada aleasă.', 'No charges in the chosen period.')}</div>`;
    const AC = '#6fd6b8', DC = '#ffb15c', lab = (b) => b.from_ + '–' + (b.from_ + 10);
    const col = (k, x, color) => `<div class="card" style="margin-top:10px"><b style="color:${color}">${k}</b><div class="grid g3" style="margin-top:8px">${stat(X('Sesiuni', 'Sessions'), nf(x.n))}${stat(X('Energie', 'Energy'), nf(x.kwh, 1), 'kWh')}${stat(X('Medie / sesiune', 'Avg / session'), x.avg_kwh == null ? '—' : nf(x.avg_kwh, 1), 'kWh')}${stat(X('Viteză medie', 'Avg speed'), x.avg_kw == null ? '—' : nf(x.avg_kw, 1), 'kW')}${stat(X('Vârf mediu', 'Avg peak'), x.avg_peak == null ? '—' : nf(x.avg_peak), 'kW')}${stat(X('Vârf maxim', 'Max peak'), x.power_max == null ? '—' : nf(x.power_max), 'kW')}${stat(X('Timp încărcat', 'Time charging'), nf(x.hours, 1), 'h')}${stat(X('Din rețea', 'From grid'), nf(x.used, 1), 'kWh')}${stat(X('Randament', 'Efficiency'), x.efficiency == null ? '—' : nf(x.efficiency), '%')}</div></div>`;
    const tot = ac.kwh + dc.kwh;
    const pw = d.power_by_soc, table = (rows) => rows.length ? `<table class="bktab"><tr><th>${X('Baterie', 'Battery')}</th><th>${X('Medie', 'Avg')} (kW)</th><th>${X('Maxim', 'Max')} (kW)</th><th>${X('Eșantioane', 'Samples')}</th></tr>${rows.map((r) => `<tr><td>${lab(r)}%</td><td><b>${nf(r.avg, 1)}</b></td><td>${nf(r.max, 1)}</td><td>${nf(r.n)}</td></tr>`).join('')}</table>` : '';
    const sh = (h) => h.ac.map((x, i) => ({ l: lab(x) + '', v: [x.n, h.dc[i].n] }));
    return head + `<h2>${X('Energie încărcată', 'Energy charged')}</h2><div class="card"><div class="grid">${stat('AC', nf(ac.kwh, 1), 'kWh')}${stat('DC', nf(dc.kwh, 1), 'kWh')}${stat(X('Total', 'Total'), nf(tot, 1), 'kWh')}${stat(X('Pondere DC', 'DC share'), d.dc_share == null ? '—' : nf(d.dc_share), '%')}</div>
      <div style="display:flex;height:14px;border-radius:99px;overflow:hidden;margin-top:12px;background:#232a31"><div style="width:${tot ? ac.kwh / tot * 100 : 0}%;background:${AC}"></div><div style="width:${tot ? dc.kwh / tot * 100 : 0}%;background:${DC}"></div></div>
      <div class="legend" style="margin-top:6px"><span><i style="background:${AC}"></i>AC</span><span><i style="background:${DC}"></i>DC</span></div></div>
      ${col('AC', ac, AC)}${col('DC', dc, DC)}
      ${sec(X('Viteza medie la DC după nivelul bateriei (kW)', 'Average DC speed by battery level (kW)'), chBars(pw.dc.map((r) => ({ l: lab(r) + '', v: [r.avg] })), [DC], { dec: 0, unit: 'kW' }))}
      ${table(pw.dc)}
      ${sec(X('Viteza medie la AC după nivelul bateriei (kW)', 'Average AC speed by battery level (kW)'), chBars(pw.ac.map((r) => ({ l: lab(r) + '', v: [r.avg] })), [AC], { dec: 1, unit: 'kW' }))}
      ${sec(X('Nivelul bateriei la începutul încărcării (număr de sesiuni)', 'Battery level when charging starts (sessions)'), chBars(sh(d.start_hist), [AC, DC]))}
      ${sec(X('Nivelul bateriei la sfârșitul încărcării (număr de sesiuni)', 'Battery level when charging ends (sessions)'), chBars(sh(d.end_hist), [AC, DC]))}
      ${sec(X('kWh pe lună, AC și DC', 'kWh per month, AC and DC'), chBars(d.months.map((m) => ({ l: m.month.slice(2), v: [m.ac, m.dc] })), [AC, DC], { dec: 0, unit: 'kWh' }))}
      <p class="note">${X('Viteza pe nivel e media eșantioanelor de putere din fiecare sesiune (nu ține cont de durata fiecărui eșantion). O sesiune e „DC” dacă TeslaMate a marcat-o ca încărcare rapidă.', 'Speed per level is the mean of the power samples of each session (not weighted by sample duration). A session is “DC” when TeslaMate flagged it as fast charging.')}</p>`;
  },
  after() { lfBind('chstats', () => render()); },
};


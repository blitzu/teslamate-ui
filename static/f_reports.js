/* Rapoarte periodice + "cat ar fi costat la PZU" (#/reports) */
NAVI.reports = 'M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zM9 17H7v-7h2v7zm4 0h-2V7h2v10zm4 0h-2v-4h2v4z';
EXTRA_MENU.push(['reports', 'Rapoarte', 'Reports', 'reports']);
let rpTab = 'reports';
PAGES.reports = {
  nav: 'reports',
  async render() {
    const head = `<div class="top"><h1>${X('Rapoarte', 'Reports')}</h1></div>
      <div class="chips">${[['reports', X('Rapoarte', 'Reports')], ['pzu', X('Cât ar fi costat la PZU', 'What PZU would have cost')]].map(([k, l]) => `<a href="#" class="chip ${rpTab === k ? 'on' : ''}" data-rptab="${k}">${l}</a>`).join('')}</div>`;
    return head + (rpTab === 'pzu' ? await rpPzu() : await rpList());
  },
  after() {
    document.querySelectorAll('[data-rptab]').forEach((a) => a.onclick = (e) => { e.preventDefault(); rpTab = a.dataset.rptab; render(); });
    const say = (t, cls) => { const m = document.getElementById('rp_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
    document.querySelectorAll('[data-rpgen]').forEach((a) => a.onclick = async (e) => {
      e.preventDefault(); say(X('Se generează…', 'Generating…'), 'busy');
      const [ok, j] = await pinPost('/api/reports/generate', { kind: a.dataset.rpgen, send: document.getElementById('rp_send') && document.getElementById('rp_send').checked });
      if (ok && j.ok) render(); else say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad');
    });
    const sv = document.getElementById('rp_save');
    if (sv) sv.onclick = async (e) => {
      e.preventDefault(); say(X('Se salvează…', 'Saving…'), 'busy');
      const [ok, j] = await pinPost('/api/reports/config', { weekly: document.getElementById('rp_weekly').checked, monthly: document.getElementById('rp_monthly').checked, hour: document.getElementById('rp_hour').value });
      say(ok && j.ok ? '✓ ' + X('Salvat', 'Saved') : '✗ ' + (j.reason || X('Eroare', 'Error')), ok && j.ok ? 'ok' : 'bad');
    };
    const pz = document.getElementById('pz_save');
    if (pz) pz.onclick = async (e) => {
      e.preventDefault(); say(X('Se salvează…', 'Saving…'), 'busy');
      const g = (id) => document.getElementById(id).value;
      const [ok, j] = await pinPost('/api/pzu/config', { addon: String(g('pz_addon')).replace(',', '.'), vat: String(g('pz_vat')).replace(',', '.'), from_h: g('pz_from'), to_h: g('pz_to') });
      if (ok && j.config) render(); else say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad');
    };
  },
};

async function rpList() {
  let d; try { d = await api('/api/reports'); } catch (e) { return `<div class="empty">${X('Nu pot încărca rapoartele.', 'Cannot load reports.')}</div>`; }
  const c = d.config;
  const items = d.reports.map((r) => `<div class="card"><b>${esc(r.title)}</b><pre class="notes" style="white-space:pre-wrap">${esc(r.text)}</pre><small class="mut">${esc(new Date(r.ts * 1000).toLocaleString(LOC()))}</small></div>`).join('');
  return `<h2>${X('Generează acum', 'Generate now')}</h2><div class="card cfg">
      ${sw('rp_send', false, X('Trimite și pe notificări/Telegram', 'Also send to notifications/Telegram'))}
      <div class="links"><a href="#" data-rpgen="week">${X('Săptămâna trecută', 'Last week')}</a><a href="#" data-rpgen="month">${X('Luna trecută', 'Last month')}</a><a href="#" data-rpgen="year">${X('Anul acesta', 'This year')}</a></div>
      <div class="toast" aria-live="polite" id="rp_msg" style="display:none"></div></div>
    <h2>${X('Programare', 'Schedule')}</h2><div class="card cfg">
      ${sw('rp_weekly', c.weekly, X('Raport săptămânal (luni)', 'Weekly report (Monday)'))}${sw('rp_monthly', c.monthly, X('Raport lunar (pe 1)', 'Monthly report (on the 1st)'))}
      <label class="cf">${X('După ora', 'After hour')}<input id="rp_hour" type="number" min="0" max="23" value="${esc(c.hour)}"></label>
      <div class="links"><a href="#" id="rp_save">${X('Salvează', 'Save')}</a></div></div>
    <h2>${X('Rapoarte anterioare', 'Past reports')}</h2>${items || `<div class="empty">${X('Niciun raport încă. Primul vine luni dimineață sau îl generezi mai sus.', 'No reports yet. The first arrives on Monday morning or generate one above.')}</div>`}`;
}

async function rpPzu() {
  let d; try { d = await api('/api/pzu?days=120'); } catch (e) { return `<div class="empty">${esc(e.message || X('Nu pot citi prețurile PZU acum.', 'Cannot read PZU prices now.'))}</div>`; }
  const c = d.config, cu = d.currency || '', n2 = (v) => v == null ? '—' : nf(v, 2);
  const sum = d.months.reduce((a, m) => ({ kwh: a.kwh + m.kwh, fixed: a.fixed + m.fixed, pzu: a.pzu + m.pzu, tot: a.tot + m.pzu_total, opt: a.opt + m.optimal }), { kwh: 0, fixed: 0, pzu: 0, tot: 0, opt: 0 });
  const rows = d.months.map((m) => `<tr><td>${esc(m.month)}</td><td>${nf(m.kwh, 0)}</td><td>${n2(m.fixed)}</td><td>${n2(m.pzu)}</td><td><b>${n2(m.pzu_total)}</b></td><td>${m.opt_n ? n2(m.optimal) : '—'}</td></tr>`).join('');
  const hrs = (v) => String(v).padStart(2, '0') + ':00';
  return `<p class="note">${X('Costul încărcărilor tale AC de acasă dacă ai plăti prețul de pe piața pentru ziua următoare (PZU, pe 15 minute), față de tariful tău fix și față de varianta „încarc doar în cele mai ieftine ore din noapte”. Prețul PZU e doar energia: o ofertă dinamică adaugă tarife de rețea, taxe și TVA — le poți aproxima mai jos. Nu e o recomandare de a schimba contractul.', 'The cost of your home AC charging if you paid the day-ahead market price (PZU, per 15 minutes), versus your fixed tariff and versus “charge only in the cheapest hours of the night”. PZU is energy only: a dynamic offer adds network fees, taxes and VAT — approximate them below. Not advice to change your contract.')}</p>
    ${d.note ? `<div class="empty">${esc(d.note)}</div>` : ''}
    ${d.months.length ? `<div class="grid">${stat(X('kWh analizați', 'kWh analysed'), nf(sum.kwh, 0))}${stat(X('Tarif fix', 'Fixed tariff'), n2(sum.fixed), cu)}${stat(X('PZU + adaos + TVA', 'PZU + add-on + VAT'), n2(sum.tot), cu)}${stat(X('Cele mai ieftine ore', 'Cheapest hours'), n2(sum.opt), cu)}</div>
      <table class="bktab"><tr><th>${X('Luna', 'Month')}</th><th>kWh</th><th>${X('Tarif fix', 'Fixed')}</th><th>PZU (${X('energie', 'energy')})</th><th>PZU + ${X('adaos + TVA', 'add-on + VAT')}</th><th>${X('Ore ieftine', 'Cheap hours')}</th></tr>${rows}</table>
      <p class="note">${X('Valori în', 'Values in')} ${esc(cu)}. ${X('Se numără doar încărcările cu prețuri pentru ≥90% din energie. Prețuri: energy-charts.info (Fraunhofer ISE), curs: BCE via frankfurter.dev.', 'Only charges with prices for ≥90% of the energy are counted. Prices: energy-charts.info (Fraunhofer ISE), FX: ECB via frankfurter.dev.')}</p>` : ''}
    <h2>${X('Ipoteze', 'Assumptions')}</h2><div class="card cfg">
      <label class="cf">${X('Adaos pe kWh (rețea, taxe, marjă furnizor)', 'Add-on per kWh (network, taxes, supplier margin)')}<input id="pz_addon" inputmode="decimal" value="${esc(c.addon)}"></label>
      <label class="cf">${X('TVA %', 'VAT %')}<input id="pz_vat" inputmode="decimal" value="${esc(c.vat)}"></label>
      <label class="cf">${X('Fereastra de noapte: de la ora', 'Night window: from hour')}<input id="pz_from" type="number" min="0" max="23" value="${esc(c.from_h)}"></label>
      <label class="cf">${X('până la ora', 'to hour')}<input id="pz_to" type="number" min="0" max="23" value="${esc(c.to_h)}"></label>
      <div class="links"><a href="#" id="pz_save">${X('Salvează', 'Save')}</a></div><div class="toast" aria-live="polite" id="rp_msg" style="display:none"></div></div>
    ${d.sessions.length ? `<h2>${X('Pe sesiune', 'Per session')}</h2><table class="bktab"><tr><th>${X('Data', 'Date')}</th><th>kWh</th><th>${X('Fix', 'Fixed')}</th><th>PZU</th><th>${X('Ieftin', 'Cheap')}</th><th>${X('Preț mediu PZU', 'Avg PZU price')}</th></tr>${d.sessions.slice(0, 40).map((s) => `<tr><td>${esc(s.start.slice(0, 10))}</td><td>${nf(s.kwh, 1)}</td><td>${n2(s.fixed)}</td><td>${n2(s.pzu_total)}</td><td>${n2(s.optimal)}</td><td>${s.avg_pzu == null ? '—' : nf(s.avg_pzu, 3)}</td></tr>`).join('')}</table>` : ''}`;
}

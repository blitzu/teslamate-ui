/* Alerte proactive + paznic de somn (#/alerts) */
NAVI.alerts = NAVI.bell || NAVI.gauge;
EXTRA_MENU.push(['alerts', 'Alerte', 'Alerts', 'alerts']);
PAGES.alerts = {
  nav: 'alerts',
  async render() {
    let cfg, log = [], sg = null;
    try { cfg = await api('/api/alerts/config'); } catch (e) { return `<div class="top"><h1>${X('Alerte', 'Alerts')}</h1></div><div class="empty">${X('Nu pot încărca alertele.', 'Cannot load alerts.')}</div>`; }
    try { log = await api('/api/alerts/log?days=30'); } catch (e) { /* ignore */ }
    try { sg = await api('/api/sleepguard?days=7'); } catch (e) { /* ignore */ }
    const c = cfg.config, sev = { critical: '#ef7a7a', high: '#ffb15c', normal: '#7aa8ff' };
    const row = (id, label, on, inner = '') => `<div class="alrow">${sw(id, on, label)}${inner ? `<div class="addf">${inner}</div>` : ''}</div>`;
    const num = (id, label, v, o = '') => `<label>${label}<input id="${id}" type="number" inputmode="decimal" value="${esc(v)}" ${o}></label>`;
    const R = { pnc: c.plugged_not_charging, np: c.not_plugged_night, tp: c.tpms_low, ch: c.cabin_hot, au: c.awake_unexplained };
    const reasonLbl = { sentry: 'Sentry', comanda: X('comenzi', 'commands'), utilizator: X('utilizator', 'user'), update: 'update', necunoscut: X('necunoscut', 'unknown') };
    const sgRows = sg && sg.days ? sg.days.slice().reverse().map((d) => `<tr><td>${esc(d.day)}</td><td>${hm(d.total)}</td><td>${d.unexplained ? '<b style="color:#ffb15c">' + hm(d.unexplained) + '</b>' : '—'}</td><td>${Object.entries(d.reasons).map(([k, v]) => `<span class="rs">${esc(reasonLbl[k] || k)} ${v}′</span>`).join(' ')}</td></tr>`).join('') : '';
    return `<div class="top"><h1>${X('Alerte', 'Alerts')}</h1><small>${X('Te anunț când ceva nu e în regulă. Se trimit prin notificările configurate (Home Assistant, push, Telegram).', 'You get told when something is off. They go through the configured notifications (Home Assistant, push, Telegram).')}</small></div>
    <h2>${X('Reguli', 'Rules')}</h2><div class="card cfg">
      ${sw('al_enabled', c.enabled, X('Alerte active', 'Alerts enabled'))}
      ${row('al_quiet_on', X('Ore de liniște (doar alertele critice trec)', 'Quiet hours (only critical alerts pass)'), c.quiet.on, `<label>${X('De la', 'From')}<input id="al_quiet_start" type="time" value="${esc(c.quiet.start)}"></label><label>${X('Până la', 'To')}<input id="al_quiet_end" type="time" value="${esc(c.quiet.end)}"></label>`)}
      ${row('al_cs_on', X('Încărcarea s-a oprit neașteptat', 'Charging stopped unexpectedly'), c.charge_stopped.on)}
      ${row('al_pnc_on', X('Conectată dar nu încarcă (cu motivul)', 'Plugged in but not charging (with the reason)'), R.pnc.on, num('al_pnc_min', X('După (min)', 'After (min)'), R.pnc.minutes))}
      ${row('al_np_on', X('Nu e conectată seara, acasă', 'Not plugged in at night, at home'), R.np.on, num('al_np_hour', X('Ora', 'Hour'), R.np.hour) + num('al_np_soc', X('Sub baterie %', 'Below battery %'), R.np.min_soc) + `<label>${X('Locul „acasă” (regex)', 'Home place (regex)')}<input id="al_np_home" value="${esc(R.np.home)}"></label>`)}
      ${row('al_tp_on', X('Presiune scăzută la anvelope', 'Low tyre pressure'), R.tp.on, num('al_tp_bar', X('Sub (bar)', 'Below (bar)'), R.tp.bar, 'step="0.05"'))}
      ${row('al_tl_on', X('Scurgere lentă la anvelope (zilnic)', 'Slow tyre leak (daily)'), c.tire_leak.on)}
      ${row('al_rw_on', X('Plouă (sau urmează) cu geam deschis', 'Rain (or coming) with a window open'), c.rain_window.on)}
      ${row('al_ch_on', X('Cabină fierbinte în Dog/Camp Mode (critică)', 'Hot cabin in Dog/Camp Mode (critical)'), R.ch.on, num('al_ch_temp', X('Peste (°C)', 'Above (°C)'), R.ch.temp))}
      ${row('al_au_on', X('Trează fără motiv (din paznicul de somn)', 'Awake for no reason (from the sleep guard)'), R.au.on, num('al_au_min', X('Peste (min/zi)', 'Over (min/day)'), R.au.minutes))}
      <div class="links"><a href="#" id="al_save">${X('Salvează', 'Save')}</a><a href="#" id="al_test">${X('Trimite o alertă de test', 'Send a test alert')}</a></div>
      <div class="toast" aria-live="polite" id="al_msg" style="display:none"></div>
      <p class="note">${X('Ploaia se verifică la Open-Meteo (coordonate rotunjite la 0,1°) doar când un geam e deschis.', 'Rain is checked at Open-Meteo (coordinates rounded to 0.1°) only while a window is open.')}</p></div>
    <h2>${X('Alerte recente (30 de zile)', 'Recent alerts (30 days)')}</h2>
    <div class="card">${log.length ? log.map((a) => `<div class="alitem"><i style="background:${sev[a.severity] || sev.normal}"></i><div><b>${esc(a.title)}</b><small>${esc(a.msg)}</small><small class="mut">${esc(new Date(a.ts * 1000).toLocaleString(LOC()))}</small></div></div>`).join('') : `<div class="mut" style="font-size:13px">${X('Nicio alertă în ultimele 30 de zile.', 'No alerts in the last 30 days.')}</div>`}</div>
    <h2>${X('Paznic de somn (7 zile)', 'Sleep guard (7 days)')}</h2>
    <div class="card">${sgRows ? `<table class="bktab"><tr><th>${X('Ziua', 'Day')}</th><th>${X('Treaz fără să conducă/încarce', 'Awake, not driving/charging')}</th><th>${X('Nelămurit', 'Unexplained')}</th><th>${X('Motive', 'Reasons')}</th></tr>${sgRows}</table>
      <p class="note">${X('„Nelămurit” = treaz fără Sentry, fără comenzi, fără utilizator și fără update. Pot fi mașina care nu adoarme din cauza unei aplicații, a unui cablu sau a unui dispozitiv BLE. Nu trezesc niciodată mașina ca să măsor.', '“Unexplained” = awake without Sentry, commands, a user or an update. It can be an app, a cable or a BLE device keeping the car awake. I never wake the car to measure.')}</p>` : `<div class="mut" style="font-size:13px">${X('Nu sunt date încă.', 'No data yet.')}</div>`}</div>`;
  },
  after() {
    const say = (t, cls) => { const m = $('#al_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
    const v = (id) => document.getElementById(id), ck = (id) => !!(v(id) && v(id).checked);
    const save = $('#al_save');
    if (save) save.onclick = async (e) => {
      e.preventDefault(); say(X('Se salvează…', 'Saving…'), 'busy');
      const body = { enabled: ck('al_enabled'), quiet: { on: ck('al_quiet_on'), start: v('al_quiet_start').value, end: v('al_quiet_end').value }, charge_stopped: { on: ck('al_cs_on') },
        plugged_not_charging: { on: ck('al_pnc_on'), minutes: v('al_pnc_min').value }, not_plugged_night: { on: ck('al_np_on'), hour: v('al_np_hour').value, min_soc: v('al_np_soc').value, home: v('al_np_home').value },
        tpms_low: { on: ck('al_tp_on'), bar: v('al_tp_bar').value }, rain_window: { on: ck('al_rw_on') }, cabin_hot: { on: ck('al_ch_on'), temp: v('al_ch_temp').value }, awake_unexplained: { on: ck('al_au_on'), minutes: v('al_au_min').value }, tire_leak: { on: ck('al_tl_on') } };
      const [ok, j] = await pinPost('/api/alerts/config', body);
      say(ok ? '✓ ' + X('Salvat', 'Saved') : '✗ ' + (j.reason || X('Eroare', 'Error')), ok ? 'ok' : 'bad');
    };
    const test = $('#al_test');
    if (test) test.onclick = async (e) => {
      e.preventDefault(); say(X('Se trimite…', 'Sending…'), 'busy');
      const [ok, j] = await pinPost('/api/alerts/test', {});
      say(ok ? '✓ ' + (j.sent ? X('Trimisă', 'Sent') : X('Înregistrată (ore de liniște active)', 'Logged (quiet hours active)')) : '✗ ' + (j.reason || X('Eroare', 'Error')), ok ? 'ok' : 'bad');
    };
  },
};

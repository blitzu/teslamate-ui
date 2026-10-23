/* Setari → Telegram (notificari pe un bot propriu) */
SETTINGS_EXT.push({
  cat: 'notif', order: 2,
  async render() {
    let st, cfg; try { st = await api('/api/telegram/status'); cfg = await api('/api/config'); } catch (e) { return ''; }
    const tg = cfg.telegram || {}, k = st.kinds;
    const L = { alert: X('Alerte', 'Alerts'), maint: X('Reamintiri service', 'Service reminders'), report: X('Rapoarte (săptămânal/lunar)', 'Reports (weekly/monthly)'), app_update: X('Versiune nouă a aplicației', 'New app version'),
      low_batt: X('Baterie scăzută', 'Low battery'), update: X('Update software mașină', 'Car software update'), charge_done: X('Încărcare terminată', 'Charge finished'), plugged: X('Cablu conectat', 'Plug-in'), door: X('Uși/portbagaj deschise', 'Doors/trunk open'), rule: X('Reguli automate', 'Automation rules'), handoff: X('Predare mașină', 'Car handoff'), test: X('Teste', 'Tests') };
    return `<h2>Telegram</h2><div class="card cfg">
      <p class="note" style="margin:0 0 8px">${X('Notificările pot ajunge și pe Telegram, printr-un bot al tău (creat cu @BotFather). Tokenul se păstrează doar pe server. Chat-ul e numărul tău (ex. 123456789) sau al unui grup (-100…).', 'Notifications can also go to Telegram through a bot of your own (created with @BotFather). The token stays on the server only. The chat is your number (e.g. 123456789) or a group (-100…).')}</p>
      <label class="cf">${X('Token bot', 'Bot token')}<input id="tg_token" type="password" autocomplete="off" placeholder="${tg.token_set ? X('••••••  (setat — lasă gol ca să-l păstrezi)', '••••••  (set — leave empty to keep)') : '123456789:AA…'}"></label>
      <label class="cf">${X('Chat ID', 'Chat ID')}<input id="tg_chat" autocomplete="off" value="${esc(tg.chat || '')}" placeholder="123456789"></label>
      <h3 class="sub">${X('Ce trimit pe Telegram', 'What goes to Telegram')}</h3>
      ${Object.keys(L).map((x) => sw('tgk_' + x, !!k[x], L[x])).join('')}
      <div class="links"><a href="#" id="tg_save">${X('Salvează', 'Save')}</a><a href="#" id="tg_test">${X('Trimite un mesaj de test', 'Send a test message')}</a></div>
      <div class="toast" aria-live="polite" id="tg_msg" style="display:none"></div></div>`;
  },
  after() {
    const say = (t, cls) => { const m = document.getElementById('tg_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
    const save = document.getElementById('tg_save'), test = document.getElementById('tg_test');
    if (save) save.onclick = async (e) => {
      e.preventDefault(); say(X('Se salvează…', 'Saving…'), 'busy');
      const body = { telegram_chat: document.getElementById('tg_chat').value.trim() };
      const tok = document.getElementById('tg_token').value.trim(); if (tok) body.telegram_token = tok;
      let [ok, j] = await pinPost('/api/config', body);
      if (ok && j.ok) {
        const kinds = {}; document.querySelectorAll('[id^="tgk_"]').forEach((c) => { kinds[c.id.slice(4)] = c.checked; });
        [ok, j] = await pinPost('/api/telegram/kinds', kinds);
      }
      say(ok && (j.ok !== false) ? '✓ ' + X('Salvat', 'Saved') : '✗ ' + (j.reason || j.error || X('Eroare', 'Error')), ok ? 'ok' : 'bad');
    };
    if (test) test.onclick = async (e) => {
      e.preventDefault(); say(X('Se trimite…', 'Sending…'), 'busy');
      const [ok, j] = await pinPost('/api/telegram/test', {});
      say(ok && j.ok ? '✓ ' + X('Trimis', 'Sent') : '✗ ' + (j.reason || X('Eroare', 'Error')), ok && j.ok ? 'ok' : 'bad');
    };
  },
});

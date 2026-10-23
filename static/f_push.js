/* Setari → Notificari push pe acest dispozitiv (Web Push, fara Home Assistant) */
const PUSH_OK = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
const pushKey = (k) => Uint8Array.from(atob(k.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - k.length % 4) % 4)), (c) => c.charCodeAt(0));
async function pushSub() { if (!PUSH_OK) return null; const reg = await navigator.serviceWorker.getRegistration(); return reg ? reg.pushManager.getSubscription() : null; }
SETTINGS_EXT.push({
  async render() {
    let st, sub = null;
    try { sub = await pushSub(); st = await api('/api/push/status' + (sub ? '?endpoint=' + encodeURIComponent(sub.endpoint) : '')); } catch (e) { return ''; }
    const ios = /iPhone|iPad/.test(navigator.userAgent) && !(navigator.standalone || matchMedia('(display-mode: standalone)').matches);
    const L = { alert: X('Alerte', 'Alerts'), maint: X('Reamintiri service', 'Service reminders'), report: X('Rapoarte', 'Reports'), app_update: X('Versiune nouă a aplicației', 'New app version'), low_batt: X('Baterie scăzută', 'Low battery'),
      update: X('Update software mașină', 'Car software update'), charge_done: X('Încărcare terminată', 'Charge finished'), plugged: X('Cablu conectat', 'Plug-in'), door: X('Uși/portbagaj deschise', 'Doors/trunk open'), rule: X('Reguli automate', 'Automation rules'), handoff: X('Predare mașină', 'Car handoff'), test: X('Teste', 'Tests') };
    const state = !PUSH_OK ? X('Acest browser nu suportă notificări push.', 'This browser does not support push notifications.')
      : ios ? X('Pe iPhone: deschide aplicația din ecranul principal (Share → Add to Home Screen), apoi activează aici.', 'On iPhone: open the app from the Home Screen (Share → Add to Home Screen), then enable here.')
      : (st.mine ? '✓ ' + X('Activate pe acest dispozitiv.', 'Enabled on this device.') : X('Neactivate pe acest dispozitiv.', 'Not enabled on this device.'));
    return `<h2>${X('Notificări push', 'Push notifications')}</h2><div class="card cfg">
      <p class="note" style="margin:0 0 8px">${X('Notificări direct pe telefon, fără Home Assistant. Dacă ai și webhook-ul Home Assistant activ, vei primi aceeași notificare de două ori: dezactivează tipurile de mai jos sau webhook-ul.', 'Notifications straight to your phone, no Home Assistant needed. If the Home Assistant webhook is also active you will get the same notification twice: turn off the kinds below or the webhook.')}</p>
      <div class="grid">${stat(X('Dispozitive abonate', 'Subscribed devices'), st.devices)}${stat(X('Acest dispozitiv', 'This device'), st.mine ? '✓' : '—')}</div>
      <p class="note">${state}</p>
      ${PUSH_OK && !ios ? `<div class="links"><a href="#" id="pu_on">${st.mine ? X('Reactivează', 'Re-enable') : X('Activează pe acest dispozitiv', 'Enable on this device')}</a>${st.mine ? `<a href="#" id="pu_off">${X('Dezactivează', 'Disable')}</a><a href="#" id="pu_test">${X('Trimite test', 'Send test')}</a>` : ''}</div>` : ''}
      <h3 class="sub">${X('Ce primești (valabil pentru toate dispozitivele)', 'What you get (applies to all devices)')}</h3>
      ${Object.keys(L).map((x) => sw('puk_' + x, !!st.kinds[x], L[x])).join('')}
      <div class="links"><a href="#" id="pu_kinds">${X('Salvează alegerile', 'Save choices')}</a></div>
      <div class="toast" aria-live="polite" id="pu_msg" style="display:none"></div></div>`;
  },
  after() {
    const say = (t, cls) => { const m = document.getElementById('pu_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
    const on = document.getElementById('pu_on'), off = document.getElementById('pu_off'), test = document.getElementById('pu_test'), kinds = document.getElementById('pu_kinds');
    if (on) on.onclick = async (e) => {
      e.preventDefault(); say(X('Se activează…', 'Enabling…'), 'busy');
      try {
        const perm = await Notification.requestPermission();
        if (perm !== 'granted') { say('✗ ' + X('Permisiunea pentru notificări a fost refuzată (o poți schimba din setările browserului).', 'Notification permission was denied (you can change it in the browser settings).'), 'bad'); return; }
        const reg = await navigator.serviceWorker.register('sw.js'); await navigator.serviceWorker.ready;
        const key = (await api('/api/push/status')).key;
        let sub = await reg.pushManager.getSubscription();
        if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: pushKey(key) });
        const r = await fetch('/api/push/subscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sub.toJSON()) }), j = await r.json().catch(() => ({}));
        if (!r.ok) { say('✗ ' + (j.reason || r.status), 'bad'); return; }
        say('✓ ' + X('Activat', 'Enabled'), 'ok'); setTimeout(render, 700);
      } catch (err) { say('✗ ' + err.message, 'bad'); }
    };
    if (off) off.onclick = async (e) => {
      e.preventDefault();
      try {
        const sub = await pushSub();
        if (sub) { await fetch('/api/push/unsubscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: sub.endpoint }) }); await sub.unsubscribe(); }
        render();
      } catch (err) { say('✗ ' + err.message, 'bad'); }
    };
    if (test) test.onclick = async (e) => {
      e.preventDefault(); say(X('Se trimite…', 'Sending…'), 'busy');
      const r = await fetch('/api/push/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }), j = await r.json().catch(() => ({}));
      say(j.ok ? '✓ ' + X('Trimis', 'Sent') : '✗ ' + (j.reason || r.status), j.ok ? 'ok' : 'bad');
    };
    if (kinds) kinds.onclick = async (e) => {
      e.preventDefault(); const body = {}; document.querySelectorAll('[id^="puk_"]').forEach((c) => { body[c.id.slice(4)] = c.checked; });
      const [ok, j] = await pinPost('/api/push/kinds', body);
      say(ok ? '✓ ' + X('Salvat', 'Saved') : '✗ ' + (j.reason || X('Eroare', 'Error')), ok ? 'ok' : 'bad');
    };
  },
});

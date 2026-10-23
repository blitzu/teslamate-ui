/* Notificari pe telefon (Web Push, fara Home Assistant): pagina ghidata #/push pentru oricine, alegerea tipurilor in Setari → Notificari */
const PUSH_OK = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
const IOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const STANDALONE = !!(navigator.standalone || matchMedia('(display-mode: standalone)').matches);
const pushKey = (k) => Uint8Array.from(atob(k.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - k.length % 4) % 4)), (c) => c.charCodeAt(0));
async function pushSub() { if (!PUSH_OK) return null; try { const reg = await navigator.serviceWorker.getRegistration(); return reg ? await reg.pushManager.getSubscription() : null; } catch (e) { return null; } }
const pushLS = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (e) { /* ignore */ } return null; };
const PUSH_KINDS = () => ({ alert: X('Alerte', 'Alerts'), maint: X('Reamintiri service', 'Service reminders'), report: X('Rapoarte', 'Reports'), app_update: X('Versiune nouă a aplicației', 'New app version'), low_batt: X('Baterie scăzută', 'Low battery'),
  update: X('Update software mașină', 'Car software update'), charge_done: X('Încărcare terminată', 'Charge finished'), plugged: X('Cablu conectat', 'Plug-in'), door: X('Uși/portbagaj deschise', 'Doors/trunk open'), rule: X('Reguli automate', 'Automation rules'), handoff: X('Predare mașină', 'Car handoff'), test: X('Teste', 'Tests') });

/* sugestie pe pagina Masina, pana se activeaza notificarile pe acest telefon */
let pushState = pushLS('push_on') === '1' ? 'on' : 'unknown';
pushSub().then((s) => { pushState = s ? 'on' : 'off'; pushLS('push_on', s ? '1' : null); });
window.CAR_CHIPS = window.CAR_CHIPS || [];
window.CAR_CHIPS.push(() => {
  if (pushState === 'on' || pushLS('push_hint') === 'off' || (!IOS && !PUSH_OK) || (typeof S !== 'undefined' && S.role === 'viewer')) return '';
  const t = IOS && !STANDALONE ? X('📲 Pune aplicația pe ecranul principal ca să primești notificări', '📲 Add the app to your Home Screen to get notifications') : X('🔔 Activează notificările pe acest telefon', '🔔 Turn on notifications on this phone');
  return `<a href="#/push" class="chip" style="text-decoration:none"><i></i>${t}</a>`;
});

NAVI.push = 'M12 22c1.1 0 2-.9 2-2h-4c0 1.1.9 2 2 2zm6-6v-5c0-3.07-1.63-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.64 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z';
EXTRA_MENU.push(['push', 'Notificări pe telefon', 'Phone notifications', 'push']);

async function pushBody() {
  const sub = await pushSub();
  let st;
  try { st = await api('/api/push/status' + (sub ? '?endpoint=' + encodeURIComponent(sub.endpoint) : '')); } catch (e) { return `<div class="empty">${X('Nu pot încărca starea notificărilor.', 'Cannot load the notification state.')}</div>`; }
  if (sub && !st.mine) {                                            // abonament in browser, dar serverul nu-l mai are: il reinregistrez singur
    try { const r = await fetch('/api/push/subscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sub.toJSON()) }); if (r.ok) st.mine = true; } catch (e) { /* ignore */ }
  }
  pushState = st.mine ? 'on' : 'off'; pushLS('push_on', st.mine ? '1' : null);
  const step = (n, t) => `<div class="pstep"><b>${n}</b><span>${t}</span></div>`;
  const share = '<svg viewBox="0 0 24 24" width="18" height="18" style="vertical-align:-3px" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v13M8 7l4-4 4 4M5 12v8h14v-8"/></svg>';
  let main;
  if (IOS && !STANDALONE) {
    main = `<div class="card cfg"><b>${X('Pasul 1 din 2: pune aplicația pe ecranul principal', 'Step 1 of 2: add the app to your Home Screen')}</b>
      <p class="note">${X('iPhone-ul trimite notificări doar aplicațiilor adăugate pe ecranul principal (iOS 16.4 sau mai nou). Se face o singură dată:', 'iPhone only sends notifications to apps added to the Home Screen (iOS 16.4 or newer). You do it once:')}</p>
      ${step(1, X(`În <b>Safari</b>, apasă butonul Partajare ${share} din bara de jos.`, `In <b>Safari</b>, tap the Share button ${share} in the bottom bar.`))}
      ${step(2, X('Derulează și alege <b>Adaugă pe ecranul principal</b>, apoi <b>Adaugă</b>.', 'Scroll and choose <b>Add to Home Screen</b>, then <b>Add</b>.'))}
      ${step(3, X('Deschide aplicația <b>de pe ecranul principal</b> (nu din Safari).', 'Open the app <b>from the Home Screen</b> (not from Safari).'))}
      ${step(4, X('Intră aici din nou (meniu → Notificări pe telefon) și apasă <b>Activează</b>.', 'Come back here (menu → Phone notifications) and tap <b>Enable</b>.'))}
      <div class="links"><a href="#" id="pu_copy">${X('Copiază adresa aplicației', 'Copy the app address')}</a></div></div>`;
  } else if (!PUSH_OK) {
    main = `<div class="card cfg"><b>${X('Acest browser nu suportă notificări push', 'This browser does not support push notifications')}</b><p class="note">${X('Încearcă Chrome, Edge, Firefox sau Safari actualizat. Pe iPhone, deschide aplicația de pe ecranul principal.', 'Try Chrome, Edge, Firefox or an up-to-date Safari. On iPhone, open the app from the Home Screen.')}</p></div>`;
  } else if (Notification.permission === 'denied') {
    main = `<div class="card cfg"><b style="color:#ffb3b3">${X('Notificările sunt blocate pentru această aplicație', 'Notifications are blocked for this app')}</b>
      <p class="note">${IOS ? X('Pe iPhone: Setări → Notificări → Tesla (sau numele aplicației) → Permite notificările. Apoi revino aici.', 'On iPhone: Settings → Notifications → Tesla (or the app name) → Allow Notifications. Then come back here.') : X('Permite notificările pentru acest site din setările browserului (iconița de lângă adresă), apoi reîncarcă pagina.', 'Allow notifications for this site in the browser settings (the icon next to the address), then reload the page.')}</p></div>`;
  } else if (st.mine) {
    main = `<div class="card cfg"><b style="color:var(--mint)">✓ ${X('Notificările sunt active pe acest telefon', 'Notifications are on for this phone')}</b>
      <p class="note">${X('Primești alertele, reamintirile și rapoartele alese de administrator. Pe iPhone apar și pe ecranul blocat.', 'You get the alerts, reminders and reports the administrator chose. On iPhone they also show on the lock screen.')}</p>
      <div class="links"><a href="#" id="pu_test">${X('Trimite o notificare de test', 'Send a test notification')}</a><a href="#" id="pu_off">${X('Dezactivează pe acest telefon', 'Turn off on this phone')}</a></div></div>`;
  } else {
    main = `<div class="card cfg">${IOS ? `<b>${X('Pasul 2 din 2: activează', 'Step 2 of 2: turn on')}</b>` : `<b>${X('Activează notificările', 'Turn on notifications')}</b>`}
      <p class="note">${X('Apasă butonul, apoi <b>Permite</b> când telefonul întreabă. Îți trimitem imediat o notificare de test.', 'Tap the button, then <b>Allow</b> when the phone asks. A test notification arrives right away.')}</p>
      <button class="bigbtn" id="pu_on">${X('Activează notificările', 'Turn on notifications')}</button></div>`;
  }
  const hint = pushLS('push_hint') === 'off' ? `<a href="#" id="pu_hint">${X('Arată din nou sugestia pe pagina Mașină', 'Show the hint on the Car page again')}</a>` : (st.mine ? '' : `<a href="#" id="pu_hint">${X('Nu mai arăta sugestia pe pagina Mașină', 'Stop showing the hint on the Car page')}</a>`);
  return `${main}<div class="toast" aria-live="polite" id="pu_msg" style="display:none"></div>
    <p class="note">${X('Dispozitive abonate în total: ', 'Subscribed devices in total: ')}${st.devices}. ${hint}</p>`;
}

function pushBind() {
  const say = (t, cls) => { const m = document.getElementById('pu_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
  const el = (id) => document.getElementById(id);
  if (el('pu_on')) el('pu_on').onclick = async (e) => {
    e.preventDefault(); say(X('Se activează…', 'Turning on…'), 'busy');
    try {
      const perm = await Notification.requestPermission();                       // trebuie apelat direct din atingere (cerinta iOS)
      if (perm !== 'granted') { say('✗ ' + X('Permisiunea a fost refuzată.', 'Permission was denied.'), 'bad'); setTimeout(render, 1200); return; }
      const reg = await navigator.serviceWorker.register('sw.js'); await navigator.serviceWorker.ready;
      const key = (await api('/api/push/status')).key;
      let sub = await reg.pushManager.getSubscription();
      if (!sub) sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: pushKey(key) });
      const r = await fetch('/api/push/subscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(sub.toJSON()) }), j = await r.json().catch(() => ({}));
      if (!r.ok) { say('✗ ' + (j.reason || r.status), 'bad'); return; }
      pushState = 'on'; pushLS('push_on', '1');
      await fetch('/api/push/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {});
      say('✓ ' + X('Activat — verifică notificarea de test.', 'Done — check the test notification.'), 'ok'); setTimeout(render, 1500);
    } catch (err) { say('✗ ' + err.message, 'bad'); }
  };
  if (el('pu_off')) el('pu_off').onclick = async (e) => {
    e.preventDefault();
    try {
      const sub = await pushSub();
      if (sub) { await fetch('/api/push/unsubscribe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ endpoint: sub.endpoint }) }); await sub.unsubscribe(); }
      pushState = 'off'; pushLS('push_on', null); render();
    } catch (err) { say('✗ ' + err.message, 'bad'); }
  };
  if (el('pu_test')) el('pu_test').onclick = async (e) => {
    e.preventDefault(); say(X('Se trimite…', 'Sending…'), 'busy');
    const r = await fetch('/api/push/test', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }), j = await r.json().catch(() => ({}));
    say(j.ok ? '✓ ' + X('Trimis', 'Sent') : '✗ ' + (j.reason || r.status), j.ok ? 'ok' : 'bad');
  };
  if (el('pu_copy')) el('pu_copy').onclick = (e) => { e.preventDefault(); try { navigator.clipboard.writeText(location.origin + '/'); say('✓ ' + X('Copiat', 'Copied'), 'ok'); } catch (x) { say(location.origin + '/'); } };
  if (el('pu_hint')) el('pu_hint').onclick = (e) => { e.preventDefault(); pushLS('push_hint', pushLS('push_hint') === 'off' ? null : 'off'); render(); };
}

PAGES.push = {
  nav: 'push',
  async render() {
    return `<div class="top"><h1>${X('Notificări pe telefon', 'Phone notifications')}</h1><small>${X('Alerte și rapoarte direct pe telefon, fără Home Assistant.', 'Alerts and reports straight to your phone, no Home Assistant needed.')}</small></div>${await pushBody()}`;
  },
  after() { pushBind(); },
};

/* Setari → Notificari: ce tipuri de mesaje merg pe push (pentru toate dispozitivele) */
SETTINGS_EXT.push({
  cat: 'notif', order: 1,
  async render() {
    let st; try { st = await api('/api/push/status'); } catch (e) { return ''; }
    const L = PUSH_KINDS();
    return `<h2>${X('Notificări push pe telefon', 'Push notifications on phones')}</h2><div class="card cfg">
      <div class="grid">${stat(X('Dispozitive abonate', 'Subscribed devices'), st.devices)}${stat(X('Acest dispozitiv', 'This device'), pushState === 'on' ? '✓' : '—')}</div>
      <p class="note">${X('Fiecare persoană își activează telefonul din pagina dedicată (merge și pe iPhone).', 'Each person turns on their own phone from the dedicated page (works on iPhone too).')}</p>
      <div class="links"><a href="#/push">${X('Activează pe acest telefon →', 'Turn on for this phone →')}</a></div>
      <h3 class="sub">${X('Ce se trimite (pentru toate telefoanele)', 'What is sent (for all phones)')}</h3>
      ${Object.keys(L).map((x) => sw('puk_' + x, !!st.kinds[x], L[x])).join('')}
      <p class="note">${X('Dacă ai și webhook-ul Home Assistant activ, primești aceeași notificare de două ori: oprește tipurile dorite pe unul dintre canale.', 'If the Home Assistant webhook is also active you get the same notification twice: turn off the kinds you do not want on one of the channels.')}</p>
      <div class="links"><a href="#" id="pu_kinds">${X('Salvează alegerile', 'Save choices')}</a></div>
      <div class="toast" aria-live="polite" id="pk_msg" style="display:none"></div></div>`;
  },
  after() {
    const k = document.getElementById('pu_kinds');
    if (k) k.onclick = async (e) => {
      e.preventDefault(); const body = {}; document.querySelectorAll('[id^="puk_"]').forEach((c) => { body[c.id.slice(4)] = c.checked; });
      const [ok, j] = await pinPost('/api/push/kinds', body), m = document.getElementById('pk_msg');
      if (m) { m.style.display = ''; m.textContent = ok ? '✓ ' + X('Salvat', 'Saved') : '✗ ' + (j.reason || X('Eroare', 'Error')); m.className = 'toast ' + (ok ? 'ok' : 'bad'); }
    };
  },
});

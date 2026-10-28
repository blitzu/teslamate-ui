/* Setari → Securitate → Acces direct din internet (HTTPS, Let's Encrypt; DuckDNS sau domeniul tau) + adrese permise din reteaua locala. Totul din interfata. */
SETTINGS_EXT.push({
  cat: 'security', order: 6,
  async render() {
    let st, cfg; try { st = await api('/api/inet/status'); cfg = await api('/api/config'); } catch (e) { return ''; }
    const n = cfg.inet || {}, own = n.mode === 'own';
    return `<h2>${X('Acces direct din internet (HTTPS)', 'Direct internet access (HTTPS)')}</h2><div class="card cfg">
      <p class="note" style="margin:0 0 8px">${X('Pentru cine nu folosește Cloudflare: aplicația obține singură un certificat <b>Let’s Encrypt</b> și se deschide prin HTTPS pe domeniul tău. Alegi mai jos cum: cu un subdomeniu gratuit <b>DuckDNS</b> sau cu <b>domeniul tău</b> (ex. <code>casa.go.ro</code> de la Digi, No-IP, un domeniu cumpărat). În router adaugi o singură regulă: portul extern 443 (TCP) către portul public al aplicației de pe server (implicit 4101).', 'For those not using Cloudflare: the app gets a <b>Let’s Encrypt</b> certificate by itself and opens over HTTPS on your domain. Choose below how: with a free <b>DuckDNS</b> subdomain or with <b>your own domain</b> (e.g. <code>home.go.ro</code> from your ISP, No-IP, a domain you bought). In the router you add one rule: external port 443 (TCP) to the app’s public port on the server (4101 by default).')}</p>
      <p class="note" style="margin:0 0 8px">⚠ ${X('Cât e pornit, portul public al aplicației (implicit 4101) trece pe HTTPS și nu mai răspunde pe HTTP. Dacă îl folosești printr-un tunel Cloudflare, nu activa opțiunea. Aplicația se expune direct pe internet: parola e obligatorie (se cere mai sus) și rămâne protecția cu limitarea încercărilor.', 'While on, the app’s public port (4101 by default) switches to HTTPS and no longer answers on HTTP. If you use it through a Cloudflare tunnel, do not enable this. The app is exposed directly to the internet: the password (set above) is required and login attempts stay rate-limited.')}</p>
      ${sw('inet_on', n.on, X('Activează accesul din internet (HTTPS)', 'Enable internet access (HTTPS)'))}
      <label class="cf">${X('Cum obții domeniul', 'Which domain')}<select id="inet_mode"><option value="duckdns" ${own ? '' : 'selected'}>${X('Subdomeniu DuckDNS (aplicația îi ține IP-ul la zi)', 'DuckDNS subdomain (the app keeps its IP up to date)')}</option><option value="own" ${own ? 'selected' : ''}>${X('Domeniul meu (IP-ul îl actualizează ISP-ul / routerul)', 'My own domain (its IP is updated by my ISP / router)')}</option></select></label>
      <div id="inet_duck" style="${own ? 'display:none' : ''}">
        <label class="cf">${X('Subdomeniu DuckDNS', 'DuckDNS subdomain')} (.duckdns.org)<input id="duck_domain" value="${esc(n.domain || '')}" placeholder="masina" autocomplete="off"></label>
        <label class="cf">${X('Token DuckDNS', 'DuckDNS token')}<input id="duck_token" type="password" autocomplete="off" placeholder="${n.token_set ? X('••••••  (setat — lasă gol ca să-l păstrezi)', '••••••  (set — leave empty to keep)') : 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx'}"></label>
        <p class="note" style="margin:0">${X('Certificatul se obține prin validare DNS (nu are nevoie de portul 80 sau de ceva deschis pentru validare), deci poți folosi <b>orice port extern</b> în router (de ex. 8443 → 4101) și deschizi <code>https://nume.duckdns.org:8443</code>.', 'The certificate is obtained with DNS validation (no port 80 or anything else open for validation needed), so you can use <b>any external port</b> in the router (e.g. 8443 → 4101) and open <code>https://name.duckdns.org:8443</code>.')}</p>
      </div>
      <div id="inet_own" style="${own ? '' : 'display:none'}">
        <label class="cf">${X('Domeniul tău (complet, fără https://)', 'Your domain (full, without https://)')}<input id="inet_domain" value="${esc(n.own_domain || '')}" placeholder="casa.go.ro" autocomplete="off"></label>
        <p class="note" style="margin:0">${X('Aplicația nu modifică DNS-ul: numele trebuie să arate deja spre IP-ul tău public (îl actualizează ISP-ul sau routerul). Certificatul se obține prin validare pe <b>portul 443</b> (TLS-ALPN): Let’s Encrypt se conectează la domeniul tău, iar aplicația răspunde câteva secunde cu un certificat de validare; în acest timp portul public nu servește aplicația (și la reînnoire, la ~60 de zile). Validarea merge <b>doar pe portul extern 443</b> (cerința Let’s Encrypt): redirecționează extern 443 → portul public al aplicației, cel puțin cât se obține și se reînnoiește certificatul. Nu merge cu IP privat sau în spatele CGNAT. Dacă domeniul are și înregistrare IPv6 (AAAA), IPv6 trebuie să ajungă la server sau înregistrarea AAAA trebuie scoasă.', 'The app does not change DNS: the name must already point at your public IP (your ISP or router updates it). The certificate is obtained by validation on <b>port 443</b> (TLS-ALPN): Let’s Encrypt connects to your domain and the app answers for a few seconds with a validation certificate; meanwhile the public port does not serve the app (and again at renewal, about every 60 days). The validation works <b>only on external port 443</b> (a Let’s Encrypt rule): forward external 443 → the app’s public port, at least while the certificate is obtained and renewed. It does not work with a private IP or behind CGNAT. If the domain also has an IPv6 (AAAA) record, IPv6 must reach the server or the AAAA record has to be removed.')}</p>
      </div>
      <label class="cf">${X('E-mail pentru Let’s Encrypt (opțional, pentru avertizări de expirare)', 'E-mail for Let’s Encrypt (optional, for expiry warnings)')}<input id="inet_email" value="${esc(n.email || '')}" placeholder="${X('tu@exemplu.ro', 'you@example.com')}" autocomplete="off"></label>
      ${sw('inet_staging', n.staging, X('Certificat de test (Let’s Encrypt staging): browserul îl marchează nesigur; folosește-l doar ca să încerci fără limite', 'Test certificate (Let’s Encrypt staging): browsers flag it as untrusted; use it only to try things without rate limits'))}
      <h3 class="sub">${X('Adrese permise din rețeaua locală', 'Addresses allowed from the local network')}</h3>
      <label class="cf">${X('Nume de domeniu separate prin virgulă (adresele IP, localhost, .local și adresa aplicației sunt mereu permise)', 'Domain names separated by commas (IP addresses, localhost, .local and the app address are always allowed)')}<input id="allowed_hosts" value="${esc(n.allowed_hosts || '')}" placeholder="masina.exemplu.ro" autocomplete="off"></label>
      <div class="note" id="inet_status" style="margin:12px 0 0"></div>
      <div class="links"><a href="#" id="inet_save">${X('Salvează', 'Save')}</a><a href="#" id="inet_issue">${X('Obține certificatul acum', 'Get the certificate now')}</a></div>
      <div class="toast" aria-live="polite" id="inet_msg" style="display:none"></div></div>`;
  },
  after() {
    const say = (t, cls) => { const m = document.getElementById('inet_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
    const box = document.getElementById('inet_status'); if (!box) return;
    const modeSel = document.getElementById('inet_mode');
    modeSel.onchange = () => { const o = modeSel.value === 'own'; document.getElementById('inet_duck').style.display = o ? 'none' : ''; document.getElementById('inet_own').style.display = o ? '' : 'none'; };
    const ago = (t) => { if (!t) return '—'; const s = Math.max(0, Math.round(Date.now() / 1000 - t)); return s < 90 ? X('acum', 'now') : s < 5400 ? Math.round(s / 60) + ' min' : Math.round(s / 3600) + ' h'; };
    const paint = (st) => {
      const ok = (b, t) => `<div>${b ? '✓' : '✗'} ${t}</div>`, c = st.cert;
      let h = ok(st.password_set, X('Parolă setată (obligatorie)', 'Password set (required)'));
      if (st.domain && st.mode === 'own') {
        h += `<div>${st.resolved ? '✓' : '⚠'} ${X('Domeniu', 'Domain')} ${esc(st.domain)}: ${st.resolved ? X('DNS arată către ', 'DNS points to ') + esc(st.resolved) : X('nu se rezolvă (încă)', 'does not resolve (yet)')}${st.public_ip ? ' · ' + X('IP-ul tău public: ', 'your public IP: ') + esc(st.public_ip) : ''}</div>`;
        if (st.resolved && st.public_ip && st.resolved !== st.public_ip) h += `<div>⚠ ${X('DNS-ul nu arată către IP-ul tău public: Let’s Encrypt nu va ajunge la aplicație (poate fi doar propagare sau o înregistrare veche).', 'DNS does not point to your public IP: Let’s Encrypt will not reach the app (may be just propagation or a stale record).')}</div>`;
      } else if (st.domain) {
        h += ok(!!st.ip, `DuckDNS ${esc(st.domain)}: ${st.ip ? esc(st.ip) + ' · ' + X('actualizat ', 'updated ') + ago(st.ip_at) : esc(st.dns_msg || X('încă neactualizat', 'not updated yet'))}`);
        if (st.ip && st.resolved) h += ok(st.resolved === st.ip, `${X('DNS arată către', 'DNS points to')} ${esc(st.resolved)}${st.resolved === st.ip ? '' : ' — ' + X('diferă de IP-ul tău public; poate fi doar propagare', 'differs from your public IP; may be just propagation')}`);
      }
      h += ok(!!(c && st.cert_ok), c ? `${X('Certificat', 'Certificate')} ${esc(c.issuer)}${c.staging ? ' (' + X('de test', 'test') + ')' : ''}: ${c.days_left >= 0 ? X('valabil încă ', 'valid for ') + c.days_left + X(' zile', ' days') : X('expirat', 'expired')}${st.cert_ok ? '' : ' — ' + X('nu se potrivește cu domeniul', 'does not match the domain')}` : X('Certificat: încă nu există', 'Certificate: none yet'));
      h += ok(st.listening, st.listening ? `${X('HTTPS activ pe portul', 'HTTPS active on port')} ${st.port}. ${X('În router: portul extern 443 (TCP) → portul', 'In the router: external port 443 (TCP) → port')} ${st.port} ${X('al serverului', 'of the server')}` : X('HTTPS inactiv (portul public rămâne pe HTTP)', 'HTTPS inactive (the public port stays on HTTP)'));
      (st.blockers || []).forEach((b) => { h += `<div>⚠ ${esc(b)}</div>`; });
      if (st.error) h += `<div style="color:#ffb3b3">✗ ${esc(st.error)}</div>`;
      if (st.issuing) h += `<div>⏳ ${X('Se obține certificatul… (poate dura 1–2 minute)', 'Getting the certificate… (may take 1–2 minutes)')}</div>`;
      if ((st.log || []).length) h += `<details ${st.issuing || st.error ? 'open' : ''} style="margin-top:6px"><summary>${X('Jurnal', 'Log')}</summary><pre class="notes">${esc(st.log.join('\n'))}</pre></details>`;
      box.innerHTML = h;
    };
    const T = { id: null, fast: false };
    const every = (ms, fast) => { clearInterval(T.id); T.fast = fast; T.id = setInterval(tick, ms); };
    const tick = async () => {
      if (!document.getElementById('inet_status')) { clearInterval(T.id); return; }                        // s-a schimbat pagina
      try { const st = await api('/api/inet/status'); paint(st); if (!st.issuing && T.fast) every(10000, false); } catch (e) { /* ignore */ }
    };
    tick(); every(10000, false);
    const fast = () => { every(2000, true); tick(); };
    document.getElementById('inet_save').onclick = async (e) => {
      e.preventDefault(); say(X('Se salvează…', 'Saving…'), 'busy');
      const body = { inet_on: document.getElementById('inet_on').checked ? '1' : '0', inet_mode: modeSel.value, duck_domain: document.getElementById('duck_domain').value.trim() || '__clear__',
        inet_domain: document.getElementById('inet_domain').value.trim() || '__clear__', inet_email: document.getElementById('inet_email').value.trim() || '__clear__',
        inet_staging: document.getElementById('inet_staging').checked ? '1' : '0', allowed_hosts: document.getElementById('allowed_hosts').value.trim() || '__clear__' };
      const tok = document.getElementById('duck_token').value.trim(); if (tok) body.duck_token = tok;
      const [ok, j] = await pinPost('/api/config', body);
      say(ok && j.ok ? '✓ ' + X('Salvat. Dacă lipsește certificatul, se obține automat.', 'Saved. If there is no certificate yet, it is requested automatically.') : '✗ ' + (j.reason || j.error || X('Eroare', 'Error')), ok && j.ok ? 'ok' : 'bad');
      if (ok && j.ok) { document.getElementById('duck_token').value = ''; setTimeout(fast, 800); }
    };
    document.getElementById('inet_issue').onclick = async (e) => {
      e.preventDefault(); say(X('Se pornește…', 'Starting…'), 'busy');
      const [ok, j] = await pinPost('/api/inet/issue', {});
      say(ok && j.ok ? '✓ ' + (j.started ? X('Obținerea certificatului a pornit', 'Getting the certificate has started') : X('Rulează deja', 'Already running')) : '✗ ' + (j.reason || X('Eroare', 'Error')), ok && j.ok ? 'ok' : 'bad');
      if (ok && j.ok) fast();
    };
  },
});

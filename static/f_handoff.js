/* Predare masina: valet / oaspete / limita de viteza cu cronometru si raport (#/handoff) */
NAVI.handoff = 'M12.65 10A5.99 5.99 0 0 0 7 6c-3.31 0-6 2.69-6 6s2.69 6 6 6a5.99 5.99 0 0 0 5.65-4H17v4h4v-4h2v-4H12.65zM7 14c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z';
EXTRA_MENU.push(['handoff', 'Predare mașină', 'Car handoff', 'handoff']);
PAGES.handoff = {
  nav: 'handoff',
  async render() {
    let d; try { d = await api('/api/handoff?car=' + car); } catch (e) { return `<div class="top"><h1>${X('Predare mașină', 'Car handoff')}</h1></div><div class="empty">${X('Doar administratorul poate folosi această pagină.', 'Only the administrator can use this page.')}</div>`; }
    const a = d.active, kmh = (mph) => Math.round(mph * 1.609);
    const rep = (r) => !r ? '—' : (r.drives ? `${r.drives} ${X('curse', 'drives')} · ${nf(r.km, 1)} km · ${X('max', 'max')} ${nf(r.speed_max, 0)} km/h${r.places && r.places.length ? '<br><small class="mut">' + r.places.map(esc).join(' → ') + '</small>' : ''}` : X('Nicio cursă', 'No drives'));
    const mod = (m) => m.split(',').map((x) => ({ guest: X('oaspete', 'guest'), valet: 'valet', 'limită': X('limită viteză', 'speed limit') }[x] || x)).join(' + ');
    const head = `<div class="top"><h1>${X('Predare mașină', 'Car handoff')}</h1><small>${X('Dai mașina cuiva (valet, service, un prieten): pornești Valet / Guest / limită de viteză pentru o perioadă și primești raportul. PIN-ul de 4 cifre al mașinii nu se salvează nicăieri.', 'Handing the car over (valet, service, a friend): turn on Valet / Guest / speed limit for a while and get a report. The car’s 4-digit PIN is never stored.')}</small></div>`;
    const cur = a ? `<h2>${X('Activă', 'Active')}</h2><div class="card cfg"><b>${esc(mod(a.modes))}${a.label ? ' · ' + esc(a.label) : ''}</b>
        <p class="note">${X('Pornită ', 'Started ')}${esc(new Date(a.started * 1000).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' }))} · ${a.ends < d.now ? '<b style="color:#ffb15c">' + X('timpul a expirat', 'time is up') + '</b>' : X('expiră ', 'expires ') + esc(new Date(a.ends * 1000).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' }))}${a.limit_mph ? ' · ' + kmh(a.limit_mph) + ' km/h' : ''}</p>
        <p class="note">${X('Până acum: ', 'So far: ')}${rep(a.so_far)}</p>
        <label class="cf">${X('PIN mașină (4 cifre) — pentru a opri Valet / limita', 'Car PIN (4 digits) — to stop Valet / the limit')}<input id="ho_pin" inputmode="numeric" maxlength="4" type="password" autocomplete="off" placeholder="••••"></label>
        <div class="links"><a href="#" id="ho_end">${X('Încheie predarea', 'End handoff')}</a></div><div class="toast" aria-live="polite" id="ho_msg" style="display:none"></div></div>`
      : `<h2>${X('Pornește', 'Start')}</h2><div class="card cfg">
        ${sw('ho_valet', true, X('Mod Valet (viteză și acces limitate, portbagaj/torpedo blocate)', 'Valet mode (limited speed and access, trunk/glovebox locked)'))}
        ${sw('ho_guest', false, X('Mod Guest (profil de oaspete)', 'Guest mode (guest profile)'))}
        <label class="cf">${X('Limită de viteză (km/h, gol = fără)', 'Speed limit (km/h, empty = none)')}<input id="ho_kmh" inputmode="numeric" placeholder="120"></label>
        <label class="cf">${X('Durată (minute)', 'Duration (minutes)')}<input id="ho_min" inputmode="numeric" value="120"></label>
        <label class="cf">${X('Etichetă (opțional)', 'Label (optional)')}<input id="ho_label" maxlength="40" placeholder="${X('Service / Mihai', 'Service / Mike')}"></label>
        <label class="cf">${X('PIN mașină (4 cifre) — nu se salvează', 'Car PIN (4 digits) — not stored')}<input id="ho_pin" inputmode="numeric" maxlength="4" type="password" autocomplete="off" placeholder="••••"></label>
        <div class="links"><a href="#" id="ho_go">${X('Pornește predarea', 'Start handoff')}</a></div><div class="toast" aria-live="polite" id="ho_msg" style="display:none"></div></div>`;
    const past = d.past.length ? `<h2>${X('Predări anterioare', 'Past handoffs')}</h2>${d.past.map((p) => `<div class="card"><b>${esc(mod(p.modes))}${p.label ? ' · ' + esc(p.label) : ''}</b><small class="mut">${esc(new Date(p.started * 1000).toLocaleString(LOC()))} → ${esc(new Date(p.ended * 1000).toLocaleTimeString(LOC(), { hour: '2-digit', minute: '2-digit' }))}</small><div class="note">${rep(p.report)}</div></div>`).join('')}` : '';
    return head + cur + past;
  },
  after() {
    const say = (t, cls) => { const m = document.getElementById('ho_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
    const v = (id) => document.getElementById(id), ck = (id) => !!(v(id) && v(id).checked);
    const go = v('ho_go');
    if (go) go.onclick = async (e) => {
      e.preventDefault();
      const kmh = parseFloat(v('ho_kmh').value);
      say(X('Se trimit comenzile către mașină…', 'Sending commands to the car…'), 'busy');
      const [ok, j] = await pinPost('/api/handoff/start', { car, valet: ck('ho_valet'), guest: ck('ho_guest'), mph: kmh ? Math.round(kmh / 1.609) : 0, minutes: v('ho_min').value, label: v('ho_label').value, pin4: v('ho_pin').value });
      if (ok && j.ok) { if (j.partial) alert((j.steps || []).filter((s) => !s.ok).map((s) => s.step + ': ' + s.reason).join('\n')); render(); }
      else say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad');
    };
    const end = v('ho_end');
    if (end) end.onclick = async (e) => {
      e.preventDefault(); say(X('Se încheie…', 'Ending…'), 'busy');
      let [ok, j] = await pinPost('/api/handoff/end', { car, pin4: v('ho_pin').value });
      if (!ok && j.can_force && confirm((j.reason || '') + ' ' + X('Încheii oricum (dezactivezi manual din mașină)?', 'End it anyway (turn it off in the car yourself)?'))) [ok, j] = await pinPost('/api/handoff/end', { car, pin4: v('ho_pin').value, force: true });
      if (ok && j.ok) { if (j.manual) alert(X('Unele funcții trebuie oprite din mașină: ', 'Some features must be turned off in the car: ') + (j.steps || []).filter((s) => !s.ok).map((s) => s.step).join(', ')); render(); }
      else say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad');
    };
  },
};

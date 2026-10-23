/* Reguli de zona / viteza / program (#/zones) */
NAVI.zones = 'M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 0 1 0-5 2.5 2.5 0 0 1 0 5z';
EXTRA_MENU.push(['zones', 'Reguli de zonă', 'Zone rules', 'zones']);
PAGES.zones = {
  nav: 'zones',
  async render() {
    let d; try { d = await api('/api/zones'); } catch (e) { return `<div class="top"><h1>${X('Reguli de zonă', 'Zone rules')}</h1></div><div class="empty">${X('Doar administratorul poate folosi această pagină.', 'Only the administrator can use this page.')}</div>`; }
    const kindLbl = { speed: X('Viteză peste', 'Speed over'), enter: X('Intră în zona', 'Enters zone'), leave: X('Iese din zona', 'Leaves zone'), curfew: X('Mișcare în afara programului', 'Moving outside schedule') };
    const detail = (r) => r.kind === 'speed' ? r.lim + ' km/h' : r.kind === 'curfew' ? esc(r.win) : esc(r.pattern);
    const rows = d.rules.map((r) => `<div class="alrow"><div><b>${esc(r.name)}</b><small class="mut">${kindLbl[r.kind]} · ${detail(r)} · ${r.scope === 'handoff' ? X('doar la predare', 'handoff only') : X('mereu', 'always')} · ${X('pauză', 'cooldown')} ${r.cooldown} min${r.fired ? ' · ' + r.fired + '×' : ''}${r.enabled ? '' : ' · ' + X('oprită', 'off')}</small></div>
      <span><a href="#" data-zt="${r.id}" data-on="${r.enabled}">${r.enabled ? X('Oprește', 'Disable') : X('Pornește', 'Enable')}</a> · <a href="#" data-zd="${r.id}">${X('Șterge', 'Delete')}</a></span></div>`).join('');
    return `<div class="top"><h1>${X('Reguli de zonă', 'Zone rules')}</h1><small>${X('Te anunț când mașina depășește o viteză, intră sau iese dintr-o zonă (geofence din TeslaMate) sau se mișcă la ore neobișnuite. Doar notificări; pot fi active mereu sau doar cât ține o predare.', 'I tell you when the car goes over a speed, enters or leaves a zone (a TeslaMate geofence) or moves at unusual hours. Notifications only; always on or only during a handoff.')}</small></div>
    <h2>${X('Reguli', 'Rules')}</h2><div class="card">${rows || `<div class="mut" style="font-size:13px">${X('Nicio regulă încă.', 'No rules yet.')}</div>`}</div>
    <h2>${X('Regulă nouă', 'New rule')}</h2><div class="card cfg">
      <label class="cf">${X('Tip', 'Type')}<select id="zr_kind"><option value="speed">${kindLbl.speed}</option><option value="enter">${kindLbl.enter}</option><option value="leave">${kindLbl.leave}</option><option value="curfew">${kindLbl.curfew}</option></select></label>
      <label class="cf" id="zr_f_limit">${X('Limită (km/h)', 'Limit (km/h)')}<input id="zr_limit" inputmode="numeric" value="130"></label>
      <label class="cf" id="zr_f_pat" style="display:none">${X('Nume zonă (regex, ex. Acas|Serviciu)', 'Zone name (regex, e.g. Home|Work)')}<input id="zr_pat" list="zr_geo" placeholder="Serviciu"><datalist id="zr_geo">${d.geofences.map((g) => `<option value="${esc(g)}">`).join('')}</datalist></label>
      <label class="cf" id="zr_f_win" style="display:none">${X('Program (HH:MM-HH:MM)', 'Schedule (HH:MM-HH:MM)')}<input id="zr_win" value="23:00-06:00"></label>
      <label class="cf">${X('Nume (opțional)', 'Name (optional)')}<input id="zr_name" maxlength="60"></label>
      <label class="cf">${X('Pauză între alerte (min)', 'Cooldown between alerts (min)')}<input id="zr_cd" inputmode="numeric" value="10"></label>
      ${sw('zr_handoff', false, X('Doar cât ține o predare a mașinii', 'Only while a car handoff is active'))}
      <div class="links"><a href="#" id="zr_add">${X('Adaugă regula', 'Add rule')}</a></div><div class="toast" aria-live="polite" id="zr_msg" style="display:none"></div></div>
    <h2>${X('Declanșări recente', 'Recent triggers')}</h2><div class="card">${d.log.length ? d.log.map((x) => `<div class="alitem"><i style="background:#7aa8ff"></i><div><b>${esc(x.name)}</b><small>${esc(x.msg)}</small><small class="mut">${esc(new Date(x.ts * 1000).toLocaleString(LOC()))}</small></div></div>`).join('') : `<div class="mut" style="font-size:13px">${X('Nimic încă.', 'Nothing yet.')}</div>`}</div>`;
  },
  after() {
    const v = (id) => document.getElementById(id);
    const say = (t, cls) => { const m = v('zr_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
    const sync = () => { const k = v('zr_kind').value; v('zr_f_limit').style.display = k === 'speed' ? '' : 'none'; v('zr_f_pat').style.display = (k === 'enter' || k === 'leave') ? '' : 'none'; v('zr_f_win').style.display = k === 'curfew' ? '' : 'none'; };
    if (v('zr_kind')) { v('zr_kind').onchange = sync; sync(); }
    const add = v('zr_add');
    if (add) add.onclick = async (e) => {
      e.preventDefault();
      const [ok, j] = await pinPost('/api/zones/rule', { kind: v('zr_kind').value, limit: v('zr_limit').value, pattern: v('zr_pat').value, window: v('zr_win').value, name: v('zr_name').value, cooldown: v('zr_cd').value, scope: v('zr_handoff').checked ? 'handoff' : 'always' });
      if (ok) render(); else say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad');
    };
    document.querySelectorAll('[data-zd]').forEach((a) => a.onclick = async (e) => { e.preventDefault(); const [ok] = await pinPost('/api/zones/delete', { id: a.dataset.zd }); if (ok) render(); });
    document.querySelectorAll('[data-zt]').forEach((a) => a.onclick = async (e) => {
      e.preventDefault();
      const r = (await api('/api/zones')).rules.find((x) => String(x.id) === a.dataset.zt); if (!r) return;
      const [ok] = await pinPost('/api/zones/rule', { id: r.id, kind: r.kind, limit: r.lim, pattern: r.pattern, window: r.win, name: r.name, cooldown: r.cooldown, scope: r.scope, enabled: !r.enabled });
      if (ok) render();
    });
  },
};

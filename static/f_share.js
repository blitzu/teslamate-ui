/* Setari → Link public de urmarire in timp real */
SETTINGS_EXT.push({
  cat: 'data', order: 2,
  async render() {
    let d; try { d = await api('/api/share'); } catch (e) { return ''; }
    const live = d.shares.filter((s) => !s.revoked && s.expires > d.now);
    const rows = live.map((s) => `<div class="alrow"><div><b>${esc(s.label || X('Link', 'Link'))}</b><small class="mut">${X('expiră ', 'expires ')}${esc(new Date(s.expires * 1000).toLocaleString(LOC()))} · ${s.views} ${X('vizualizări', 'views')}${s.hide_home ? ' · ' + X('ascunde acasa', 'hides home') : ''}${s.show_dest ? ' · ' + X('arată destinația', 'shows destination') : ''}</small></div><a href="#" data-shr="${s.id}">${X('Retrage', 'Revoke')}</a></div>`).join('');
    return `<h2>${X('Link de urmărire în timp real', 'Live-location link')}</h2><div class="card cfg">
      <p class="note" style="margin:0 0 8px">${X('Un link public cu harta și ora sosirii, pe care îl trimiți cuiva care te așteaptă. Expiră singur, îl poți retrage oricând și implicit ascunde poziția cât ești acasă. Oricine are linkul vede poziția cât e valabil.', 'A public link with the map and arrival time to send to someone waiting for you. It expires by itself, you can revoke it any time, and by default hides the position while you are at home. Anyone with the link sees the position while it is valid.')}</p>
      ${d.base ? '' : `<p class="note" style="color:#ffb3b3">${X('Lipsește domeniul public Fleet; nu pot genera linkuri.', 'The public Fleet domain is missing; cannot create links.')}</p>`}
      <label class="cf">${X('Valabil (ore)', 'Valid for (hours)')}<select id="sh_h"><option value="1">1</option><option value="2" selected>2</option><option value="4">4</option><option value="8">8</option><option value="24">24</option><option value="48">48</option></select></label>
      <label class="cf">${X('Etichetă (apare pe pagină, opțional)', 'Label (shown on the page, optional)')}<input id="sh_l" maxlength="40" placeholder="Mihai"></label>
      ${sw('sh_home', true, X('Ascunde poziția cât sunt acasă', 'Hide the position while at home'))}${sw('sh_dest', true, X('Arată destinația', 'Show the destination'))}
      <div class="links"><a href="#" id="sh_new">${X('Creează link', 'Create link')}</a>${live.length ? `<a href="#" id="sh_all">${X('Retrage toate', 'Revoke all')}</a>` : ''}</div>
      <div id="sh_out"></div>
      ${rows ? `<h3 class="sub">${X('Linkuri active', 'Active links')}</h3>${rows}` : ''}
      <div class="toast" aria-live="polite" id="sh_msg" style="display:none"></div></div>`;
  },
  after() {
    const say = (t, cls) => { const m = document.getElementById('sh_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
    const nw = document.getElementById('sh_new');
    if (nw) nw.onclick = async (e) => {
      e.preventDefault(); say(X('Se creează…', 'Creating…'), 'busy');
      const [ok, j] = await pinPost('/api/share/create', { hours: document.getElementById('sh_h').value, label: document.getElementById('sh_l').value, hide_home: document.getElementById('sh_home').checked, show_dest: document.getElementById('sh_dest').checked });
      if (!ok || !j.url) { say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad'); return; }
      document.getElementById('sh_out').innerHTML = `<label class="cf">${X('Link (se arată o singură dată)', 'Link (shown once)')}<input readonly id="sh_url" value="${esc(j.url)}"></label><div class="links"><a href="#" id="sh_copy">${X('Copiază', 'Copy')}</a>${navigator.share ? `<a href="#" id="sh_send">${X('Trimite…', 'Share…')}</a>` : ''}</div>`;
      say('✓ ' + X('Creat', 'Created'), 'ok');
      document.getElementById('sh_copy').onclick = (ev) => { ev.preventDefault(); const i = document.getElementById('sh_url'); i.select(); try { navigator.clipboard.writeText(i.value); say('✓ ' + X('Copiat', 'Copied'), 'ok'); } catch (x) { document.execCommand('copy'); } };
      const s = document.getElementById('sh_send'); if (s) s.onclick = (ev) => { ev.preventDefault(); navigator.share({ title: X('Urmărește-mă live', 'Follow me live'), url: j.url }).catch(() => {}); };
    };
    const all = document.getElementById('sh_all');
    if (all) all.onclick = async (e) => { e.preventDefault(); const [ok] = await pinPost('/api/share/revoke', { all: true }); if (ok) render(); };
    document.querySelectorAll('[data-shr]').forEach((a) => a.onclick = async (e) => { e.preventDefault(); const [ok] = await pinPost('/api/share/revoke', { id: a.dataset.shr }); if (ok) render(); });
  },
});

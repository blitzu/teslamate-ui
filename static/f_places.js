/* Locuri salvate cu pret pe kWh (pe pagina unei incarcari): toate incarcarile de acolo primesc cost = kWh x pret */
async function afterChargePlace() {
  const box = $('#chplace'), c = window.__chrow; if (!box || !c) return;
  let list = []; try { list = (await api('/api/places')).places; } catch (e) { return; }
  const cu = esc(CU()), here = c.place_name ? list.find((p) => p.name === c.place_name) : null;
  const hasPos = c.lat != null && c.lon != null;
  const rows = list.map((p) => `<div class="alrow"><div><b>${esc(p.name)}</b><small class="mut">${nf(p.price, 3)} ${cu}/kWh · ${X('rază', 'radius')} ${p.radius} m</small></div><a href="#" data-pl-del="${p.id}">${X('Șterge', 'Delete')}</a></div>`).join('');
  box.innerHTML = `<h2>${X('Loc salvat și preț pe kWh', 'Saved place and price per kWh')}</h2><div class="card cfg">
    ${here ? `<p class="note" style="margin:0 0 8px">${X('Această încărcare e la „', 'This charge is at “')}<b>${esc(here.name)}</b>${X('”: ', '”: ')}${nf(here.price, 3)} ${cu}/kWh${c.cost_manual == null && c.cost_real == null ? '' : ' · ' + X('costul afișat e cel introdus manual sau cel real, care au prioritate', 'the shown cost is the manual or real one, which take priority')}.</p>` : `<p class="note" style="margin:0 0 8px">${X('Salvează locul acesta cu un preț pe kWh: toate încărcările de aici, și cele vechi, primesc costul kWh × preț (în aplicație; nu se scrie în TeslaMate). Costul introdus manual sau cel real de acasă au prioritate.', 'Save this place with a price per kWh: every charge here, including old ones, gets the cost kWh × price (in the app; nothing is written to TeslaMate). A manually entered cost or the real home cost take priority.')}</p>`}
    ${hasPos ? `<div class="addf"><label>${X('Nume loc', 'Place name')}<input id="pl_name" maxlength="60" value="${esc(here ? here.name : c.name || '')}"></label><label>${X('Preț', 'Price')} (${cu}/kWh)<input id="pl_price" inputmode="decimal" value="${here ? here.price : ''}" placeholder="2.30"></label><label>${X('Rază (m)', 'Radius (m)')}<input id="pl_rad" inputmode="numeric" value="${here ? here.radius : 150}"></label></div>
    <div class="links"><a href="#" id="pl_save">${here ? X('Actualizează locul', 'Update place') : X('Salvează locul', 'Save place')}</a></div>` : `<p class="note">${X('Nu cunosc coordonatele acestei încărcări.', 'The coordinates of this charge are unknown.')}</p>`}
    <div class="toast" id="pl_msg" style="display:none"></div>
    ${rows ? `<h3 class="sub">${X('Locuri salvate', 'Saved places')}</h3>${rows}` : ''}</div>`;
  const say = (t, cls) => { const m = $('#pl_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + cls; } };
  const sv = $('#pl_save');
  if (sv) sv.onclick = async (e) => {
    e.preventDefault(); say(X('Se salvează…', 'Saving…'), 'busy');
    const [ok, j] = await pinPost('/api/places/save', { id: here ? here.id : undefined, name: $('#pl_name').value, price: $('#pl_price').value, radius: $('#pl_rad').value, lat: c.lat, lon: c.lon });
    if (ok) { say('✓ ' + X('Salvat', 'Saved'), 'ok'); setTimeout(render, 700); } else say('✗ ' + (j.reason || X('Eroare', 'Error')), 'bad');
  };
  box.querySelectorAll('[data-pl-del]').forEach((a) => a.onclick = async (e) => {
    e.preventDefault(); if (!confirm(X('Șterg locul salvat?', 'Delete the saved place?'))) return;
    const [ok] = await pinPost('/api/places/delete', { id: a.dataset.plDel }); if (ok) render();
  });
}

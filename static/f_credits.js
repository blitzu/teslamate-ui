/* Credit cumparat la un furnizor (#/credits): "am platit 1000 lei si am primit 2000 lei credit" sau "100 lei pentru 1000 km". Cat timp furnizorul unei incarcari are un pachet,
   costul real al incarcarii se calculeaza singur (pretul de lista x platit/credit, sau km adaugati x lei/km); vezi features/credits.py. */
const crRate = (p) => p.paid / p.amount;
const crLine = (p) => p.kind === 'km'
  ? `${nf(p.paid, 2)} ${CU()} → ${nf(p.amount, 0)} km · <b>${nf(crRate(p), 3)} ${CU()}/km</b>`
  : `${nf(p.paid, 2)} ${CU()} → ${nf(p.amount, 2)} ${CU()} ${X('credit', 'credit')} · ${X('1 leu din tarif costă de fapt', 'each 1 of list price really costs')} <b>${nf(crRate(p), 3)} ${CU()}</b>`;

function crUsage(p) {
  const u = p.usage || {};
  if (!u.n) return `<small class="mut">${X('Nicio încărcare folosită încă din acest pachet.', 'No charge has used this pack yet.')}</small>`;
  const left = p.amount - u.used, unit = p.kind === 'km' ? 'km' : CU();
  return `<small class="mut">${X('Folosit', 'Used')} <b>${nf(u.used, p.kind === 'km' ? 0 : 2)}</b> ${X('din', 'of')} ${nf(p.amount, p.kind === 'km' ? 0 : 2)} ${unit} · ${u.n} ${X('încărcări', 'charges')}, ${nf(u.kwh, 0)} kWh, ${X('cost real', 'real cost')} ${nf(u.real, 2)} ${CU()}${u.saved != null ? ' · ' + X('economie față de tarif', 'saved vs list price') + ' ' + nf(u.saved, 2) + ' ' + CU() : ''}<br>
    ${left >= 0 ? X('Rămas din credit: ', 'Credit left: ') + `<b>${nf(left, p.kind === 'km' ? 0 : 2)} ${unit}</b>` : `<span style="color:var(--bad,#ff7a7a)">${X('Creditul a fost depășit cu ', 'The credit was exceeded by ')}${nf(-left, p.kind === 'km' ? 0 : 2)} ${unit}</span>`}</small>`;
}

PAGES.credits = {
  nav: 'charges',
  async render() {
    const head = `<a class="back" href="#/charges">‹ ${X('Încărcări', 'Charges')}</a><div class="top"><h1>${X('Credit cumpărat', 'Prepaid credit')}</h1><small>${X('Dacă ai cumpărat credit la un furnizor mai ieftin decât tariful afișat, spune-i aplicației și costul real al încărcărilor de acolo se calculează singur.', 'If you bought credit from a provider below its list price, tell the app and the real cost of the charges there is worked out by itself.')}</small></div>`;
    let j; try { j = await api('/api/credits?car=' + car); } catch (e) { return head + `<div class="empty">${X('Nu pot încărca pachetele.', 'Cannot load the packs.')}</div>`; }
    window.__cr = j;
    const cu = esc(CU());
    const list = (j.packs || []).map((p) => `<div class="card" style="margin-top:10px"><div class="row"><b>${esc(p.provider)}</b><div class="sp"></div><a href="#" data-cr-edit="${p.id}">${X('Modifică', 'Edit')}</a> <a href="#" data-cr-del="${p.id}" style="margin-left:12px">${X('Șterge', 'Delete')}</a></div>
      <div class="ldsub">${crLine(p)}${p.since ? ' · ' + X('din ', 'from ') + esc(p.since) : ''}${p.note ? ' · ' + esc(p.note) : ''}</div><div style="margin-top:6px">${crUsage(p)}</div></div>`).join('');
    const provs = [...new Set((j.providers || []).concat((j.packs || []).map((p) => p.provider)))].sort((a, b) => a.localeCompare(b));
    return `${head}<div id="crlist">${list || `<div class="empty">${X('Niciun pachet adăugat încă.', 'No pack added yet.')}</div>`}</div>
    <h2 id="crh">${X('Adaugă un pachet', 'Add a pack')}</h2><div class="card cfg" id="crform">
      <div class="addf"><label>${X('Furnizor', 'Provider')}<select id="cr_prov">${provs.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join('')}<option value="__new__">➕ ${X('Furnizor nou…', 'New provider…')}</option></select></label>
        <label id="cr_newl" style="display:${provs.length ? 'none' : ''}">${X('Nume furnizor', 'Provider name')}<input id="cr_provnew" maxlength="40" placeholder="ex. iHunt" autocomplete="off"></label>
        <label>${X('Tip de credit', 'Credit type')}<select id="cr_kind"><option value="money">${X('Bani (credit în ' + CU() + ')', 'Money (credit in ' + CU() + ')')}</option><option value="km">${X('Kilometri de autonomie (ex. Tesla)', 'Kilometres of range (e.g. Tesla)')}</option></select></label>
        <label>${X('Am plătit', 'I paid')} (${cu})<input id="cr_paid" type="number" inputmode="decimal" step="0.01" min="0" placeholder="1000"></label>
        <label id="cr_al">${X('Am primit credit', 'I received credit')} (${cu})<input id="cr_amount" type="number" inputmode="decimal" step="0.01" min="0" placeholder="2000"></label>
        <label>${X('Se aplică de la data (opțional)', 'Applies from (optional)')}<input id="cr_since" type="date"></label>
        <label>${X('Notă (opțional)', 'Note (optional)')}<input id="cr_note" maxlength="60"></label></div>
      <p class="note" id="cr_prev" style="margin:8px 0 0"></p>
      <div class="links"><a href="#" id="cr_save">${X('Salvează pachetul', 'Save pack')}</a><a href="#" id="cr_cancel" style="display:none">${X('Renunță la modificare', 'Cancel edit')}</a></div>
      <div class="toast" id="cr_msg" style="display:none"></div>
      <p class="note" style="margin:10px 0 0">${X('Fără dată, pachetul se aplică tuturor încărcărilor furnizorului; cu dată, doar celor de atunci încolo (dacă ai mai multe pachete, se folosește cel mai recent valabil la data încărcării). O sumă scrisă de tine pe o încărcare rămâne neschimbată, pentru că e suma reală. Un cost venit din tariful unei stații e preț de listă, deci i se aplică creditul. La tip „kilometri” se folosesc kilometrii de autonomie adăugați de încărcare (ex. Tesla Supercharger).', 'Without a date the pack applies to every charge of the provider; with a date, only to charges from then on (with several packs, the latest one valid on the charge date is used). An amount you typed on a charge stays as it is, since it is the real amount. A cost that comes from a station tariff is a list price, so the credit applies to it. With the “kilometres” type the kilometres of range added by the charge are used (e.g. Tesla Supercharger).')}</p></div>`;
  },
  after() {
    const j = window.__cr || { packs: [] }; let editing = 0;
    const el = (id) => $('#' + id), say = (t, cls) => { const m = el('cr_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + cls; } };
    const prov = () => { const s = el('cr_prov'); return s.value === '__new__' ? el('cr_provnew').value.trim() : s.value; };
    const prev = () => {
      const km = el('cr_kind').value === 'km', paid = parseFloat(String(el('cr_paid').value).replace(',', '.')), am = parseFloat(String(el('cr_amount').value).replace(',', '.'));
      el('cr_al').firstChild.textContent = km ? X('Am primit kilometri', 'I received kilometres') + ' ' : X('Am primit credit', 'I received credit') + ' (' + CU() + ')';
      el('cr_prev').innerHTML = paid > 0 && am > 0 ? (km ? `→ ${X('fiecare km de autonomie adăugat costă', 'each km of range added costs')} <b>${nf(paid / am, 3)} ${esc(CU())}</b>` : `→ ${X('la 1 leu din tariful afișat plătești de fapt', 'for each 1 of the list price you really pay')} <b>${nf(paid / am, 3)} ${esc(CU())}</b> (${nf(paid / am * 100, 0)}%)`) : '';
    };
    ['cr_kind', 'cr_paid', 'cr_amount'].forEach((i) => el(i).oninput = prev);
    el('cr_prov').onchange = () => { const on = el('cr_prov').value === '__new__'; el('cr_newl').style.display = on ? '' : 'none'; if (on) el('cr_provnew').focus(); };
    const reset = () => { editing = 0; ['cr_paid', 'cr_amount', 'cr_since', 'cr_note', 'cr_provnew'].forEach((i) => el(i).value = ''); el('cr_cancel').style.display = 'none'; el('crh').textContent = X('Adaugă un pachet', 'Add a pack'); prev(); };
    el('cr_cancel').onclick = (e) => { e.preventDefault(); reset(); };
    document.querySelectorAll('[data-cr-edit]').forEach((a) => a.onclick = (e) => {
      e.preventDefault(); const p = j.packs.find((x) => x.id === +a.dataset.crEdit); if (!p) return;
      editing = p.id; el('cr_prov').value = p.provider; el('cr_newl').style.display = 'none'; el('cr_kind').value = p.kind; el('cr_paid').value = p.paid; el('cr_amount').value = p.amount;
      el('cr_since').value = p.since || ''; el('cr_note').value = p.note || ''; el('cr_cancel').style.display = ''; el('crh').textContent = X('Modifică pachetul', 'Edit the pack'); prev(); el('crform').scrollIntoView({ behavior: 'smooth' });
    });
    document.querySelectorAll('[data-cr-del]').forEach((a) => a.onclick = async (e) => {
      e.preventDefault(); if (!confirm(X('Șterg pachetul? Costurile încărcărilor revin la cele de dinainte.', 'Delete the pack? Charge costs go back to what they were.'))) return;
      const [ok, r] = await pinPost('/api/credits/delete', { id: a.dataset.crDel }); if (ok) render(); else say('✗ ' + (r.reason || X('Eroare', 'Error')), 'bad');
    });
    el('cr_save').onclick = async (e) => {
      e.preventDefault(); say(X('Se salvează…', 'Saving…'), 'busy');
      const [ok, r] = await pinPost('/api/credits/save', { id: editing || undefined, provider: prov(), kind: el('cr_kind').value, paid: el('cr_paid').value, amount: el('cr_amount').value, since: el('cr_since').value, note: el('cr_note').value });
      if (ok) { say('✓ ' + X('Salvat', 'Saved'), 'ok'); setTimeout(render, 600); } else say('✗ ' + (r.reason || X('Eroare', 'Error')), 'bad');
    };
    prev();
  },
};

/* pe o incarcare: cum s-a ajuns la costul real (listat in lista incarcarilor si pe pagina ei) */
function crNote(c) {
  const k = c && c.credit; if (!k) return '';
  const cu = esc(CU());
  return k.kind === 'km'
    ? X(`Credit în km la ${esc(c.provider)}: ${nf(k.km, 0)} km de autonomie × ${nf(k.rate, 3)} ${cu}/km = <b>${nf(k.cost, 2)} ${cu}</b>.`, `Prepaid km at ${esc(c.provider)}: ${nf(k.km, 0)} km of range × ${nf(k.rate, 3)} ${cu}/km = <b>${nf(k.cost, 2)} ${cu}</b>.`)
    : X(`Credit la ${esc(c.provider)}: preț de listă ${nf(k.list, 2)} ${cu} × ${nf(k.rate, 3)} = <b>${nf(k.cost, 2)} ${cu}</b> cost real.`, `Prepaid credit at ${esc(c.provider)}: list price ${nf(k.list, 2)} ${cu} × ${nf(k.rate, 3)} = <b>${nf(k.cost, 2)} ${cu}</b> real cost.`);
}

/* pretul real langa un tarif de statie: " → 0,45 lei/kWh cu creditul tau" (bani: tarif x platit/credit; km: lei/km x km adaugati pe kWh la aceasta incarcare) */
function crReal(c, t) {
  const k = c && c.credit_rate; if (!k || !t || !(t.price >= 0)) return '';
  const v = k.kind === 'km' ? k.per_kwh : t.price * k.rate; if (v == null) return '';
  return ' → ' + nf(v, 2) + ' ' + esc(t.cur || CU()) + '/kWh ' + X('cu creditul tău', 'with your credit');
}

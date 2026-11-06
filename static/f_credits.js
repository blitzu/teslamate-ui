/* Credit cumparat la un furnizor (#/credits): "am platit 1000 lei si am primit 2000 lei credit" sau "100 lei pentru 1000 km". Cat timp furnizorul unei incarcari are un pachet,
   costul real al incarcarii se calculeaza singur (pretul de lista x platit/credit, sau km adaugati x lei/km); vezi features/credits.py. */
const crRate = (p) => p.paid / p.amount;
const crFee = (p) => p.fee ? ' · ' + X('taxă conectare ', 'connection fee ') + nf(p.fee, 2) + ' ' + CU() + (p.kind === 'km' || !p.fee_in_credit ? ' ' + X('(separat)', '(separate)') : ' ' + X('(din credit)', '(from credit)')) : '';
const crSrc = (p) => p.kind === 'km' && p.source === 'tesla' ? ' · ' + X('kilometri după Tesla', 'kilometres per Tesla') : '';
const crScale = (p) => p.kind === 'km' && p.km_kwh ? ' · ' + nf(p.km_kwh, 2) + ' km/kWh ≈ ' + nf(100 / p.km_kwh, 1) + ' kWh/100 km ' + X('(potrivit cu aplicația furnizorului)', '(matched to the provider’s app)') : '';
/* expirare: zile ramase / expirat */
const crDays = (iso) => Math.floor((new Date(iso + 'T23:59:59') - new Date()) / 864e5);          // zile intregi pana la sfarsitul zilei de expirare (0 = expira azi)
function crExp(p) {
  if (!p.expires) return '';
  const d = crDays(p.expires), left = p.kind === 'km' ? p.amount - ((p.usage || {}).used || 0) : p.amount - ((p.usage || {}).used || 0);
  const lost = left > 0.004 ? X(' · neconsumat: ', ' · unused: ') + nf(left, p.kind === 'km' ? 0 : 2) + ' ' + (p.kind === 'km' ? 'km' : CU()) : '';
  if (d < 0) return `<br><span style="color:var(--bad,#ff7a7a)">${X('Expirat pe ', 'Expired on ')}${esc(p.expires)}${lost}</span>`;
  const c = d <= 14 ? 'var(--warn,#ffb454)' : 'var(--mut,#9aa4b2)';
  return `<br><span style="color:${c}">${X('Expiră pe ', 'Expires on ')}${esc(p.expires)} · ${d === 0 ? X('azi', 'today') : X('mai sunt ' + d + (d === 1 ? ' zi' : ' zile'), d + (d === 1 ? ' day' : ' days') + ' left')}</span>`;
}
const crLine = (p) => p.kind === 'voucher'
  ? `🎁 <b>${nf(p.amount, 2)} ${CU()}</b> ${X('voucher: bani gratis, se scad primii din încărcări', 'voucher: free money, taken off the charges first')}`
  : p.kind === 'km'
  ? `${nf(p.paid, 2)} ${CU()} → ${nf(p.amount, 0)} km · <b>${nf(crRate(p), 3)} ${CU()}/km</b>${crSrc(p)}${p.source === 'tesla' ? '' : crScale(p)}${crFee(p)}`
  : `${nf(p.paid, 2)} ${CU()} → ${nf(p.amount, 2)} ${CU()} ${X('credit', 'credit')} · ${X('1 leu din tarif costă de fapt', 'each 1 of list price really costs')} <b>${nf(crRate(p), 3)} ${CU()}</b>${crFee(p)}`;

function crUsage(p) {
  const u = p.usage || {};
  if (p.kind === 'voucher') {
    const left = p.amount - (u.used || 0), cu = CU();
    return `<small class="mut">${X('Folosit', 'Used')} <b>${nf(u.used || 0, 2)}</b> ${X('din', 'of')} ${nf(p.amount, 2)} ${cu} · ${u.n || 0} ${X('încărcări', 'charges')}<br>${left > 0.004 ? X('Rămas din voucher: ', 'Voucher left: ') + `<b>${nf(left, 2)} ${cu}</b>` : X('Voucherul a fost consumat.', 'The voucher is used up.')}</small>`;
  }
  if (u.tesla) {
    const left = p.amount - u.used;
    return `<small class="mut">${X('Folosit după Tesla', 'Used per Tesla')} <b>${nf(u.used, 0)}</b> ${X('din', 'of')} ${nf(p.amount, 0)} km · ${u.n} ${X('sesiuni', 'sessions')}, ${nf(u.kwh, 0)} kWh<br>${left >= 0 ? X('Rămas: ', 'Left: ') + `<b>${nf(left, 0)} km</b>` : `<span style="color:var(--bad,#ff7a7a)">${X('Creditul a fost depășit cu ', 'The credit was exceeded by ')}${nf(-left, 0)} km</span>`}</small>`;
  }
  if (!u.n) return `<small class="mut">${X('Nicio încărcare folosită încă din acest pachet.', 'No charge has used this pack yet.')}</small>`;
  const left = p.amount - u.used, unit = p.kind === 'km' ? 'km' : CU();
  return `<small class="mut">${X('Folosit', 'Used')} <b>${nf(u.used, p.kind === 'km' ? 0 : 2)}</b> ${X('din', 'of')} ${nf(p.amount, p.kind === 'km' ? 0 : 2)} ${unit} · ${u.n} ${X('încărcări', 'charges')}, ${nf(u.kwh, 0)} kWh, ${X('cost real', 'real cost')} ${nf(u.real, 2)} ${CU()}${u.saved != null ? ' · ' + X('economie față de tarif', 'saved vs list price') + ' ' + nf(u.saved, 2) + ' ' + CU() : ''}${u.typed ? '<br>' + X(u.typed + ' din încărcări au costul scris de tine: kilometrii lor sunt scăzuți din credit, dar costul rămâne cel scris.', u.typed + ' of the charges have a cost you typed: their kilometres are taken off the credit, but the cost stays as typed.') : ''}<br>
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
      <div class="ldsub">${crLine(p)}${p.since ? ' · ' + X('din ', 'from ') + esc(p.since) : ''}${p.note ? ' · ' + esc(p.note) : ''}${crExp(p)}</div><div style="margin-top:6px">${crUsage(p)}</div></div>`).join('');
    const provs = [...new Set((j.providers || []).concat((j.packs || []).map((p) => p.provider)))].sort((a, b) => a.localeCompare(b));
    const tz = j.tesla, last = tz && tz.last ? new Date(tz.last.at.replace(' ', 'T')).toLocaleString(LOC(), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
    const tbox = tz && tz.available ? `<div class="card" style="margin-top:10px"><b>${X('Istoric Supercharger Tesla', 'Tesla Supercharger history')}</b><div class="ldsub">${tz.sessions ? tz.sessions + ' ' + X('sesiuni', 'sessions') + (last ? ' · ' + X('sincronizat ', 'synced ') + esc(last) : '') : X('Încă nesincronizat.', 'Not synced yet.')}</div>
      <div class="links"><a href="#" id="cr_tsync">⟳ ${X('Sincronizează cu Tesla', 'Sync with Tesla')}</a></div><div class="toast" id="cr_tmsg" style="display:none"></div>
      <p class="note" style="margin:6px 0 0">${X('Citit din contul Tesla conectat (doar citire): kilometrii de credit consumați exact pe fiecare sesiune, energia măsurată de încărcător și ce ai plătit. Un pachet în km marcat „după Tesla” le folosește în loc de calcul.', 'Read from the connected Tesla account (read-only): the credit kilometres used in each session, the energy the charger measured and what you paid. A kilometre pack marked “per Tesla” uses them instead of a calculation.')}</p></div>` : '';
    return `${head}${tbox}<div id="crlist">${list || `<div class="empty">${X('Niciun pachet adăugat încă.', 'No pack added yet.')}</div>`}</div>
    <h2 id="crh">${X('Adaugă un pachet', 'Add a pack')}</h2><div class="card cfg" id="crform">
      <div class="addf"><label>${X('Furnizor', 'Provider')}<select id="cr_prov">${provs.map((p) => `<option value="${esc(p)}">${esc(p)}</option>`).join('')}<option value="__new__">➕ ${X('Furnizor nou…', 'New provider…')}</option></select></label>
        <label id="cr_newl" style="display:${provs.length ? 'none' : ''}">${X('Nume furnizor', 'Provider name')}<input id="cr_provnew" maxlength="40" placeholder="ex. iHunt" autocomplete="off"></label>
        <label>${X('Tip de credit', 'Credit type')}<select id="cr_kind"><option value="money">${X('Bani (credit în ' + CU() + ')', 'Money (credit in ' + CU() + ')')}</option><option value="km">${X('Kilometri de autonomie (ex. Tesla)', 'Kilometres of range (e.g. Tesla)')}</option><option value="voucher">${X('Voucher (bani gratis)', 'Voucher (free money)')}</option></select></label>
        <label>${X('Am plătit', 'I paid')} (${cu})<input id="cr_paid" type="number" inputmode="decimal" step="0.01" min="0" placeholder="1000"></label>
        <label id="cr_al">${X('Am primit credit', 'I received credit')} (${cu})<input id="cr_amount" type="number" inputmode="decimal" step="0.01" min="0" placeholder="2000"></label>
        <label id="cr_src">${X('Kilometrii consumați', 'Kilometres used')}<select id="cr_source"><option value="">${X('calculați de aplicație', 'calculated by the app')}</option><option value="tesla">${X('exact, după istoricul Tesla', 'exact, from the Tesla history')}</option></select></label>
        <label id="cr_ll">${X('Mai am acum, după aplicația furnizorului (km), opțional', 'Left now, per the provider’s app (km), optional')}<input id="cr_left" type="number" inputmode="decimal" step="1" min="0" placeholder="375"></label>
        <label id="cr_sl">${X('Km de credit pe kWh (avansat)', 'Credit km per kWh (advanced)')}<input id="cr_scale" type="number" inputmode="decimal" step="0.01" min="0.2" placeholder="ex. 4.95"></label>
        <label>${X('Taxă de conectare pe sesiune', 'Connection fee per session')} (${cu})<input id="cr_fee" type="number" inputmode="decimal" step="0.01" min="0" placeholder="2"></label>
        <label id="cr_fcl">${X('Taxa se plătește', 'The fee is paid')}<select id="cr_fic"><option value="1">${X('din credit', 'from the credit')}</option><option value="0">${X('separat, în bani', 'separately, in cash')}</option></select></label>
        <label>${X('Se aplică de la data (opțional)', 'Applies from (optional)')}<input id="cr_since" type="date"></label>
        <label>${X('Valabil până la (opțional)', 'Valid until (optional)')}<input id="cr_exp" type="date"></label>
        <label>${X('Notă (opțional)', 'Note (optional)')}<input id="cr_note" maxlength="60"></label></div>
      <p class="note" id="cr_prev" style="margin:8px 0 0"></p>
      <div class="links"><a href="#" id="cr_save">${X('Salvează pachetul', 'Save pack')}</a><a href="#" id="cr_cancel" style="display:none">${X('Renunță la modificare', 'Cancel edit')}</a></div>
      <div class="toast" id="cr_msg" style="display:none"></div>
      <p class="note" style="margin:10px 0 0">${X('Fără dată, pachetul se aplică tuturor încărcărilor furnizorului; cu dată, doar celor de atunci încolo (dacă ai mai multe pachete, se folosește cel mai recent valabil la data încărcării). O sumă scrisă de tine pe o încărcare rămâne neschimbată, pentru că e suma reală. Un cost venit din tariful unei stații e preț de listă, deci i se aplică creditul. La tip „kilometri” se folosesc kilometrii de autonomie adăugați de încărcare (ex. Tesla Supercharger). Un voucher (bani gratis) se scade primul din încărcările de la data primirii, de la cel mai vechi la cel mai nou, și acoperă și taxa de conectare plătită din credit; o încărcare acoperită cu totul de voucher costă 0. La un pachet în km, furnizorul numără după energia luată de la încărcător, nu după autonomia nominală: scrie la „Mai am acum” cât îți arată aplicația furnizorului că a rămas, iar aplicația calculează câți km de credit scade pe fiecare kWh (se vede lângă pachet) și îl folosește pentru toate încărcările, și cele viitoare. Pe un Model 3 cu Tesla Supercharger rezultatul a fost cam 5 km pe kWh. „Valabil până la” e data de expirare a creditului (cele Tesla expiră după vreo 6 luni): după ea pachetul sau voucherul nu se mai aplică încărcărilor, iar ce a rămas neconsumat se vede ca pierdut. Taxa de conectare se adaugă la fiecare încărcare a furnizorului; dacă ai doar taxă, fără reducere, scrie aceeași sumă la „plătit” și la „credit”.', 'Without a date the pack applies to every charge of the provider; with a date, only to charges from then on (with several packs, the latest one valid on the charge date is used). An amount you typed on a charge stays as it is, since it is the real amount. A cost that comes from a station tariff is a list price, so the credit applies to it. With the “kilometres” type the kilometres of range added by the charge are used (e.g. Tesla Supercharger). A voucher (free money) is taken off the charges first, from the day you received it, oldest charge first, and it also covers the connection fee when that is paid from the credit; a charge covered entirely by the voucher costs 0. A kilometre pack is counted by the energy taken from the charger, not by the rated range: type what the provider’s app says is left under “Left now” and the app works out how many credit km each kWh takes (shown next to the pack) and uses it for all charges, future ones included. On a Model 3 at a Tesla Supercharger it came out near 5 km per kWh. “Valid until” is the expiry date of the credit (Tesla’s expire after about 6 months): after it the pack or voucher no longer applies to charges and what is left unused shows as lost. The connection fee is added to every charge of the provider; if you only have a fee and no discount, type the same amount for “paid” and “credit”.')}</p></div>`;
  },
  after() {
    const j = window.__cr || { packs: [] }; let editing = 0;
    const el = (id) => $('#' + id), say = (t, cls) => { const m = el('cr_msg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + cls; } };
    const prov = () => { const s = el('cr_prov'); return s.value === '__new__' ? el('cr_provnew').value.trim() : s.value; };
    const prev = () => {
      const km = el('cr_kind').value === 'km', paid = parseFloat(String(el('cr_paid').value).replace(',', '.')), am = parseFloat(String(el('cr_amount').value).replace(',', '.'));
      const vo = el('cr_kind').value === 'voucher';
      { const kk = parseFloat(String(el('cr_scale').value).replace(',', '.')), lb = el('cr_sl'); let hint = lb.querySelector('small'); if (!hint) { hint = document.createElement('small'); hint.className = 'mut'; lb.appendChild(hint); } hint.textContent = kk > 0 ? '≈ ' + nf(100 / kk, 1) + ' kWh/100 km' : ''; }
      el('cr_fcl').style.display = km || vo ? 'none' : '';
      ['cr_ll', 'cr_sl', 'cr_src'].forEach((i) => { el(i).style.display = km ? '' : 'none'; });
      ['cr_paid', 'cr_fee'].forEach((i) => { const lb = el(i).closest('label'); if (lb) lb.style.display = vo ? 'none' : ''; });
      el('cr_al').firstChild.textContent = vo ? X('Valoarea voucherului', 'Voucher value') + ' (' + CU() + ') ' : km ? X('Am primit kilometri', 'I received kilometres') + ' ' : X('Am primit credit', 'I received credit') + ' (' + CU() + ')';
      if (vo) { el('cr_prev').innerHTML = am > 0 ? X('→ se scade primul din încărcările de la data primirii; până se termină, încărcările costă 0.', '→ taken off the charges first, from the day you received it; until it is used up the charges cost 0.') : ''; return; }
      el('cr_prev').innerHTML = paid > 0 && am > 0 ? (km ? `→ ${X('fiecare km de autonomie adăugat costă', 'each km of range added costs')} <b>${nf(paid / am, 3)} ${esc(CU())}</b>` : `→ ${X('la 1 leu din tariful afișat plătești de fapt', 'for each 1 of the list price you really pay')} <b>${nf(paid / am, 3)} ${esc(CU())}</b> (${nf(paid / am * 100, 0)}%)`) : '';
    };
    const tAvail = !!(j.tesla && j.tesla.available);
    el('cr_kind').addEventListener('change', () => { if (el('cr_kind').value === 'km' && tAvail && /tesla/i.test(prov()) && !el('cr_source').value) el('cr_source').value = 'tesla'; });
    ['cr_kind', 'cr_paid', 'cr_amount', 'cr_fee', 'cr_fic', 'cr_scale'].forEach((i) => el(i).oninput = prev);
    el('cr_prov').onchange = () => { const on = el('cr_prov').value === '__new__'; el('cr_newl').style.display = on ? '' : 'none'; if (on) el('cr_provnew').focus(); };
    const reset = () => { editing = 0; ['cr_paid', 'cr_amount', 'cr_since', 'cr_exp', 'cr_note', 'cr_provnew', 'cr_fee', 'cr_left', 'cr_scale', 'cr_source'].forEach((i) => el(i).value = ''); el('cr_fic').value = '1'; el('cr_cancel').style.display = 'none'; el('crh').textContent = X('Adaugă un pachet', 'Add a pack'); prev(); };
    el('cr_cancel').onclick = (e) => { e.preventDefault(); reset(); };
    document.querySelectorAll('[data-cr-edit]').forEach((a) => a.onclick = (e) => {
      e.preventDefault(); const p = j.packs.find((x) => x.id === +a.dataset.crEdit); if (!p) return;
      editing = p.id; el('cr_prov').value = p.provider; el('cr_newl').style.display = 'none'; el('cr_kind').value = p.kind; el('cr_paid').value = p.paid; el('cr_amount').value = p.amount;
      el('cr_since').value = p.since || ''; el('cr_exp').value = p.expires || ''; el('cr_source').value = p.source === 'tesla' ? 'tesla' : ''; el('cr_note').value = p.note || ''; el('cr_fee').value = p.fee || ''; el('cr_scale').value = p.kind === 'km' && p.km_kwh ? p.km_kwh : ''; el('cr_left').value = ''; el('cr_fic').value = p.fee_in_credit ? '1' : '0'; el('cr_cancel').style.display = ''; el('crh').textContent = X('Modifică pachetul', 'Edit the pack'); prev(); el('crform').scrollIntoView({ behavior: 'smooth' });
    });
    document.querySelectorAll('[data-cr-del]').forEach((a) => a.onclick = async (e) => {
      e.preventDefault(); if (!confirm(X('Șterg pachetul? Costurile încărcărilor revin la cele de dinainte.', 'Delete the pack? Charge costs go back to what they were.'))) return;
      const [ok, r] = await pinPost('/api/credits/delete', { id: a.dataset.crDel }); if (ok) render(); else say('✗ ' + (r.reason || X('Eroare', 'Error')), 'bad');
    });
    el('cr_save').onclick = async (e) => {
      e.preventDefault(); say(X('Se salvează…', 'Saving…'), 'busy');
      const [ok, r] = await pinPost('/api/credits/save', { id: editing || undefined, provider: prov(), kind: el('cr_kind').value, paid: el('cr_paid').value, amount: el('cr_amount').value, since: el('cr_since').value, expires: el('cr_exp').value, source: el('cr_source').value, note: el('cr_note').value, fee: el('cr_fee').value, fee_in_credit: el('cr_fic').value, km_kwh: el('cr_scale').value, left_now: el('cr_left').value });
      if (ok) { say('✓ ' + X('Salvat', 'Saved'), 'ok'); setTimeout(render, 600); } else say('✗ ' + (r.reason || X('Eroare', 'Error')), 'bad');
    };
    const sb = document.getElementById('cr_tsync');
    if (sb) sb.onclick = async (e) => {
      e.preventDefault(); const m = document.getElementById('cr_tmsg'); m.style.display = ''; m.className = 'toast busy'; m.textContent = X('Se citește istoricul Tesla…', 'Reading the Tesla history…');
      const [ok, r] = await pinPost('/api/credits/tesla-sync', {});
      if (ok) { m.className = 'toast ok'; m.textContent = '✓ ' + r.total + ' ' + X('sesiuni', 'sessions') + (r.new ? ' · ' + r.new + ' ' + X('noi', 'new') : ''); setTimeout(render, 800); } else { m.className = 'toast bad'; m.textContent = '✗ ' + (r.reason || X('Eroare', 'Error')); }
    };
    prev();
  },
};

/* pe o incarcare: cum s-a ajuns la costul real (listat in lista incarcarilor si pe pagina ei) */
function crNote(c) {
  const k = c && c.credit; if (!k) return '';
  const cu = esc(CU()), fee = k.fee ? ` + ${X('taxă de conectare', 'connection fee')} ${nf(k.fee, 2)} ${cu}` : '';
  if (k.voucher) return X(`Credit la ${esc(c.provider)}: ${nf(k.list, 2)} ${cu} prin credit, din care ${nf(k.voucher, 2)} ${cu} acoperiți de voucher (gratis), restul × ${nf(k.rate, 3)}${k.fee && !k.fee_in_credit ? fee : ''} = <b>${nf(k.cost, 2)} ${cu}</b> cost real.`,
    `Prepaid credit at ${esc(c.provider)}: ${nf(k.list, 2)} ${cu} through credit, ${nf(k.voucher, 2)} ${cu} of it covered by the voucher (free), the rest × ${nf(k.rate, 3)}${k.fee && !k.fee_in_credit ? fee : ''} = <b>${nf(k.cost, 2)} ${cu}</b> real cost.`);
  if (k.kind === 'km' && k.tesla) return X(`Tesla a scăzut ${nf(k.tesla.km, 0)} km de credit pentru sesiunea din ${new Date(k.tesla.start.replace(' ', 'T') + 'Z').toLocaleDateString(LOC(), { day: 'numeric', month: 'short' })} (${esc(k.tesla.site)}, ${nf(k.tesla.kwh, 1)} kWh) × ${nf(k.rate, 3)} ${cu}/km${fee} = <b>${nf(k.cost, 2)} ${cu}</b>.`, `Tesla took ${nf(k.tesla.km, 0)} credit km for the session on ${new Date(k.tesla.start.replace(' ', 'T') + 'Z').toLocaleDateString(LOC(), { day: 'numeric', month: 'short' })} (${esc(k.tesla.site)}, ${nf(k.tesla.kwh, 1)} kWh) × ${nf(k.rate, 3)} ${cu}/km${fee} = <b>${nf(k.cost, 2)} ${cu}</b>.`);
  if (k.kind === 'km') return k.km_kwh && k.kwh
    ? X(`Credit în km la ${esc(c.provider)}: ${nf(k.kwh, 1)} kWh × ${nf(k.km_kwh, 2)} km/kWh (≈ ${nf(100 / k.km_kwh, 1)} kWh/100 km) = ${nf(k.km, 0)} km de credit × ${nf(k.rate, 3)} ${cu}/km${fee} = <b>${nf(k.cost, 2)} ${cu}</b>.`, `Prepaid km at ${esc(c.provider)}: ${nf(k.kwh, 1)} kWh × ${nf(k.km_kwh, 2)} km/kWh (≈ ${nf(100 / k.km_kwh, 1)} kWh/100 km) = ${nf(k.km, 0)} credit km × ${nf(k.rate, 3)} ${cu}/km${fee} = <b>${nf(k.cost, 2)} ${cu}</b>.`)
    : X(`Credit în km la ${esc(c.provider)}: ${nf(k.km, 0)} km de autonomie × ${nf(k.rate, 3)} ${cu}/km${fee} = <b>${nf(k.cost, 2)} ${cu}</b>.`, `Prepaid km at ${esc(c.provider)}: ${nf(k.km, 0)} km of range × ${nf(k.rate, 3)} ${cu}/km${fee} = <b>${nf(k.cost, 2)} ${cu}</b>.`);
  return X(`Credit la ${esc(c.provider)}: preț de listă ${nf(k.base, 2)} ${cu}${k.fee && !sep ? fee : ''} × ${nf(k.rate, 3)}${sep ? fee : ''} = <b>${nf(k.cost, 2)} ${cu}</b> cost real.`,
           `Prepaid credit at ${esc(c.provider)}: list price ${nf(k.base, 2)} ${cu}${k.fee && !sep ? fee : ''} × ${nf(k.rate, 3)}${sep ? fee : ''} = <b>${nf(k.cost, 2)} ${cu}</b> real cost.`);
}

/* pretul real langa un tarif de statie: " → 0,45 lei/kWh cu creditul tau" (bani: tarif x platit/credit; km: lei/km x km adaugati pe kWh la aceasta incarcare) */
function crReal(c, t) {
  const k = c && c.credit_rate; if (!k || !t || !(t.price >= 0)) return '';
  const v = k.kind === 'km' ? k.per_kwh : t.price * k.rate; if (v == null) return '';
  return ' → ' + nf(v, 2) + ' ' + esc(t.cur || CU()) + '/kWh ' + X('cu creditul tău', 'with your credit');
}

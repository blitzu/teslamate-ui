/* Cost per cursa: pretul mediu al kWh din baterie la plecare (calculat in features/drivecost.py), comparat cu o masina termica. */
function driveCostChip(d) {
  if (d.cost_ev == null) return '';
  return `<span title="${esc(X('Costul kWh consumați (energia cea mai veche prima)', 'Cost of the kWh used (oldest energy first)'))}"><b>${d.cost_est ? '~' : ''}${nf(d.cost_ev, 2)}</b> ${esc(CU())}</span>`;
}
function driveCostCard(d, title) {
  if (!d || d.cost_ev == null) return '';
  const cu = esc(CU()), est = d.cost_est ? '~' : '';
  const cells = [stat(title || X('Cost cursă', 'Drive cost'), est + nf(d.cost_ev, 2), cu),
    stat(X('Preț mediu kWh consumat', 'Avg price of kWh used'), est + nf(d.price_kwh, 3), cu),
    d.eq_l100 != null ? stat(X('Echivalent termic', 'Petrol equivalent'), nf(d.eq_l100, 1), 'l/100 km') : '',
    d.cost_ice != null ? stat(X('Cu mașină termică', 'With a petrol car'), nf(d.cost_ice, 2), cu) : '',
    d.ice_saving != null ? stat(d.ice_saving >= 0 ? X('Economie', 'Saved') : X('Mai scump cu ', 'Costs more by '), nf(Math.abs(d.ice_saving), 2), cu) : ''].join('');
  const notes = [];
  if (d.cost_est) notes.push(X('~ Estimat: o parte din energie vine din încărcări fără preț (introdu costul încărcărilor).', '~ Estimated: part of the energy comes from charges without a price (enter the cost of those charges).'));
  if (d.eq_l100 == null) notes.push(X('Prețul combustibilului lipsește (Setări → Afișare).', 'Fuel price is missing (Settings → Display).'));
  else if (d.cost_ice == null) notes.push(X('Ca să vezi și costul cu mașină termică, setează consumul ei (Setări → Afișare).', 'To also see the cost with a petrol car, set its consumption (Settings → Display).'));
  return `<h2>${title || X('Cost cursă', 'Drive cost')}</h2><div class="grid g3">${cells}</div>${notes.length ? `<p class="note" style="margin:8px 2px 0">${notes.map(esc).join(' ')}</p>` : ''}`;
}

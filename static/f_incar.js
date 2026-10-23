/* Setari → Ecran pentru masina / tableta (/incar.html) */
SETTINGS_EXT.push({
  cat: 'data', order: 3,
  render() {
    const u = location.origin + '/incar.html';
    return `<h2>${X('Ecran pentru mașină / tabletă', 'In-car / tablet screen')}</h2><div class="card cfg">
      <p class="note" style="margin:0 0 8px">${X('O pagină doar pentru afișare (fără comenzi), cu litere mari, făcută pentru browserul mașinii sau o tabletă fixă: baterie, autonomie, stare, temperaturi, anvelope. Rămâne aprinsă, se întunecă noaptea și se actualizează live.', 'A display-only page (no controls) with big type, made for the car browser or a wall tablet: battery, range, state, temperatures, tyres. It stays awake, dims at night and updates live.')}</p>
      <label class="cf">${X('Adresă (deschide-o în browserul mașinii)', 'Address (open it in the car browser)')}<input readonly value="${esc(u)}"></label>
      <label class="cf">${X('Mod tabletă fixă (fără butoane)', 'Wall-tablet mode (no buttons)')}<input readonly value="${esc(u)}?kiosk=1"></label>
      <p class="note">${X('Opțiuni în adresă: ', 'URL options: ')}<code>?car=2</code> ${X('(altă mașină)', '(another car)')}, <code>?dim=on|off|auto</code> ${X('(luminozitate de noapte)', '(night dimming)')}.</p>
      <div class="links"><a href="incar.html" target="_blank" rel="noopener">${X('Deschide acum', 'Open now')}</a></div></div>`;
  },
});
document.addEventListener('click', (e) => { if (e.target.matches && e.target.matches('input[readonly]')) e.target.select(); });

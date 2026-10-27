/* Efecte de stare desenate peste poza de sus a masinii (spatiu 640 x 1401, ca poza): Sentry, incarcare (port, cablu, luminita), clima, dezghetare,
   Dog/Camp, somn / offline / actualizare. Deschiderea usilor, frunk-ului, portbagajului si geamurilor ramane in openPhoto (piese decupate din poza). */
const carAsleep = (L) => L.state === 'asleep' || L.state === 'offline';          // la fel ca "Doarme de..." din card: TeslaMate raporteaza somnul masinii ca "offline"
function carStateClass(L) {
  return carAsleep(L) ? 'st-asleep' : L.state === 'updating' ? 'st-upd' : '';
}
function carFx(L) {
  const on = (v) => v === true || v === 'true';
  const PORT = [112, 1324];                                                   // portul de incarcare = farul din spate stanga
  let g = '';
  if (on(L.sentry_mode)) {
    g += [0, 1, 2].map((i) => `<ellipse class="fxr" style="animation-delay:${i * 1.05}s" cx="320" cy="700" rx="335" ry="735"/>`).join('');
  }
  if (on(L.plugged_in)) {
    const chg = L.charging_state === 'Charging', done = L.charging_state === 'Complete', col = chg || done ? '#6fd6b8' : '#8f99a4';
    g += `<path d="M${PORT[0]} ${PORT[1]}C70 1342 -10 1372 -140 1396" fill="none" stroke="#252b32" stroke-width="15" stroke-linecap="round"/>`
      + `<path d="M${PORT[0]} ${PORT[1]}C70 1342 -10 1372 -140 1396" fill="none" stroke="#5b6671" stroke-width="3.5" stroke-linecap="round"/>`
      + (chg ? `<path class="fxd" d="M${PORT[0]} ${PORT[1]}C70 1342 -10 1372 -140 1396" fill="none" stroke="#6fd6b8" stroke-width="5" stroke-linecap="round" stroke-dasharray="14 36"/>` : '')
      + `<circle class="${chg ? 'fxg' : ''}" cx="${PORT[0]}" cy="${PORT[1]}" r="34" fill="${col}" opacity="${chg ? '.8' : done ? '.55' : '.35'}" filter="url(#fxb)"/>`
      + `<circle cx="${PORT[0]}" cy="${PORT[1]}" r="9" fill="${col}"/>`;
  } else if (on(L.charge_port_door_open)) {
    g += `<circle cx="${PORT[0]}" cy="${PORT[1]}" r="12" fill="none" stroke="#ffb15c" stroke-width="5"/>`;      // portita deschisa, fara cablu
  }
  if (on(L.is_climate_on)) {
    const cold = (L.outside_temp ?? 15) > 22 ? ' cold' : '';
    g += [650, 760, 870].map((y, i) => `<path class="fxh${cold}" style="animation-delay:${i * 0.5}s" d="M240 ${y}q40 -34 80 0t80 0"/>`).join('');
  }
  if (on(L.is_front_defroster_on)) g += [372, 404].map((y, i) => `<path class="fxh" style="animation-delay:${i * 0.4}s" d="M236 ${y}q28 -22 56 0t56 0t56 0"/>`).join('');
  if (on(L.is_rear_defroster_on)) g += [1172, 1204].map((y, i) => `<path class="fxh" style="animation-delay:${i * 0.4}s" d="M246 ${y}q26 -20 52 0t52 0t52 0"/>`).join('');
  const kp = String(L.climate_keeper_mode || '').toLowerCase();
  if (kp === 'dog' || kp === 'camp') g += `<text x="320" y="800" text-anchor="middle" font-size="120" opacity=".9">${kp === 'dog' ? '🐕' : '⛺'}</text>`;
  if (carAsleep(L)) g += `<g class="fxz" fill="#8fb4ff" font-weight="800" font-family="system-ui,sans-serif"><text x="470" y="270" font-size="70">z</text><text x="520" y="190" font-size="96">z</text><text x="570" y="90" font-size="124">z</text></g>`;
  if (L.state === 'updating') g += `<ellipse class="fxu" cx="320" cy="700" rx="330" ry="730" fill="none" stroke="#7aa8ff" stroke-width="7" stroke-dasharray="40 26"/>`;
  if (!g) return '';
  return `<svg class="fx" viewBox="0 0 640 1401" aria-hidden="true"><defs><filter id="fxb" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="16"/></filter></defs>${g}</svg>`;
}

/* ---------- Vederea 3/4 (poza reala de la configuratorul Tesla, 1920 x 1120): stari desenate peste ea ---------- */
// Geometrie masurata pe imaginile Model 3 Highland / Model Y Juniper (coordonate in poza de 1920 x 1120).
const GEO34 = {
  '3': {
    hood: '185,525 260,460 400,415 560,385 700,372 905,388 780,420 690,455 610,492 500,520 420,535 330,545',
    fl: '965,410 1330,372 1332,610 1320,640 990,660 975,500',
    rl: '1330,372 1590,330 1590,420 1500,560 1440,620 1320,640 1332,610',
    trunk: '1560,300 1690,345 1745,385 1740,410 1640,380 1560,340',
    belt: 'M1010 392L1300 372L1560 335', port: [1722, 392], ground: [955, 700, 860, 160], roof: [1050, 170], z: [1560, 150],
    wheels: { fl: [41, 78], rl: [85, 70] },
  },
  'Y': {
    hood: '118,490 180,420 320,370 480,335 560,310 700,308 890,318 780,345 690,375 610,420 520,455 400,470 280,485 170,495',
    fl: '950,335 1340,300 1340,640 1000,690 955,680',
    rl: '1340,300 1600,285 1630,320 1640,420 1560,600 1520,628 1340,640',
    trunk: '1590,215 1650,225 1780,300 1805,345 1700,320 1600,285',
    belt: 'M1000 322L1340 300L1620 270', port: [1790, 335], ground: [960, 720, 900, 140], roof: [1100, 110], z: [1560, 90],
    wheels: { fl: [39, 80], rl: [87, 68] },
  },
};
function carView34(c, L) {
  const g = GEO34[String(c.model || '').toUpperCase()];
  if (!g || !c.image34) return '';
  const on = (v) => v === true || v === 'true';
  const o = (S.opens || {})[c.id], st = openState(L, o);
  const hl = (pts) => `<polygon class="fxo" points="${pts}"/>`;
  let s = '';
  if (on(L.sentry_mode)) s += [0, 1, 2].map((i) => `<ellipse class="fxr" style="animation-delay:${i * 1.05}s" cx="${g.ground[0]}" cy="${g.ground[1]}" rx="${g.ground[2]}" ry="${g.ground[3]}"/>`).join('');
  if (st.frunk) s += hl(g.hood);
  if (st.trunk) s += hl(g.trunk);
  if (st.doorsKnown ? st.doors.fl : st.anyDoor) s += hl(g.fl);
  if (st.doorsKnown ? st.doors.rl : st.anyDoor) s += hl(g.rl);
  if (st.windows) s += `<path d="${g.belt}" fill="none" stroke="#8fd3ff" stroke-width="12" stroke-linecap="round" stroke-dasharray="6 26" class="fxd"/>`;
  if (on(L.plugged_in)) {
    const [px, py] = g.port, chg = L.charging_state === 'Charging', done = L.charging_state === 'Complete', col = chg || done ? '#6fd6b8' : '#8f99a4';
    const cab = `M${px} ${py}c60 40 110 160 150 330`;
    s += `<path d="${cab}" fill="none" stroke="#252b32" stroke-width="22" stroke-linecap="round"/><path d="${cab}" fill="none" stroke="#5b6671" stroke-width="5" stroke-linecap="round"/>`
      + (chg ? `<path class="fxd" d="${cab}" fill="none" stroke="#6fd6b8" stroke-width="8" stroke-linecap="round" stroke-dasharray="20 50"/>` : '')
      + `<circle class="${chg ? 'fxg' : ''}" cx="${px}" cy="${py}" r="50" fill="${col}" opacity="${chg ? '.8' : done ? '.55' : '.35'}" filter="url(#fxb34)"/><circle cx="${px}" cy="${py}" r="13" fill="${col}"/>`;
  } else if (on(L.charge_port_door_open)) s += `<circle cx="${g.port[0]}" cy="${g.port[1]}" r="18" fill="none" stroke="#ffb15c" stroke-width="7"/>`;
  if (on(L.is_climate_on)) {
    const cold = (L.outside_temp ?? 15) > 22 ? ' cold' : '', [rx, ry] = g.roof;
    s += [0, 1, 2].map((i) => `<path class="fxh${cold}" style="animation-delay:${i * 0.5}s;stroke-width:11" d="M${rx - 150 + i * 150} ${ry - 50}q38 -44 76 0t76 0"/>`).join('');
  }
  const kp = String(L.climate_keeper_mode || '').toLowerCase();
  if (kp === 'dog' || kp === 'camp') s += `<text x="${g.roof[0]}" y="${g.roof[1] + 150}" text-anchor="middle" font-size="150">${kp === 'dog' ? '🐕' : '⛺'}</text>`;
  if (carAsleep(L)) s += `<g class="fxz" fill="#8fb4ff" font-weight="800" font-family="system-ui,sans-serif"><text x="${g.z[0]}" y="${g.z[1] + 90}" font-size="90">z</text><text x="${g.z[0] + 70}" y="${g.z[1] + 20}" font-size="120">z</text><text x="${g.z[0] + 150}" y="${g.z[1] - 70}" font-size="150">z</text></g>`;
  if (L.state === 'updating') s += `<ellipse class="fxu" cx="${g.ground[0]}" cy="${g.ground[1]}" rx="${g.ground[2]}" ry="${g.ground[3]}" fill="none" stroke="#7aa8ff" stroke-width="9" stroke-dasharray="50 30"/>`;
  const right = st.doorsKnown && (st.doors.fr || st.doors.rr);
  const pills = ['fl', 'rl'].map((k) => { const v = L['tpms_pressure_' + k]; return `<span class="tw34 ${v != null && v < 2.5 ? 'low' : ''}" style="left:${g.wheels[k][0]}%;top:${g.wheels[k][1]}%">${v == null ? '—' : nf(v, 1)}<small>bar</small></span>`; }).join('');
  return `<div class="cw34 ${carStateClass(L)}"><img src="${esc(c.image34)}" alt=""><svg class="fx34" viewBox="0 0 1920 1120" aria-hidden="true"><defs><filter id="fxb34" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="22"/></filter></defs>${s}</svg>${pills}`
    + (right ? `<span class="fxnote">${X('Ușă pe partea dreaptă deschisă', 'Right-side door open')}</span>` : '') + '</div>';
}
function carViewSwitch(c, v34) {
  if (!c.image34) return '';
  return `<div class="cvsw" role="group"><button data-cv="top" class="${v34 ? '' : 'on'}">${X('De sus', 'Top')}</button><button data-cv="34" class="${v34 ? 'on' : ''}">3/4</button></div>`;
}

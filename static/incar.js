/* Ecran pentru browserul masinii / tableta (doar afisare, fara comenzi). ?car=ID  ?dim=auto|on|off  ?kiosk=1 (ascunde butoanele) */
(() => {
  const P = new URLSearchParams(location.search);
  const RO = ((() => { try { return localStorage.getItem('lang'); } catch (e) { return null; } })() || navigator.language || 'ro').toLowerCase().startsWith('ro');
  const X = (ro, en) => (RO ? ro : en);
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const n = (v, d = 0) => (v == null || isNaN(v) ? '—' : Number(v).toLocaleString(RO ? 'ro-RO' : 'en-GB', { maximumFractionDigits: d, minimumFractionDigits: d }));
  let S = null, car = null, es = null, dimMode = P.get('dim') || 'auto', dimOn = false;
  if (P.get('kiosk')) { $('b_dim').style.display = $('b_full').style.display = $('b_back').style.display = 'none'; }

  const live = () => (car && car.live) || {};
  const hm = (min) => (min >= 60 ? Math.floor(min / 60) + ' h ' + String(Math.round(min % 60)).padStart(2, '0') + ' min' : Math.round(min) + ' min');

  function tile(label, value, unit, sub, cls) { return `<div class="t"><i>${label}</i><b class="${cls || ''}">${value}${unit ? '<small>' + unit + '</small>' : ''}</b>${sub ? '<span>' + sub + '</span>' : ''}</div>`; }

  function draw() {
    if (!car) return;
    const l = live(), soc = l.battery_level, rng = l.est_battery_range_km ?? l.ideal_battery_range_km ?? l.rated_battery_range_km;
    $('car').textContent = car.name || l.display_name || 'Tesla';
    $('geo').textContent = l.geofence ? '📍 ' + l.geofence : '';
    const charging = l.charging_state === 'Charging', driving = l.shift_state && l.shift_state !== 'P';
    const tm = l.time_to_full_charge ? hm(l.time_to_full_charge * 60) : '';
    let status;
    if (driving) status = tile(X('Viteză', 'Speed'), n(l.speed), 'km/h', l.power != null ? n(l.power) + ' kW' : '', 'info');
    else if (charging) status = tile(X('Încarcă', 'Charging'), n(l.charger_power), 'kW', tm ? X('încă ', 'about ') + tm : '', 'ok');
    else if (l.plugged_in) status = tile(X('Conectată', 'Plugged in'), '🔌', '', l.charging_state ? esc(l.charging_state) : '', '');
    else status = tile(X('Stare', 'State'), l.state === 'asleep' ? '💤' : (l.state === 'online' ? '●' : '○'), '', esc(l.state || ''), l.state === 'online' ? 'ok' : '');
    const tp = [['fl', 'S-F', 'FL'], ['fr', 'D-F', 'FR'], ['rl', 'S-S', 'RL'], ['rr', 'D-S', 'RR']].map(([k, ro, en]) => {
      const v = l['tpms_pressure_' + k];
      return `<div><small>${X(ro, en)}</small><br><span class="${v != null && v < 2.5 ? 'bad' : ''}">${n(v, 1)}</span></div>`;
    }).join('');
    $('main').innerHTML = `<div class="t big"><i>${X('Baterie', 'Battery')}</i><b class="${soc != null && soc < 20 ? 'bad' : ''}">${n(soc)}<small>%</small></b>
        <div class="bar"><div style="width:${Math.max(0, Math.min(100, soc || 0))}%;${soc != null && soc < 20 ? 'background:var(--red)' : ''}"></div></div><span>${n(rng)} km${l.charge_limit_soc ? ' · ' + X('limită ', 'limit ') + l.charge_limit_soc + '%' : ''}</span></div>
      ${status}
      ${tile(X('Interior', 'Cabin'), n(l.inside_temp), '°C', X('exterior ', 'outside ') + n(l.outside_temp) + '°C')}
      ${tile(X('Blocată', 'Locked'), l.locked ? '🔒' : '🔓', '', l.sentry_mode ? 'Sentry' : (l.doors_open ? X('uși deschise', 'doors open') : ''), l.locked ? 'ok' : 'warn')}
      ${tile('Odometer', n(l.odometer), 'km', l.version ? 'v' + esc(l.version) : '')}
      <div class="t wide"><i>${X('Anvelope (bar)', 'Tyres (bar)')}</i><div class="tp">${tp}</div></div>`;
  }

  function tick() {
    const d = new Date();
    $('clock').textContent = d.toLocaleTimeString(RO ? 'ro-RO' : 'en-GB', { hour: '2-digit', minute: '2-digit' });
    const night = d.getHours() >= 21 || d.getHours() < 7;
    const want = dimMode === 'on' ? true : dimMode === 'off' ? false : night;
    if (want !== dimOn) { dimOn = want; document.documentElement.style.setProperty('--dim', want ? '0.45' : '1'); }
  }

  async function wake() { try { if (navigator.wakeLock) { const w = await navigator.wakeLock.request('screen'); w.addEventListener('release', () => {}); } } catch (e) { /* nu merge peste tot */ } }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) { wake(); refresh(); } });

  async function refresh() {
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (r.status === 401) { location.href = '/login'; return; }
      S = await r.json();
      const id = +P.get('car') || (S.cars[0] && S.cars[0].id);
      car = S.cars.find((c) => c.id === id) || S.cars[0];
      $('conn').style.color = 'var(--mint)';
      draw();
    } catch (e) { $('conn').style.color = 'var(--red)'; }
  }

  function stream() {
    if (es) es.close();
    es = new EventSource('/api/stream');
    es.onmessage = (e) => {
      try { const m = JSON.parse(e.data); if (car && m.car === car.id && !S.demo) { car.live = car.live || {}; car.live[m.k] = m.v; draw(); } } catch (x) { /* ignore */ }
    };
    es.onerror = () => { $('conn').style.color = 'var(--red)'; };
    es.onopen = () => { $('conn').style.color = 'var(--mint)'; };
  }

  $('b_dim').onclick = () => { dimMode = dimMode === 'auto' ? 'on' : dimMode === 'on' ? 'off' : 'auto'; $('b_dim').textContent = { auto: '☾', on: '☾ on', off: '☀' }[dimMode]; tick(); };
  $('b_full').onclick = () => { const e = document.documentElement; if (document.fullscreenElement) document.exitFullscreen(); else if (e.requestFullscreen) e.requestFullscreen().catch(() => {}); };
  tick(); setInterval(tick, 15000);
  refresh().then(() => { stream(); setInterval(refresh, 60000); wake(); });
})();

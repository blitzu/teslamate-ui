/* Liste Curse / Incarcari: perioada (inclusiv interval ales), tag, marimea paginii. Starea se tine in browser. */
const LFS = (() => { try { return JSON.parse(localStorage.getItem('lf') || '{}'); } catch (e) { return {}; } })();
const lfGet = (k) => Object.assign({ p: k === 'charges' ? 90 : 'all', from: '', to: '', tag: '', n: 50 }, LFS[k] || {});
const lfSet = (k, v) => { LFS[k] = Object.assign(lfGet(k), v); try { localStorage.setItem('lf', JSON.stringify(LFS)); } catch (e) { /* ignore */ } };
let LF_TAGS = [];
async function lfLoadTags() { try { LF_TAGS = (await api('/api/tags')).tags || []; } catch (e) { LF_TAGS = []; } }

/* [de la, pana la) ca obiecte Date, sau null = nelimitat */
function lfRange(k) {
  const f = lfGet(k), now = new Date(), y = now.getFullYear();
  if (typeof f.p === 'number') return [new Date(+now - f.p * 864e5), null];
  if (f.p === 'ytd') return [new Date(y, 0, 1), null];
  if (f.p === 'ly') return [new Date(y - 1, 0, 1), new Date(y, 0, 1)];
  if (f.p === 'custom') return [f.from ? new Date(f.from + 'T00:00:00') : null, f.to ? new Date(+new Date(f.to + 'T00:00:00') + 864e5) : null];
  return [null, null];
}
function lfQuery(k) {
  const [a, b] = lfRange(k), f = lfGet(k);
  return (a && !isNaN(a) ? '&from=' + encodeURIComponent(a.toISOString()) : '') + (b && !isNaN(b) ? '&to=' + encodeURIComponent(b.toISOString()) : '') + (f.tag ? '&tag=' + encodeURIComponent(f.tag) : '');
}
function lfBar(k) {
  const f = lfGet(k), P = [['all', X('Tot', 'All')], [30, X('30 zile', '30 days')], [90, X('90 zile', '90 days')], ['ytd', X('Anul acesta', 'This year')], ['ly', X('Anul trecut', 'Last year')], ['custom', X('Interval', 'Range')]];
  return `<div class="seg lfseg" style="margin-top:12px">${P.map(([v, l]) => `<button data-lfp="${v}" class="${String(f.p) === String(v) ? 'on' : ''}">${l}</button>`).join('')}</div>
    ${f.p === 'custom' ? `<div class="addf" style="margin-top:8px"><label>${X('De la', 'From')}<input type="date" id="lf_from" value="${esc(f.from)}"></label><label>${X('Până la', 'To')}<input type="date" id="lf_to" value="${esc(f.to)}"></label></div>` : ''}
    <div class="lfrow">${LF_TAGS.length ? `<label>${X('Tag', 'Tag')}<select id="lf_tag"><option value="">${X('toate', 'all')}</option>${LF_TAGS.map((t) => `<option value="${esc(t.name)}" ${t.name === f.tag ? 'selected' : ''}>${esc(t.name)} (${t.n})</option>`).join('')}</select></label>` : ''}
    <label>${X('Pe pagină', 'Per page')}<select id="lf_n">${[25, 50, 100, 200].map((n) => `<option ${n === f.n ? 'selected' : ''}>${n}</option>`).join('')}</select></label></div>`;
}
function lfBind(k, redraw) {
  document.querySelectorAll('[data-lfp]').forEach((b) => b.onclick = () => { const v = b.dataset.lfp; lfSet(k, { p: v === 'all' || v === 'ytd' || v === 'ly' || v === 'custom' ? v : +v, n: 50 }); redraw(); });
  const on = (id, fn) => { const el = document.getElementById(id); if (el) el.onchange = () => { fn(el.value); redraw(); }; };
  on('lf_from', (v) => lfSet(k, { from: v, n: 50 }));
  on('lf_to', (v) => lfSet(k, { to: v, n: 50 }));
  on('lf_tag', (v) => lfSet(k, { tag: v, n: 50 }));
  on('lf_n', (v) => lfSet(k, { n: +v }));
  document.querySelectorAll('[data-lfmore]').forEach((b) => b.onclick = (e) => { e.preventDefault(); window.__keep = true; setTimeout(() => { window.__keep = false; }, 2500); lfSet(k, { n: lfGet(k).n + (+b.dataset.lfmore || 50) }); redraw(); });
}

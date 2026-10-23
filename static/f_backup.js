/* Setari → Backup date TeslaMate (copie locala SQLite, sincronizata la 10 minute) */
SETTINGS_EXT.push({
  async render() {
    let st; try { st = await api('/api/backup/status'); } catch (e) { return ''; }
    const last = st.last, mb = (b) => (b / 1048576).toFixed(1) + ' MB';
    const rows = last && last.tables ? Object.entries(last.tables).map(([t, r]) => `<tr><td>${esc(t)}</td><td>${nf(r.rows)}</td><td>${r.src_max_id - r.max_id > 0 ? '<b style="color:#ffb3b3">−' + nf(r.src_max_id - r.max_id) + '</b>' : '✓'}</td></tr>`).join('') : '';
    return `<h2>${X('Backup date TeslaMate', 'TeslaMate data backup')}</h2><div class="card cfg">
      <p class="note" style="margin:0 0 8px">${X('Aplicația păstrează o copie locală a datelor din TeslaMate (curse, poziții, încărcări, stări, update-uri). Se sincronizează singură la 10 minute, nu șterge nimic din copie și face zilnic un instantaneu (ultimele 7). Dacă baza TeslaMate se pierde, datele se refac cu <code>tools/restore_backup.py</code>.', 'The app keeps a local copy of the TeslaMate data (drives, positions, charges, states, updates). It syncs by itself every 10 minutes, never deletes anything from the copy and takes a daily snapshot (last 7). If the TeslaMate database is lost the data can be restored with <code>tools/restore_backup.py</code>.')}</p>
      <div class="grid">${stat(X('Ultima sincronizare', 'Last sync'), last ? esc(new Date(last.ts * 1000).toLocaleString(LOC())) : '—')}${stat(X('Mărime copie', 'Copy size'), mb(st.size))}</div>
      ${last && last.error ? `<p class="note" style="color:#ffb3b3">✗ ${esc(last.error)}</p>` : ''}
      ${rows ? `<table class="bktab"><tr><th>${X('Tabel', 'Table')}</th><th>${X('Rânduri în copie', 'Rows in copy')}</th><th>${X('Rămas în urmă', 'Behind')}</th></tr>${rows}</table>` : ''}
      <p class="note">${X('Instantanee', 'Snapshots')}: ${st.snapshots.length ? st.snapshots.map((x) => esc(x.replace(/^teslamate-|\.db$/g, ''))).join(', ') : '—'}</p>
      <div class="links"><a href="#" data-bk="sync">${X('Sincronizează acum', 'Sync now')}</a><a href="#" data-bk="teslamate">${X('Descarcă copia TeslaMate (.db)', 'Download TeslaMate copy (.db)')}</a><a href="#" data-bk="app">${X('Descarcă baza proprie (.db)', 'Download the app database (.db)')}</a></div>
      <div class="toast" aria-live="polite" id="bkmsg" style="display:none"></div></div>`;
  },
  after() {
    const say = (t, cls) => { const m = document.getElementById('bkmsg'); if (m) { m.style.display = ''; m.textContent = t; m.className = 'toast ' + (cls || ''); } };
    document.querySelectorAll('[data-bk]').forEach((b) => b.onclick = async (e) => {
      e.preventDefault();
      const what = b.dataset.bk, pin = await getPin(); if (!pin) return;
      say(X('Se lucrează…', 'Working…'), 'busy');
      try {
        const r = await fetch(what === 'sync' ? '/api/backup/sync' : '/api/backup/download', { method: 'POST', headers: { 'X-Pin': pin, 'Content-Type': 'application/json' }, body: JSON.stringify({ what }) });
        if (r.status === 403) pinClear();
        if (what === 'sync') { const j = await r.json(); say(j.ok ? '✓ ' + X('Sincronizarea a pornit; reîncarcă pagina în câteva secunde.', 'Sync started; reload the page in a few seconds.') : '✗ ' + (j.reason || X('Eroare', 'Error')), j.ok ? 'ok' : 'bad'); return; }
        if (!r.ok) { const j = await r.json().catch(() => ({})); say('✗ ' + (j.reason || r.status), 'bad'); return; }
        const blob = await r.blob(), a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = what === 'app' ? 'tesla-ui-app.db' : 'teslamate-backup.db'; document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000); say('✓ ' + X('Descărcat', 'Downloaded'), 'ok');
      } catch (err) { say('✗ ' + err.message, 'bad'); }
    });
  },
});

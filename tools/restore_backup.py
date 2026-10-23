#!/usr/bin/env python3
"""Reface datele TeslaMate dintr-o copie de siguranta a aplicatiei (teslamate_backup.db, SQLite) intr-o baza Postgres TeslaMate.

  python3 tools/restore_backup.py /cale/teslamate_backup.db --dsn "postgresql://teslamate:PAROLA@localhost:5432/teslamate" [--dry-run]

* Porneste TeslaMate o data pe baza noua (ca sa-si creeze schema), apoi OPRESTE-l si ruleaza scriptul.
* Insereaza cu `ON CONFLICT (id) DO NOTHING`: randurile care exista deja nu sunt atinse, deci scriptul se poate rula si peste o baza partiala.
* Cere psycopg2 (pip install psycopg2-binary). Cheile straine se opresc pe durata restaurarii (`session_replication_role = replica`), ceea ce cere un utilizator
  superuser (utilizatorul din imaginea oficiala Postgres a TeslaMate este). Dupa inserare, secventele id se reseteaza.
* `tokens` (token-urile contului Tesla) nu se copiaza niciodata: dupa restaurare reconectezi contul in TeslaMate.
"""
import argparse
import json
import sqlite3
import sys

ORDER = ['cars', 'addresses', 'geofences', 'drives', 'positions', 'charging_processes', 'charges', 'states', 'updates', 'settings']


def cast(v, pgtype):
    if v is None:
        return None
    if pgtype == 'boolean':
        return bool(v)
    if pgtype in ('integer', 'bigint', 'smallint'):
        return int(v)
    if pgtype in ('numeric', 'double precision', 'real'):
        return float(v)
    if pgtype == 'bytea' and isinstance(v, str):
        return bytes.fromhex(v)
    return v


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('backup')
    ap.add_argument('--dsn', required=True)
    ap.add_argument('--tables', help='lista separata prin virgula (implicit toate)')
    ap.add_argument('--dry-run', action='store_true', help='doar numara, nu scrie nimic')
    a = ap.parse_args()
    import psycopg2
    import psycopg2.extras
    src = sqlite3.connect('file:%s?mode=ro' % a.backup, uri=True)
    src.row_factory = sqlite3.Row
    pg = psycopg2.connect(a.dsn)
    cur = pg.cursor()
    try:
        cur.execute("set session_replication_role = replica")
    except Exception as e:  # noqa
        print('ATENTIE: nu pot opri cheile straine (%s). Restaurarea poate esua pe dependente.' % e)
        pg.rollback()
    want = [t for t in ORDER if not a.tables or t in a.tables.split(',')]
    total = 0
    for t in want:
        meta = {r['col']: r['pgtype'] for r in src.execute('select col, pgtype from _meta where tbl=?', (t,))}
        if not meta:
            print('%-20s lipseste din copie' % t)
            continue
        cur.execute("select column_name from information_schema.columns where table_schema='public' and table_name=%s", (t,))
        target = {r[0] for r in cur.fetchall()}
        cols = [c for c in meta if c in target]
        if not cols:
            print('%-20s tabelul nu exista in baza tinta (porneste TeslaMate o data pe ea)' % t)
            continue
        n = src.execute('select count(*) from "%s"' % t).fetchone()[0]
        if a.dry_run:
            print('%-20s %9d randuri (%d coloane)' % (t, n, len(cols)))
            continue
        sql = 'insert into "%s" (%s) values %%s on conflict (id) do nothing' % (t, ','.join('"%s"' % c for c in cols))
        batch, done = [], 0
        for row in src.execute('select %s from "%s" order by id' % (','.join('"%s"' % c for c in cols), t)):
            batch.append([cast(row[c], meta[c]) for c in cols])
            if len(batch) >= 2000:
                psycopg2.extras.execute_values(cur, sql, batch, page_size=500)
                done += len(batch)
                batch = []
        if batch:
            psycopg2.extras.execute_values(cur, sql, batch, page_size=500)
            done += len(batch)
        cur.execute("select setval(pg_get_serial_sequence('\"%s\"', 'id'), greatest(coalesce((select max(id) from \"%s\"), 1), 1))" % (t, t))
        pg.commit()
        total += done
        print('%-20s %9d randuri procesate' % (t, done))
    print('Gata.' if not a.dry_run else 'Simulare terminata (nu s-a scris nimic).')
    return 0


if __name__ == '__main__':
    sys.exit(main())

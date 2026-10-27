"""Copie de siguranta locala a datelor din TeslaMate, intr-un fisier SQLite propriu (DATA_DIR/teslamate_backup.db).
* se sincronizeaza incremental la fiecare 10 minute (tabelele mari, "append-only", doar randurile noi; cele mici, complet);
* NU sterge nimic din copie: daca randuri dispar din TeslaMate (accident, bug, baza pierduta), raman aici;
* schema se adapteaza singura (coloane noi din TeslaMate sunt adaugate);
* o data pe zi se face un instantaneu consistent in DATA_DIR/backups/ (se pastreaza 7);
* `tools/restore_backup.py` reface datele intr-o baza TeslaMate noua.
Nu copiem `tokens` (token-urile Tesla) si nici tabelele de import/migrari."""
import datetime as dt
import decimal
import json
import os
import re
import sqlite3
import threading
import time

TABLES = ['car_settings', 'cars', 'addresses', 'geofences', 'drives', 'positions', 'charging_processes', 'charges', 'states', 'updates', 'settings']
APPEND = {'positions', 'charges'}               # randuri imutabile: se copiaza doar ce are id mai mare decat ultimul copiat
SYNC_EVERY = 600
KEEP_SNAPSHOTS = 7
BATCH = 5000


def sql_type(pgtype):
    if pgtype in ('integer', 'bigint', 'smallint', 'boolean'):
        return 'INTEGER'
    if pgtype in ('numeric', 'double precision', 'real'):
        return 'REAL'
    return 'TEXT'


def conv(v):
    """Valoare Postgres -> valoare SQLite (None, int, float, str)."""
    if v is None or isinstance(v, (int, float, str)):
        return int(v) if isinstance(v, bool) else v
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return v.isoformat()
    if isinstance(v, (dict, list)):
        return json.dumps(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).hex()
    return str(v)


class PgSource:
    """Sursa reala: Postgres-ul TeslaMate. Citeste cu un cursor pe server, in loturi."""
    def __init__(self, S):
        self.S = S
        self.cn = None

    def __enter__(self):
        import psycopg2
        self.S.DB_SEM.acquire()
        try:
            self.cn = psycopg2.connect(options='-c statement_timeout=600000 -c default_transaction_read_only=on', **self.S.DB)
        except Exception:
            self.S.DB_SEM.release()
            raise
        return self

    def __exit__(self, *a):
        try:
            self.cn.close()
        finally:
            self.S.DB_SEM.release()

    def columns(self, table):
        with self.cn.cursor() as cur:
            cur.execute("select column_name, data_type from information_schema.columns where table_schema='public' and table_name=%s order by ordinal_position", (table,))
            return cur.fetchall()

    def max_id(self, table):
        with self.cn.cursor() as cur:
            cur.execute('select coalesce(max(id), 0) from "%s"' % table)
            return cur.fetchone()[0]

    def count(self, table):
        with self.cn.cursor() as cur:
            cur.execute('select count(*) from "%s"' % table)
            return cur.fetchone()[0]

    def rows(self, table, cols, after_id=None):
        sel = ', '.join('"%s"' % c for c in cols)
        sql = 'select %s from "%s"%s order by id' % (sel, table, ' where id > %s' if after_id is not None else '')
        with self.cn.cursor(name='bk_' + table) as cur:
            cur.itersize = BATCH
            cur.execute(sql, (after_id,) if after_id is not None else ())
            while True:
                batch = cur.fetchmany(BATCH)
                if not batch:
                    return
                yield batch


class Backup:
    def __init__(self, S, path=None, snapdir=None):
        from .store import Store
        self.S = S
        self.path = path or (S.DATA_DIR + '/teslamate_backup.db')
        self.snapdir = snapdir or (S.DATA_DIR + '/backups')
        self.db = Store(self.path)
        self.lock = threading.Lock()
        self.running = False
        self.db.run('create table if not exists _meta (tbl text not null, col text not null, pgtype text not null, primary key (tbl, col))')
        self.db.run('create table if not exists _status (k text primary key, v text)')

    # ---------------------------------------------------------------- schema
    def ensure_table(self, table, cols):
        have = {r['name'] for r in self.db.rows('pragma table_info("%s")' % table)}
        if not have:
            defs = ', '.join('"%s" %s%s' % (c, sql_type(t), ' primary key' if c == 'id' else '') for c, t in cols)
            self.db.run('create table "%s" (%s)' % (table, defs))
        else:
            for c, t in cols:
                if c not in have:
                    self.db.run('alter table "%s" add column "%s" %s' % (table, c, sql_type(t)))
        for c, t in cols:
            self.db.run('insert into _meta(tbl, col, pgtype) values(?,?,?) on conflict(tbl, col) do update set pgtype=excluded.pgtype', (table, c, t))

    def sync_table(self, src, table):
        cols = src.columns(table)
        if not cols or 'id' not in [c for c, _ in cols]:
            return None
        self.ensure_table(table, cols)
        names = [c for c, _ in cols]
        last = self.db.one('select coalesce(max(id), 0) m from "%s"' % table)['m']
        ph = ','.join('?' * len(names))
        sql = 'insert %s into "%s" (%s) values (%s)' % ('or ignore' if table in APPEND else 'or replace', table, ','.join('"%s"' % n for n in names), ph)
        new = 0
        for batch in src.rows(table, names, last if table in APPEND else None):
            with self.db.tx() as c:
                c.executemany(sql, [[conv(v) for v in row] for row in batch])
            new += len(batch)
        have = self.db.one('select count(*) n, coalesce(max(id), 0) m from "%s"' % table)
        return dict(new=new, rows=have['n'], max_id=have['m'], src_max_id=src.max_id(table))

    # ---------------------------------------------------------------- sincronizare + instantanee
    def sync(self, src=None):
        if not self.lock.acquire(blocking=False):
            return dict(ok=False, reason='o sincronizare ruleaza deja')
        self.running = True
        t0 = time.time()
        res, err = {}, ''
        try:
            own = src is None
            if own:
                src = PgSource(self.S)
                src.__enter__()
            try:
                for t in TABLES:
                    try:
                        r = self.sync_table(src, t)
                        if r is not None:
                            res[t] = r
                    except Exception as e:  # noqa
                        err = (err + '; ' if err else '') + '%s: %s' % (t, e)
                        self.S.log('backup %s: %s' % (t, e))
                        try:
                            if getattr(src, 'cn', None) is not None:
                                src.cn.rollback()                      # o tranzactie esuata ar strica si tabelele urmatoare
                        except Exception:  # noqa
                            pass
            finally:
                if own:
                    src.__exit__()
        except Exception as e:  # noqa
            err = str(e)[:200]
            self.S.log('backup: %s' % e)
        finally:
            self.running = False
            self.lock.release()
        st = dict(ts=time.time(), seconds=round(time.time() - t0, 1), tables=res, error=err)
        self.db.run('insert into _status(k, v) values(?, ?) on conflict(k) do update set v=excluded.v', ('last', json.dumps(st)))
        return dict(ok=not err, **st)

    def snapshot(self):
        """Instantaneu consistent al copiei (API-ul de backup SQLite), pastrat KEEP_SNAPSHOTS zile."""
        os.makedirs(self.snapdir, exist_ok=True)
        name = os.path.join(self.snapdir, 'teslamate-%s.db' % dt.date.today().strftime('%Y%m%d'))
        if os.path.exists(name):
            return name
        part = name + '.part'                                           # se scrie intr-un fisier partial: o cadere la mijloc nu lasa un instantaneu "gata" dar trunchiat
        os.close(os.open(part, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600))
        with self.db.lock:
            dst = sqlite3.connect(part)
            try:
                self.db.conn().backup(dst)
            finally:
                dst.close()
        os.replace(part, name)
        snaps = sorted(f for f in os.listdir(self.snapdir) if re.fullmatch(r'teslamate-\d{8}\.db', f))
        for f in snaps[:-KEEP_SNAPSHOTS]:
            try:
                os.remove(os.path.join(self.snapdir, f))
            except OSError:
                pass
        return name

    def status(self):
        row = self.db.one("select v from _status where k='last'")
        last = json.loads(row['v']) if row else None
        snaps = sorted(f for f in os.listdir(self.snapdir) if not f.endswith('.part')) if os.path.isdir(self.snapdir) else []
        size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
        return dict(last=last, running=self.running, size=size, snapshots=snaps, every=SYNC_EVERY)

    def copy_for_download(self):
        """Copie consistenta intr-un fisier temporar (fisierul viu poate fi modificat in timp ce se descarca)."""
        tmp = self.path + '.dl-%d-%s' % (time.time_ns(), os.urandom(3).hex())
        os.close(os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))      # contine toata istoria locatiilor: doar proprietarul o citeste
        with self.db.lock:
            dst = sqlite3.connect(tmp)
            try:
                self.db.conn().backup(dst)
            finally:
                dst.close()
        return tmp


def init(S):
    B = Backup(S)
    S.BACKUP = B

    def loop():
        time.sleep(45)
        last_snap = ''
        while True:
            if S.has_cars():
                B.sync()
                today = dt.date.today().isoformat()
                if today != last_snap and dt.datetime.now().hour >= 3:
                    try:
                        B.snapshot()
                        last_snap = today
                    except Exception as e:  # noqa
                        S.log('backup instantaneu: %s' % e)
            time.sleep(SYNC_EVERY)

    S.BG_TASKS.append(loop)

    @S.route('GET', '/api/backup/status', role='admin')
    def status(h, a):
        return B.status()

    @S.route('POST', '/api/backup/sync', pin=True, role='admin')
    def sync_now(h, body):
        if B.running:
            return dict(ok=False, reason='O sincronizare rulează deja.')
        threading.Thread(target=B.sync, daemon=True).start()
        return dict(ok=True, started=True)

    @S.route('POST', '/api/backup/download', pin=True, role='admin')
    def download(h, body):
        what = body.get('what')
        if what == 'teslamate':
            path, name = B.copy_for_download(), 'teslamate-backup.db'
        elif what == 'app':
            tmp = S.DATA_DIR + '/app.db.dl-%d-%s' % (time.time_ns(), os.urandom(3).hex())
            os.close(os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            with S.OWN.lock:
                dst = sqlite3.connect(tmp)
                try:
                    S.OWN.conn().backup(dst)
                finally:
                    dst.close()
            path, name = tmp, 'tesla-ui-app.db'
        else:
            raise ValueError('what = teslamate | app')
        S.log('audit: descarcare backup %s rol=%s ip=%s' % (what, h.role, h.client_ip()))
        return S.Raw(path=path, ctype='application/octet-stream', headers={'Content-Disposition': 'attachment; filename="%s"' % name}, delete=True)

"""Baza de date proprie a aplicatiei (SQLite din biblioteca standard), in DATA_DIR/app.db.
Aici stau datele care NU apartin TeslaMate (intretinere, anvelope, evenimente, rapoarte, partajari...). Schema TeslaMate nu e o interfata stabila,
deci tot ce adaugam noi sta separat. Fiecare modul isi declara tabelele prin `migrate(nume, [instructiuni...])` (aplicate o singura data, in ordine)."""
import contextlib
import json
import os
import sqlite3
import threading
import time


class Store:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self._c = None

    def conn(self):
        if self._c is None:
            os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
            c = sqlite3.connect(self.path, check_same_thread=False, timeout=30, isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute('pragma journal_mode=wal')
            c.execute('pragma synchronous=normal')
            c.execute('pragma foreign_keys=on')
            self._c = c
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        return self._c

    def run(self, sql, args=()):
        with self.lock:
            return self.conn().execute(sql, args)

    def many(self, sql, rows):
        with self.lock:
            return self.conn().executemany(sql, rows)

    def rows(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.conn().execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        r = self.rows(sql, args)
        return r[0] if r else None

    @contextlib.contextmanager
    def tx(self):
        with self.lock:
            c = self.conn()
            c.execute('begin immediate')
            try:
                yield c
                c.execute('commit')
            except Exception:
                c.execute('rollback')
                raise

    def migrate(self, name, steps):
        """Aplica instructiunile din `steps` care nu au rulat inca pentru modulul `name` (versiunea = numarul de pasi aplicati)."""
        with self.lock:
            c = self.conn()
            c.execute('create table if not exists _schema (name text primary key, v integer not null)')
            row = c.execute('select v from _schema where name=?', (name,)).fetchone()
            done = row['v'] if row else 0
            for i in range(done, len(steps)):
                with self.tx() as t:
                    t.execute(steps[i])
                    t.execute('insert into _schema(name, v) values(?, ?) on conflict(name) do update set v=excluded.v', (name, i + 1))

    # --- chei/valori JSON (setari mici ale modulelor)
    def kv_get(self, k, default=None):
        self.run('create table if not exists kv (k text primary key, v text not null, ts real)')
        r = self.one('select v from kv where k=?', (k,))
        if r is None:
            return default
        try:
            return json.loads(r['v'])
        except ValueError:
            return default

    def kv_set(self, k, v):
        self.run('create table if not exists kv (k text primary key, v text not null, ts real)')
        self.run('insert into kv(k, v, ts) values(?, ?, ?) on conflict(k) do update set v=excluded.v, ts=excluded.ts', (k, json.dumps(v), time.time()))

"""Teste pentru partile care au nevoie de baza de date sau de psycopg2 (inlocuite aici cu variante in memorie): raportul paznicului de somn,
analiza PZU si unealta tools/restore_backup.py."""
import datetime as dt
import os
import sqlite3
import sys
import tempfile
import time
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tesla-ui-extra-'))
os.environ.setdefault('DEMO_ONLY', '1')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as S  # noqa: E402
from isolation import Isolated  # noqa: E402
from features import backup as BK  # noqa: E402

utc = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).replace(tzinfo=None).isoformat()


class SleepGuardReportTests(Isolated):
    CAR = 77

    def setUp(self):
        S.OWN.run('delete from events where car=?', (self.CAR,))
        S.OWN.run('delete from cmd_log where car=?', (self.CAR,))
        self.now = time.time()

    def tearDown(self):
        S.OWN.run('delete from events where car=?', (self.CAR,))
        S.OWN.run('delete from cmd_log where car=?', (self.CAR,))

    def rows(self, online, busy=()):
        def q(sql, params=()):
            if 'from states' in sql:
                return [dict(s='online', start_date=utc(a), end_date=utc(b)) for a, b in online]
            if 'from drives' in sql:
                return [dict(a=utc(a), b=utc(b)) for a, b in busy]
            return []                                                                 # updates
        S.q = q

    def test_sentry_started_before_the_window_still_explains_the_whole_stay(self):
        n = self.now
        self.rows([(n - 5 * 3600, n - 2 * 3600)])
        S.OWN.run('insert into events(ts, car, key, old, new) values(?,?,?,?,?)', (n - 5 * 86400, self.CAR, 'sentry_mode', 'False', 'True'))      # pornit acum 5 zile, fara alte tranzitii
        rep = S.SLEEPGUARD(self.CAR, 2)
        reasons = {}
        for d in rep.values():
            for k, v in d['reasons'].items():
                reasons[k] = reasons.get(k, 0) + v
        self.assertEqual(reasons.get('sentry'), 180)
        self.assertNotIn('necunoscut', reasons)
        self.assertEqual(sum(d['unexplained'] for d in rep.values()), 0)

    def test_without_any_reason_the_time_is_unexplained_and_driving_is_excluded(self):
        n = self.now
        self.rows([(n - 6 * 3600, n - 2 * 3600)], busy=[(n - 6 * 3600, n - 4 * 3600)])               # prima jumatate: conducea
        rep = S.SLEEPGUARD(self.CAR, 2)
        self.assertGreater(sum(d['unexplained'] for d in rep.values()), 100)                         # ~ 2 h - 5 min de rezerva
        self.assertLess(sum(d['total'] for d in rep.values()), 130)

    def test_command_explains_the_following_minutes(self):
        n = self.now
        self.rows([(n - 3 * 3600, n - 2 * 3600)])
        S.OWN.run('insert into cmd_log(ts, car, name, actor) values(?,?,?,?)', (n - 3 * 3600 + 30, self.CAR, 'lock', 'user:admin'))
        rep = S.SLEEPGUARD(self.CAR, 2)
        by = {}
        for d in rep.values():
            for k, v in d['reasons'].items():
                by[k] = by.get(k, 0) + v
        self.assertGreaterEqual(by.get('comanda', 0), 10)                                           # ~12 min dupa comanda


class PzuAnalyzeTests(Isolated):
    def test_cost_optimal_night_and_offline_fallback(self):
        S.CURRENCY = '€'
        day = (dt.datetime.utcnow() - dt.timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
        t0 = int(day.replace(hour=22, tzinfo=dt.timezone.utc).timestamp())               # sesiune 22:00-00:00 UTC, 7.2 kW = 14.4 kWh
        S.LOCAL_TZ = 'UTC'
        S.OWN.run('delete from pzu_prices')
        slots = range(int(t0 - 86400 // 2 // 900 * 900), t0 + 12 * 3600, 900)
        S.OWN.many('insert into pzu_prices(ts, eur_mwh) values(?,?)', [(s, 100.0 if t0 <= s < t0 + 7200 else (50.0 if t0 + 4 * 3600 <= s < t0 + 7 * 3600 else 200.0)) for s in slots])

        def boom(url, timeout=20):
            raise OSError('fara retea')
        S._get_text = boom                                                                  # preturile azi nu se pot descarca: se foloseste cache-ul
        S.cget = lambda *a, **k: ''
        row = dict(id=501, start_date=utc(t0), end_date=utc(t0 + 7200), dc=False, power_max=7, name='Acasă', tariff=0.5, cost=None)
        S._charges_rows = lambda *a, **k: [row]
        S.q = lambda sql, params=(): [dict(date=utc(t0 + i * 300), charger_power=7.2 if i < 24 else 0) for i in range(25)]
        out = S.PZU(1, 30)
        self.assertEqual(len(out['sessions']), 1)
        s = out['sessions'][0]
        self.assertAlmostEqual(s['kwh'], 14.4, places=1)
        self.assertAlmostEqual(s['pzu'], 1.44, places=2)                                    # 14.4 kWh x 0.100 EUR
        self.assertAlmostEqual(s['optimal'], 0.87, places=2)                                # 8 sferturi de 1.8 kWh la 0.050 + TVA 21% (setarea implicita)
        self.assertAlmostEqual(s['pzu_total'], 1.74, places=2)
        self.assertEqual(s['covered'], 1.0)
        self.assertAlmostEqual(s['fixed'], 7.2, places=1)                                   # tariful din geofence 0.5 / kWh
        self.assertEqual(out['months'][0]['n'], 1)

    def test_no_home_session_gives_a_note(self):
        S.CURRENCY = '€'
        S.cget = lambda *a, **k: ''
        S._charges_rows = lambda *a, **k: [dict(id=1, start_date=utc(time.time() - 3600), end_date=None, dc=True, power_max=120, name='Supercharger', tariff=None, cost=None)]
        out = S.PZU(1, 30)
        self.assertEqual(out['sessions'], [])
        self.assertTrue(out['note'])

    def test_unconvertible_currency_is_rejected(self):
        S.CURRENCY = 'XYZ'
        with self.assertRaises(ValueError):
            S.PZU(1, 30)


class FakeCursor:
    def __init__(self, log, target_cols):
        self.log, self.target_cols = log, target_cols
        self.res = []

    def execute(self, sql, params=None):
        self.log.append(('exec', sql, params))
        if 'information_schema.columns' in sql:
            self.res = [(c,) for c in self.target_cols.get(params[0], [])]

    def fetchall(self):
        return self.res

    def fetchone(self):
        return (1,)


class RestoreBackupTests(Isolated):
    def make_backup(self):
        path = os.path.join(tempfile.mkdtemp(), 'bk.db')
        con = sqlite3.connect(path)
        con.execute('create table _meta (tbl text, col text, pgtype text)')
        for tbl, cols in (('car_settings', [('id', 'integer'), ('suspend_min', 'integer')]), ('drives', [('id', 'integer'), ('distance', 'double precision'), ('ok', 'boolean')]),
                          ('settings', [('id', 'integer'), ('language', 'text')])):
            con.execute('create table "%s" (%s)' % (tbl, ', '.join('"%s"' % c for c, _ in cols)))
            con.executemany('insert into _meta values(?,?,?)', [(tbl, c, t) for c, t in cols])
        con.execute('insert into car_settings values(1, 21)')
        con.execute('insert into drives values(1, 12.5, 1)')
        con.execute('insert into drives values(2, 7.0, 0)')
        con.execute("insert into settings values(1, 'ro')")
        con.commit()
        con.close()
        return path

    def run_tool(self, argv, env=None):
        sys.path.insert(0, os.path.join(ROOT, 'tools'))
        import restore_backup as RB
        log, batches, dsns = [], [], []
        target = {'car_settings': ['id', 'suspend_min'], 'drives': ['id', 'distance', 'ok', 'extra_col_nou'], 'settings': ['id', 'language']}
        conn = types.SimpleNamespace(cursor=lambda: FakeCursor(log, target), commit=lambda: log.append(('commit',)), rollback=lambda: log.append(('rollback',)))
        pg = types.ModuleType('psycopg2')
        pg.connect = lambda dsn: (dsns.append(dsn) or conn)
        ex = types.ModuleType('psycopg2.extras')
        ex.execute_values = lambda cur, sql, rows, page_size=100: batches.append((sql, [list(r) for r in rows]))
        pg.extras = ex
        old_mods = {k: sys.modules.get(k) for k in ('psycopg2', 'psycopg2.extras')}
        old_argv, old_env = sys.argv, dict(os.environ)
        sys.modules.update({'psycopg2': pg, 'psycopg2.extras': ex})
        sys.argv = ['restore_backup.py'] + argv
        os.environ.pop('TESLAMATE_DSN', None)
        os.environ.update(env or {})
        try:
            code = RB.main()
        finally:
            sys.argv = old_argv
            os.environ.clear()
            os.environ.update(old_env)
            for k, v in old_mods.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        return code, log, batches, dsns

    def test_restores_in_order_with_conflict_rules_and_casts(self):
        code, log, batches, dsns = self.run_tool([self.make_backup()], env=dict(TESLAMATE_DSN='postgresql://u:secret@h/db'))
        self.assertEqual(code, 0)
        self.assertEqual(dsns, ['postgresql://u:secret@h/db'])                                     # parola din mediu, nu din linia de comanda
        self.assertIn(('exec', 'set session_replication_role = replica', None), log)
        order = [b[0].split('"')[1] for b in batches]
        self.assertEqual(order, ['car_settings', 'drives', 'settings'])                           # ORDER: car_settings inaintea masinilor / cursele inaintea setarilor
        sql = {b[0].split('"')[1]: b[0] for b in batches}
        self.assertIn('do update set', sql['car_settings'])                                        # setarile existente dupa prima pornire se suprascriu
        self.assertIn('do update set', sql['settings'])
        self.assertIn('do nothing', sql['drives'])                                                 # restul nu ating randurile existente
        self.assertNotIn('extra_col_nou', sql['drives'])                                           # coloana inexistenta in copie nu se cere
        rows = [b[1] for b in batches if '"drives"' in b[0]][0]
        self.assertEqual(rows, [[1, 12.5, True], [2, 7.0, False]])                                 # boolean convertit din 0/1

    def test_dry_run_writes_nothing_and_missing_dsn_is_an_error(self):
        code, log, batches, _ = self.run_tool([self.make_backup(), '--dry-run', '--dsn', 'postgresql://x'])
        self.assertEqual((code, batches), (0, []))
        self.assertFalse([e for e in log if e[0] == 'exec' and 'insert' in e[1]])
        with self.assertRaises(SystemExit):
            self.run_tool([self.make_backup()])

    def test_cast_helper(self):
        sys.path.insert(0, os.path.join(ROOT, 'tools'))
        import restore_backup as RB
        self.assertEqual((RB.cast(1, 'boolean'), RB.cast('5', 'bigint'), RB.cast(3, 'double precision'), RB.cast('0aff', 'bytea'), RB.cast(None, 'integer')), (True, 5, 3.0, b'\x0a\xff', None))
        self.assertEqual(set(RB.ORDER), set(BK.TABLES) - {'tokens'})                              # unealta restaureaza exact ce salveaza copia (fara token-uri)


if __name__ == '__main__':
    unittest.main()

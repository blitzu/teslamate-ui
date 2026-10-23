"""Teste pentru modulele din features/ (depozit propriu, evenimente, backup TeslaMate)."""
import datetime as dt
import decimal
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='tesla-ui-feat-')
os.environ.setdefault('DATA_DIR', TMP)
os.environ.setdefault('DEMO_ONLY', '1')
sys.path.insert(0, ROOT)
import server as S  # noqa: E402
REAL_NOTIFY = S.notify                                                 # alte teste il inlocuiesc; cele pentru receptori au nevoie de cel adevarat
from features.store import Store  # noqa: E402
from features import backup as BK  # noqa: E402


class StoreTests(unittest.TestCase):
    def test_migrate_is_incremental_and_kv(self):
        st = Store(os.path.join(tempfile.mkdtemp(), 'x.db'))
        st.migrate('m', ['create table a (id integer primary key, v text)'])
        st.migrate('m', ['create table a (id integer primary key, v text)', 'create table b (id integer primary key)'])
        st.migrate('m', ['create table a (id integer primary key, v text)', 'create table b (id integer primary key)'])    # a doua oara: nimic de facut
        self.assertEqual(st.one("select v from _schema where name='m'")['v'], 2)
        st.run('insert into a(v) values (?)', ('x',))
        self.assertEqual(st.rows('select v from a'), [{'v': 'x'}])
        st.kv_set('k', {'a': [1, 2]})
        self.assertEqual(st.kv_get('k'), {'a': [1, 2]})
        self.assertEqual(st.kv_get('lipsa', 7), 7)

    def test_tx_rolls_back(self):
        st = Store(os.path.join(tempfile.mkdtemp(), 'y.db'))
        st.run('create table t (v integer)')
        with self.assertRaises(ZeroDivisionError):
            with st.tx() as c:
                c.execute('insert into t values (1)')
                1 / 0
        self.assertEqual(st.rows('select * from t'), [])


class RegistryTests(unittest.TestCase):
    def test_route_lookup_exact_and_prefix(self):
        @S.route('GET', '/api/test-exact')
        def a(h, d):
            return 1

        @S.route('GET', '/api/test-pre/', prefix=True)
        def b(h, d):
            return 2
        self.assertIs(S.route_lookup('GET', '/api/test-exact')[0], a)
        self.assertIs(S.route_lookup('GET', '/api/test-pre/xyz')[0], b)
        self.assertIsNone(S.route_lookup('POST', '/api/test-exact'))

    def test_events_and_audit_hooks_write_to_the_own_db(self):
        self.assertIn('events', S.FEATURES)
        S.OWN.run('delete from events')
        for fn in S.MQTT_HOOKS:
            fn(1, 'sentry_mode', False, True, True)
            fn(1, 'latitude', 1.0, 2.0, True)               # nu e urmarit
            fn(1, 'plugged_in', None, True, False)          # prima valoare dupa repornire: se retine ca stare de baza (old=None)
        rows = S.OWN.rows('select key, old, new from events order by id')
        self.assertEqual(rows, [{'key': 'sentry_mode', 'old': 'False', 'new': 'True'}, {'key': 'plugged_in', 'old': None, 'new': 'True'}])
        S.audit('cmd', car=1, name='lock', actor='rule:test', ok=True, via='ble', note='x')
        self.assertEqual(S.OWN.rows('select name, actor, ok from cmd_log')[-1], {'name': 'lock', 'actor': 'rule:test', 'ok': 1})


class FakeSource:
    """Inlocuieste Postgres-ul: tabele in memorie (coloane + randuri)."""
    def __init__(self, tables):
        self.t = tables

    def columns(self, table):
        return self.t.get(table, {}).get('cols', [])

    def max_id(self, table):
        rows = self.t[table]['rows']
        return max([r[0] for r in rows], default=0)

    def rows(self, table, cols, after_id=None):
        allc = [c for c, _ in self.t[table]['cols']]
        idx = [allc.index(c) for c in cols]
        out = [tuple(r[i] for i in idx) for r in sorted(self.t[table]['rows']) if after_id is None or r[0] > after_id]
        for i in range(0, len(out), 2):
            yield out[i:i + 2]


class BackupTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.B = BK.Backup(S, path=os.path.join(d, 'bk.db'), snapdir=os.path.join(d, 'snaps'))
        self.src = FakeSource({
            'drives': dict(cols=[('id', 'integer'), ('start_date', 'timestamp without time zone'), ('distance', 'double precision'), ('ok', 'boolean'), ('extra', 'jsonb')],
                           rows=[(1, dt.datetime(2026, 10, 1, 8, 0), 12.5, True, {'a': 1}), (2, dt.datetime(2026, 10, 2, 8, 0), decimal.Decimal('7.25'), False, None)]),
            'positions': dict(cols=[('id', 'integer'), ('latitude', 'double precision')], rows=[(1, 44.1), (2, 44.2), (3, 44.3)]),
        })

    def sync(self):
        orig = BK.TABLES
        BK.TABLES = ['drives', 'positions', 'nu_exista']
        try:
            return self.B.sync(src=self.src)
        finally:
            BK.TABLES = orig

    def test_first_sync_copies_with_conversions(self):
        r = self.sync()
        self.assertTrue(r['ok'])
        self.assertEqual(r['tables']['positions']['rows'], 3)
        self.assertNotIn('nu_exista', r['tables'])
        d = self.B.db.rows('select * from drives order by id')
        self.assertEqual(d[0]['start_date'], '2026-10-01T08:00:00')
        self.assertEqual((d[0]['ok'], d[1]['ok'], d[1]['distance']), (1, 0, 7.25))
        self.assertEqual(d[0]['extra'], '{"a": 1}')
        self.assertEqual(self.B.db.one("select pgtype from _meta where tbl='drives' and col='ok'")['pgtype'], 'boolean')

    def test_append_only_and_updates_and_no_deletes(self):
        self.sync()
        self.src.t['positions']['rows'].append((4, 44.4))
        self.src.t['drives']['rows'][0] = (1, dt.datetime(2026, 10, 1, 8, 0), 99.0, True, None)      # randul s-a schimbat (cursa terminata)
        self.src.t['drives']['rows'].pop(1)                                                           # randul a disparut din sursa
        r = self.sync()
        self.assertEqual(r['tables']['positions']['new'], 1)                                          # doar randul nou
        self.assertEqual(self.B.db.one('select distance from drives where id=1')['distance'], 99.0)   # actualizat
        self.assertEqual(self.B.db.one('select count(*) n from drives')['n'], 2)                      # cel disparut ramane in copie

    def test_new_source_column_is_added(self):
        self.sync()
        self.src.t['positions']['cols'].append(('speed', 'integer'))
        self.src.t['positions']['rows'] = [r + (50,) for r in self.src.t['positions']['rows']] + [(9, 1.0, 70)]
        self.sync()
        self.assertEqual(self.B.db.one('select speed from positions where id=9')['speed'], 70)

    def test_snapshot_and_retention(self):
        self.sync()
        name = self.B.snapshot()
        self.assertTrue(os.path.exists(name))
        con = sqlite3.connect(name)
        self.assertEqual(con.execute('select count(*) from positions').fetchone()[0], 3)
        con.close()
        for i in range(10):                                                                           # fisiere vechi: se pastreaza doar ultimele 7
            open(os.path.join(self.B.snapdir, 'teslamate-2026010%d.db' % i), 'w').close()
        os.remove(name)
        self.B.snapshot()
        left = [f for f in os.listdir(self.B.snapdir) if f.startswith('teslamate-')]
        self.assertEqual(len(left), BK.KEEP_SNAPSHOTS)

    def test_status_and_download_copy(self):
        self.sync()
        st = self.B.status()
        self.assertFalse(st['running'])
        self.assertEqual(st['last']['tables']['drives']['rows'], 2)
        tmp = self.B.copy_for_download()
        con = sqlite3.connect(tmp)
        self.assertEqual(con.execute('select count(*) from drives').fetchone()[0], 2)
        con.close()
        os.remove(tmp)

    def test_conv(self):
        self.assertEqual(BK.conv(True), 1)
        self.assertEqual(BK.conv(decimal.Decimal('1.5')), 1.5)
        self.assertEqual(BK.conv({'a': 1}), '{"a": 1}')
        self.assertEqual(BK.conv(b'\x01\xff'), '01ff')
        self.assertIsNone(BK.conv(None))


from features import alerts as AL  # noqa: E402
from features import sleepguard as SG  # noqa: E402


class AlertsTests(unittest.TestCase):
    def setUp(self):
        S.OWN.kv_set('alerts_cfg', {})
        S.OWN.run('delete from alerts_log')
        S.OWN.run('delete from cmd_log')
        self.sent = []
        S.notify = lambda kind, title, msg, data=None, log=True: self.sent.append((kind, title, msg))
        S.LIVE.clear()
        self.E = AL.Engine(S)

    def test_clean_validates(self):
        c = AL.clean({'tpms_low': {'bar': '9'}, 'quiet': {'start': 'abc'}, 'cabin_hot': {'temp': '5'}, 'unknown': {'x': 1}})
        self.assertEqual(c['tpms_low']['bar'], 3.5)
        self.assertEqual(c['quiet']['start'], '23:00')
        self.assertEqual(c['cabin_hot']['temp'], 20)
        self.assertNotIn('unknown', c)

    def test_quiet_hours_across_midnight(self):
        q = dict(on=True, start='23:00', end='07:00')
        self.assertTrue(AL.in_quiet(q, dt.datetime(2026, 1, 1, 23, 30)))
        self.assertTrue(AL.in_quiet(q, dt.datetime(2026, 1, 1, 6, 59)))
        self.assertFalse(AL.in_quiet(q, dt.datetime(2026, 1, 1, 12, 0)))
        self.assertFalse(AL.in_quiet(dict(q, on=False), dt.datetime(2026, 1, 1, 23, 30)))

    def test_charge_stopped_rules(self):
        S.LIVE[1] = dict(battery_level=40, charge_limit_soc=90)
        self.E.on_mqtt(1, 'charging_state', 'Charging', 'NoPower', True)
        self.E.on_mqtt(1, 'charging_state', 'Charging', 'NoPower', True)            # cooldown
        self.assertEqual(len(self.sent), 1)
        self.assertIn('curent', self.sent[0][2])
        S.LIVE[1] = dict(battery_level=90, charge_limit_soc=90)
        self.E.fired.clear()
        self.E.on_mqtt(1, 'charging_state', 'Charging', 'Stopped', True)            # a atins limita
        self.assertEqual(len(self.sent), 1)
        S.LIVE[1] = dict(battery_level=40, charge_limit_soc=90)
        S.OWN.run("insert into cmd_log(ts, car, name, actor, ok) values(?,?,?,?,?)", (time.time(), 1, 'charge_stop', 'user:admin', 1))
        self.E.on_mqtt(1, 'charging_state', 'Charging', 'Stopped', True)            # tu ai oprit-o
        self.assertEqual(len(self.sent), 1)

    def test_plugged_not_charging_waits_then_explains(self):
        S.LIVE[1] = dict(plugged_in=True, charging_state='NoPower', battery_level=30, charge_limit_soc=80)
        self.E.tick(now=1000)
        self.E.tick(now=1000 + 10 * 60)
        self.assertEqual(self.sent, [])
        self.E.tick(now=1000 + 25 * 60)
        self.assertEqual(len(self.sent), 1)
        self.assertIn('nu vine curent', self.sent[0][2])
        S.LIVE[1]['scheduled_charging_start_time'] = '2026-10-23T01:00:00'          # programata: nu alerta
        self.E.fired.clear()
        self.E.since.clear()
        self.E.tick(now=5000)
        self.E.tick(now=5000 + 3600)
        self.assertEqual(len(self.sent), 1)

    def test_not_plugged_at_night_only_at_home(self):
        S.LIVE[1] = dict(geofence='Acasă', plugged_in=False, battery_level=50, state='online')
        self.E.tick(now=1, now_dt=dt.datetime(2026, 10, 23, 21, 0))
        self.assertEqual(self.sent, [])
        self.E.tick(now=2, now_dt=dt.datetime(2026, 10, 23, 22, 3))
        self.assertEqual(len(self.sent), 1)
        self.E.tick(now=3, now_dt=dt.datetime(2026, 10, 23, 22, 4))                 # o singura data pe zi
        self.assertEqual(len(self.sent), 1)
        S.LIVE[1]['geofence'] = 'Birou'
        self.E.fired.clear()
        self.E.tick(now=10**6, now_dt=dt.datetime(2026, 10, 24, 22, 3))
        self.assertEqual(len(self.sent), 1)

    def test_tpms_and_cabin(self):
        S.LIVE[1] = dict(tpms_pressure_fl=2.1, tpms_pressure_fr=2.9, tpms_pressure_rl=0, tpms_soft_warning_rr=True, climate_keeper_mode='dog', inside_temp=41)
        self.E.tick(now=100)
        titles = [t for _, t, _ in self.sent]
        self.assertTrue(any('anvelope' in t for t in titles))
        self.assertTrue(any('fierbinte' in t for t in titles))
        tp = [m for _, t, m in self.sent if 'anvelope' in t][0]
        self.assertIn('2.10 bar', tp)
        self.assertNotIn('spate stânga', tp)                                       # 0 = senzor fara date

    def test_quiet_hours_log_but_do_not_notify_except_critical(self):
        S.OWN.kv_set('alerts_cfg', {'quiet': {'on': True, 'start': '00:00', 'end': '23:59'}})
        S.LIVE[1] = dict(tpms_pressure_fl=2.0, climate_keeper_mode='camp', inside_temp=50)
        self.E.tick(now=100, now_dt=dt.datetime(2026, 10, 23, 12, 0))
        self.assertEqual(len(self.sent), 1)
        self.assertIn('fierbinte', self.sent[0][1])                                 # doar cea critica a trecut
        self.assertEqual(len(S.OWN.rows('select * from alerts_log')), 2)            # ambele sunt in jurnal

    def test_rain_with_open_window(self):
        S.LIVE[1] = dict(windows_open=True, latitude=44.43, longitude=26.1)
        S._get_text = lambda url, timeout=20: '{"current": {"precipitation": 0.0}, "hourly": {"precipitation": [0.0, 0.8]}}'
        self.E.tick(now=1000)
        self.assertEqual(len(self.sent), 1)
        self.assertIn('urmează', self.sent[0][1])
        self.E.tick(now=3000)
        self.assertEqual(len(self.sent), 1)                                         # o singura alerta per episod
        self.E.on_mqtt(1, 'windows_open', True, False, True)
        self.assertNotIn(1, self.E.rain_alerted)


class SleepGuardTests(unittest.TestCase):
    H = 3600

    def test_interval_helpers(self):
        self.assertEqual(SG.merge([[5, 8], [1, 3], [2, 4]]), [[1, 4], [5, 8]])
        self.assertEqual(SG.subtract([[0, 10]], [[2, 3], [5, 7]]), [[0, 2], [3, 5], [7, 10]])
        self.assertTrue(SG.overlaps(1, 5, [[4, 9]]))
        self.assertFalse(SG.overlaps(1, 4, [[4, 9]]))

    def test_analyze_reasons_and_busy_gap(self):
        H = self.H
        base = 1_800_000_000 - (1_800_000_000 % 86400)                               # miezul noptii UTC
        online = [[base, base + 6 * H]]
        busy = [[base + H, base + H + 20 * 60]]                                      # cursa 01:00-01:20 (+-5 min taiate)
        sentry = [[base + 2 * H, base + 3 * H]]
        cmds = [(base + 4 * H, 'rule:x')]
        r = SG.analyze(online, busy, sentry, [], [], cmds)
        day = r[list(r)[0]]
        self.assertEqual(day['reasons']['sentry'], 60)
        self.assertEqual(day['reasons']['comanda'], 13)                              # 03:59-04:12
        self.assertEqual(day['total'], sum(day['reasons'].values()))
        self.assertTrue(day['unexplained'] > 0)                                      # 00:00-00:55 si 01:25-02:00 nu au motiv

    def test_short_intervals_ignored_and_day_split_in_local_time(self):
        H = self.H
        base = 1_800_000_000 - (1_800_000_000 % 86400)
        self.assertEqual(SG.analyze([[base + 5 * 60, base + 6 * 60]], [], [], [], [], []), {})           # 1 minut: ignorat
        eet = lambda t: 2 * H
        r = SG.analyze([[base + 21 * H, base + 27 * H]], [], [], [], [], [], tz_offset=eet)               # 23:00-05:00 local: trece in ziua urmatoare
        self.assertEqual(len(r), 2)
        self.assertEqual(sum(v['total'] for v in r.values()), 360)

    def test_intervals_from_events(self):
        rows = [(10, 'True'), (20, 'False'), (30, 'True')]
        self.assertEqual(SG.intervals_from_events(rows, 'True', 99), [[10, 20], [30, 99]])


from features import service as SV  # noqa: E402
from features import trips as TR  # noqa: E402
from features import software as SW  # noqa: E402


class ServiceTests(unittest.TestCase):
    def test_add_months_clamps_end_of_month(self):
        self.assertEqual(SV.add_months(dt.date(2026, 1, 31), 1), dt.date(2026, 2, 28))
        self.assertEqual(SV.add_months(dt.date(2026, 11, 15), 3), dt.date(2027, 2, 15))

    def test_due_by_km_and_by_time(self):
        today = dt.date(2026, 10, 23)
        it = dict(interval_km=10000, interval_months=None, last_date=None, last_km=1000)
        self.assertEqual(SV.due(it, 5000, today)['status'], 'ok')
        self.assertEqual(SV.due(it, 10500, today)['status'], 'soon')              # mai putin de 10% ramas
        d = SV.due(it, 12000, today)
        self.assertEqual((d['status'], d['km_left']), ('overdue', -1000))
        t = dict(interval_km=None, interval_months=12, last_date='2025-10-01', last_km=None)
        self.assertEqual(SV.due(t, None, today)['status'], 'overdue')
        t2 = dict(t, last_date='2026-01-15')
        self.assertEqual(SV.due(t2, None, today)['status'], 'ok')
        self.assertEqual(SV.due(dict(interval_km=1000, interval_months=None, last_date=None, last_km=None), 5, today)['status'], 'unknown')

    def test_whichever_comes_first_wins(self):
        today = dt.date(2026, 10, 23)
        it = dict(interval_km=20000, interval_months=12, last_date='2025-11-20', last_km=0)       # timpul expira in 28 zile, km sunt departe
        d = SV.due(it, 3000, today)
        self.assertEqual(d['status'], 'soon')
        self.assertEqual(d['days_left'], 28)

    def test_slope_and_pressure_normalisation(self):
        self.assertAlmostEqual(SV.slope([(0, 3.0), (1, 2.9), (2, 2.8), (3, 2.7)]), -0.1)
        self.assertIsNone(SV.slope([(0, 1), (1, 2)]))
        warm = SV.norm_pressure(2.9, 30)
        cold = SV.norm_pressure(2.7, 10)
        self.assertAlmostEqual(SV.norm_pressure(2.9, 20), 2.9, places=3)
        self.assertLess(warm, 2.9)                                                # la 30 C masoara mai mult decat la 20 C
        self.assertGreater(cold, 2.7)

    def test_item_flow_through_the_routes(self):
        S.OWN.run('delete from maint_items')
        fn, o = S.route_lookup('POST', '/api/service/item')
        fn(None, dict(name='Filtru', interval_months=24, last_date='2025-01-01'))
        it = S.OWN.rows('select * from maint_items')[0]
        self.assertEqual((it['name'], it['interval_months']), ('Filtru', 24))
        done, _ = S.route_lookup('POST', '/api/service/done')
        done(None, dict(id=it['id'], date='2026-10-01', odometer='17000', cost='120,5'))
        it = S.OWN.rows('select * from maint_items')[0]
        self.assertEqual((it['last_date'], it['last_km']), ('2026-10-01', 17000.0))
        self.assertEqual(S.OWN.rows('select cost, odometer from service_log order by id desc')[0], {'cost': 120.5, 'odometer': 17000.0})
        with self.assertRaises(ValueError):
            fn(None, dict(name=''))


class TripsTests(unittest.TestCase):
    def drives(self):
        d = lambda i, a, b, km, n1, n2: dict(id=i, start_date=a, end_date=b, distance=km, duration_min=30, kwh=km * 0.15, start_name=n1, end_name=n2, speed_max=100 + i)
        return [d(1, '2026-10-01T08:00:00', '2026-10-01T09:00:00', 60, 'Acasa', 'Pitesti'), d(2, '2026-10-01T09:50:00', '2026-10-01T11:00:00', 80, 'Pitesti', 'Sibiu'),
                d(3, '2026-10-01T18:00:00', '2026-10-01T19:00:00', 50, 'Sibiu', 'Acasa'), dict(id=4, start_date='2026-10-02T08:00:00', end_date=None, distance=5)]

    def test_groups_by_gap_and_attaches_charges(self):
        charges = [dict(start_date='2026-10-01T09:10:00', end_date='2026-10-01T09:45:00', charge_energy_added=20.0, cost_eff=40.0),
                   dict(start_date='2026-10-05T10:00:00', end_date='2026-10-05T11:00:00', charge_energy_added=9.0, cost_eff=1.0)]
        t = TR.group(self.drives(), charges, dt.timedelta(hours=2))
        self.assertEqual(len(t), 2)                                                # (1+2) si (3); cursa 4 nu s-a terminat
        first = t[1]
        self.assertEqual((first['n_drives'], first['km'], first['n_charges'], first['charge_kwh'], first['charge_cost']), (2, 140.0, 1, 20.0, 40.0))
        self.assertEqual((first['start_name'], first['end_name'], first['stops']), ('Acasa', 'Sibiu', ['Pitesti']))
        self.assertEqual(first['id'], 1)
        self.assertEqual(len(TR.group(self.drives(), [], dt.timedelta(hours=12))), 1)           # pauza mare: totul intr-o calatorie
        self.assertEqual(t[0]['start'] > t[1]['start'], True)                      # cele mai noi primele


class SoftwareTests(unittest.TestCase):
    def test_wh_km_needs_enough_distance(self):
        self.assertIsNone(SW.wh_km([dict(distance=10, kwh=2.0)]))
        self.assertEqual(SW.wh_km([dict(distance=100, kwh=15.0), dict(distance=50, kwh=None)]), 150)


from features import pzu as PZ  # noqa: E402


class ReportsTests(unittest.TestCase):
    def test_periods(self):
        per = S.REPORTS['period']
        self.assertEqual(per('week', dt.date(2026, 10, 21)), (dt.date(2026, 10, 12), dt.date(2026, 10, 19)))          # luni..luni, saptamana trecuta
        self.assertEqual(per('week', dt.date(2026, 10, 19)), (dt.date(2026, 10, 12), dt.date(2026, 10, 19)))          # chiar luni: tot cea de dinainte
        self.assertEqual(per('month', dt.date(2026, 1, 15)), (dt.date(2025, 12, 1), dt.date(2026, 1, 1)))
        a, b = per('year', dt.date(2026, 3, 5))
        self.assertEqual((a, b), (dt.date(2026, 1, 1), dt.date(2026, 3, 6)))
        with self.assertRaises(ValueError):
            per('zi')

    def test_text_has_the_main_lines_and_comparison(self):
        r = dict(start='2026-10-12', end='2026-10-18', drives=5, km=210.4, kwh=31.2, wh_km=148, drive_min=200, speed_max=130, longest=dict(km=80.2, a='A', b='B'), best=dict(wh_km=120, km=30),
                 charges=2, charged=40.0, cost=32.0, price=0.8, dc=0, power_max=7.4, solar_pct=35, ice=None)
        prev = dict(r, km=105.2, kwh=31.2, cost=16.0)
        title, body = S.REPORTS['text']('week', r, prev, 1.5)
        self.assertIn('12 oct', title)
        for part in ('210 km', '5 curse', '148 Wh/km', '2 încărcări', '~35% din soare', 'Scurgere în repaus: 1,5 kWh', 'cea mai lungă cursă 80 km', 'km +100%'):
            self.assertIn(part, body)
        empty = dict(r, drives=0, km=0, kwh=0, wh_km=None, charges=0, longest=None, best=None, power_max=None, solar_pct=None)
        self.assertIn('Nicio cursă', S.REPORTS['text']('week', empty, None, None)[1])


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.orig, self.orig_notify = S.http, S.notify
        S.notify = REAL_NOTIFY
        S.http = lambda url, data=None, **k: (self.calls.append((url, data)) or (200, {'ok': True}))
        os.environ['TELEGRAM_TOKEN'] = '123456789:' + 'A' * 30
        os.environ['TELEGRAM_CHAT'] = '4242'
        S.OWN.kv_set('telegram_kinds', {})

    def tearDown(self):
        S.http, S.notify = self.orig, self.orig_notify
        os.environ.pop('TELEGRAM_TOKEN', None)
        os.environ.pop('TELEGRAM_CHAT', None)

    def fire(self, kind, title, msg):
        S.notify(kind, title, msg, {})
        time.sleep(0.3)                                                    # receptorii ruleaza pe fire separate

    def test_only_enabled_kinds_are_sent(self):
        self.fire('alert', 'T', 'mesaj')
        self.fire('door', 'T', 'nu')                                       # implicit oprit
        self.assertEqual(len(self.calls), 1)
        self.assertIn('/sendMessage', self.calls[0][0])
        self.assertEqual(self.calls[0][1]['chat_id'], '4242')
        fn, _ = S.route_lookup('POST', '/api/telegram/kinds')
        fn(None, dict(door=True))
        self.calls.clear()
        self.fire('door', 'T', 'da')
        self.fire('alert', 'T', 'nu')                                      # alert nu a mai fost bifat (kinds salvat inlocuieste tot)
        self.assertEqual([c[1]['text'] for c in self.calls], ['T\nda'])

    def test_not_configured_does_not_call_out(self):
        os.environ.pop('TELEGRAM_TOKEN')
        self.calls.clear()
        self.fire('alert', 'T', 'x')
        self.assertEqual(self.calls, [])
        self.assertFalse(S.TELEGRAM_SEND('x')['ok'])


class PzuTests(unittest.TestCase):
    def test_slot_energy_integrates_across_slot_edges(self):
        e = PZ.slot_energy([(t, 7.2) for t in range(0, 5400, 300)] + [(5400, 0), (99999, 0)])
        self.assertEqual(sorted(e), [0, 900, 1800, 2700, 3600, 4500])
        self.assertAlmostEqual(sum(e.values()), 7.2 * 5400 / 3600)          # 10.8 kWh; golul spre 99999 e ignorat
        self.assertAlmostEqual(e[0], 7.2 * 900 / 3600)

    def test_cost_with_addon_vat_and_coverage(self):
        price = {0: 0.10, 900: 0.20}.get
        c, cov = PZ.cost_of({0: 1.0, 900: 1.0, 1800: 1.0}, price)
        self.assertAlmostEqual(c, 0.30)
        self.assertAlmostEqual(cov, 2.0)                                    # slotul fara pret nu intra
        c2, _ = PZ.cost_of({0: 1.0}, price, addon=0.05, vat=20)
        self.assertAlmostEqual(c2, (0.10 + 0.05) * 1.2)

    def test_cheapest_slots_and_capacity(self):
        price = {0: 0.30, 900: 0.10, 1800: 0.20, 2700: 0.05}.get
        best = PZ.cheapest(3.0, [0, 900, 1800, 2700], price, 1.5)
        self.assertEqual(best, {2700: 1.5, 900: 1.5})
        self.assertIsNone(PZ.cheapest(10.0, [0, 900], price, 1.5))          # nu incape in fereastra


from features import push as PU  # noqa: E402


class PushTests(unittest.TestCase):
    UA = 'BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4'
    AUTH = 'BTBZMqHH6r4Tts7J_aSIgg'

    def test_encryption_matches_the_rfc8291_vector(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        k = ec.derive_private_key(int.from_bytes(PU.b64d('yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw'), 'big'), ec.SECP256R1())
        out = PU.encrypt(b'When I grow up, I want to be a watermelon', self.UA, self.AUTH, as_priv=k, salt=PU.b64d('DGv6ra1nlYgDCS1FRnbzlw'))
        self.assertEqual(PU.b64u(out), 'DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN')

    def test_only_known_push_services_are_accepted(self):
        for ok in ('https://fcm.googleapis.com/fcm/send/abc', 'https://updates.push.services.mozilla.com/wpush/v2/x', 'https://web.push.apple.com/Q123', 'https://wns2-par02p.notify.windows.com/w/?token=1'):
            self.assertTrue(PU.valid_endpoint(ok), ok)
        for bad in ('http://fcm.googleapis.com/x', 'https://evil.example.com/x', 'https://fcm.googleapis.com.evil.com/x', 'https://user@fcm.googleapis.com/x', 'https://192.168.1.1/x', ''):
            self.assertFalse(PU.valid_endpoint(bad), bad)

    def handler(self):
        class H:
            role = 'admin'
            headers = {'User-Agent': 'test'}
        return H()

    def test_subscribe_validates_and_410_removes_the_device(self):
        S.OWN.run('delete from push_subs')
        sub, _ = S.route_lookup('POST', '/api/push/subscribe')
        with self.assertRaises(ValueError):
            sub(self.handler(), dict(endpoint='https://evil.example.com/x', keys=dict(p256dh=self.UA, auth=self.AUTH)))
        with self.assertRaises(ValueError):
            sub(self.handler(), dict(endpoint='https://fcm.googleapis.com/x', keys=dict(p256dh='AAAA', auth=self.AUTH)))
        sub(self.handler(), dict(endpoint='https://fcm.googleapis.com/ok', keys=dict(p256dh=self.UA, auth=self.AUTH)))
        sub(self.handler(), dict(endpoint='https://fcm.googleapis.com/gone', keys=dict(p256dh=self.UA, auth=self.AUTH)))
        self.assertEqual(S.OWN.one('select count(*) n from push_subs')['n'], 2)
        import urllib.error
        import urllib.request
        real = urllib.request.urlopen
        seen = []

        def fake(req, timeout=0):
            seen.append(req)
            if req.full_url.endswith('/gone'):
                raise urllib.error.HTTPError(req.full_url, 410, 'Gone', {}, None)

            class R:
                status = 201
                def __enter__(self): return self
                def __exit__(self, *a): return False
            return R()
        urllib.request.urlopen = fake
        try:
            r = S.PUSH_DELIVER(dict(title='t', body='b'))
        finally:
            urllib.request.urlopen = real
        self.assertEqual((r['sent'], r['gone']), (1, 1))
        self.assertEqual([x['endpoint'] for x in S.OWN.rows('select endpoint from push_subs')], ['https://fcm.googleapis.com/ok'])
        h = {k.lower(): v for k, v in seen[0].header_items()}
        self.assertEqual(h['content-encoding'], 'aes128gcm')
        self.assertTrue(h['authorization'].startswith('vapid t='))
        self.assertEqual(seen[0].data[20], 65)                                     # lungimea cheii publice din antet


from features import share as SHR  # noqa: E402


class ShareTests(unittest.TestCase):
    def sh(self, **k):
        return dict(dict(label='Andrei', expires=time.time() + 3600, hide_home=1, show_dest=1), **k)

    def test_view_exposes_only_allowed_fields(self):
        live = dict(latitude=44.123456, longitude=26.654321, speed=87.4, heading=90, shift_state='D', geofence=None, battery_level=55, odometer=1234, display_name='X',
                    active_route=dict(destination='Piata Unirii', minutes_to_arrival=23.4, miles_to_arrival=10, energy_at_arrival=40))
        v = SHR.view(self.sh(), live, now=1000)
        self.assertEqual((v['lat'], v['lon'], v['speed'], v['eta_min'], v['eta_ts'], v['dest']), (44.12346, 26.65432, 87, 23, 1000 + int(23.4 * 60), 'Piata Unirii'))
        self.assertTrue(not ({'battery_level', 'odometer', 'display_name', 'energy_at_arrival'} & set(v)))
        self.assertNotIn('dest', SHR.view(self.sh(show_dest=0), live, now=1000))

    def test_position_hidden_at_home_and_without_route_when_parked(self):
        live = dict(latitude=44.1, longitude=26.1, shift_state='D', geofence='Acasă', active_route=dict(destination='X', minutes_to_arrival=5))
        v = SHR.view(self.sh(), live)
        self.assertEqual(v['state'], 'home')
        self.assertTrue(not ({'lat', 'lon', 'eta_min', 'dest'} & set(v)))
        self.assertIn('lat', SHR.view(self.sh(hide_home=0), live))
        parked = SHR.view(self.sh(), dict(latitude=44.1, longitude=26.1, shift_state=None, geofence=None, active_route=dict(destination='X', minutes_to_arrival=5)))
        self.assertEqual(parked['state'], 'parked')
        self.assertNotIn('eta_min', parked)                                    # ruta veche nu se mai arata cand stai pe loc

    def test_public_flow_create_expire_revoke(self):
        S.OWN.run('delete from shares')
        os.environ['SHARE_BASE'] = 'https://pub.example.com'
        try:
            create, _ = S.route_lookup('POST', '/api/share/create')
            with self.assertRaises(ValueError):
                create(None, dict(hours=500))
            url = create(None, dict(hours=1, label='<b>x'))['url']
            tok = url.rsplit('/', 1)[1]
            self.assertEqual(len(tok), 43)
            self.assertEqual(S.OWN.one('select count(*) n from shares where h=?', (tok,))['n'], 0)       # in baza e doar amprenta
            class H:
                headers = {'CF-Connecting-IP': '9.9.9.9'}
                client_address = ('1.1.1.1', 1)
            self.assertEqual(S.PUBLIC_ROUTES[-1](H(), '/share/' + tok + '/data', {})[0], 200)
            self.assertEqual(S.PUBLIC_ROUTES[-1](H(), '/share/' + tok, {})[0], 200)
            self.assertEqual(S.PUBLIC_ROUTES[-1](H(), '/share/' + 'A' * 43 + '/data', {})[0], 404)
            self.assertEqual(S.OWN.one('select label, views from shares')['label'], 'bx')
            S.OWN.run('update shares set expires=?', (time.time() - 1,))
            self.assertEqual(S.PUBLIC_ROUTES[-1](H(), '/share/' + tok + '/data', {})[0], 410)
            S.OWN.run('update shares set expires=?, revoked=1', (time.time() + 99,))
            self.assertEqual(S.PUBLIC_ROUTES[-1](H(), '/share/' + tok + '/data', {})[0], 410)
            self.assertIsNone(S.PUBLIC_ROUTES[-1](H(), '/altceva', {}))
        finally:
            os.environ.pop('SHARE_BASE', None)

    def test_page_sends_a_referer_to_the_tile_server(self):
        html = open(os.path.join(S.STATIC, 'share.html'), encoding='utf-8').read()
        self.assertNotIn('no-referrer', html)                                  # OSM blocheaza cererile de dale fara Referer ("Access blocked" 403)
        self.assertIn('content="strict-origin"', html)                         # doar domeniul, nu si calea cu tokenul

    def test_brute_force_is_blocked(self):
        class H:
            headers = {'CF-Connecting-IP': '8.8.4.4'}
            client_address = ('1.1.1.1', 1)
        codes = [S.PUBLIC_ROUTES[-1](H(), '/share/' + ('%043d' % i) + '/data', {})[0] for i in range(25)]
        self.assertEqual(codes[:20], [404] * 20)
        self.assertEqual(set(codes[20:]), {429})


from features import handoff as HO  # noqa: E402


class HandoffTests(unittest.TestCase):
    def setUp(self):
        S.OWN.run('delete from handoffs')
        self.cmds, self.orig_run, self.orig_q, self.orig_notify = [], S.run_command, S.q, S.notify
        S.run_command = lambda car, name, arg=None: (self.cmds.append((name, dict(arg or {}))) or dict(ok=self.ok.get(name, True), reason='' if self.ok.get(name, True) else 'refuzat'))
        S.q = lambda *a, **k: [dict(id=1, start_date='2026-10-23T10:00:00', end_date='2026-10-23T10:20:00', distance=12.34, speed_max=71, start_name='Acasa', end_name='Piata')]
        S.notify = lambda *a, **k: None
        self.ok = {}

    def tearDown(self):
        S.run_command, S.q, S.notify = self.orig_run, self.orig_q, self.orig_notify

    def test_build_cmd_validates_pin_and_speed(self):
        self.assertEqual(S.build_cmd('valet_on', dict(pin='1234'), {}), ('set_valet_mode', dict(on=True, password='1234')))
        self.assertEqual(S.build_cmd('speed_limit_set', dict(mph=500), {}), ('speed_limit_set_limit', dict(limit_mph=90)))
        self.assertEqual(S.build_cmd('guest_off', {}, {}), ('guest_mode', dict(enable=False)))
        for bad in ('12', 'abcd', '12345', ''):
            with self.assertRaises(ValueError):
                S.build_cmd('valet_on', dict(pin=bad), {})

    def test_start_requires_pin_and_end_reports(self):
        start, _ = S.route_lookup('POST', '/api/handoff/start')
        end, _ = S.route_lookup('POST', '/api/handoff/end')
        with self.assertRaises(ValueError):
            start(None, dict(valet=True, minutes=60))                         # fara PIN
        with self.assertRaises(ValueError):
            start(None, dict(minutes=60))                                     # nimic ales
        r = start(None, dict(valet=True, mph=75, minutes=5, pin4='4321'))
        self.assertTrue(r['ok'])
        self.assertEqual([c[0] for c in self.cmds], ['valet_on', 'speed_limit_set', 'speed_limit_on'])
        row = S.OWN.one('select * from handoffs')
        self.assertEqual((row['modes'], row['limit_mph']), ('valet,limită', 75))
        self.assertEqual(row['ends'] - row['started'], 15 * 60)               # minim 15 minute
        self.assertNotIn('4321', json.dumps(S.OWN.rows('select * from handoffs')))     # PIN-ul nu e salvat
        with self.assertRaises(ValueError):
            start(None, dict(guest=True))                                     # exista deja una activa
        self.cmds.clear()
        e = end(None, dict(pin4='4321'))
        self.assertTrue(e['ok'] and not e['manual'])
        self.assertEqual([c[0] for c in self.cmds], ['speed_limit_off', 'valet_off'])
        self.assertEqual((e['report']['drives'], e['report']['km'], e['report']['speed_max'], e['report']['places']), (1, 12.3, 71, ['Acasa', 'Piata']))
        self.assertIsNone(S.OWN.one('select * from handoffs where ended is null'))

    def test_end_without_pin_flags_manual_steps(self):
        start, _ = S.route_lookup('POST', '/api/handoff/start')
        end, _ = S.route_lookup('POST', '/api/handoff/end')
        start(None, dict(valet=True, guest=True, minutes=30, pin4='1111'))
        self.cmds.clear()
        e = end(None, {})
        self.assertTrue(e['manual'])
        self.assertEqual([c[0] for c in self.cmds], ['guest_off'])             # valet nu se poate opri fara PIN

    def test_failed_commands_do_not_open_a_session(self):
        start, _ = S.route_lookup('POST', '/api/handoff/start')
        self.ok = {'valet_on': False}
        r = start(None, dict(valet=True, minutes=30, pin4='1111'))
        self.assertFalse(r['ok'])
        self.assertIsNone(S.OWN.one('select * from handoffs'))

    def test_summarize(self):
        self.assertEqual(HO.summarize([])['drives'], 0)


from features import zones as ZN  # noqa: E402


class ZonesTests(unittest.TestCase):
    def test_in_window_wraps_midnight(self):
        self.assertTrue(ZN.in_window('23:30', '23:00-06:00'))
        self.assertTrue(ZN.in_window('02:00', '23:00-06:00'))
        self.assertFalse(ZN.in_window('12:00', '23:00-06:00'))
        self.assertTrue(ZN.in_window('10:00', '09:00-17:00'))
        self.assertFalse(ZN.in_window('17:00', '09:00-17:00'))
        self.assertFalse(ZN.in_window('10:00', 'prost'))

    def test_evaluate_rules(self):
        sp = dict(kind='speed', limit=130, pattern='', window='')
        self.assertIn('140', ZN.evaluate(sp, 'speed', 120, 140, True, {}, '12:00'))
        self.assertIsNone(ZN.evaluate(sp, 'speed', 135, 140, True, {}, '12:00'))                 # deja depasita: o singura alerta
        self.assertIsNone(ZN.evaluate(sp, 'speed', 100, 120, True, {}, '12:00'))
        en = dict(kind='enter', limit=None, pattern='Serviciu|Work', window='')
        self.assertIn('Serviciu', ZN.evaluate(en, 'geofence', None, 'Serviciu', True, {}, '12:00'))
        self.assertIsNone(ZN.evaluate(en, 'geofence', None, 'Serviciu', False, {}, '12:00'))     # valoare de baza la pornire: nu e o intrare
        lv = dict(en, kind='leave')
        self.assertIn('Serviciu', ZN.evaluate(lv, 'geofence', 'Serviciu', None, True, {}, '12:00'))
        self.assertIsNone(ZN.evaluate(lv, 'geofence', 'Acasa', None, True, {}, '12:00'))
        cf = dict(kind='curfew', limit=None, pattern='', window='23:00-06:00')
        self.assertIn('23:00-06:00', ZN.evaluate(cf, 'shift_state', 'P', 'D', True, {}, '01:00'))
        self.assertIsNone(ZN.evaluate(cf, 'shift_state', 'P', 'D', True, {}, '12:00'))
        self.assertIsNone(ZN.evaluate(cf, 'shift_state', 'D', 'R', True, {}, '01:00'))           # tot in miscare

    def test_clean_validates(self):
        self.assertEqual(ZN.clean(dict(kind='speed', limit='130.4'))['limit'], 130)
        for bad in (dict(kind='speed', limit='10'), dict(kind='speed'), dict(kind='enter', pattern=' '), dict(kind='curfew', window='25:00-06:00'), dict(kind='altceva')):
            with self.assertRaises(ValueError):
                ZN.clean(bad)
        self.assertEqual(ZN.clean(dict(kind='enter', pattern='Acas<a>|Work'))['pattern'], 'Acasa|Work')

    def test_hook_fires_once_per_cooldown_and_respects_handoff_scope(self):
        S.OWN.run('delete from zone_rules')
        S.OWN.run('delete from zone_log')
        S.OWN.run('delete from handoffs')
        sent = []
        orig = S.notify
        S.notify = lambda kind, title, msg, data=None, log=True: sent.append((kind, title, msg))
        try:
            save, _ = S.route_lookup('POST', '/api/zones/rule')
            save(None, dict(kind='speed', limit=100, name='Limita', cooldown=60))
            save(None, dict(kind='speed', limit=50, name='Doar predare', scope='handoff', cooldown=1))
            hook = S.MQTT_HOOKS[-1]
            hook(1, 'speed', 60, 120, True)
            hook(1, 'speed', 60, 130, True)                                    # in pauza
            self.assertEqual([m[1] for m in sent], ['📍 Limita'])              # regula de predare nu e activa
            S.OWN.run("insert into handoffs(car, started, ends, modes) values(1, ?, ?, 'valet')", (time.time(), time.time() + 600))
            hook(1, 'speed', 10, 70, True)
            self.assertEqual([m[1] for m in sent][-1], '📍 Doar predare')
            self.assertEqual(S.OWN.one('select count(*) n from zone_log')['n'], 2)
        finally:
            S.notify = orig
            S.OWN.run('delete from handoffs')


class BuildIdTests(unittest.TestCase):
    def test_build_id_is_stable_and_in_the_state(self):
        a = S.static_build()
        self.assertEqual(len(a), 10)
        self.assertEqual(a, S.static_build())
        self.assertEqual(S.app_brief()['build'], a)


import importer as IM  # noqa: E402


class ImporterGapTests(unittest.TestCase):
    def item(self, a, b):
        return dict(started_at=a, ended_at=b)

    def test_select_gaps_vs_older(self):
        items = [self.item(100, 200), self.item(1000, 1100), self.item(5000, 5100), self.item(6000, None), self.item(300, 250)]
        none = lambda x: False
        self.assertEqual([x['started_at'] for x in IM.select(items, none, 'gaps', 1000)], [100, 1000, 5000])      # tot ce se termina valid
        self.assertEqual([x['started_at'] for x in IM.select(items, none, 'older', 1000)], [100])
        dup = lambda x: x['started_at'] == 1000
        self.assertEqual([x['started_at'] for x in IM.select(items, dup, 'gaps', 1000)], [100, 5000])            # cele care exista deja in TeslaMate sunt sarite

    def test_where_buckets(self):
        items = [self.item(50, 60), self.item(150, 160), self.item(900, 910)]
        self.assertEqual(IM.where(items, 100, 500), dict(before=1, between=1, after=1))
        self.assertEqual(IM.where(items, None, None), dict(before=0, between=3, after=0))

    def test_overlap_tolerates_a_few_seconds(self):
        seen = []

        class Cur:
            def execute(self, sql, params):
                seen.append(params)

            def fetchone(self):
                return None
        a, b = IM.utc(1_000_000), IM.utc(1_000_600)
        IM.overlaps(Cur(), 1, a, b, 'drives')
        car, hi, lo = seen[0]
        self.assertEqual((hi - b).total_seconds(), -IM.TOL)                    # intervalul cautat e micsorat cu 30 s la fiecare capat
        self.assertEqual((lo - a).total_seconds(), IM.TOL)
        short = IM.shrink(IM.utc(0), IM.utc(8))
        self.assertEqual((short[1] - short[0]).total_seconds(), 4)             # cursa foarte scurta: doar un sfert din durata la fiecare capat

    def test_ledger_is_merged_on_a_second_run(self):
        import tempfile
        IM.LEDGER = os.path.join(tempfile.mkdtemp(), 'l.json')
        json_ = __import__('json')
        json_.dump(dict(drives=[1], positions=[10, 11], charging=[], addresses=[], tessie_drives=['a'], tessie_charges=[], at=1.0), open(IM.LEDGER, 'w'))

        class Cur:
            def __init__(self): self.q = None
            def execute(self, sql, params=None): self.q = sql
            def fetchone(self): return (50000.0,) if 'efficiency' in (self.q or '') else (None,)
            def fetchall(self): return []
            def close(self): pass

        class Conn:
            def cursor(self): return Cur()
            def commit(self): pass
            def rollback(self): pass
        orig_plan = IM.plan
        IM.plan = lambda cur, token, vin, car, mode, cutoff=None: (0, [], [], [], [])
        try:
            IM.run(Conn(), 't', 'v', 1, {}, mode='gaps')
        finally:
            IM.plan = orig_plan
        led = json_.load(open(IM.LEDGER))
        self.assertEqual((led['drives'], led['positions'], led['tessie_drives']), ([1], [10, 11], ['a']))


class DriveScoreTests(unittest.TestCase):
    def test_quantisation_noise_is_not_a_hard_event(self):
        pts = [(i * 0.25, 50 + (i % 2) * 3) for i in range(400)]            # 50/53 km/h alternand la 4 Hz: pe un pas ar parea 3,3 m/s2
        self.assertEqual(S.hard_events(pts), (0, 0))

    def test_real_braking_and_launch_count_once_each(self):
        pts = [(i * 0.25, 60) for i in range(8)]
        pts += [(2 + (j + 1) * 0.25, max(0, 60 - 5 * (j + 1))) for j in range(12)]       # 60 -> 0 km/h in 3 s = 5,6 m/s2
        pts += [(5 + (j + 1) * 0.25, min(50, 4 * (j + 1))) for j in range(16)]           # 0 -> 50 km/h in 3 s = 4,6 m/s2
        pts += [(9 + i * 0.25, 50) for i in range(8)]
        self.assertEqual(S.hard_events(pts), (1, 1))

    def test_gaps_in_data_are_not_guessed(self):
        self.assertEqual(S.hard_events([(0, 100), (10, 0), (20, 100), (30, 0)]), (0, 0))      # puncte la 10 s: nu estimam

    def test_score_is_scaled_for_long_drives(self):
        self.assertEqual(S.drive_score(0, 0, 5), 100)
        self.assertEqual(S.drive_score(2, 2, 10), 84)                          # 100 - (10 + 6)
        self.assertEqual(S.drive_score(2, 2, 60), 92)                          # penalizarea la jumatate
        self.assertEqual(S.drive_score(40, 40, 20), 0)
        self.assertEqual(S.drive_score(1, 1, None), 92)


from features import tags as TG  # noqa: E402


class TagsAndJourneyTests(unittest.TestCase):
    def drive(self, i, a, b, km=10, sl=(44.0, 26.0), el=(44.1, 26.1)):
        return dict(id=i, start_date=a, end_date=b, distance=km, kwh=km * 0.15, duration_min=30, start_name='A', end_name='B' + str(i), start_lat=sl[0], start_lon=sl[1], end_lat=el[0], end_lon=el[1])

    def test_build_breaks_and_charges(self):
        ds = [self.drive(1, '2026-10-01T08:00:00', '2026-10-01T09:00:00'), self.drive(2, '2026-10-01T09:20:00', '2026-10-01T10:00:00'),
              self.drive(3, '2026-10-01T10:02:00', '2026-10-01T11:00:00'), self.drive(4, '2026-10-01T13:00:00', '2026-10-01T14:00:00'), self.drive(5, '2026-10-01T15:30:00', '2026-10-01T16:00:00')]
        chs = [dict(id=7, start_date='2026-10-01T09:05:00', end_date='2026-10-01T09:18:00', charge_energy_added=15.0, cost_eff=30.0),
               dict(id=8, start_date='2026-10-01T11:30:00', end_date='2026-10-01T12:30:00', charge_energy_added=20.0, cost_eff=None),
               dict(id=9, start_date='2026-10-05T11:30:00', end_date='2026-10-05T12:30:00', charge_energy_added=9.0, cost_eff=1.0)]
        keep, stops, summ = TG.build(ds, chs)
        self.assertEqual([c['id'] for c in keep], [7, 8])                      # incarcarea din alta zi nu intra
        # 1->2 are o incarcare, 2->3 e prea scurta (2 min), 3->4 are o incarcare: doar pauza 4->5 e o oprire
        self.assertEqual([(s['min'], s['name']) for s in stops], [(90, 'B4')])
        self.assertEqual((summ['drives'], summ['km'], summ['charges'], summ['charged_kwh'], summ['cost']), (5, 50, 2, 35.0, 30.0))
        k2, _, s2 = TG.build(ds, chs, tagged_charge_ids={9})
        self.assertEqual([c['id'] for c in k2], [7, 8, 9])

    def test_tags_set_filter_and_cleanup(self):
        S.OWN.run('delete from tag_links')
        S.OWN.run('delete from tags')
        fn, _ = S.route_lookup('POST', '/api/tags/set')
        fn(None, dict(kind='drive', ids=[1, 2, 3], add=['Vacanta <b>Grecia', 'x']))
        self.assertEqual(sorted(S.TAGS.ids('drive', 'vacanta bgrecia')), [1, 2, 3])        # fara semne speciale si fara deosebire intre litere mari/mici
        rows = S.TAGS.attach('drive', [dict(id=1), dict(id=9)])
        self.assertEqual(rows[0]['tags'], ['Vacanta bGrecia', 'x'])
        self.assertEqual(rows[1]['tags'], [])
        fn(None, dict(kind='drive', ids=[1, 2, 3], remove=['x']))
        self.assertEqual([t['name'] for t in S.route_lookup('GET', '/api/tags')[0](None, {})['tags']], ['Vacanta bGrecia'])      # "x" nu mai e folosit: dispare
        with self.assertRaises(ValueError):
            fn(None, dict(kind='altceva', ids=[1]))
        with self.assertRaises(ValueError):
            fn(None, dict(kind='drive', ids=[]))

    def test_thin_keeps_last_point(self):
        pts = list(range(1000))
        out = TG.thin(pts, 100)
        self.assertLessEqual(len(out), 101)
        self.assertEqual(out[-1], 999)


from features import places as PL  # noqa: E402


class PlacesTests(unittest.TestCase):
    def test_nearest_respects_radius(self):
        ps = [dict(name='A', lat=44.0, lon=26.0, radius=150, price=2.0), dict(name='B', lat=44.0005, lon=26.0, radius=500, price=3.0)]
        self.assertEqual(PL.nearest(ps, 44.0001, 26.0)['name'], 'A')                 # ambele contin punctul: cel mai apropiat
        self.assertEqual(PL.nearest(ps, 44.0004, 26.0)['name'], 'B')
        self.assertIsNone(PL.nearest(ps, 45.0, 26.0))

    def test_clean_validates(self):
        self.assertEqual(PL.clean(dict(name=' Ionity <b>', lat='44.1', lon='26,1'.replace(',', '.'), price='2,3', radius='10'))['radius'], 30)   # raza minima 30 m
        for bad in (dict(name='', lat=1, lon=1, price=1), dict(name='x', lat=99, lon=1, price=1), dict(name='x', lat=1, lon=1, price=99), dict(name='x', lat='a', lon=1, price=1)):
            with self.assertRaises(ValueError):
                PL.clean(bad)

    def test_place_price_priority_in_cost_eff(self):
        S.OWN.run('delete from places')
        fn, _ = S.route_lookup('POST', '/api/places/save')
        fn(None, dict(name='Ionity Test', lat=44.0, lon=26.0, price='2,5', radius=200))
        row = lambda **k: dict(dict(id=987654, lat=44.0001, lon=26.0, charge_energy_added=10.0, charge_energy_used=12.0, cost=5.0, cost_real=None), **k)
        r = S.decorate([row()])[0]
        self.assertEqual((r['cost_place'], r['cost_eff'], r['place_name']), (30.0, 30.0, 'Ionity Test'))      # 12 kWh x 2,5; bate costul TeslaMate
        self.assertEqual(S.decorate([row(cost_real=4.0)])[0]['cost_eff'], 4.0)                                # costul real are prioritate
        self.assertEqual(S.decorate([row(lat=46.0)])[0]['cost_eff'], 5.0)                                     # in afara razei: costul TeslaMate
        self.assertEqual(S.decorate([row(charge_energy_used=None)])[0]['cost_eff'], 25.0)                     # fara kWh consumati: cei adaugati


if __name__ == '__main__':
    unittest.main()

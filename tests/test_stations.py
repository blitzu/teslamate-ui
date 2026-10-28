import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from features import stations as T                       # noqa: E402

AUTO = lambda n: 'Ionity' if 'ionity' in (n or '').lower() else ''
LAT, LON = 44.4000, 26.1000
SAMPLE = {'elements': [
    {'type': 'node', 'id': 1, 'lat': 44.4009, 'lon': 26.1000, 'tags': {'amenity': 'charging_station', 'operator': 'Tesla, Inc.', 'name': 'Supercharger Test', 'capacity': '12', 'socket:tesla_supercharger': '12'}},
    {'type': 'way', 'id': 2, 'center': {'lat': 44.40022, 'lon': 26.10015}, 'tags': {'amenity': 'charging_station', 'operator': 'IONITY GmbH', 'fee': 'yes', 'charge': '2,5 RON/kWh',
                                                                                  'socket:type2_combo': '4', 'opening_hours': '24/7'}},
    {'type': 'node', 'id': 3, 'lat': 44.4003, 'lon': 26.1003, 'tags': {'amenity': 'charging_station', 'network': 'Some <b>Net</b>', 'charge': 'EUR 0.69/kWh'}},
    {'type': 'node', 'id': 4, 'tags': {'amenity': 'charging_station'}}]}               # fara coordonate: ignorat


class StationTests(unittest.TestCase):
    def test_price_parsing(self):
        self.assertEqual(T.price_of('2,5 RON/kWh'), (2.5, 'RON'))
        self.assertEqual(T.price_of('EUR 0.69/kWh'), (0.69, 'EUR'))
        self.assertEqual(T.price_of('1.89 lei per kWh'), (1.89, 'RON'))
        self.assertEqual(T.price_of('0.5/kWh'), (0.5, None))
        self.assertIsNone(T.price_of('free'))
        self.assertIsNone(T.price_of(''))

    def test_candidates_sorted_by_distance_with_provider_and_estimate(self):
        c = T.parse(SAMPLE, LAT, LON, AUTO, 'RON', 20.0)
        self.assertEqual([x['id'] for x in c], ['way/2', 'node/3', 'node/1'])                # cele mai apropiate primele; cea fara coordonate lipseste
        self.assertEqual(c[0]['provider'], 'Ionity')
        self.assertEqual((c[0]['price'], c[0]['price_cur'], c[0]['cost_est']), (2.5, 'RON', 50.0))        # 2.5 lei/kWh x 20 kWh
        self.assertEqual(c[0]['sockets'], ['CCS'])
        self.assertIsNone(c[1]['cost_est'])                                                  # alta moneda decat a aplicatiei: fara cost propus
        self.assertNotIn('<', c[1]['network'])                                                # text curatat
        self.assertEqual(c[2]['provider'], 'Tesla Supercharger')
        self.assertLess(c[0]['dist'], c[2]['dist'])

    def test_route_uses_cache_and_reports_server_errors(self):
        calls = []
        S = types.SimpleNamespace(CURRENCY='lei', CUR_CODES={'lei': 'RON'}, provider_auto=AUTO, has_cars=lambda: True, NotFound=KeyError, DBDown=RuntimeError,
                                  _charges_rows=lambda car, lim, off, cid: [dict(lat=LAT, lon=LON, charge_energy_used=20.0, charge_energy_added=18.0)], routes={})
        S.route = lambda m, p, **k: (lambda fn: S.routes.__setitem__(p, fn) or fn)
        T.CACHE.clear()
        S._get_text = lambda url, timeout=0: (calls.append(url) or __import__('json').dumps(SAMPLE))
        T.init(S)
        r = S.routes['/api/station'](None, dict(id='5'))
        self.assertTrue(r['ok'])
        self.assertEqual(len(r['candidates']), 3)
        S.routes['/api/station'](None, dict(id='5'))
        self.assertEqual(len(calls), 1)                                                      # a doua cerere vine din cache
        T.CACHE.clear()

        def down(url, timeout=0):
            calls.append(url)
            raise OSError('timed out')
        S._get_text = down
        calls.clear()
        r = S.routes['/api/station'](None, dict(id='5'))
        self.assertFalse(r['ok'])
        self.assertIn('nu răspund', r['reason'])
        self.assertEqual(len(calls), len(T.ENDPOINTS))                                       # le incearca pe toate, pe rand


class ExtraSourceFirstTests(unittest.TestCase):
    def make(self, amp):
        S = types.SimpleNamespace(CURRENCY='lei', CUR_CODES={'lei': 'RON'}, provider_auto=AUTO, has_cars=lambda: True, NotFound=KeyError, DBDown=RuntimeError, log=lambda *a, **k: None,
                                  _charges_rows=lambda car, lim, off, cid: [dict(lat=LAT, lon=LON, charge_energy_used=20.0, charge_energy_added=18.0, dc=True, power_max=120)], routes={}, STATION_SOURCE=amp)
        S.route = lambda m, p, **k: (lambda fn: S.routes.__setitem__(p, fn) or fn)
        S._get_text = lambda url, timeout=0: __import__('json').dumps(SAMPLE)
        T.CACHE.clear()
        T.init(S)
        return S

    def test_uses_the_extra_source_when_it_has_results_and_osm_otherwise(self):
        seen = {}

        def find(lat, lon, radius, **kw):
            seen.update(kw)
            return [dict(id='x', name='X', provider='Ionity', dist=10)]
        r = self.make(types.SimpleNamespace(find=find, name='Other')).routes['/api/station'](None, dict(id='5'))
        self.assertEqual((r['source'], r['prices_now']), ('Other', True))
        self.assertEqual((seen['dc'], seen['power'], seen['kwh'], seen['cur_code']), (True, 120, 20.0, 'RON'))        # incarcarea alege incarcatorul potrivit
        for none in (lambda *a, **k: None, lambda *a, **k: [], lambda *a, **k: 1 / 0):                                # fara date, fara statii in raza, eroare
            r = self.make(types.SimpleNamespace(find=none)).routes['/api/station'](None, dict(id='5'))
            self.assertEqual(r['source'], 'OpenStreetMap')

    def test_no_extra_source_means_openstreetmap_only(self):
        self.assertEqual(self.make(None).routes['/api/station'](None, dict(id='5'))['source'], 'OpenStreetMap')


class LinkTests(unittest.TestCase):
    def make(self, found, meta=None):
        calls = []
        S = types.SimpleNamespace(CURRENCY='lei', CUR_CODES={'lei': 'RON'}, routes={}, meta_load=lambda: dict(meta or {}),
                                  meta_update=lambda cid, body: calls.append((cid, body)), decorate=lambda r: r,
                                  _charges_rows=lambda car, lim, off: [dict(id=1, start_date='2026-10-01T10:00:00', lat=LAT, lon=LON, dc=True, power_max=120, charge_energy_added=18.0),
                                                                       dict(id=2, start_date='2026-10-02T10:00:00', lat=None, lon=None, dc=False, power_max=7, charge_energy_added=5.0)],
                                  STATION_SOURCE=types.SimpleNamespace(name='Src', find=lambda lat, lon, radius, **kw: found(radius, kw)))
        S.route = lambda m, p, **k: (lambda fn: S.routes.__setitem__(p, fn) or fn)
        T.init(S)
        return S, calls

    TARIFFS = [dict(kind='dc', price=3.2, per_h=0, cur='RON', power=150, n=2), dict(kind='ac', price=2.55, per_h=0, cur='RON', power=22, n=2)]

    def test_links_without_touching_cost_or_a_manual_provider(self):
        seen = {}

        def found(radius, kw):
            seen.update(radius=radius, **kw)
            return [dict(name='Metro', provider='ElDrive', address='Str. X', tariffs=self.TARIFFS, matched=0, dist=12)]
        S, calls = self.make(found)
        s = T.link_row(S, dict(id=1, lat=LAT, lon=LON, dc=True, power_max=120, charge_energy_added=18.0, charge_energy_used=20.0))
        self.assertEqual(s['name'], 'Metro')
        cid, body = calls[0]
        self.assertEqual(set(body), {'station'})                                              # doar statia: nici costul, nici furnizorul ales manual
        self.assertEqual((body['station']['sel'], body['station']['auto'], body['station']['src']), (0, True, 'Src'))
        self.assertEqual((seen['radius'], seen['dc'], seen['power'], seen['kwh']), (T.LINK_RADIUS, True, 120, 20.0))

    def test_already_linked_charges_are_skipped_unless_forced(self):
        found = lambda radius, kw: [dict(name='Metro', provider='ElDrive', tariffs=[], matched=-1, dist=5)]
        S, calls = self.make(found, meta={'1': {'station': {'name': 'Altă stație'}}})
        self.assertIsNone(T.link_row(S, dict(id=1, lat=LAT, lon=LON)))
        self.assertEqual(calls, [])
        self.assertIsNotNone(T.link_row(S, dict(id=1, lat=LAT, lon=LON), force=True))
        self.assertIsNone(T.link_row(S, dict(id=3, lat=None, lon=None)))                      # fara coordonate

    def test_bulk_links_only_charges_with_a_station_nearby(self):
        S, calls = self.make(lambda radius, kw: [dict(name='Metro', provider='ElDrive', tariffs=[], matched=-1, dist=9)])
        res = T.autolink(S, 1)
        self.assertEqual([r[0] for r in res], [1])                                            # incarcarea 2 nu are coordonate
        S2, calls2 = self.make(lambda radius, kw: None)
        self.assertEqual(T.autolink(S2, 1), [])
        self.assertEqual(calls2, [])


class BackfillTests(unittest.TestCase):
    def make(self, ready=True, linked=True):
        kv, calls = {}, []
        S = types.SimpleNamespace(CURRENCY='lei', CUR_CODES={'lei': 'RON'}, routes={}, log=lambda *a, **k: calls.append(('log', a)), decorate=lambda r: r,
                                  OWN=types.SimpleNamespace(kv_get=lambda k, d=None: kv.get(k, d), kv_set=lambda k, v: kv.__setitem__(k, v)),
                                  q=lambda sql, *a: [dict(id=1), dict(id=2)], meta_load=lambda: {}, meta_update=lambda cid, body: calls.append(('meta', cid)),
                                  _charges_rows=lambda car, lim, off: [dict(id=car * 10, start_date='2026-10-01T10:00:00', lat=LAT, lon=LON, dc=True, power_max=120, charge_energy_added=18.0)],
                                  STATION_SOURCE=types.SimpleNamespace(name='Src', ready=lambda: ready,
                                                                       find=lambda lat, lon, radius, **kw: [dict(name='Metro', provider='ElDrive', tariffs=[], matched=-1, dist=5)] if linked else None))
        return S, kv, calls

    def test_links_all_existing_charges_once_and_remembers_it(self):
        S, kv, calls = self.make()
        self.assertTrue(T.backfill_once(S))
        self.assertEqual([c[1] for c in calls if c[0] == 'meta'], [10, 20])                   # cate o incarcare pentru fiecare masina
        self.assertEqual(kv[T.BACKFILL_KEY]['linked'], 2)
        calls.clear()
        self.assertTrue(T.backfill_once(S))
        self.assertEqual([c for c in calls if c[0] == 'meta'], [])                             # a doua oara: nimic (deja facut)

    def test_waits_while_the_source_is_not_ready(self):
        S, kv, calls = self.make(ready=False)
        self.assertFalse(T.backfill_once(S))
        self.assertNotIn(T.BACKFILL_KEY, kv)                                                  # nu se marcheaza: se reia cand sursa devine disponibila
        S.STATION_SOURCE.ready = lambda: True
        self.assertTrue(T.backfill_once(S))
        self.assertIn(T.BACKFILL_KEY, kv)

    def test_a_failed_download_during_the_run_means_retry_later(self):
        S, kv, calls = self.make()
        src = S.STATION_SOURCE
        src.last_fail = 0

        def find(lat, lon, radius, **kw):
            src.last_fail = 5.0                                                               # o tara nu s-a putut descarca
            return None
        src.find = find
        self.assertFalse(T.backfill_once(S))
        self.assertNotIn(T.BACKFILL_KEY, kv)

    def test_without_any_source_there_is_nothing_to_do(self):
        S, kv, _ = self.make()
        S.STATION_SOURCE = None
        self.assertTrue(T.backfill_once(S))
        self.assertNotIn(T.BACKFILL_KEY, kv)


class StationMetaTests(unittest.TestCase):
    def test_station_is_cleaned_limited_and_provider_derived(self):
        import server as SRV
        st = SRV.station_clean(dict(name='<b>Metro</b>', provider='ElDrive', tariffs=[dict(kind='DC', price='3,2'.replace(',', '.'), cur='RON', power=150, n=2), dict(kind='weird', price=1)], sel=1, auto=1))
        self.assertEqual(st['name'], 'bMetro/b')
        self.assertEqual([t['kind'] for t in st['tariffs']], ['dc', ''])
        self.assertEqual((st['sel'], st['auto']), (1, True))
        self.assertEqual(SRV.station_clean(dict(name='X', tariffs=[dict(price=1)] * 3, sel=9))['sel'], -1)       # sel in afara listei -> niciun tarif
        self.assertIsNone(SRV.station_clean(None))
        with self.assertRaises(ValueError):
            SRV.station_clean(dict(name='', provider=''))
        with self.assertRaises(ValueError):
            SRV.station_clean(dict(name='X', tariffs=[dict(price=5000)]))


if __name__ == '__main__':
    unittest.main()

import json
import os
import sys
import tempfile
import time
import types
import unittest
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from features import ampwhere as A                       # noqa: E402

LAT, LON = 45.5000, 25.0000                              # Brasov: doar in dreptunghiul Romaniei
SAMPLE = {'success': True, 'providers_data': {'1': {'name': 'ElDrive'}, '2': {'name': 'Petrom'}},
          'data': [
              {'uid': 'a', 'provider_id': 1, 'name': 'Metro Brasov', 'address': 'Str. X 44D', 'coordinates': [LAT, LON], 'schedule': {'is_always_open': True},
               'chargers': [{'power': 22, 'current_type': 'ac', 'price': {'value': 2.55, 'value_per_h': 0, 'currency': 'RON'}, 'connector': {'type': 'type2'}},
                            {'power': 150, 'current_type': 'dc', 'price': {'value': 3.2, 'value_per_h': 1.5, 'currency': 'RON'}, 'connector': {'type': 'ccs'}}]},
              {'uid': 'b', 'provider_id': 2, 'name': 'Petrom Test', 'address': '', 'coordinates': [LAT + 0.0018, LON], 'chargers': [{'power': 50, 'current_type': 'dc', 'price': {'value': 2.9, 'currency': 'RON'}}]},
              {'uid': 'c', 'provider_id': 1, 'name': 'Departe', 'coordinates': [46.5, 26.0], 'chargers': []},
              {'uid': 'd', 'provider_id': 1, 'name': 'Rupt'}]}                                 # fara coordonate: ignorat


class CompactTests(unittest.TestCase):
    def test_keeps_only_what_is_used_and_skips_broken_rows(self):
        st = A.compact(SAMPLE)
        self.assertEqual([s['n'] for s in st], ['Metro Brasov', 'Petrom Test', 'Departe'])
        self.assertEqual(st[0]['p'], 'ElDrive')
        self.assertTrue(st[0]['h'])
        self.assertEqual(st[0]['ch'][1], [150, 'dc', 3.2, 1.5, 'RON', 'ccs'])

    def test_unexpected_format_is_rejected(self):
        self.assertIsNone(A.compact({'foo': 1}))
        self.assertIsNone(A.compact([1, 2]))
        self.assertIsNone(A.compact({'data': []}))


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.st = A.compact(SAMPLE)

    def test_nearest_first_within_radius_with_matching_charger_price(self):
        c = A.candidates(self.st, LAT + 0.0001, LON, 250, dc=True, power=120, kwh=20.0, cur_code='RON', auto=lambda n: 'Petrom' if n == 'Petrom' else '')
        self.assertEqual([x['name'] for x in c], ['Metro Brasov', 'Petrom Test'])              # "Departe" e in afara razei
        self.assertEqual((c[0]['price'], c[0]['price_cur']), (3.2, 'RON'))                      # incarcatorul DC de 150 kW, nu AC de 22
        self.assertEqual(c[0]['cost_est'], 64.0)
        self.assertEqual(c[0]['price_text'], '3.2 RON/kWh · +1.5 RON/h')
        self.assertEqual(c[0]['provider'], 'ElDrive')
        self.assertEqual(c[1]['provider'], 'Petrom')                                            # nume cunoscut din lista aplicatiei

    def test_tariffs_list_has_ac_and_dc_with_the_matching_one_marked(self):
        c = A.candidates(self.st, LAT, LON, 250, dc=True, power=120)[0]
        self.assertEqual([(t['kind'], t['price']) for t in c['tariffs']], [('dc', 3.2), ('ac', 2.55)])
        self.assertEqual(c['matched'], 0)
        c = A.candidates(self.st, LAT, LON, 250, dc=False, power=11)[0]
        self.assertEqual(c['matched'], 1)

    def test_ac_charge_picks_the_ac_charger(self):
        c = A.candidates(self.st, LAT, LON, 250, dc=False, power=11, kwh=10.0, cur_code='RON')
        self.assertEqual(c[0]['price'], 2.55)
        self.assertEqual(c[0]['cost_est'], 25.5)

    def test_no_cost_estimate_for_another_currency(self):
        c = A.candidates(self.st, LAT, LON, 250, dc=False, power=11, kwh=10.0, cur_code='EUR')
        self.assertIsNone(c[0]['cost_est'])


class CountryTests(unittest.TestCase):
    def test_country_from_coordinates(self):
        self.assertEqual(A.countries_at(44.43, 26.10), ['ro'])                                  # Bucuresti
        self.assertEqual(A.countries_at(47.50, 19.04), ['hu'])                                  # Budapesta
        self.assertEqual(sorted(A.countries_at(43.75, 28.58)), ['bg', 'ro'])                    # Vama Veche: granita
        self.assertEqual(A.countries_at(48.14, 11.58), [])                                      # Munchen: AmpWhere n-are Germania
        self.assertEqual(len(A.COUNTRIES), 14)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.orig = A.fetch_raw
        self.opt = {}

    def tearDown(self):
        A.fetch_raw = self.orig

    def make(self, d=None):
        d = d or tempfile.mkdtemp()
        logs = []
        S = types.SimpleNamespace(DATA_DIR=d, APP_VERSION='1.0', log=lambda *a, **k: logs.append(a), provider_auto=lambda n: '', cget=lambda k, env='', d_='': self.opt.get(k, d_))
        A.init(S)
        return S, d, logs

    def test_downloads_once_a_day_per_country_and_keeps_it_on_disk(self):
        calls = []
        A.fetch_raw = lambda url, ua: (calls.append((url, ua)) or json.dumps(SAMPLE))
        S, d, _ = self.make()
        self.assertEqual(len(S.STATION_SOURCE.find(LAT, LON, 250)), 2)
        S.STATION_SOURCE.find(LAT, LON, 250)
        self.assertEqual(len(calls), 1)                                                         # a doua cautare: din memorie
        self.assertTrue(calls[0][0].endswith('/api/locations/ro'))
        self.assertIn('one snapshot per day', calls[0][1])
        S2, _, _ = self.make(d)                                                                 # dupa repornire: citeste de pe disc, nu descarca
        S2.STATION_SOURCE.find(LAT, LON, 250)
        self.assertEqual(len(calls), 1)
        S2.STATION_SOURCE.snaps['ro']['ts'] = time.time() - 25 * 3600                           # snapshot vechi: descarca din nou
        S2.STATION_SOURCE.find(LAT, LON, 250)
        self.assertEqual(len(calls), 2)

    def test_only_the_countries_where_the_charge_is_are_downloaded(self):
        calls = []
        A.fetch_raw = lambda url, ua: (calls.append(url.rsplit('/', 1)[1]) or json.dumps(SAMPLE))
        S, _, _ = self.make()
        S.STATION_SOURCE.find(LAT, LON, 250)
        self.assertEqual(calls, ['ro'])                                                         # nu toate cele 14
        S.STATION_SOURCE.find(47.5, 19.04, 250)                                                 # Budapesta: se adauga doar Ungaria
        self.assertEqual(calls, ['ro', 'hu'])
        S.STATION_SOURCE.find(43.75, 28.58, 250)                                                # granita RO/BG: Romania e deja descarcata, urmeaza Bulgaria
        self.assertEqual(calls, ['ro', 'hu', 'bg'])
        self.assertEqual(S.STATION_SOURCE.find(48.14, 11.58, 250), [])                          # Germania: in afara tarilor AmpWhere, fara nicio cerere
        self.assertEqual(len(calls), 3)

    def test_fixed_countries_override_the_location(self):
        calls = []
        A.fetch_raw = lambda url, ua: (calls.append(url.rsplit('/', 1)[1]) or json.dumps(SAMPLE))
        self.opt['ampwhere_country'] = 'ro, xx, bg'                                             # cod necunoscut ignorat
        S, _, _ = self.make()
        S.STATION_SOURCE.find(LAT, LON, 250)
        self.assertEqual(sorted(calls), ['bg', 'ro'])

    def test_on_by_default_and_never_downloads_when_switched_off(self):
        calls = []
        A.fetch_raw = lambda url, ua: (calls.append(url) or json.dumps(SAMPLE))
        S, d, _ = self.make()
        self.opt['ampwhere'] = '0'                                                              # oprit de utilizator (Setari sau AMPWHERE=0)
        self.assertIsNone(S.STATION_SOURCE.find(LAT, LON, 250))
        self.assertEqual(calls, [])
        self.assertFalse(os.path.exists(os.path.join(d, 'ampwhere_ro.json')))
        self.opt.clear()                                                                        # nicio setare: implicit pornit
        self.assertEqual(len(S.STATION_SOURCE.find(LAT, LON, 250)), 2)
        self.assertEqual(len(calls), 1)

    def test_failure_falls_back_and_is_not_retried_for_an_hour(self):
        calls = []

        def boom(url, ua):
            calls.append(url)
            raise OSError('down')
        A.fetch_raw = boom
        S, _, logs = self.make()
        self.assertIsNone(S.STATION_SOURCE.find(LAT, LON, 250))                                 # None => butonul foloseste OpenStreetMap
        self.assertIsNone(S.STATION_SOURCE.find(LAT, LON, 250))
        self.assertEqual(len(calls), 1)
        self.assertTrue(logs)
        self.assertGreater(S.STATION_SOURCE.last_fail, 0)

    def test_refusal_backs_off_for_a_day(self):
        calls = []

        def refuse(url, ua):
            calls.append(ua)
            raise urllib.error.HTTPError(url, 429, 'Too Many Requests', {}, None)
        A.fetch_raw = refuse
        S, _, _ = self.make()
        self.assertIsNone(S.STATION_SOURCE.find(LAT, LON, 250))
        S.STATION_SOURCE.fail['ro'] -= 2 * 3600                                                 # dupa 2 ore: tot nu mai incearca (ar fi incercat dupa o eroare obisnuita)
        self.assertIsNone(S.STATION_SOURCE.find(LAT, LON, 250))
        self.assertEqual(len(calls), 1)
        self.assertIn('github.com/blitzu/teslamate-ui', calls[0])                               # ne identificam

    def test_one_country_failing_does_not_hide_the_other(self):
        def partly(url, ua):
            if url.endswith('/bg'):
                raise OSError('down')
            return json.dumps(SAMPLE)
        A.fetch_raw = partly
        S, _, _ = self.make()
        self.assertEqual(len(S.STATION_SOURCE.find(LAT, LON, 250, ) or []), 2)                  # Romania (nu si Bulgaria) e destul
        r = S.STATION_SOURCE.find(43.75, 28.58, 250)                                            # granita: Romania din memorie, Bulgaria cade
        self.assertIsNotNone(r)

    def test_broken_format_is_not_stored(self):
        A.fetch_raw = lambda url, ua: json.dumps({'weird': True})
        S, d, _ = self.make()
        self.assertIsNone(S.STATION_SOURCE.find(LAT, LON, 250))
        self.assertFalse(os.path.exists(os.path.join(d, 'ampwhere_ro.json')))


if __name__ == '__main__':
    unittest.main()

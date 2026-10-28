import json
import os
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tesla-ui-fx-'))
os.environ.setdefault('DEMO_ONLY', '1')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as S  # noqa: E402
from isolation import Isolated  # noqa: E402
from features import stations as T  # noqa: E402


class FxRateTests(Isolated):
    def setUp(self):
        S.FXFILE = os.path.join(tempfile.mkdtemp(), 'fx.json')
        S.FX_CACHE.clear()
        self.urls = []

    def feed(self, table):
        def get(url, timeout=20):
            self.urls.append(url)
            for k, v in table.items():
                if k in url:
                    if isinstance(v, Exception):
                        raise v
                    return json.dumps(v)
            raise OSError('no route')
        S._get_text = get

    def test_ecb_rate_is_used_first_and_cached(self):
        self.feed({'frankfurter.dev/v1/latest?base=HUF&symbols=RON': {'rates': {'RON': 0.0125}}})
        self.assertEqual(S.fx_rate('huf', 'ron'), 0.0125)
        self.assertEqual(S.fx_rate('HUF', 'RON'), 0.0125)
        self.assertEqual(len(self.urls), 1)                                                   # a doua oara din cache (12 h)
        self.assertEqual(S.fx_rate('RON', 'RON'), 1.0)

    def test_currencies_the_ecb_does_not_publish_use_the_fallback(self):
        self.feed({'frankfurter.dev': OSError('404'), 'open.er-api.com/v6/latest/MDL': {'result': 'success', 'rates': {'RON': 0.26}}})
        self.assertEqual(S.fx_rate('MDL', 'RON'), 0.26)
        self.assertTrue(any('open.er-api.com' in u for u in self.urls))

    def test_last_known_rate_survives_an_outage_and_garbage_is_refused(self):
        self.feed({'frankfurter.dev/v1/latest?base=CZK&symbols=RON': {'rates': {'RON': 0.2}}})
        self.assertEqual(S.fx_rate('CZK', 'RON'), 0.2)
        S.FX_CACHE['CZK>RON'] = (0, 0.2)                                                      # intrat in expirare
        self.feed({})                                                                         # nicio sursa nu raspunde
        self.assertEqual(S.fx_rate('CZK', 'RON'), 0.2)
        self.assertIsNone(S.fx_rate('XXX', 'RON'))
        self.assertIsNone(S.fx_rate('../etc', 'RON'))                                         # doar coduri de 3 litere ajung in URL
        self.assertIsNone(S.fx_rate('', 'RON'))


class ConvertTests(unittest.TestCase):
    def make(self, rates, currency='lei'):
        return types.SimpleNamespace(CURRENCY=currency, CUR_CODES={'lei': 'RON', 'ron': 'RON', 'eur': 'EUR', '€': 'EUR'}, fx_rate=lambda a, b: rates.get((a, b)))

    def cand(self):
        return dict(price=289.0, price_cur='HUF', price_text='289 HUF/kWh', cost_est=None,
                    tariffs=[dict(kind='dc', price=289.0, per_h=10.0, cur='HUF', power=150, n=2), dict(kind='ac', price=0.5, per_h=0, cur='RON', power=22, n=1)])

    def test_prices_are_converted_to_the_app_currency_keeping_the_original(self):
        c = T.convert(self.make({('HUF', 'RON'): 0.0125}), [self.cand()], kwh=20.0)[0]
        t = c['tariffs'][0]
        self.assertEqual((t['cur'], t['price'], t['orig_cur'], t['orig_price'], t['per_h']), ('RON', 3.613, 'HUF', 289.0, 0.12))
        self.assertEqual(c['tariffs'][1]['cur'], 'RON')                                       # deja in moneda aplicatiei: neatins
        self.assertNotIn('orig_cur', c['tariffs'][1])
        self.assertEqual((c['price_cur'], c['price']), ('RON', 3.613))
        self.assertEqual(c['cost_est'], 72.26)                                                # pret convertit x kWh
        self.assertIn('289 HUF', c['price_text'])

    def test_without_a_rate_nothing_is_changed(self):
        c = T.convert(self.make({}), [self.cand()], kwh=20.0)[0]
        self.assertEqual((c['tariffs'][0]['cur'], c['price_cur'], c['cost_est']), ('HUF', 'HUF', None))

    def test_unknown_app_currency_is_left_alone(self):
        c = T.convert(self.make({('HUF', 'RON'): 0.0125}, currency='???'), [self.cand()], kwh=20.0)[0]
        self.assertEqual(c['tariffs'][0]['cur'], 'HUF')

    def test_converted_tariffs_survive_in_the_station_metadata(self):
        c = T.convert(self.make({('HUF', 'RON'): 0.0125}), [self.cand()], kwh=20.0)[0]
        st = S.station_clean(dict(name='X', tariffs=c['tariffs'], sel=0))
        self.assertEqual((st['tariffs'][0]['orig_cur'], st['tariffs'][0]['orig_price']), ('HUF', 289.0))


if __name__ == '__main__':
    unittest.main()

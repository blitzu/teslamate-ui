import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from features import drivecost as D                       # noqa: E402


def ch(start, end, kwh, soc0, soc1, cost):
    return dict(start_date=start, end_date=end, charge_energy_added=kwh, start_soc=soc0, end_soc=soc1, cost_eff=cost)


def dr(i, start, km, kwh):
    return dict(id=i, start_date=start, distance=km, kwh=kwh)


FULL = ch('2026-01-01T00:00:00', '2026-01-01T05:00:00', 60, 0, 100, 60.0)             # 0 -> 100 %, 60 kWh la 1.0/kWh (capacitate 60)


class SimulateTests(unittest.TestCase):
    def test_capacity_from_charges(self):
        cs = [ch('2026-01-01T10:00:00', '2026-01-01T12:00:00', 30, 20, 70, 0), ch('2026-01-02T10:00:00', '2026-01-02T11:00:00', 31, 30, 80, 0), ch('2026-01-03T10:00:00', '2026-01-03T10:05:00', 1, 50, 52, 0)]
        self.assertAlmostEqual(D.capacity(cs), 61.0, delta=1.5)
        self.assertEqual(D.capacity([]), D.CAP_DEFAULT)

    def test_energy_from_the_factory_is_free(self):
        out = D.simulate([FULL], [dr(1, '2025-12-30T08:00:00', 50, 8.0)])                 # inainte de prima incarcare
        self.assertEqual(out[1], (0.0, 0.0, False))

    def test_oldest_energy_is_used_first(self):
        free = ch('2026-01-05T00:00:00', '2026-01-05T01:00:00', 15, 75, 100, 0.0)         # 15 kWh gratuiti peste 45 kWh la 1.0
        out = D.simulate([FULL, free], [dr(1, '2026-01-02T08:00:00', 100, 15.0), dr(2, '2026-01-06T08:00:00', 200, 50.0), dr(3, '2026-01-07T08:00:00', 20, 10.0)])
        self.assertAlmostEqual(out[1][0], 15.0)                                           # primii 15 kWh platiti
        self.assertAlmostEqual(out[2][0], 45.0)                                           # 45 kWh platiti ramasi + 5 gratuiti
        self.assertAlmostEqual(out[2][1], 0.9)
        self.assertAlmostEqual(out[3][0], 0.0)                                            # energia platita s-a consumat: nimic nu "ramane" amestecat
        self.assertFalse(out[3][2])

    def test_parked_drain_removes_the_oldest_energy(self):
        # dupa prima cursa raman 45 kWh; la a doua incarcare SOC-ul de start e 50 % (30 kWh): 15 kWh au disparut din parcare, din cei mai vechi
        c2 = ch('2026-01-05T00:00:00', '2026-01-05T01:00:00', 30, 50, 100, 0.0)
        out = D.simulate([FULL, c2], [dr(1, '2026-01-02T08:00:00', 100, 15.0), dr(2, '2026-01-06T08:00:00', 200, 40.0)])
        self.assertAlmostEqual(out[2][0], 30.0)                                           # 30 kWh platiti ramasi + 10 gratuiti

    def test_charge_without_price_is_an_estimate(self):
        unknown = ch('2026-01-05T00:00:00', '2026-01-05T01:00:00', 50, 10, 100, None)
        out = D.simulate([FULL, unknown], [dr(1, '2026-01-06T08:00:00', 100, 20.0)])
        cost, price, est = out[1]
        self.assertTrue(est)
        self.assertAlmostEqual(price, 1.0)                                                # pretul mediu al incarcarilor cu pret

    def test_no_priced_charge_means_no_cost(self):
        self.assertEqual(D.simulate([ch('2026-01-01T00:00:00', '2026-01-01T05:00:00', 60, 0, 100, None)], [dr(1, '2026-01-02T08:00:00', 10, 2.0)]), {})


class AnnotateTests(unittest.TestCase):
    def setUp(self):
        D.init(S := types.SimpleNamespace(
            LOCAL_TZ='UTC', log=lambda *a, **k: None, ha_ok=lambda: False, HA={}, decorate=lambda r: r,
            DEMO=dict(charges=[FULL], drives=[dr(1, '2026-01-02T08:00:00', 100.0, 15.0), dr(2, '2026-01-02T09:00:00', 0, None)]),
            fuel_conf=lambda: dict(l100=7.0, manual=8.0), fuel_book=lambda fc: [], fuel_lookup=lambda book, day, manual: (manual, 'manual')))
        self.S = S

    def test_costs_and_petrol_equivalent(self):
        rows = [dict(S_ for S_ in self.S.DEMO['drives'][0].items()), dict(self.S.DEMO['drives'][1])]
        self.S.DRIVECOST.annotate(1, rows, True)
        r = rows[0]
        self.assertEqual((r['cost_ev'], r['price_kwh'], r['cost_est']), (15.0, 1.0, False))
        self.assertEqual(r['eq_l100'], round(15.0 / 100 * 100 / 8.0, 2))                  # 15 lei / 100 km la 8 lei/l = 1.88 l/100 km
        self.assertEqual(r['cost_ice'], 56.0)                                             # 100 km x 7 l/100 x 8 lei
        self.assertEqual(r['ice_saving'], 41.0)
        self.assertIsNone(rows[1]['cost_ev'])

    def test_without_ice_consumption_only_equivalent_is_shown(self):
        self.S.fuel_conf = lambda: dict(l100=0.0, manual=8.0)
        rows = [dict(self.S.DEMO['drives'][0], distance=50.0, kwh=5.0)]
        self.S.DRIVECOST.annotate(1, rows, True)
        self.assertIsNone(rows[0]['cost_ice'])
        self.assertEqual(rows[0]['eq_l100'], round(15.0 / 50 * 100 / 8.0, 2))


class PeriodTotalTests(unittest.TestCase):
    def test_total_matches_drive_costs_and_feeds_the_stats_panel(self):
        S = types.SimpleNamespace(DEMO=dict(charges=[FULL], drives=[dr(1, '2026-01-02T08:00:00', 100.0, 15.0), dr(2, '2026-01-03T08:00:00', 50.0, 8.0)]),
                                  decorate=lambda r: r, log=lambda *a, **k: None, LOCAL_TZ='UTC')
        D.init(S)
        self.assertAlmostEqual(S.DRIVECOST.total(1, [1, 2, 99], True), 23.0)
        self.assertAlmostEqual(S.DRIVECOST.total(1, [2], True), 8.0)
        import server as SRV
        ic = SRV.ice_calc([dict(day='2026-01-02', km=100.0), dict(day='2026-01-03', km=50.0)], 23.0, 10.0, 23.0, l100=7.0, book=[], manual=8.0, ev_total=23.0)
        self.assertEqual(ic['ev_cost'], 23.0)                                              # nu mai media pe kWh incarcat
        self.assertEqual(ic['cost'], round(150 / 100 * 7.0 * 8.0, 2))


class TripCostTests(unittest.TestCase):
    def test_trip_cost_is_the_sum_of_its_drives(self):
        from features import trips as T
        g = [dict(distance=100.0, kwh=15.0, cost_ev=15.0, cost_est=False, fuel_price=8.0, cost_ice=56.0),
             dict(distance=50.0, kwh=8.0, cost_ev=9.0, cost_est=True, fuel_price=8.0, cost_ice=28.0),
             dict(distance=1.0, kwh=None, cost_ev=None)]                                    # cursa fara energie: nu intra
        c = T.cost_of(g)
        self.assertEqual((c['cost_ev'], c['cost_est'], c['cost_ice'], c['ice_saving']), (24.0, True, 84.0, 60.0))
        self.assertAlmostEqual(c['price_kwh'], 24.0 / 23.0, places=3)
        self.assertEqual(c['eq_l100'], round((15 / 8 + 9 / 8) / 150 * 100, 2))
        none = T.cost_of([dict(distance=3.0, kwh=None, cost_ev=None)])
        self.assertTrue(all(v is None for v in none.values()))
        self.assertIsNone(T.cost_of([dict(distance=5.0, kwh=1.0, cost_ev=2.0, cost_est=False, fuel_price=None, cost_ice=None)])['eq_l100'])


if __name__ == '__main__':
    unittest.main()

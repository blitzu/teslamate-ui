"""Cost per cursa: energia din baterie se consuma in ordinea in care a fost incarcata (cea mai veche prima, FIFO).

Bateria e un sir de "straturi": fiecare incarcare adauga kWh la pretul ei (cost / kWh adaugati); energia de dinaintea primei incarcari din istoric
(venita din fabrica) e gratuita. O cursa consuma kWh incepand de la cel mai vechi strat si costa suma pretului straturilor consumate, deci banii unei
incarcari ajung la cursele care au folosit-o. Inainte de fiecare incarcare, bateria se aduce la kWh dati de SOC-ul de start (consumul din parcare
scade din cel mai vechi strat). Incarcarile fara pret (cost necunoscut) intra la pretul mediu al incarcarilor cu pret si fac cursele care le folosesc
"estimate". Comparatia cu masina termica foloseste pretul combustibilului din ziua cursei; echivalentul in l/100 km = (costul electric la 100 km) / pretul litrului."""
import datetime as dt
import time

MIN_DSOC = 15          # incarcari cu cel putin 15 % pentru estimarea capacitatii utile
EST_FRAC = 0.30        # peste 30 % din energia unei curse din straturi cu pret presupus -> cursa e "estimata"
CAP_DEFAULT = 60.0
EPS = 1e-9


def _p(x):
    return dt.datetime.fromisoformat(str(x)) if x else None


def capacity(charges):
    """Capacitatea utila (kWh) din incarcari: mediana energiei adaugate / variatia SOC; 60 daca nu sunt date."""
    vals = sorted(c['charge_energy_added'] / ((c['end_soc'] - c['start_soc']) / 100) for c in charges
                  if c.get('charge_energy_added') and c.get('start_soc') is not None and c.get('end_soc') is not None and c['end_soc'] - c['start_soc'] >= MIN_DSOC)
    return vals[len(vals) // 2] if vals else CAP_DEFAULT


def _take(layers, kwh):
    """Consuma `kwh` de la cel mai vechi strat. Intoarce (cost, kWh din straturi estimate, kWh fara strat)."""
    cost = est = 0.0
    while kwh > EPS and layers:
        n = min(layers[0][0], kwh)
        cost += n * layers[0][1]
        est += n if layers[0][2] else 0.0
        layers[0][0] -= n
        kwh -= n
        if layers[0][0] <= EPS:
            layers.pop(0)
    return cost, est, max(kwh, 0.0)


def simulate(charges, drives):
    """{id_cursa: (cost, pret_kwh, estimat)} pentru cursele cu energie; {} daca nicio incarcare nu are pret."""
    cs = sorted((c for c in charges if c.get('end_date') and c.get('charge_energy_added')), key=lambda c: c['start_date'])
    known = [c for c in cs if c.get('cost_eff') is not None]
    if not known:
        return {}
    cap = capacity(cs)
    avg = sum(c['cost_eff'] for c in known) / sum(c['charge_energy_added'] for c in known)      # pret presupus pentru incarcarile fara cost
    layers = [[cap, 0.0, False]]                                                               # energia de dinaintea primei incarcari: din fabrica, gratuita
    ev = sorted([(_p(c['start_date']), 0, c) for c in cs] + [(_p(d['start_date']), 1, d) for d in drives if d.get('kwh') and d['kwh'] > 0 and d.get('start_date')], key=lambda x: (x[0], x[1]))
    out = {}
    for _, kind, x in ev:
        if kind == 0:
            before = min(cap, max(0.0, (x.get('start_soc') or 0) / 100 * cap))
            have = sum(l[0] for l in layers)
            if have > before:
                _take(layers, have - before)                                                    # consum din parcare: scade din cel mai vechi
            elif before - have > EPS:
                layers.append([before - have, layers[-1][1] if layers else 0.0, False])        # energie netinuta in evidenta: la pretul ultimului strat
            e = float(x['charge_energy_added'])
            priced = x.get('cost_eff') is not None
            layers.append([e, x['cost_eff'] / e if priced else avg, not priced])
        else:
            kwh = float(x['kwh'])
            cost, est, rest = _take(layers, kwh)
            if rest > EPS:                                                                      # mai mult decat stim ca e in baterie: pretul ultimului strat cunoscut
                cost += rest * avg
                est += rest
            out[x['id']] = (cost, cost / kwh, est / kwh > EST_FRAC)
    return out


def init(S):
    class DriveCost:
        cache = {}

        def costs(self, car, demo):
            k = (car, demo)
            hit = self.cache.get(k)
            if hit and time.time() - hit[0] < 30:
                return hit[1]
            if demo:
                ch = S.decorate([dict(c) for c in S.DEMO['charges']])
                dr = S.DEMO['drives']
            else:
                ch = S._charges_rows(car, 5000, 0)
                if S.ha_ok() and S.HA['grid']:
                    for r in ch:
                        try:
                            r['cost_real'] = S.real_cost(r, False)[0]          # doar din cache: nicio interogare noua in HA aici
                        except Exception:  # noqa
                            pass
                ch = S.decorate(ch)
                dr = S.drives(car, 100000, 0)
            val = simulate(ch, dr)
            self.cache[k] = (time.time(), val)
            return val

        def total(self, car, ids, demo=False):
            """Suma costurilor curselor `ids` (acelasi calcul ca pe pagina curselor); None daca nu exista costuri (nicio incarcare cu pret)."""
            costs = self.costs(car, demo)
            return sum(costs[i][0] for i in ids if i in costs) if costs else None

        def annotate(self, car, rows, demo=False):
            """Adauga la fiecare cursa: cost_ev, price_kwh, cost_est, cost_ice, eq_l100, ice_saving (None unde nu se poate calcula)."""
            try:
                costs = self.costs(car, demo)
            except Exception as e:  # noqa
                S.log('cost cursa:', e, flush=True)
                return rows
            fc = S.fuel_conf()
            book = S.fuel_book(fc)
            for r in rows:
                for k in ('cost_ev', 'price_kwh', 'cost_est', 'cost_ice', 'eq_l100', 'ice_saving', 'fuel_price'):
                    r[k] = None
                km, c = r.get('distance'), costs.get(r.get('id'))
                when = _p(r.get('start_date'))
                if c is None or not when or not km or km <= 0:
                    continue
                r['cost_ev'], r['price_kwh'], r['cost_est'] = round(c[0], 2), round(c[1], 3), c[2]
                day = when.replace(tzinfo=dt.timezone.utc).astimezone(_tz(S)).date().isoformat()
                fp, _ = S.fuel_lookup(book, day, fc['manual'])
                if fp:
                    r['fuel_price'] = round(fp, 3)
                    r['eq_l100'] = round(r['cost_ev'] / km * 100 / fp, 2)
                    if fc['l100'] > 0:
                        r['cost_ice'] = round(km / 100 * fc['l100'] * fp, 2)
                        r['ice_saving'] = round(r['cost_ice'] - r['cost_ev'], 2)
            return rows

    S.DRIVECOST = DriveCost()


def _tz(S):
    try:
        import zoneinfo
        return zoneinfo.ZoneInfo(S.LOCAL_TZ)
    except Exception:  # noqa
        return dt.timezone.utc

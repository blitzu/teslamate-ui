"""Raport "cat ar fi costat la PZU": costul incarcarilor de acasa la pretul orar (15 min) de pe piata pentru ziua urmatoare (PZU), comparat cu tariful tau fix
si cu varianta "incarcat in cele mai ieftine ore din noapte". Preturile vin de la energy-charts.info (Fraunhofer ISE, date EPEX/OPCOM, uz personal), cursul de la ECB (frankfurter.dev).
Pretul PZU e doar energie: o oferta dinamica adauga tarife de retea, taxe si TVA (setari: adaos pe kWh si TVA). Nu e o recomandare de a schimba contractul."""
import datetime as dt
import json
import re
import time

SLOT = 900                                  # 15 minute
CODES = {'lei': 'RON', 'ron': 'RON', '€': 'EUR', 'eur': 'EUR'}


def slot_energy(samples, max_gap=600):
    """samples: [(ts_unix, kW)]. Intoarce {inceput_slot: kWh} integrand puterea pe intervale (goluri > max_gap s se ignora)."""
    out = {}
    for (t0, p0), (t1, _) in zip(samples, samples[1:]):
        if t1 <= t0 or t1 - t0 > max_gap or not p0:
            continue
        t = t0
        while t < t1:
            s = int(t // SLOT) * SLOT
            e = min(t1, s + SLOT)
            out[s] = out.get(s, 0.0) + p0 * (e - t) / 3600
            t = e
    return out


def cost_of(energy, price_kwh, addon=0.0, vat=0.0):
    """energy {slot: kWh}, price_kwh(slot) -> pret local/kWh sau None. Intoarce (cost, kWh acoperite de preturi)."""
    cost = cov = 0.0
    for s, e in energy.items():
        p = price_kwh(s)
        if p is None:
            continue
        cost += e * (p + addon) * (1 + vat / 100)
        cov += e
    return cost, cov


def cheapest(total_kwh, slots, price_kwh, max_slot_kwh):
    """Umple total_kWh in cele mai ieftine sloturi (fiecare max max_slot_kWh). Intoarce {slot: kWh} sau None daca nu incap."""
    ranked = sorted((s for s in slots if price_kwh(s) is not None), key=price_kwh)
    left, out = total_kwh, {}
    for s in ranked:
        take = min(max_slot_kwh, left)
        if take <= 0:
            break
        out[s] = take
        left -= take
    return out if left <= 1e-6 else None


def init(S):
    S.OWN.migrate('pzu', ['create table pzu_prices (ts integer primary key, eur_mwh real not null)'])
    DEFAULT = dict(addon=0.0, vat=21.0, from_h=22, to_h=7)

    def cfg():
        c = dict(DEFAULT)
        c.update({k: v for k, v in (S.OWN.kv_get('pzu_cfg', {}) or {}).items() if k in DEFAULT})
        return c

    def tz():
        try:
            import zoneinfo
            return zoneinfo.ZoneInfo(S.LOCAL_TZ)
        except Exception:  # noqa
            return dt.timezone.utc

    def fetch_prices(day_a, day_b):
        """Completeaza in cache preturile pentru [day_a, day_b] (date UTC) care lipsesc."""
        have = {r['d'] for r in S.OWN.rows("select distinct date(ts, 'unixepoch') d from pzu_prices where ts >= ? and ts < ?",
                                           (int(dt.datetime(day_a.year, day_a.month, day_a.day, tzinfo=dt.timezone.utc).timestamp()), int(dt.datetime(day_b.year, day_b.month, day_b.day, tzinfo=dt.timezone.utc).timestamp()) + 86400))}
        d, need = day_a, []
        while d <= day_b:
            if d.isoformat() not in have or d >= dt.date.today():
                need.append(d)
            d += dt.timedelta(days=1)
        i = 0
        while i < len(need):
            chunk = need[i:i + 31]
            i += 31
            r = json.loads(S._get_text('https://api.energy-charts.info/price?bzn=RO&start=%s&end=%s' % (chunk[0].isoformat(), chunk[-1].isoformat()), 40))
            rows = [(int(t), float(p)) for t, p in zip(r.get('unix_seconds') or [], r.get('price') or []) if p is not None]
            if rows:
                S.OWN.many('insert into pzu_prices(ts, eur_mwh) values(?,?) on conflict(ts) do update set eur_mwh=excluded.eur_mwh', rows)

    def rate_for(day_a, day_b, code):
        """Curs EUR -> moneda pe zile (ultimul curs cunoscut pentru weekenduri)."""
        if code == 'EUR':
            return lambda d: 1.0
        cache = S.OWN.kv_get('fx_' + code, {}) or {}
        missing = [d for d in ((day_a + dt.timedelta(days=i)).isoformat() for i in range((day_b - day_a).days + 1)) if d not in cache]
        if missing:
            r = json.loads(S._get_text('https://api.frankfurter.dev/v1/%s..%s?base=EUR&symbols=%s' % (day_a.isoformat(), day_b.isoformat(), code), 30))
            got = {d: v[code] for d, v in (r.get('rates') or {}).items()}
            cache.update(got)
            if got:                                                    # weekendurile/sarbatorile nu apar in raspuns: le umplem cu ultimul curs, ca sa nu reinterogam la fiecare cerere
                last, top = None, max(got)
                for i in range((day_b - day_a).days + 1):
                    d = (day_a + dt.timedelta(days=i)).isoformat()
                    if d in cache:
                        last = cache[d]
                    elif last is not None and d < top:
                        cache[d] = last
            S.OWN.kv_set('fx_' + code, cache)
        keys = sorted(cache)

        def f(d):
            prev = [k for k in keys if k <= d]
            return cache[prev[-1]] if prev else (cache[keys[0]] if keys else 1.0)
        return f

    def analyze(car, days):
        c = cfg()
        code = CODES.get(str(S.CURRENCY).strip().lower(), '')
        if not code:
            raise ValueError('Moneda "%s" nu poate fi convertită automat.' % S.CURRENCY)
        today = dt.date.today()
        since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
        try:
            gprice = float(S.cget('price_grid', 'PRICE_GRID', '') or 0)
        except ValueError:
            gprice = 0
        sess = [r for r in S._charges_rows(car, 800, 0) if r['start_date'] >= since and not r['dc'] and (r['power_max'] or 0) <= 25 and re.search(r'acas|home', r['name'] or '', re.I)]
        if not sess:
            return dict(sessions=[], months=[], config=c, note='Nicio încărcare AC acasă în perioadă.')
        d0 = dt.datetime.fromisoformat(min(r['start_date'] for r in sess)).date() - dt.timedelta(days=1)
        try:
            fetch_prices(d0, today)
        except Exception as e:  # noqa
            S.log('pzu preturi: %s (folosesc ce am in cache)' % e)           # fara retea, sesiunile deja acoperite de cache se calculeaza in continuare
        try:
            rate = rate_for(d0, today, code)
        except Exception as e:  # noqa
            S.log('pzu curs: %s (folosesc ce am in cache)' % e)
            cache_fx = S.OWN.kv_get('fx_' + code, {}) or {}
            keys_fx = sorted(cache_fx)
            rate = lambda d: next((cache_fx[k] for k in reversed(keys_fx) if k <= d), cache_fx[keys_fx[0]] if keys_fx else 1.0)
        prices = {r['ts']: r['eur_mwh'] for r in S.OWN.rows('select ts, eur_mwh from pzu_prices where ts >= ?', (int(dt.datetime(d0.year, d0.month, d0.day, tzinfo=dt.timezone.utc).timestamp()),))}

        def price_kwh(slot):
            p = prices.get(slot)
            if p is None:
                p = prices.get(slot - slot % 3600)                      # preturi orare (date mai vechi): valabile pentru toate sferturile orei
            return None if p is None else p / 1000 * rate(dt.datetime.fromtimestamp(slot, dt.timezone.utc).strftime('%Y-%m-%d'))
        out, z = [], tz()
        for r in sess:
            if not r['end_date']:
                continue
            rows = S.q('select date, charger_power from charges where charging_process_id=%s order by date', (r['id'],))
            samples = [(dt.datetime.fromisoformat(x['date']).replace(tzinfo=dt.timezone.utc).timestamp(), x['charger_power'] or 0) for x in rows]
            energy = slot_energy(samples)
            wall = sum(energy.values())
            if wall < 0.5:
                continue
            pzu, cov = cost_of(energy, price_kwh)
            tot, _ = cost_of(energy, price_kwh, c['addon'], c['vat'])
            start_local = dt.datetime.fromisoformat(r['start_date']).replace(tzinfo=dt.timezone.utc).astimezone(z)
            dur = dt.timedelta(hours=(int(c['to_h']) - int(c['from_h'])) % 24 or 24)             # 22->7 = 9 h, 0->7 = 7 h (nu 31 h)
            base = start_local.replace(hour=int(c['from_h']), minute=0, second=0, microsecond=0)
            cands = [base - dt.timedelta(days=1), base, base + dt.timedelta(days=1)]
            night0 = next((x for x in cands if x <= start_local < x + dur), None) or next(x for x in cands if x > start_local)     # fereastra in care incepe sesiunea, sau prima urmatoare
            night1 = night0 + dur
            slots = range(int(night0.timestamp() // SLOT * SLOT), int(night1.timestamp()), SLOT)
            pmax = max([p for _, p in samples] or [3.7]) or 3.7
            best = cheapest(wall, slots, price_kwh, pmax * SLOT / 3600)
            opt = cost_of(best, price_kwh, c['addon'], c['vat'])[0] if best else None
            fixed = wall * (gprice or float(r.get('tariff') or 0))
            out.append(dict(id=r['id'], start=r['start_date'], kwh=round(wall, 2), real=r.get('cost') if r.get('cost') is not None else None, fixed=round(fixed, 2), pzu=round(pzu, 2), pzu_total=round(tot, 2),
                            optimal=None if opt is None else round(opt, 2), avg_pzu=round(pzu / cov, 3) if cov else None, covered=round(cov / wall, 2)))
        months = {}
        for s in out:
            if s['covered'] < 0.9:
                continue
            m = months.setdefault(s['start'][:7], dict(month=s['start'][:7], n=0, kwh=0.0, fixed=0.0, pzu=0.0, pzu_total=0.0, optimal=0.0, opt_n=0))
            m['n'] += 1
            m['kwh'] += s['kwh']
            m['fixed'] += s['fixed']
            m['pzu'] += s['pzu']
            m['pzu_total'] += s['pzu_total']
            if s['optimal'] is not None:
                m['optimal'] += s['optimal']
                m['opt_n'] += 1
        for m in months.values():
            for k in ('kwh', 'fixed', 'pzu', 'pzu_total', 'optimal'):
                m[k] = round(m[k], 2)
        return dict(sessions=sorted(out, key=lambda x: x['start'], reverse=True), months=sorted(months.values(), key=lambda m: m['month'], reverse=True), config=c, currency=code, fixed_price=gprice or None)

    S.PZU = analyze

    @S.route('GET', '/api/pzu')
    def api(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        if hc is False:
            return dict(sessions=[], months=[], config=cfg(), note='În demo nu există încărcări reale.')
        try:
            return analyze(int(a.get('car', 1)), max(7, min(int(a.get('days', 90)), 365)))
        except ValueError as e:
            return dict(sessions=[], months=[], config=cfg(), note=str(e))
        except Exception as e:  # noqa
            S.log('pzu: %s' % e)
            return dict(sessions=[], months=[], config=cfg(), note='Nu pot citi prețurile PZU acum (%s).' % str(e)[:80])

    @S.route('POST', '/api/pzu/config', pin=True, role='admin')
    def set_cfg(h, b):
        c = dict(addon=max(0.0, min(float(b.get('addon', 0)), 10)), vat=max(0.0, min(float(b.get('vat', 21)), 40)), from_h=max(0, min(int(b.get('from_h', 22)), 23)), to_h=max(0, min(int(b.get('to_h', 7)), 23)))
        S.OWN.kv_set('pzu_cfg', c)
        return dict(ok=True, config=c)

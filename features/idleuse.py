"""Consum in afara condusului: cat costa celelalte functii care folosesc energie cand masina sta (climatizare / preincalzire habitaclu, incalzirea bateriei, Sentry,
masina treaza fara motiv, somn). Nu exista un contor pentru fiecare functie, asa ca energia se scoate din ce se vede in baza TeslaMate:

  - intre doua puncte consecutive in care masina NU conduce si NU se incarca, energia consumata = (autonomia ideala de la inceput - cea de la sfarsit) x eficienta masinii
    (aceeasi formula cu care TeslaMate calculeaza kWh-ul unei curse);
  - punctele sunt pozitiile din staționare (la ~5 min cand masina e treaza) plus capetele curselor si incarcarilor; cand masina doarme nu exista pozitii, iar tot intervalul
    de somn e un singur segment;
  - fiecare segment e atribuit dupa steagurile de la capete (clima pornita, incalzirea bateriei) si dupa intervalele Sentry din jurnalul de evenimente; ce ramane e
    "treaza" (masina online, fara nimic activ) sau "somn" (segment lung fara pozitii).
Rezultatele sunt estimari: autonomia ideala se schimba in pasi de ~0,16 km (~0,02 kWh), deci un segment de 5 minute are zgomot, dar suma pe zile si saptamani e stabila."""
import bisect
import datetime as dt
import time

from features.sleepguard import intervals_from_events, merge

GAP_S = 20 * 60               # peste atat intre doua puncte masina doarme / e oprita (TeslaMate nu mai are pozitii)
EDGE_S = 2                    # toleranta la marginea unei curse / incarcari (secunde)
OPEN_MAX_S = 24 * 3600        # o incarcare "neinchisa" nu poate tine mai mult
PLUG_ADDED_KWH = 0.15          # o "incarcare" care a adaugat mai putin de atat in baterie e masina conectata, nu o incarcare
MAX_KW = 12.0                # o masina parcata nu trage atat: segmentul e semn de ceva nemasurat (cursa lipsa, reset de autonomie) si se numara separat
CATS = ('climate', 'heater', 'both', 'sentry', 'awake', 'sleep')


def _cover(a, b, iv, starts):
    """Secundele din [a, b] acoperite de intervalele `iv` (sortate, fara suprapuneri; `starts` = capetele lor de inceput)."""
    if b <= a or not iv:
        return 0.0
    tot = 0.0
    i = max(0, bisect.bisect_right(starts, a) - 1)
    while i < len(iv) and iv[i][0] < b:
        tot += max(0.0, min(b, iv[i][1]) - max(a, iv[i][0]))
        i += 1
    return tot


def split_segment(dt_s, wc, wh, sf, asleep):
    """Cum se imparte un segment: {categorie: fractiune} cu suma 1. wc/wh = partea de clima / incalzire baterie (0..1), sf = partea acoperita de Sentry, asleep = segment lung."""
    both = min(wc, wh)                                   # clima si incalzirea bateriei in acelasi timp: semnalele nu spun cat a consumat fiecare, deci nu se imparte
    wc, wh = wc - both, wh - both
    rest = max(0.0, 1.0 - wc - wh - both)
    out = {'climate': wc, 'heater': wh, 'both': both, 'sentry': rest * sf}
    out['sleep' if asleep else 'awake'] = rest * (1 - sf)
    return out


def analyze(samples, busy, sentry, eff, lo=None, hi=None, tz_offset=lambda t: 0, trace=None, plug=()):
    """samples: [(t, autonomie_km, clima, incalzire)] pozitii din afara curselor/incarcarilor (momente UNIX, sortate); busy: [(inceput, sfarsit|None, autonomie_start, autonomie_sfarsit)]
    curse si incarcari (sfarsit None = in curs); sentry: [[inceput, sfarsit]]; eff = kWh pe km de autonomie ideala. Se numara segmentele care incep in [lo, hi).
    plug: [(inceput, sfarsit, autonomie_start, autonomie_sfarsit, kWh_din_retea)] = "incarcari" fara energie adaugata (TeslaMate inregistreaza asa preincalzirea cand masina e la
    incarcator): ramane staționare, iar la energia din baterie se adauga ce a venit din retea in acel interval.
    Intoarce {cats: {cat: {kwh, hours}}, by_day: {zi: {cat: kwh}}, kwh, hours, skipped_kwh, skipped_n, first, last}."""
    busy = sorted(busy, key=lambda b: b[0])
    for i, (t0, t1, r0, r1) in enumerate(busy):
        if t1 is None:                                   # TeslaMate lasa uneori procese de incarcare neinchise: se opresc la urmatoarea activitate (cel mult 24 h)
            busy[i] = (t0, min(t0 + OPEN_MAX_S, busy[i + 1][0]) if i + 1 < len(busy) else t0 + OPEN_MAX_S, r0, None)
    starts = [b[0] for b in busy]
    ends_max = []                                        # sfarsitul maxim pana la fiecare element, ca sa gasim repede o cursa care acopera un moment
    m = 0.0
    for b in busy:
        m = max(m, b[1])
        ends_max.append(m)

    def inside(t):                                       # TeslaMate scrie pozitia de start chiar in secunda in care deschide cursa/incarcarea
        i = bisect.bisect_right(starts, t + EDGE_S) - 1
        return i >= 0 and ends_max[i] >= t

    anch = [(t, r, 'park', bool(c), bool(h)) for t, r, c, h in samples if r is not None and not inside(t)]
    for t0, t1, r0, r1 in busy:
        if r0 is not None:
            anch.append((t0, r0, 'start', False, False))
        if r1 is not None:
            anch.append((t1, r1, 'end', False, False))
    s_t = [x[0] for x in samples]
    for t0, t1, r0, r1, _ in plug:                       # capetele lor, daca nu exista deja o pozitie langa ele
        for t, r in ((t0, r0), (t1, r1)):
            i = bisect.bisect_left(s_t, t - 90)
            if r is not None and not (i < len(s_t) and s_t[i] <= t + 90) and not inside(t):
                anch.append((t, r, 'park', False, False))
    anch.sort(key=lambda a: (a[0], 0 if a[2] == 'end' else 1))
    sentry = merge([list(x) for x in sentry])
    s_starts = [x[0] for x in sentry]
    cats = {c: dict(kwh=0.0, hours=0.0) for c in CATS}
    by_day = {}
    skipped = skipped_n = 0
    first = last = None
    for a, b in zip(anch, anch[1:]):
        if a[2] == 'start' or b[2] == 'end':             # in interiorul unei curse / incarcari
            continue
        if (lo is not None and a[0] < lo) or (hi is not None and a[0] >= hi):
            continue
        dts = b[0] - a[0]
        if dts <= 0:
            continue
        if bisect.bisect_left(starts, b[0] - 1) - bisect.bisect_right(starts, a[0] + 1) > 0:      # o cursa pornește în interior, dar fără capăt de autonomie: nu putem ști
            continue
        e = (a[1] - b[1]) * eff
        for p0, p1, _, _, g in plug:                     # energia venita din retea in timpul acestui segment (clima pornita la incarcator)
            ov = min(b[0], p1) - max(a[0], p0)
            if ov > 0 and p1 > p0:
                e += g * ov / (p1 - p0)
        if trace is not None:
            trace.append((a[0], b[0], a[2], b[2], round(e, 3)))
        if e > MAX_KW * dts / 3600:
            skipped += e
            skipped_n += 1
            continue
        asleep = dts > GAP_S
        wc = 0.0 if asleep else (a[3] + b[3]) / 2
        wh = 0.0 if asleep else (a[4] + b[4]) / 2
        sf = _cover(a[0], b[0], sentry, s_starts) / dts
        parts = split_segment(dts, wc, wh, sf, asleep)
        first = a[0] if first is None else first
        last = b[0]
        cur = a[0]
        while cur < b[0]:                                # impartire pe zile locale, proportional cu timpul
            off = tz_offset(cur)
            day_end = (int(cur + off) // 86400 + 1) * 86400 - off
            end = min(b[0], day_end)
            share = (end - cur) / dts
            day = dt.datetime.fromtimestamp(cur + off, dt.timezone.utc).strftime('%Y-%m-%d')
            d = by_day.setdefault(day, {c: 0.0 for c in CATS})
            for c, f in parts.items():
                d[c] += e * f * share
                cats[c]['kwh'] += e * f * share
                cats[c]['hours'] += dts * f * share / 3600
            cur = end
    for c in cats.values():                              # zgomotul de masurare poate da cateva sutimi negative pe o categorie
        c['kwh'] = max(0.0, c['kwh'])
    return dict(cats=cats, by_day=by_day, kwh=sum(c['kwh'] for c in cats.values()), hours=sum(c['hours'] for c in cats.values()), skipped_kwh=skipped, skipped_n=skipped_n, first=first, last=last)


def summarize(res, price=None, driving_kwh=None):
    """Din rezultatul `analyze` face lista pentru ecran: kWh, ore, kW mediu, cost, pondere, cat e peste ce ar consuma masina doar dormind, proiectie la 30 de zile."""
    c = res['cats']
    sleep_kw = c['sleep']['kwh'] / c['sleep']['hours'] if c['sleep']['hours'] > 1 else None
    days = (res['last'] - res['first']) / 86400 if res['first'] is not None and res['last'] is not None else 0
    tot = res['kwh']
    out = []
    for k in CATS:
        x = c[k]
        kw = x['kwh'] / x['hours'] if x['hours'] > 0.05 else None
        extra = max(0.0, x['kwh'] - x['hours'] * sleep_kw) if sleep_kw is not None and k != 'sleep' else None
        out.append(dict(key=k, kwh=round(x['kwh'], 2), hours=round(x['hours'], 1), kw=None if kw is None else round(kw, 2), pct=round(x['kwh'] / tot * 100) if tot > 0 else None,
                        cost=None if price is None else round(x['kwh'] * price, 2), extra_kwh=None if extra is None else round(extra, 2),
                        extra_cost=None if extra is None or price is None else round(extra * price, 2),
                        per30_kwh=round(x['kwh'] / days * 30, 1) if days >= 2 else None, per30_cost=round(x['kwh'] / days * 30 * price, 2) if days >= 2 and price is not None else None))
    return dict(cats=out, kwh=round(tot, 2), hours=round(res['hours'], 1), cost=None if price is None else round(tot * price, 2), days=round(days, 1), price=None if price is None else round(price, 3),
                sleep_kw=None if sleep_kw is None else round(sleep_kw, 3), driving_kwh=None if driving_kwh is None else round(driving_kwh, 1),
                idle_share=round(tot / (tot + driving_kwh) * 100) if driving_kwh and tot + driving_kwh > 0 else None,
                skipped_kwh=round(res['skipped_kwh'], 2), skipped_n=res['skipped_n'])


def init(S):
    def tzoff():
        try:
            import zoneinfo
            z = zoneinfo.ZoneInfo(S.LOCAL_TZ)
            return lambda t: int(dt.datetime.fromtimestamp(t, z).utcoffset().total_seconds())
        except Exception:  # noqa
            return lambda t: 0

    def load(car, lo, hi):
        """Date brute din TeslaMate pentru [lo, hi): pozitii din staționare, curse + incarcari (cu o marja, ca sa existe capetele din jurul perioadei), eficienta."""
        now = time.time()
        P = lambda x: x.replace(tzinfo=dt.timezone.utc).timestamp()
        pad = dt.timedelta(days=3)
        wlo = lo - pad if lo else None
        whi = (hi + pad) if hi else None
        eff = (S.q('select efficiency e from cars where id=%s', (car,)) or [{}])[0].get('e') or 0.15
        sp, bp = ['car_id = %s', 'drive_id is null', 'ideal_battery_range_km is not null'], [car]
        if wlo:
            sp.append('date >= %s')
            bp.append(wlo)
        if whi:
            sp.append('date < %s')
            bp.append(whi)
        samples = [(float(r['t']), float(r['r']), bool(r['c']), bool(r['h'])) for r in S.q(
            'select extract(epoch from date) t, ideal_battery_range_km r, is_climate_on c, battery_heater h from positions where ' + ' and '.join(sp) + ' order by date', tuple(bp))]
        busy, plug = [], []
        for tab in ('drives', 'charging_processes'):
            sel, par = ['car_id = %s'], [car]
            if wlo:
                sel.append('(end_date is null or end_date >= %s)')
                par.append(wlo)
            if whi:
                sel.append('start_date < %s')
                par.append(whi)
            extra = ', charge_energy_added ea, charge_energy_used eu' if tab == 'charging_processes' else ''
            for r in S.q('select start_date a, end_date b, start_ideal_range_km ra, end_ideal_range_km rb' + extra + ' from ' + tab + ' where ' + ' and '.join(sel), tuple(par)):
                a = P(dt.datetime.fromisoformat(str(r['a']))) if r['a'] else None
                if a is None:
                    continue
                b = P(dt.datetime.fromisoformat(str(r['b']))) if r['b'] else None
                ra, rb = (None if r['ra'] is None else float(r['ra'])), (None if r['rb'] is None else float(r['rb']))
                if tab == 'charging_processes' and b is not None and r['ea'] is not None and float(r['ea']) < PLUG_ADDED_KWH:
                    plug.append((a, b, ra, rb, float(r['eu'] or 0)))          # nu a incarcat nimic: e doar masina conectata (de obicei preincalzire)
                else:
                    busy.append((a, b, ra, rb))
        since = P(lo) if lo else 0
        ev = [(x['ts'], x['new']) for x in S.OWN.rows('select ts, new from events where key=? and car=? and ts >= ? order by ts', ('sentry_mode', car, since - 86400))]
        prev = S.OWN.one('select ts, new from events where key=? and car=? and ts < ? order by ts desc limit 1', ('sentry_mode', car, since - 86400))
        sentry = intervals_from_events(([(prev['ts'], prev['new'])] if prev else []) + ev, 'True', now)
        return samples, busy, sentry, float(eff), plug

    def price_and_driving(car, lo, hi):
        """(pret mediu pe kWh din baterie in perioada, kWh condusi in perioada) - pretul vine din costul curselor (FIFO din drivecost)."""
        try:
            ds = S.drives(car, 100000, 0, lo, hi)
        except Exception:  # noqa
            return None, None
        km = sum(float(d['kwh']) for d in ds if d.get('kwh') and d['kwh'] > 0)
        dc = getattr(S, 'DRIVECOST', None)
        try:
            costs = dc.costs(car, False) if dc else {}
        except Exception:  # noqa
            costs = {}
        num = den = 0.0
        for d in ds:
            c = costs.get(d['id']) if costs else None
            if c and d.get('kwh') and d['kwh'] > 0:
                num += c[0]
                den += float(d['kwh'])
        return (num / den if den > 1 else None), km

    @S.route('GET', '/api/idleuse')
    def api(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        if hc is False:
            return dict(empty=True)
        car = int(a.get('car', 1))
        lo, hi, _ = S.list_filters(a, 'drive')
        samples, busy, sentry, eff, plug = load(car, lo, hi)
        P = lambda x: x.replace(tzinfo=dt.timezone.utc).timestamp()
        res = analyze(samples, busy, sentry, eff, P(lo) if lo else None, P(hi) if hi else None, tzoff(), plug=plug)
        price, driving = price_and_driving(car, lo, hi)
        out = summarize(res, price, driving)
        out['by_day'] = [dict(day=d, **{c: round(v[c], 2) for c in CATS}) for d, v in sorted(res['by_day'].items())][-400:]
        out['eff'] = round(eff, 4)
        out['period'] = dict(from_=lo.isoformat() if lo else None, to=hi.isoformat() if hi else None)
        return out

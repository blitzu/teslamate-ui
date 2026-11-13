"""Statistici de consum (#/usage): cat consuma masina (Wh/km) pe ultimele X zile sau pe ultimii X km, comparat cu perioada anterioara si cu consumul nominal,
impartit pe temperatura exterioara, viteza medie si evolutie in timp. Energia unei curse = diferenta de autonomie ideala x eficienta masinii (ca peste tot in aplicatie)."""
import datetime as dt

MIN_KM = 1.0                                   # cursele mai scurte nu intra in raportul Wh/km (zgomot)
MAX_WH_KM = 1500.0                             # peste asta e o masuratoare gresita (autonomia sare cand masina se trezeste)
RANK_KM = 10.0                                 # clasamentul celor mai bune / mai rele curse ia doar curse de cel putin atat (pe cele scurte autonomia ideala e prea aproximativa)
TEMP_B = [(-99, 0), (0, 10), (10, 20), (20, 30), (30, 99)]
SPEED_B = [(0, 30), (30, 50), (50, 80), (80, 110), (110, 999)]
MAX_DAYS, MAX_KM = 3650, 200000


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _when(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace('Z', '')).replace(tzinfo=None)
    except ValueError:
        return None


def prepare(rows):
    """Randuri de curse (din S.drives) -> cursele cu masuratori valide, cu Wh/km si viteza medie calculate."""
    out = []
    for r in rows:
        km, kwh, when = _f(r.get('distance')), _f(r.get('kwh')), _when(r.get('start_date'))
        if km is None or when is None:
            continue
        d = dict(id=r.get('id'), when=when, km=km, kwh=kwh, minutes=_f(r.get('duration_min')), temp=_f(r.get('outside_temp_avg')),
                 start=r.get('start_name'), end=r.get('end_name'), cost=None, valid=False)
        if kwh is not None and kwh > 0 and km >= MIN_KM and kwh * 1000 / km <= MAX_WH_KM:
            d['valid'] = True
            d['wh_km'] = kwh * 1000 / km
        d['speed'] = km / (d['minutes'] / 60) if d['minutes'] and d['minutes'] > 0 else None
        out.append(d)
    return out


def window(drives, mode, n, now):
    """(curente, anterioare): ultimele n zile / ultimii n km si fereastra de aceeasi marime dinaintea lor. drives: cele mai noi primele."""
    if mode == 'km':
        cur, prev, acc = [], [], 0.0
        for d in drives:
            if acc < n:
                cur.append(d)
            elif acc < 2 * n:
                prev.append(d)
            else:
                break
            acc += d['km']
        return cur, prev
    lo, lo2 = now - dt.timedelta(days=n), now - dt.timedelta(days=2 * n)
    return [d for d in drives if d['when'] >= lo], [d for d in drives if lo2 <= d['when'] < lo]


def totals(ds):
    v = [d for d in ds if d['valid']]
    km, kwh = sum(d['km'] for d in v), sum(d['kwh'] for d in v)
    return dict(n=len(ds), n_valid=len(v), km=km, kwh=kwh, wh_km=kwh * 1000 / km if km > 0 else None)


def group(ds, bounds, key):
    out = []
    for lo, hi in bounds:
        v = [d for d in ds if d['valid'] and d.get(key) is not None and lo <= d[key] < hi]
        t = totals(v)
        out.append(dict(lo=lo, hi=hi, n=t['n'], km=round(t['km'], 1), kwh=round(t['kwh'], 2), wh_km=round(t['wh_km']) if t['wh_km'] else None))
    return out


def local_day(when, tz):
    if tz is None:
        return when.strftime('%Y-%m-%d')
    return when.replace(tzinfo=dt.timezone.utc).astimezone(tz).strftime('%Y-%m-%d')


def trend(ds, tz, by_week):
    """Consum pe zi (sau pe saptamana cand perioada e lunga), in ordine cronologica."""
    acc = {}
    for d in ds:
        if not d['valid']:
            continue
        day = local_day(d['when'], tz)
        k = day
        if by_week:
            x = dt.date.fromisoformat(day)
            k = (x - dt.timedelta(days=x.weekday())).isoformat()             # luni = inceputul saptamanii
        a = acc.setdefault(k, [0.0, 0.0])
        a[0] += d['km']
        a[1] += d['kwh']
    return [dict(day=k, km=round(a[0], 1), wh_km=round(a[1] * 1000 / a[0]) if a[0] > 0 else None) for k, a in sorted(acc.items())]


def summarize(rows, mode, n, now, eff=None, tz=None, costs=None):
    drives = sorted(prepare(rows), key=lambda d: d['when'], reverse=True)
    cur, prev = window(drives, mode, n, now)
    if costs:
        for d in cur:
            c = costs.get(d['id'])
            d['cost'] = c[0] if c else None
    t, p = totals(cur), totals(prev)
    out = dict(mode=mode, n=n, drives=t['n'], used_drives=t['n_valid'], skipped=t['n'] - t['n_valid'])
    if not cur:
        return dict(out, empty_window=True)
    valid = [d for d in cur if d['valid']]
    hours = sum(d['minutes'] for d in valid if d['minutes']) / 60
    first, last = min(d['when'] for d in cur), max(d['when'] for d in cur)
    rated = eff * 1000 if eff else None
    priced = [d for d in valid if d['cost'] is not None]
    pkm, pkwh = sum(d['km'] for d in priced), sum(d['kwh'] for d in priced)
    out.update(km=round(t['km'], 1), kwh=round(t['kwh'], 2), wh_km=round(t['wh_km']) if t['wh_km'] else None, kwh_100=round(t['kwh'] / t['km'] * 100, 1) if t['km'] > 0 else None,
               rated_wh_km=round(rated) if rated else None, vs_rated_pct=round((t['wh_km'] / rated - 1) * 100) if rated and t['wh_km'] else None,
               avg_speed=round(t['km'] / hours) if hours > 0 else None, avg_trip_km=round(t['km'] / t['n_valid'], 1) if t['n_valid'] else None,
               hours=round(hours, 1), from_=first.isoformat(), to=last.isoformat(),
               span_days=max(1, (last.date() - first.date()).days + 1),
               cost=round(sum(d['cost'] for d in priced), 2) if priced else None,
               cost_100=round(sum(d['cost'] for d in priced) / pkm * 100, 2) if priced and pkm > 0 else None,
               price_kwh=round(sum(d['cost'] for d in priced) / pkwh, 3) if priced and pkwh > 0 else None)
    out['prev'] = dict(km=round(p['km'], 1), wh_km=round(p['wh_km']) if p['wh_km'] else None,
                       delta_pct=round((t['wh_km'] / p['wh_km'] - 1) * 100) if t['wh_km'] and p['wh_km'] else None)
    out['by_temp'] = group(valid, TEMP_B, 'temp')
    out['by_speed'] = group(valid, SPEED_B, 'speed')
    out['trend'] = trend(cur, tz, out['span_days'] > 45)
    far = [d for d in valid if d['km'] >= RANK_KM]
    far.sort(key=lambda d: d['wh_km'])

    def brief(d):
        return dict(id=d['id'], when=d['when'].isoformat(), km=round(d['km'], 1), wh_km=round(d['wh_km']), temp=None if d['temp'] is None else round(d['temp']),
                    speed=None if d['speed'] is None else round(d['speed']), start=d['start'], end=d['end'])
    out['best'] = [brief(d) for d in far[:3]]
    out['worst'] = [brief(d) for d in far[::-1][:3] if d not in far[:3]]
    return out


def init(S):
    @S.route('GET', '/api/usage')
    def api(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        if hc is False:
            return dict(empty=True)
        car = int(a.get('car', 1))
        mode = 'km' if a.get('mode') == 'km' else 'days'
        try:
            n = int(float(a.get('n') or (30 if mode == 'days' else 500)))
        except ValueError:
            n = 30 if mode == 'days' else 500
        n = max(1, min(n, MAX_KM if mode == 'km' else MAX_DAYS))
        now = dt.datetime.utcnow().replace(microsecond=0)
        lo = now - dt.timedelta(days=2 * n) if mode == 'days' else None             # in modul "km" luam cele mai noi curse si ne oprim cand avem destui km
        rows = S.drives(car, 100000 if mode == 'days' else 5000, 0, lo, None)
        eff = (S.q('select efficiency e from cars where id=%s', (car,)) or [{}])[0].get('e')
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(S.LOCAL_TZ)
        except Exception:  # noqa
            tz = None
        dc = getattr(S, 'DRIVECOST', None)
        try:
            costs = dc.costs(car, False) if dc else {}
        except Exception:  # noqa
            costs = {}
        return summarize(rows, mode, n, now, float(eff) if eff else None, tz, costs)

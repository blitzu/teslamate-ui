"""Calatorii: cursele separate de pauze scurte (< gap) se grupeaza intr-o singura calatorie, cu opririle si incarcarile dintre ele.
Aceeasi pauza (setare) e folosita si de reluarea 3D a traseului, ca lista si reluarea sa arate acelasi lant de curse."""
import datetime as dt
import time


def parse(s):
    return dt.datetime.fromisoformat(s) if s else None


def group(drives, charges, gap):
    """drives: lista de curse (cu start_date/end_date ISO); charges: incarcari; gap: timedelta. Intoarce calatoriile, cele mai noi primele."""
    ds = sorted((d for d in drives if d.get('end_date')), key=lambda d: d['start_date'])
    groups, cur = [], []
    for d in ds:
        if cur and parse(d['start_date']) - parse(cur[-1]['end_date']) >= gap:
            groups.append(cur)
            cur = []
        cur.append(d)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        a, b = parse(g[0]['start_date']), parse(g[-1]['end_date'])
        ch = [c for c in charges if c.get('end_date') and a <= parse(c['start_date']) <= b]
        km = sum(d.get('distance') or 0 for d in g)
        kwh = sum(d.get('kwh') or 0 for d in g)
        stops = []
        for x, y in zip(g, g[1:]):
            n = y.get('start_name')
            if n and n != '—' and n not in stops:
                stops.append(n)
        out.append(dict(id=g[0]['id'], start=g[0]['start_date'], end=g[-1]['end_date'], n_drives=len(g), km=round(km, 1), drive_min=round(sum(d.get('duration_min') or 0 for d in g)),
                        total_min=round((b - a).total_seconds() / 60), kwh=round(kwh, 1), wh_km=round(kwh * 1000 / km) if km > 0 and kwh else None,
                        start_name=g[0].get('start_name'), end_name=g[-1].get('end_name'), stops=stops[:6], speed_max=max((d.get('speed_max') or 0 for d in g), default=0),
                        n_charges=len(ch), charge_kwh=round(sum(c.get('charge_energy_added') or 0 for c in ch), 1),
                        charge_cost=round(sum((c.get('cost_eff') if c.get('cost_eff') is not None else c.get('cost')) or 0 for c in ch), 2), drive_ids=[d['id'] for d in g]))
    out.sort(key=lambda t: t['start'], reverse=True)
    return out


def init(S):
    def set_gap(h):
        S.TRIP_GAP = dt.timedelta(hours=h)

    gh = S.OWN.kv_get('trip_gap_h', 2)
    set_gap(gh if gh in (1, 2, 3, 4, 6, 12) else 2)

    @S.route('GET', '/api/trips')
    def list_trips(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        days = max(1, min(int(a.get('days', 90)), 730))
        since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
        car = int(a.get('car', 1))
        if hc is False:
            drives = [d for d in S.DEMO['drives']]
            charges = S.decorate([dict(c) for c in S.DEMO['charges']])
        else:
            drives = S.drives(car, 5000, 0, dt.datetime.fromisoformat(since))
            charges = S.charges(car, 3000, 0, None, dt.datetime.fromisoformat(since))
        trips = group(drives, charges, S.TRIP_GAP)
        return dict(gap_h=int(S.TRIP_GAP.total_seconds() // 3600), trips=trips)

    @S.route('POST', '/api/trips/gap', pin=True, role='admin')
    def gap(h, b):
        v = int(b.get('hours', 2))
        if v not in (1, 2, 3, 4, 6, 12):
            raise ValueError('pauza: 1, 2, 3, 4, 6 sau 12 ore')
        S.OWN.kv_set('trip_gap_h', v)
        set_gap(v)
        return dict(ok=True, gap_h=v)

    @S.route('GET', '/api/trips/detail')
    def detail(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        did = int(a['id'])
        car = int(a.get('car', 1))
        data = S.demo_trip(did) if hc is False else S.trip(car, did)
        ids = [s['drive']['id'] for s in data['segments'] if s.get('drive')]
        # fara punctele complete in lista de curse; harta primeste punctele deja esantionate de trip()
        return dict(segments=data['segments'], stops=data['stops'], ids=ids)

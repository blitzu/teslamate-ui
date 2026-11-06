"""Sugestii de calatorii similare pentru comparatie: aceeasi plecare si aceeasi sosire (la cel mult ~1 km, si in sens invers), distanta apropiata, cu insigne
"acelasi drum" / "alt drum" (cat se suprapun traseele GPS) si cu perioada anului si temperatura fata de calatoria aleasa. Nu scrie nimic; totul vine din cursele TeslaMate."""
import datetime as dt
import math
import time

from .trips import group

RADIUS_KM = 1.0              # plecarea si sosirea la cel mult atat una de alta
KM_TOL = 0.20                # distanta totala +-20%
MAX_RESULTS = 12
SAME_ROAD = 0.80             # peste atat din traseu se suprapune => "acelasi drum"
NEAR_M = 300                 # un punct e "pe acelasi drum" daca e la sub 300 m de celalalt traseu
PATH_PTS = 100
_paths = {}


def hav_km(a, b, c, d):
    r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742 * math.asin(min(1, math.sqrt(x)))


def doy_gap(a, b):
    """Diferenta in zile intre doua date, ca perioada a anului (decembrie e aproape de ianuarie); 0..182."""
    da, db = a.timetuple().tm_yday, b.timetuple().tm_yday
    d = abs(da - db)
    return min(d, 365 - d)


def _pt(t, k):
    return t.get(k + '_lat'), t.get(k + '_lon')


def candidates(main, trips, radius=RADIUS_KM):
    """Calatoriile cu plecare si sosire apropiate de ale celei alese (si in sens invers) si distanta apropiata; ordonate dupa cat de aproape sunt, apoi dupa perioada anului."""
    ma, mb = _pt(main, 'a'), _pt(main, 'b')
    if None in ma + mb or not (main.get('km') or 0) >= 1:
        return []
    ms = dt.datetime.fromisoformat(str(main['start'])[:19])
    out = []
    for t in trips:
        if t['id'] == main['id']:
            continue
        ta, tb = _pt(t, 'a'), _pt(t, 'b')
        if None in ta + tb:
            continue
        fa, fb = hav_km(*ma, *ta), hav_km(*mb, *tb)
        ra, rb = hav_km(*ma, *tb), hav_km(*mb, *ta)
        same = max(fa, fb) <= max(ra, rb) + 0.05                          # la bucle (plecare = sosire) ambele sensuri se potrivesc la fel: ramane sensul normal
        d1, d2 = (fa, fb) if same else (ra, rb)
        if max(d1, d2) > radius:
            continue
        dk = (t['km'] - main['km']) / main['km']
        if abs(dk) > KM_TOL:
            continue
        ts = dt.datetime.fromisoformat(str(t['start'])[:19])
        season = doy_gap(ms, ts)
        score = (d1 + d2) / (2 * radius) + abs(dk) / KM_TOL * 0.5 + season / 182 * 0.7          # mai aproape = mai bine; aceeasi perioada a anului mai sus
        out.append(dict(id=t['id'], start=t['start'], end=t['end'], start_name=t.get('start_name'), end_name=t.get('end_name'), km=t['km'], dkm=round(dk * 100, 1), kwh=t.get('kwh'),
                        wh_km=t.get('wh_km'), total_min=t.get('total_min'), n_drives=t.get('n_drives'), n_charges=t.get('n_charges'), temp=t.get('temp'),
                        dtemp=round(t['temp'] - main['temp'], 1) if t.get('temp') is not None and main.get('temp') is not None else None,
                        season_days=season, reverse=not same, d_start_m=round(d1 * 1000), d_end_m=round(d2 * 1000), score=round(score, 3),
                        year_ago=(ms - ts).days // 365 if ms > ts else 0))
    out.sort(key=lambda x: x['score'])
    return out


def _seg_dist_m(p, a, b, kx):
    """Distanta in metri de la p la segmentul a-b (proiectie locala, suficient de buna pentru zeci de km)."""
    ax, ay, bx, by, px, py = a[1] * kx, a[0] * 111320.0, b[1] * kx, b[0] * 111320.0, p[1] * kx, p[0] * 111320.0
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def share_near(pts, line, near=NEAR_M):
    """Cat din punctele `pts` (0..1) sunt la sub `near` metri de linia `line`."""
    if len(pts) < 2 or len(line) < 2:
        return 0.0
    kx = 111320.0 * math.cos(math.radians(pts[len(pts) // 2][0]))
    hit = 0
    for p in pts:
        best = 1e12
        for a, b in zip(line, line[1:]):
            if min(a[0], b[0]) - 0.01 > p[0] or max(a[0], b[0]) + 0.01 < p[0] or min(a[1], b[1]) - 0.015 > p[1] or max(a[1], b[1]) + 0.015 < p[1]:
                continue
            d = _seg_dist_m(p, a, b, kx)
            if d < best:
                best = d
                if best < near:
                    break
        hit += best < near
    return hit / len(pts)


def overlap(a, b):
    """Suprapunerea a doua trasee 0..1 (cel mai mic dintre cele doua sensuri de masurare, ca sa nu conteze care e cel scurt)."""
    return min(share_near(a, b), share_near(b, a))


def thin(pts, n=PATH_PTS):
    step = max(1, len(pts) // n)
    out = pts[::step]
    if pts and out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def init(S):
    def path(car, tid):
        k = (car, tid)
        hit = _paths.get(k)
        if hit and time.time() - hit[0] < 3600:
            return hit[1]
        data = S.trip(car, tid)
        pts = [(p[1], p[2]) for sg in data.get('segments') or [] for p in sg['points'] if p[1] is not None and p[2] is not None]
        pts = thin(pts)
        _paths[k] = (time.time(), pts)
        if len(_paths) > 80:
            _paths.pop(next(iter(_paths)))
        return pts

    @S.route('GET', '/api/trips/similar')
    def similar(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        if hc is False:
            return dict(ok=True, suggestions=[])
        car, tid = int(a.get('car', 1)), int(a['id'])
        days = max(30, min(int(a.get('days', 1460)), 3650))
        radius = max(0.3, min(float(a.get('r', RADIUS_KM)), 5.0))
        since = dt.datetime.utcnow() - dt.timedelta(days=days)
        drives = S.drives(car, 8000, 0, since)
        trips = group(drives, [], S.TRIP_GAP)
        main = next((t for t in trips if t['id'] == tid), None)
        if not main:
            return dict(ok=True, suggestions=[])
        cands = candidates(main, trips, radius)
        total = len(cands)
        top = cands[:MAX_RESULTS]
        if top:
            mp = path(car, tid)
            for c in top:
                try:
                    o = overlap(mp, path(car, c['id']))
                    c['overlap'] = round(o * 100)
                    c['same_road'] = o >= SAME_ROAD
                except Exception as e:  # noqa
                    S.log('similar traseu:', str(e)[:80], flush=True)
                    c['overlap'], c['same_road'] = None, None
        return dict(ok=True, total=total, radius_km=radius, suggestions=top)

"""Import istoric din Tessie (API oficial, tokenul utilizatorului) in baza de date TeslaMate: curse (cu traseu GPS, altitudine, temperaturi, autonomie), incarcari (cu curba reala de putere),
adrese, nume de locuri. Ce TeslaMate nu poate pastra (staționări, sanatatea bateriei, alerte firmware, autopilot, putere estimata) se intoarce prin `sink` si ajunge in baza proprie a aplicatiei.

Principii: (1) fara duplicate: se aduce doar ce NU se suprapune cu o cursa/incarcare existenta in TeslaMate (modul "gaps": tot ce lipseste, oricand; modul "older": doar ce e mai vechi
decat prima inregistrare), (2) o singura tranzactie (dry-run = ROLLBACK),
(3) ledger cu id-urile inserate => importul se poate ANULA complet, (4) niciun rand existent nu e modificat sau sters.
"""
import collections, gzip, json, math, os, threading, time, zlib, datetime as dt
import urllib.request, urllib.error, urllib.parse
from concurrent.futures import ThreadPoolExecutor

API = 'https://api.tessie.com'
LEDGER = os.path.join(os.environ.get('DATA_DIR', '/data'), 'import_tessie.json')
KM = 1.609344
WORKERS = max(1, min(8, int(os.environ.get('IMPORT_WORKERS', '5') or 5)))       # cereri de traseu in paralel (o cursa = o cerere); 1 = ca inainte, una cate una
CACHE = os.path.join(os.environ.get('DATA_DIR', '/data'), 'import_cache')        # traseele aduse la "Test" raman aici, ca "Import" sa nu le ceara a doua oara
CACHE_TTL = 3 * 86400
KEEP = ('timestamp', 'latitude', 'longitude', 'battery_level', 'usable_battery_level', 'battery_range', 'elevation', 'speed', 'odometer', 'inside_temp', 'outside_temp', 'is_climate_on',
        'battery_heater_on', 'energy_remaining', 'charger_power', 'charger_voltage', 'charger_actual_current', 'charging_state')      # campurile folosite din /states (cele din /path sunt o parte din ele)
SLOW = dict(until=0.0)                                                              # cand Tessie raspunde 429, TOATE firele asteapta (nu doar cel care a primit eroarea)


class TessieError(Exception):
    pass


def tget(token, path, params=None, timeout=90):
    url = API + path + (('?' + urllib.parse.urlencode(params)) if params else '')
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json', 'User-Agent': 'teslamate-ui-import'})
    for attempt in range(6):
        wait = SLOW['until'] - time.time()
        if wait > 0:
            time.sleep(min(wait, 30))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read()[:200].decode('utf-8', 'replace')
            if (e.code == 429 or 500 <= e.code < 600) and attempt < 5:            # limita de rata sau eroare temporara la Tessie: reincercam
                d = min(30, 3 * (attempt + 1))
                SLOW['until'] = max(SLOW['until'], time.time() + d)
                time.sleep(d)
                continue
            if e.code in (401, 403):
                raise TessieError('Token Tessie invalid sau fără permisiuni (%s).' % e.code)
            raise TessieError('Tessie a răspuns %s: %s' % (e.code, body))
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 5:
                time.sleep(2)
                continue
            raise TessieError('Nu mă pot conecta la Tessie: %s' % e)


def results(x):
    if isinstance(x, dict):
        return x.get('results') or []
    return x or []


def vehicles(token):
    out = []
    for v in results(tget(token, '/vehicles', {'only_active': 'false'})):
        vin = v.get('vin') or (v.get('last_state') or {}).get('vin')
        if vin:
            out.append(dict(vin=vin, name=(v.get('last_state') or {}).get('display_name') or v.get('display_name') or ''))
    return out


def fetch_lists(token, vin, until_ts):
    p = {'from': 0, 'to': int(until_ts), 'distance_format': 'km', 'temperature_format': 'c', 'timezone': 'UTC', 'format': 'json'}
    drives = results(tget(token, '/%s/drives' % vin, p))
    charges = results(tget(token, '/%s/charges' % vin, {k: v for k, v in p.items() if k != 'temperature_format'}))
    return sorted(drives, key=lambda d: d['started_at']), sorted(charges, key=lambda c: c['started_at'])


def fetch_path(token, vin, a, b):
    """Traseul unei curse din /path (viteza in mph, odometru in mile; folosit doar daca /states nu are puncte); pastram doar campurile folosite."""
    pts = results(tget(token, '/%s/path' % vin, {'from': int(a) - 5, 'to': int(b) + 5, 'details': 'true', 'simplify': 'false'}))
    return [{k: p.get(k) for k in KEEP} for p in pts if isinstance(p, dict)]


def fetch_states(token, vin, a, b):
    """Starile masinii din interval (aproximativ la 30 s): pozitie, baterie, autonomie, altitudine, temperaturi, putere de incarcare... (km, km/h, grade C)."""
    rows = results(tget(token, '/%s/states' % vin, {'from': int(a) - 5, 'to': int(b) + 5, 'interval': 1, 'condense': 'false', 'timezone': 'UTC', 'distance_format': 'km', 'temperature_format': 'c'}))
    return [{k: p.get(k) for k in KEEP} for p in rows if isinstance(p, dict)] if isinstance(rows, list) else []


def cache_file(vin, a, b):
    return os.path.join(CACHE, ''.join(ch for ch in vin if ch.isalnum()), '%d-%d.s.json.gz' % (a, b))


def cached_points(token, vin, a, b, kind='drive'):
    """Punctele din cache-ul de pe disc (aduse la "Test"), altfel de la Tessie si salvate in cache. Istoricul din trecut nu se mai schimba."""
    f = cache_file(vin, a, b)
    try:
        with gzip.open(f, 'rt', encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError, EOFError):
        pass
    pts = fetch_states(token, vin, a, b)
    if kind == 'drive' and sum(1 for p in pts if p.get('latitude') is not None) < 2:
        pts = fetch_path(token, vin, a, b)
    try:
        os.makedirs(os.path.dirname(f), exist_ok=True)
        tmp = '%s.%d.tmp' % (f, threading.get_ident())
        with gzip.open(tmp, 'wt', encoding='utf-8', compresslevel=3) as fh:
            json.dump(pts, fh)
        os.replace(tmp, f)
    except OSError:
        pass                                                                       # fara cache (disc plin / drepturi): importul merge oricum
    return pts


def clean_cache(vin=None, older_than=None):
    """Sterge din cache fisierele mai vechi de older_than secunde (sau tot traseele unui VIN, daca older_than e None)."""
    base = CACHE if vin is None else os.path.dirname(cache_file(vin, 0, 0))
    now = time.time()
    for root, _, files in os.walk(base):
        for n in files:
            f = os.path.join(root, n)
            try:
                if older_than is None or now - os.path.getmtime(f) > older_than:
                    os.remove(f)
            except OSError:
                pass


def prefetch(token, vin, items, workers=None, kind='drive'):
    """Genereaza (cursa sau incarcarea, puncte) in ordine, cu pana la `workers` cereri in zbor; o eroare apare la elementul respectiv."""
    n = workers or WORKERS
    ex = ThreadPoolExecutor(max_workers=n)
    win, it = collections.deque(), iter(items)

    def fill():
        while len(win) < n * 2:
            d = next(it, None)
            if d is None:
                return
            win.append((d, ex.submit(cached_points, token, vin, d['started_at'], d['ended_at'], kind)))
    try:
        fill()
        while win:
            d, f = win.popleft()
            fill()
            yield d, f.result()
    finally:
        ex.shutdown(wait=True, cancel_futures=True)


def iso_ts(s):
    """Marca de timp Tessie (numar sau text ISO 8601) -> secunde UNIX; None daca nu se poate citi."""
    if isinstance(s, (int, float)):
        return float(s)
    try:
        return dt.datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def fetch_extras(token, vin, until_ts=None):
    """Staționari, sanatatea bateriei, alerte firmware: tot ce Tessie are si TeslaMate nu poate pastra (merg in baza proprie a aplicatiei)."""
    to = int(until_ts or time.time() + 86400)
    idles = results(tget(token, '/%s/idles' % vin, {'from': 0, 'to': to, 'distance_format': 'km', 'timezone': 'UTC', 'format': 'json'}))
    h = tget(token, '/%s/battery_health' % vin, {'from': 0, 'to': to, 'distance_format': 'km'})
    health = [dict(ts=iso_ts(x.get('timestamp')), odometer=x.get('odometer'), max_range=x.get('max_range'), capacity=x.get('capacity')) for x in (h.get('results') if isinstance(h, dict) else None) or []]
    alerts = results(tget(token, '/%s/firmware_alerts' % vin, {'from': 0, 'to': to}))
    return dict(idles=[x for x in idles if x.get('ended_at')], health=[x for x in health if x['ts']], alerts=[x for x in alerts if x.get('timestamp')])


def climb(elev):
    """Urcare / coborare totala (m) din altitudinile unui traseu, dupa o mediere pe 3 puncte (altitudinea vine in metri intregi: fara mediere zgomotul s-ar aduna)."""
    e = [float(x) for x in elev if x is not None]
    if len(e) < 2:
        return None, None
    sm = [sum(e[max(0, i - 1):i + 2]) / len(e[max(0, i - 1):i + 2]) for i in range(len(e))]
    up = sum(max(0.0, b - a) for a, b in zip(sm, sm[1:]))
    down = sum(max(0.0, a - b) for a, b in zip(sm, sm[1:]))
    return int(round(up)), int(round(down))


def est_power(pts, window=60):
    """Puterea ESTIMATA (kW) din energia ramasa in baterie (energy_remaining, kWh) pe ferestre de ~60 s: (maxim, minim, medie); minim negativ = recuperare. Tessie nu da puterea reala."""
    s = sorted((p['timestamp'], float(p['energy_remaining'])) for p in pts if p.get('timestamp') is not None and p.get('energy_remaining') is not None)
    out, j = [], 0
    for i in range(len(s)):
        j = max(j, i + 1)
        while j < len(s) and s[j][0] - s[i][0] < window:
            j += 1
        if j >= len(s):
            break
        out.append((s[i][1] - s[j][1]) / ((s[j][0] - s[i][0]) / 3600.0))
    if len(out) < 3:
        return None, None, None
    return round(max(out), 1), round(min(out), 1), round(sum(out) / len(out), 1)


def mean(xs):
    xs = [float(x) for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def flag(v):
    return None if v is None else bool(v)


def utc(ts):
    return dt.datetime.utcfromtimestamp(float(ts))


def hav_m(a, b, c, d):
    r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742000 * math.asin(min(1, math.sqrt(x)))


def pick_factor(measured, target):
    """Alege 1 sau 1.609344 (mile/h -> km/h) dupa care se apropie mai mult de valoarea cunoscuta (km)."""
    if not measured or not target:
        return 1.0
    return min((1.0, KM), key=lambda f: abs(measured * f - target))


class Ctx:
    def __init__(self, cur, car_id):
        self.cur, self.car, self.addr_cache = cur, car_id, {}
        self.ofac = None                                       # factorul odometru (1 sau 1.609) dedus dintr-o cursa cu date bune; folosit pentru restul
        self.skipped = 0
        self.extra = dict(drives=[], charges=[])                 # date pentru baza proprie (autopilot, putere estimata, locuri salvate...), scrise dupa commit
        cur.execute('select efficiency from cars where id=%s', (car_id,))
        r = cur.fetchone()
        self.eff = float(r[0]) if r and r[0] else 0.15
        cur.execute("""select avg(ideal_battery_range_km*100.0/battery_level) from positions where car_id=%s and battery_level>=20 and ideal_battery_range_km is not null""", (car_id,))
        r = cur.fetchone()
        self.r100 = float(r[0]) if r and r[0] else 480.0
        cur.execute('select id, latitude, longitude, radius from geofences')
        self.geo = [(i, float(a), float(b), int(c or 20)) for i, a, b, c in cur.fetchall()]
        self.ledger = dict(drives=[], positions=[], charging=[], addresses=[], tessie_drives=[], tessie_charges=[])

    def geofence(self, lat, lon):
        best = None
        for i, a, b, r in self.geo:
            d = hav_m(lat, lon, a, b)
            if d <= r and (best is None or d < best[0]):
                best = (d, i)
        return best[1] if best else None

    def address(self, lat, lon, text, saved=None):
        k = (round(lat, 3), round(lon, 3))
        if k in self.addr_cache:
            return self.addr_cache[k]
        cur = self.cur
        cur.execute('select id from addresses where abs(latitude-%s)<0.001 and abs(longitude-%s)<0.0015 order by (name is null), id limit 1', (lat, lon))
        r = cur.fetchone()
        if r:
            self.addr_cache[k] = r[0]
            return r[0]
        text = (text or '').strip() or None                       # text gol -> NULL (altfel locul apare cu numele "" in loc de "—")
        name = (saved or '').strip() or text                      # locul salvat in Tessie ("Acasa") devine numele adresei; un rand TeslaMate deja existent nu se atinge
        oid = -int(zlib.crc32(('%.4f,%.4f' % (lat, lon)).encode()))
        cur.execute("""insert into addresses (display_name, latitude, longitude, name, inserted_at, updated_at, osm_id, osm_type)
            values (%s,%s,%s,%s,now() at time zone 'utc',now() at time zone 'utc',%s,'node')
            on conflict (osm_id, osm_type) do update set updated_at=now() at time zone 'utc' returning id, (xmax = 0)""", (text or name or '—', lat, lon, name, oid))
        i, fresh = cur.fetchone()
        if fresh:
            self.ledger['addresses'].append(i)
        self.addr_cache[k] = i
        return i

    def ideal(self, soc):
        return round(float(soc) * self.r100 / 100.0, 2)


TOL = 30      # secunde: TeslaMate si Tessie nu pornesc/opresc la aceeasi secunda; o suprapunere mai mica de atat nu inseamna aceeasi cursa


def shrink(a, b):
    """Intervalul Tessie micsorat cu toleranta (pentru curse foarte scurte, cu un sfert din durata)."""
    t = min(TOL, max(0.0, (b - a).total_seconds() / 4.0))
    return a + dt.timedelta(seconds=t), b - dt.timedelta(seconds=t)


def overlaps(cur, car, a, b, table):
    a, b = shrink(a, b)
    cur.execute('select 1 from %s where car_id=%%s and start_date < %%s and coalesce(end_date, start_date) > %%s limit 1' % table, (car, b, a))
    return cur.fetchone() is not None


def select(items, exists, mode, cut):
    """Ce se importa. items = liste Tessie; exists(item) -> se suprapune cu ceva din TeslaMate?; mode 'gaps' = tot ce lipseste, 'older' = doar ce e mai vechi decat cut."""
    out = []
    for x in items:
        if not x.get('ended_at') or x['ended_at'] < x['started_at']:
            continue                                   # in curs sau invalid
        if mode == 'older' and x['started_at'] >= cut:
            continue
        if not exists(x):
            out.append(x)
    return out


def bounds(cur, car):
    """(prima, ultima) inregistrare TeslaMate, ca timestamp UNIX."""
    cur.execute("""select min(d), max(e) from (select min(start_date) d, max(coalesce(end_date, start_date)) e from drives where car_id=%s union all
        select min(start_date), max(coalesce(end_date, start_date)) from charging_processes where car_id=%s union all select min(date), max(date) from positions where car_id=%s) x""", (car, car, car))
    r = cur.fetchone()
    f = lambda v: v.replace(tzinfo=dt.timezone.utc).timestamp() if v else None
    return (f(r[0]), f(r[1])) if r else (None, None)


def where(items, first, last):
    """Cate dintre elemente sunt inainte de prima inregistrare TeslaMate, intre ele, sau dupa ultima."""
    n = dict(before=0, between=0, after=0)
    for x in items:
        k = 'before' if first and x['started_at'] < first else ('after' if last and x['started_at'] > last else 'between')
        n[k] += 1
    return n


def cutoff_ts(cur, car):
    cur.execute("""select min(d) from (select min(start_date) d from drives where car_id=%s union all select min(start_date) from charging_processes where car_id=%s
        union all select min(date) from positions where car_id=%s) x""", (car, car, car))
    r = cur.fetchone()
    return r[0].replace(tzinfo=dt.timezone.utc).timestamp() if r and r[0] else time.time()


def plan(cur, token, vin, car, mode, cutoff=None):
    """Listele Tessie si ce din ele se importa."""
    cut = cutoff or cutoff_ts(cur, car)
    drives, charges = fetch_lists(token, vin, cut if mode == 'older' else time.time() + 86400)
    nd = select(drives, lambda d: overlaps(cur, car, utc(d['started_at']), utc(d['ended_at']), 'drives'), mode, cut)
    nc = select(charges, lambda c: overlaps(cur, car, utc(c['started_at']), utc(c['ended_at']), 'charging_processes'), mode, cut)
    return cut, drives, charges, nd, nc


def preview(conn, token, vin, car, cutoff=None, mode='gaps'):
    cur = conn.cursor()
    cut, drives, charges, nd, nc = plan(cur, token, vin, car, mode, cutoff)
    first_tm, last_tm = bounds(cur, car)
    cur.close()
    ex = fetch_extras(token, vin, cut if mode == 'older' else None)
    first = min([x['started_at'] for x in nd + nc], default=None)
    last = max([x['started_at'] for x in nd + nc], default=None)
    return dict(ok=True, mode=mode, cutoff=cut, teslamate_first=first_tm, teslamate_last=last_tm, tessie_drives=len(drives), tessie_charges=len(charges), to_import_drives=len(nd), to_import_charges=len(nc),
                already_in_teslamate=dict(drives=len(drives) - len(nd), charges=len(charges) - len(nc)), drives_where=where(nd, first_tm, last_tm), charges_where=where(nc, first_tm, last_tm),
                first=first, last=last, km=round(sum(d.get('odometer_distance') or 0 for d in nd), 1), kwh=round(sum(c.get('energy_added') or 0 for c in nc), 1),
                extras=dict(idles=len(ex['idles']), health=len(ex['health']), alerts=len(ex['alerts'])))


def import_drive(ctx, token, vin, d, path=None):
    cur, car = ctx.cur, ctx.car
    a, b = d['started_at'], d['ended_at']
    if path is None:
        path = cached_points(token, vin, a, b)
    pts = [p for p in path if isinstance(p, dict) and p.get('latitude') is not None and a - 5 <= (p.get('timestamp') or a) <= b + 5]
    pts.sort(key=lambda p: p.get('timestamp') or 0)
    if len(pts) < 2:
        pts = [dict(timestamp=a, latitude=d['starting_latitude'], longitude=d['starting_longitude'], battery_level=d['starting_battery'], speed=0, odometer=None),
               dict(timestamp=b, latitude=d['ending_latitude'], longitude=d['ending_longitude'], battery_level=d['ending_battery'], speed=0, odometer=None)]
    if d.get('starting_battery') is None or d.get('ending_battery') is None:
        ctx.skipped += 1                                                     # fara nivel de baterie nu putem construi cursa
        return 0
    dist = float(d.get('odometer_distance') or 0)
    odos = [p['odometer'] for p in pts if p.get('odometer') is not None]
    if len(odos) > 1 and odos[-1] > odos[0] and dist:
        ofac = ctx.ofac = pick_factor(odos[-1] - odos[0], dist)
    else:
        ofac = ctx.ofac                                                      # unitate nesigura aici: folosim ce am dedus din celelalte curse (sau nimic)
        if ofac is None:
            odos = []
    spds = [p.get('speed') or 0 for p in pts]
    sfac = pick_factor(max(spds), d.get('max_speed'))
    soc0, soc1 = d['starting_battery'], d['ending_battery']
    energy = float(d.get('energy_used') or 0)
    real0 = next((p['battery_range'] for p in pts if p.get('battery_range') is not None), None)      # autonomia reala (km) de la primul punct; altfel o deducem din procente
    ideal0 = round(float(real0), 2) if real0 else ctx.ideal(soc0)
    ideal1 = max(0.0, round(ideal0 - (energy / ctx.eff if energy > 0 else (soc0 - soc1) * ctx.r100 / 100.0), 2))      # sfarsitul din energia Tessie: consumul (kWh) iese ca la Tessie
    sa = ctx.address(d['starting_latitude'], d['starting_longitude'], d.get('starting_location') or '', d.get('starting_saved_location'))
    ea = ctx.address(d['ending_latitude'], d['ending_longitude'], d.get('ending_location') or '', d.get('ending_saved_location'))
    sg, eg = ctx.geofence(d['starting_latitude'], d['starting_longitude']), ctx.geofence(d['ending_latitude'], d['ending_longitude'])
    odo0 = float(d['starting_odometer']) if d.get('starting_odometer') is not None else ((odos[0] * ofac) if odos else None)
    odo1 = (float(d['ending_odometer']) if d.get('ending_odometer') is not None and float(d['ending_odometer']) >= (odo0 or 0) else ((odo0 + dist) if odo0 is not None else None))
    dur = max(1, round((b - a) / 60))
    up, down = climb([p.get('elevation') for p in pts])
    t_out = d.get('average_outside_temperature') if d.get('average_outside_temperature') is not None else mean(p.get('outside_temp') for p in pts)
    t_in = d.get('average_inside_temperature') if d.get('average_inside_temperature') is not None else mean(p.get('inside_temp') for p in pts)
    cur.execute("""insert into drives (start_date, end_date, outside_temp_avg, inside_temp_avg, speed_max, start_ideal_range_km, end_ideal_range_km, start_rated_range_km, end_rated_range_km,
        start_km, end_km, distance, duration_min, car_id, start_address_id, end_address_id, start_geofence_id, end_geofence_id, ascent, descent)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                (utc(a), utc(b), t_out, t_in, int(round(d.get('max_speed') or max(spds) * sfac)), ideal0, ideal1, ideal0, ideal1,
                 odo0, odo1, dist, dur, car, sa, ea, sg, eg, up, down))
    did = cur.fetchone()[0]
    ctx.ledger['drives'].append(did)
    n = len(pts)
    rows = []
    for i, p in enumerate(pts):
        f = i / (n - 1)
        ideal = round(ideal0 + (ideal1 - ideal0) * f, 2)
        rng = round(float(p['battery_range']), 2) if p.get('battery_range') is not None else ideal                    # autonomia reala a punctului, daca Tessie o da
        o = (p['odometer'] * ofac) if (odos and p.get('odometer') is not None) else (odo0 + dist * f if odo0 is not None else None)
        soc = p.get('battery_level') if p.get('battery_level') is not None else round(soc0 + (soc1 - soc0) * f)
        usable = p.get('usable_battery_level') if p.get('usable_battery_level') is not None else soc
        elev = int(round(p['elevation'])) if p.get('elevation') is not None else None
        rows.append((utc(p.get('timestamp') or a), p['latitude'], p['longitude'], int(round((p.get('speed') or 0) * sfac)), o, rng, rng, rng, soc, usable, elev,
                     p.get('outside_temp'), p.get('inside_temp'), flag(p.get('is_climate_on')), flag(p.get('battery_heater_on')), car, did))
    import psycopg2.extras
    ids = psycopg2.extras.execute_values(cur, """insert into positions (date, latitude, longitude, speed, odometer, ideal_battery_range_km, est_battery_range_km, rated_battery_range_km,
        battery_level, usable_battery_level, elevation, outside_temp, inside_temp, is_climate_on, battery_heater_on, car_id, drive_id) values %s returning id""", rows, page_size=500, fetch=True)
    ids = [r[0] for r in ids]
    ctx.ledger['positions'] += ids
    cur.execute('update drives set start_position_id=%s, end_position_id=%s where id=%s', (ids[0], ids[-1], did))
    ctx.ledger['tessie_drives'].append(d['id'])
    pmax, pmin, pavg = est_power(pts)
    ctx.extra['drives'].append(dict(tessie_id=d['id'], drive_id=did, started_at=a, ended_at=b, autopilot_km=d.get('autopilot_distance'), avg_speed=d.get('average_speed'), energy_used=d.get('energy_used'),
                                    rated_range_used=d.get('rated_range_used'), tag=d.get('tag'), est_power_max=pmax, est_power_min=pmin, est_power_avg=pavg,
                                    start_saved=d.get('starting_saved_location'), end_saved=d.get('ending_saved_location')))
    return len(ids)


def charge_curve(c, pts, i0, i1):
    """Punctele din `charges` (curba reala de incarcare) din starile masinii: putere, tensiune, curent, autonomie; energia adaugata se integreaza din putere si se aduce la total-ul Tessie.
    Fara putere in date (sau mai putin de 2 puncte) intoarce [] si se pastreaza cele doua puncte (start / sfarsit)."""
    a, b = c['started_at'], c['ended_at']
    good = sorted((p for p in pts if p.get('timestamp') is not None and a - 5 <= p['timestamp'] <= b + 5 and p.get('battery_level') is not None), key=lambda p: p['timestamp'])
    if len(good) < 2 or not any(p.get('charger_power') for p in good):
        return []
    cum, tot = [0.0], 0.0
    for p, q in zip(good, good[1:]):
        tot += (float(p.get('charger_power') or 0) + float(q.get('charger_power') or 0)) / 2.0 * (q['timestamp'] - p['timestamp']) / 3600.0
        cum.append(tot)
    added = float(c.get('energy_added') or 0)
    fast = bool(c.get('is_fast_charger') or c.get('is_supercharger'))
    out = []
    for p, e in zip(good, cum):
        v = p.get('charger_voltage')
        rng = round(float(p['battery_range']), 2) if p.get('battery_range') is not None else None
        out.append(dict(ts=p['timestamp'], soc=p['battery_level'], usable=p.get('usable_battery_level') if p.get('usable_battery_level') is not None else p['battery_level'],
                        energy=round(added * e / tot, 2) if tot > 0 else 0.0, power=int(round(float(p.get('charger_power') or 0))), volt=int(v) if v is not None and v >= 10 else None,
                        amps=int(p['charger_actual_current']) if p.get('charger_actual_current') is not None else None, rng=rng, temp=p.get('outside_temp'),
                        heater=flag(p.get('battery_heater_on')), fast=fast))
    return out


def import_charge(ctx, c, pts=None):
    cur, car = ctx.cur, ctx.car
    a, b = c['started_at'], c['ended_at']
    s0, s1 = c['starting_battery'], c['ending_battery']
    if s0 is None or s1 is None:
        ctx.skipped += 1
        return
    pts = pts or []
    real = [p['battery_range'] for p in sorted((p for p in pts if p.get('battery_range') is not None and p.get('timestamp') is not None), key=lambda p: p['timestamp'])]
    i0, i1 = (round(float(real[0]), 2), round(float(real[-1]), 2)) if len(real) > 1 else (ctx.ideal(s0), ctx.ideal(s1))
    addr = ctx.address(c['latitude'], c['longitude'], c.get('location') or '', c.get('saved_location'))
    geo = ctx.geofence(c['latitude'], c['longitude'])
    cur.execute("""insert into positions (date, latitude, longitude, speed, odometer, ideal_battery_range_km, est_battery_range_km, rated_battery_range_km, battery_level, usable_battery_level, car_id)
        values (%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s) returning id""", (utc(a), c['latitude'], c['longitude'], (c['odometer'] * ctx.ofac) if (c.get('odometer') is not None and ctx.ofac) else None, i0, i0, i0, s0, s0, car))
    pid = cur.fetchone()[0]
    ctx.ledger['positions'].append(pid)
    added = float(c.get('energy_added') or 0)
    dur = max(1, round((b - a) / 60))
    cur.execute("""insert into charging_processes (start_date, end_date, charge_energy_added, charge_energy_used, start_ideal_range_km, end_ideal_range_km, start_rated_range_km, end_rated_range_km,
        start_battery_level, end_battery_level, duration_min, car_id, position_id, address_id, geofence_id, cost, outside_temp_avg)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                (utc(a), utc(b), added, c.get('energy_used'), i0, i1, i0, i1, s0, s1, dur, car, pid, addr, geo, c.get('cost'), mean(p.get('outside_temp') for p in pts)))
    cid = cur.fetchone()[0]
    ctx.ledger['charging'].append(cid)
    fast = bool(c.get('is_fast_charger') or c.get('is_supercharger'))
    curve = charge_curve(c, pts, i0, i1)
    if curve:
        if curve[0]['ts'] > a + 60:                                          # curba trebuie sa acopere tot intervalul: adaugam capetele care lipsesc
            curve.insert(0, dict(curve[0], ts=a, energy=0.0))
        if curve[-1]['ts'] < b - 60:
            curve.append(dict(curve[-1], ts=b, energy=round(added, 2), power=0, amps=0))
        for x in curve:
            cur.execute("""insert into charges (date, battery_level, usable_battery_level, charge_energy_added, charger_power, charger_voltage, charger_actual_current, ideal_battery_range_km,
                rated_battery_range_km, outside_temp, battery_heater_on, fast_charger_present, charging_process_id) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (utc(x['ts']), x['soc'], x['usable'], x['energy'], x['power'], x['volt'], x['amps'], x['rng'] if x['rng'] is not None else ctx.ideal(x['soc']),
                         x['rng'] if x['rng'] is not None else ctx.ideal(x['soc']), x['temp'], x['heater'], fast, cid))
    else:
        kw = int(round(added / (dur / 60.0))) if added else 0                # putere medie (nu avem curba reala)
        for t, soc, ideal, e in ((a, s0, i0, 0.0), (b, s1, i1, added)):
            cur.execute("""insert into charges (date, battery_level, usable_battery_level, charge_energy_added, charger_power, ideal_battery_range_km, rated_battery_range_km, fast_charger_present, charging_process_id)
                values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (utc(t), soc, soc, e, kw, ideal, ideal, fast, cid))
    ctx.ledger['tessie_charges'].append(c['id'])
    ctx.extra['charges'].append(dict(tessie_id=c['id'], charge_id=cid, started_at=a, ended_at=b, max_range=c.get('max_range'), capacity=c.get('capacity'), since_last_charge=c.get('since_last_charge'),
                                     saved=c.get('saved_location'), fast=fast, curve_points=len(curve), odometer=c.get('odometer')))


def run(conn, token, vin, car, progress, cutoff=None, dry_run=False, mode='gaps', sink=None):
    """Importa din Tessie ce lipseste din TeslaMate (mode 'gaps') sau doar ce e mai vechi decat prima inregistrare ('older'). progress = dict mutabil citit de UI.
    sink(date_extra) primeste, dupa commit, ce nu are loc in TeslaMate (staționari, sanatatea bateriei, alerte, autopilot, putere estimata)."""
    cur = conn.cursor()
    progress.update(phase='Citesc listele din Tessie…', done=0, total=0)
    cut, _, _, drives, charges = plan(cur, token, vin, car, mode, cutoff)
    progress.update(phase='Citesc staționările, starea bateriei și alertele…')
    extras = fetch_extras(token, vin, cut if mode == 'older' else None)
    ctx = Ctx(cur, car)
    progress.update(total=len(drives) + len(charges))
    npts = 0
    clean_cache(older_than=CACHE_TTL)
    for i, (d, path) in enumerate(prefetch(token, vin, drives)):
        progress.update(phase='Curse %d/%d' % (i + 1, len(drives)), done=i)
        npts += import_drive(ctx, token, vin, d, path)
    for i, (c, pts) in enumerate(prefetch(token, vin, charges, kind='charge')):
        progress.update(phase='Încărcări %d/%d' % (i + 1, len(charges)), done=len(drives) + i)
        import_charge(ctx, c, pts)
    res = dict(drives=len(drives), charges=len(charges), positions=npts, addresses=len(ctx.ledger['addresses']), skipped=ctx.skipped, dry_run=dry_run, mode=mode,
               idles=len(extras['idles']), health=len(extras['health']) + sum(1 for x in ctx.extra['charges'] if x.get('max_range') and x.get('capacity')), alerts=len(extras['alerts']),
               curve_charges=sum(1 for x in ctx.extra['charges'] if x['curve_points']), power_estimated=sum(1 for x in ctx.extra['drives'] if x.get('est_power_max') is not None))
    if dry_run:
        conn.rollback()
    else:
        ctx.ledger['at'] = time.time()
        if os.path.isfile(LEDGER) or os.path.isfile(LEDGER + '.pending'):                     # import repetat: jurnalul se completeaza, iar "Anuleaza" scoate tot ce a adus aplicatia
            with open(LEDGER if os.path.isfile(LEDGER) else LEDGER + '.pending') as lf:
                old = json.load(lf)
            for k, v in old.items():
                if isinstance(v, list):
                    ctx.ledger[k] = list(v) + ctx.ledger.get(k, [])
        pend = LEDGER + '.pending'                     # jurnalul se scrie INAINTE de commit: daca procesul cade intre ele, undo-ul il gaseste tot
        with open(pend, 'w') as lf:
            json.dump(ctx.ledger, lf)
            lf.flush()
            os.fsync(lf.fileno())
        try:
            conn.commit()
        except Exception:
            os.remove(pend)
            raise
        os.replace(pend, LEDGER)
        clean_cache(vin)                                                                # importul s-a facut: traseele din cache nu mai trebuie
        if sink:
            try:
                sink(dict(vin=vin, car=car, idles=extras['idles'], health=extras['health'], alerts=extras['alerts'], drives=ctx.extra['drives'], charges=ctx.extra['charges']))
            except Exception as e:  # noqa: datele din TeslaMate sunt deja salvate; la o noua rulare datele extra se rescriu (upsert)
                res['extras_error'] = str(e)[:200]
    cur.close()
    progress.update(phase='Gata', done=progress.get('total', 0))
    return res


def undo(conn):
    """Sterge exact randurile inserate de import (dupa ledger). Ordinea respecta cheile straine."""
    src = LEDGER if os.path.exists(LEDGER) else LEDGER + '.pending'
    led = json.load(open(src))
    cur = conn.cursor()
    q = lambda sql, ids: ids and cur.execute(sql, (list(ids),))
    q('delete from charging_processes where id = any(%s)', led['charging'])       # sterge si charges (cascade)
    q('delete from drives where id = any(%s)', led['drives'])
    q('delete from positions where id = any(%s)', led['positions'])
    q('delete from addresses where id = any(%s) and not exists (select 1 from drives d where d.start_address_id=addresses.id or d.end_address_id=addresses.id) and not exists (select 1 from charging_processes c where c.address_id=addresses.id)', led['addresses'])
    conn.commit()
    cur.close()
    os.rename(src, LEDGER + '.undone-%d' % int(time.time()))
    return dict(drives=len(led['drives']), charges=len(led['charging']), positions=len(led['positions']))

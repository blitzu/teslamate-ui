"""Import istoric din Tessie (API oficial, tokenul utilizatorului) in baza de date TeslaMate: curse (cu traseu GPS), incarcari, adrese, geofence-uri.

Principii: (1) doar date MAI VECHI decat prima inregistrare TeslaMate (fara duplicate), (2) o singura tranzactie (dry-run = ROLLBACK),
(3) ledger cu id-urile inserate => importul se poate ANULA complet, (4) niciun rand existent nu e modificat sau sters.
"""
import json, math, os, time, zlib, datetime as dt
import urllib.request, urllib.error, urllib.parse

API = 'https://api.tessie.com'
LEDGER = '/data/import_tessie.json'
KM = 1.609344


class TessieError(Exception):
    pass


def tget(token, path, params=None, timeout=90):
    url = API + path + (('?' + urllib.parse.urlencode(params)) if params else '')
    req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json', 'User-Agent': 'teslamate-ui-import'})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read()[:200].decode('utf-8', 'replace')
            if e.code == 429 and attempt < 3:
                time.sleep(3 * (attempt + 1))
                continue
            if e.code in (401, 403):
                raise TessieError('Token Tessie invalid sau fără permisiuni (%s).' % e.code)
            raise TessieError('Tessie a răspuns %s: %s' % (e.code, body))
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 3:
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
    return results(tget(token, '/%s/path' % vin, {'from': int(a) - 5, 'to': int(b) + 5, 'details': 'true', 'simplify': 'false'}))


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

    def address(self, lat, lon, text):
        k = (round(lat, 3), round(lon, 3))
        if k in self.addr_cache:
            return self.addr_cache[k]
        cur = self.cur
        cur.execute('select id from addresses where abs(latitude-%s)<0.001 and abs(longitude-%s)<0.0015 order by (name is null), id limit 1', (lat, lon))
        r = cur.fetchone()
        if r:
            self.addr_cache[k] = r[0]
            return r[0]
        oid = -int(zlib.crc32(('%.4f,%.4f' % (lat, lon)).encode()))
        cur.execute("""insert into addresses (display_name, latitude, longitude, name, inserted_at, updated_at, osm_id, osm_type)
            values (%s,%s,%s,%s,now() at time zone 'utc',now() at time zone 'utc',%s,'node')
            on conflict (osm_id, osm_type) do update set updated_at=now() at time zone 'utc' returning id, (xmax = 0)""", (text, lat, lon, text, oid))
        i, fresh = cur.fetchone()
        if fresh:
            self.ledger['addresses'].append(i)
        self.addr_cache[k] = i
        return i

    def ideal(self, soc):
        return round(float(soc) * self.r100 / 100.0, 2)


def overlaps(cur, car, a, b, table):
    cur.execute('select 1 from %s where car_id=%%s and start_date < %%s and coalesce(end_date, start_date) > %%s limit 1' % table, (car, b, a))
    return cur.fetchone() is not None


def cutoff_ts(cur, car):
    cur.execute("""select min(d) from (select min(start_date) d from drives where car_id=%s union all select min(start_date) from charging_processes where car_id=%s
        union all select min(date) from positions where car_id=%s) x""", (car, car, car))
    r = cur.fetchone()
    return r[0].replace(tzinfo=dt.timezone.utc).timestamp() if r and r[0] else time.time()


def preview(conn, token, vin, car, cutoff=None):
    cur = conn.cursor()
    cut = cutoff or cutoff_ts(cur, car)
    drives, charges = fetch_lists(token, vin, cut)
    nd = [d for d in drives if d['started_at'] < cut and not overlaps(cur, car, utc(d['started_at']), utc(d['ended_at']), 'drives')]
    nc = [c for c in charges if c['started_at'] < cut and not overlaps(cur, car, utc(c['started_at']), utc(c['ended_at']), 'charging_processes')]
    cur.close()
    first = min([x['started_at'] for x in nd + nc], default=None)
    last = max([x['started_at'] for x in nd + nc], default=None)
    return dict(ok=True, cutoff=cut, tessie_drives=len(drives), tessie_charges=len(charges), to_import_drives=len(nd), to_import_charges=len(nc),
                first=first, last=last, km=round(sum(d.get('odometer_distance') or 0 for d in nd), 1), kwh=round(sum(c.get('energy_added') or 0 for c in nc), 1))


def import_drive(ctx, token, vin, d):
    cur, car = ctx.cur, ctx.car
    a, b = d['started_at'], d['ended_at']
    path = fetch_path(token, vin, a, b)
    pts = [p for p in path if isinstance(p, dict) and p.get('latitude') is not None and a - 5 <= (p.get('timestamp') or a) <= b + 5]
    pts.sort(key=lambda p: p.get('timestamp') or 0)
    if len(pts) < 2:
        pts = [dict(timestamp=a, latitude=d['starting_latitude'], longitude=d['starting_longitude'], battery_level=d['starting_battery'], speed=0, odometer=None),
               dict(timestamp=b, latitude=d['ending_latitude'], longitude=d['ending_longitude'], battery_level=d['ending_battery'], speed=0, odometer=None)]
    dist = float(d.get('odometer_distance') or 0)
    odos = [p['odometer'] for p in pts if p.get('odometer') is not None]
    ofac = pick_factor(odos[-1] - odos[0], dist) if len(odos) > 1 and odos[-1] > odos[0] else 1.0
    spds = [p.get('speed') or 0 for p in pts]
    sfac = pick_factor(max(spds), d.get('max_speed'))
    soc0, soc1 = d['starting_battery'], d['ending_battery']
    energy = float(d.get('energy_used') or 0)
    ideal0 = ctx.ideal(soc0)
    ideal1 = max(0.0, round(ideal0 - (energy / ctx.eff if energy > 0 else (soc0 - soc1) * ctx.r100 / 100.0), 2))
    sa = ctx.address(d['starting_latitude'], d['starting_longitude'], d.get('starting_location') or '')
    ea = ctx.address(d['ending_latitude'], d['ending_longitude'], d.get('ending_location') or '')
    sg, eg = ctx.geofence(d['starting_latitude'], d['starting_longitude']), ctx.geofence(d['ending_latitude'], d['ending_longitude'])
    odo0 = (odos[0] * ofac) if odos else None
    odo1 = (odo0 + dist) if odo0 is not None else None
    dur = max(1, round((b - a) / 60))
    cur.execute("""insert into drives (start_date, end_date, outside_temp_avg, inside_temp_avg, speed_max, start_ideal_range_km, end_ideal_range_km, start_rated_range_km, end_rated_range_km,
        start_km, end_km, distance, duration_min, car_id, start_address_id, end_address_id, start_geofence_id, end_geofence_id)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                (utc(a), utc(b), d.get('average_outside_temperature'), d.get('average_inside_temperature'), int(round(d.get('max_speed') or max(spds) * sfac)), ideal0, ideal1, ideal0, ideal1,
                 odo0, odo1, dist, dur, car, sa, ea, sg, eg))
    did = cur.fetchone()[0]
    ctx.ledger['drives'].append(did)
    n = len(pts)
    rows = []
    for i, p in enumerate(pts):
        f = i / (n - 1)
        ideal = round(ideal0 + (ideal1 - ideal0) * f, 2)
        o = (p['odometer'] * ofac) if p.get('odometer') is not None else (odo0 + dist * f if odo0 is not None else None)
        soc = p.get('battery_level') if p.get('battery_level') is not None else round(soc0 + (soc1 - soc0) * f)
        rows.append((utc(p.get('timestamp') or a), p['latitude'], p['longitude'], int(round((p.get('speed') or 0) * sfac)), o, ideal, ideal, ideal, soc, soc, car, did))
    import psycopg2.extras
    ids = psycopg2.extras.execute_values(cur, """insert into positions (date, latitude, longitude, speed, odometer, ideal_battery_range_km, est_battery_range_km, rated_battery_range_km,
        battery_level, usable_battery_level, car_id, drive_id) values %s returning id""", rows, page_size=500, fetch=True)
    ids = [r[0] for r in ids]
    ctx.ledger['positions'] += ids
    cur.execute('update drives set start_position_id=%s, end_position_id=%s where id=%s', (ids[0], ids[-1], did))
    ctx.ledger['tessie_drives'].append(d['id'])
    return len(ids)


def import_charge(ctx, c):
    cur, car = ctx.cur, ctx.car
    a, b = c['started_at'], c['ended_at']
    s0, s1 = c['starting_battery'], c['ending_battery']
    i0, i1 = ctx.ideal(s0), ctx.ideal(s1)
    addr = ctx.address(c['latitude'], c['longitude'], c.get('location') or '')
    geo = ctx.geofence(c['latitude'], c['longitude'])
    cur.execute("""insert into positions (date, latitude, longitude, speed, odometer, ideal_battery_range_km, est_battery_range_km, rated_battery_range_km, battery_level, usable_battery_level, car_id)
        values (%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s) returning id""", (utc(a), c['latitude'], c['longitude'], c.get('odometer'), i0, i0, i0, s0, s0, car))
    pid = cur.fetchone()[0]
    ctx.ledger['positions'].append(pid)
    added = float(c.get('energy_added') or 0)
    dur = max(1, round((b - a) / 60))
    cur.execute("""insert into charging_processes (start_date, end_date, charge_energy_added, charge_energy_used, start_ideal_range_km, end_ideal_range_km, start_rated_range_km, end_rated_range_km,
        start_battery_level, end_battery_level, duration_min, car_id, position_id, address_id, geofence_id, cost)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id""",
                (utc(a), utc(b), added, c.get('energy_used'), i0, i1, i0, i1, s0, s1, dur, car, pid, addr, geo, c.get('cost')))
    cid = cur.fetchone()[0]
    ctx.ledger['charging'].append(cid)
    kw = int(round(added / (dur / 60.0))) if added else 0                # putere medie (nu avem curba reala)
    fast = bool(c.get('is_supercharger'))
    for t, soc, ideal, e in ((a, s0, i0, 0.0), (b, s1, i1, added)):
        cur.execute("""insert into charges (date, battery_level, usable_battery_level, charge_energy_added, charger_power, ideal_battery_range_km, rated_battery_range_km, fast_charger_present, charging_process_id)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (utc(t), soc, soc, e, kw, ideal, ideal, fast, cid))
    ctx.ledger['tessie_charges'].append(c['id'])


def run(conn, token, vin, car, progress, cutoff=None, dry_run=False):
    """Importa tot ce e mai vechi decat prima inregistrare TeslaMate. progress = dict mutabil citit de UI."""
    cur = conn.cursor()
    cut = cutoff or cutoff_ts(cur, car)
    progress.update(phase='Citesc listele din Tessie…', done=0, total=0)
    drives, charges = fetch_lists(token, vin, cut)
    drives = [d for d in drives if d['started_at'] < cut and not overlaps(cur, car, utc(d['started_at']), utc(d['ended_at']), 'drives')]
    charges = [c for c in charges if c['started_at'] < cut and not overlaps(cur, car, utc(c['started_at']), utc(c['ended_at']), 'charging_processes')]
    ctx = Ctx(cur, car)
    progress.update(total=len(drives) + len(charges))
    npts = 0
    for i, d in enumerate(drives):
        progress.update(phase='Curse %d/%d' % (i + 1, len(drives)), done=i)
        npts += import_drive(ctx, token, vin, d)
        time.sleep(0.15)
    for i, c in enumerate(charges):
        progress.update(phase='Încărcări %d/%d' % (i + 1, len(charges)), done=len(drives) + i)
        import_charge(ctx, c)
    res = dict(drives=len(drives), charges=len(charges), positions=npts, addresses=len(ctx.ledger['addresses']), dry_run=dry_run)
    if dry_run:
        conn.rollback()
    else:
        conn.commit()
        ctx.ledger['at'] = time.time()
        json.dump(ctx.ledger, open(LEDGER, 'w'))
    cur.close()
    progress.update(phase='Gata', done=progress.get('total', 0))
    return res


def undo(conn):
    """Sterge exact randurile inserate de import (dupa ledger). Ordinea respecta cheile straine."""
    led = json.load(open(LEDGER))
    cur = conn.cursor()
    q = lambda sql, ids: ids and cur.execute(sql, (list(ids),))
    q('delete from charging_processes where id = any(%s)', led['charging'])       # sterge si charges (cascade)
    q('delete from drives where id = any(%s)', led['drives'])
    q('delete from positions where id = any(%s)', led['positions'])
    q('delete from addresses where id = any(%s) and not exists (select 1 from drives d where d.start_address_id=addresses.id or d.end_address_id=addresses.id) and not exists (select 1 from charging_processes c where c.address_id=addresses.id)', led['addresses'])
    conn.commit()
    cur.close()
    os.rename(LEDGER, LEDGER + '.undone-%d' % int(time.time()))
    return dict(drives=len(led['drives']), charges=len(led['charging']), positions=len(led['positions']))

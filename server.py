#!/usr/bin/env python3
"""TeslaMate UI (stil Tessie): backend. MQTT (live) + Postgres TeslaMate (istoric) -> JSON/SSE. Fara date demo cat timp TeslaMate nu are masini => mod DEMO."""
import json, math, os, queue, random, secrets, ssl, threading, time, datetime as dt
import urllib.request, urllib.error, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get('PORT', '4100'))
DEMO_ONLY = os.environ.get('DEMO_ONLY') == '1'   # instanta publica: doar date fictive, fara DB/MQTT/comenzi
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
DB = dict(host=os.environ.get('DATABASE_HOST', 'database'), user=os.environ.get('DATABASE_USER', 'teslamate'),
          password=os.environ.get('DATABASE_PASS', ''), dbname=os.environ.get('DATABASE_NAME', 'teslamate'), connect_timeout=5)
MQ = dict(host=os.environ.get('MQTT_HOST', ''), port=int(os.environ.get('MQTT_PORT', '1883')),
          user=os.environ.get('MQTT_USERNAME', ''), pw=os.environ.get('MQTT_PASSWORD', ''), ns=os.environ.get('MQTT_NAMESPACE', ''))
LINKS = dict(teslamate=os.environ.get('TESLAMATE_URL', ''), grafana=os.environ.get('GRAFANA_URL', ''))
CURRENCY = os.environ.get('CURRENCY', '€')   # simbolul afisat langa costul incarcarilor (costul vine din TeslaMate)

# ---------------------------------------------------------------- live (MQTT)
LIVE = {}            # car_id -> {key: value}
LIVE_TS = {}         # car_id -> last message ts
CLIENTS = set()
CLOCK = threading.Lock()


def broadcast(msg):
    with CLOCK:
        for q in list(CLIENTS):
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass


def conv(v):
    if v in ('true', 'false'):
        return v == 'true'
    if v in ('', 'nil', 'null'):
        return None
    try:
        return float(v) if ('.' in v or 'e' in v.lower()) else int(v)
    except ValueError:
        pass
    if v[:1] in '{[':
        try:
            return json.loads(v)
        except ValueError:
            pass
    return v


def mqtt_thread():
    if not MQ['host']:
        return
    import paho.mqtt.client as mqtt
    prefix = (MQ['ns'] + '/' if MQ['ns'] else '') + 'teslamate/cars/'

    def on_connect(c, *a):
        c.subscribe(prefix + '#')

    def on_message(c, u, m):
        parts = m.topic[len(prefix):].split('/')
        if len(parts) != 2 or not parts[0].isdigit():
            return
        car, key = int(parts[0]), parts[1]
        val = conv(m.payload.decode('utf-8', 'replace'))
        d = LIVE.setdefault(car, {})
        if d.get(key) != val:
            prev = d.get(key)
            d[key] = val
            LIVE_TS[car] = time.time()
            broadcast({'car': car, 'k': key, 'v': val})
            try:
                notify_check(car, key, prev, val)
            except Exception as e:  # noqa
                print('notify:', e, flush=True)

    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except Exception:
        c = mqtt.Client()
    if MQ['user']:
        c.username_pw_set(MQ['user'], MQ['pw'])
    c.on_connect, c.on_message = on_connect, on_message
    c.reconnect_delay_set(2, 30)
    while True:
        try:
            c.connect(MQ['host'], MQ['port'], 60)
            c.loop_forever(retry_first_connection=True)
        except Exception as e:
            print('mqtt:', e, flush=True)
            time.sleep(5)


# ---------------------------------------------------------------- DB
def q(sql, args=()):
    import psycopg2, psycopg2.extras
    cn = psycopg2.connect(**DB)
    try:
        with cn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, args)
            rows = cur.fetchall()
        return [{k: (v.isoformat() if isinstance(v, (dt.datetime, dt.date)) else (float(v) if hasattr(v, 'quantize') else v)) for k, v in r.items()} for r in rows]
    finally:
        cn.close()


NAME_A = "coalesce(nullif(g.name,''), nullif(trim(both ', ' from concat_ws(', ', a.name, a.road, a.city)),''), a.display_name, '—')"
NAME_B = NAME_A.replace('g.', 'g2.').replace('a.', 'a2.')


def cars():
    return q("select c.id, coalesce(c.name,'Tesla') as name, c.model, c.trim_badging as trim, c.marketing_name, c.exterior_color as color, c.efficiency, c.vin, c.wheel_type from cars c order by c.display_priority, c.id")


DRIVE_SQL = f"""select d.id, d.start_date, d.end_date, d.distance, d.duration_min, d.speed_max, d.power_max, d.start_km, d.end_km,
        d.outside_temp_avg, d.inside_temp_avg, d.ascent, d.descent,
        (d.start_ideal_range_km - d.end_ideal_range_km) * c.efficiency as kwh,
        {NAME_A} as start_name, {NAME_B} as end_name, sp.battery_level as start_soc, ep.battery_level as end_soc
      from drives d join cars c on c.id=d.car_id
      left join geofences g on g.id=d.start_geofence_id left join addresses a on a.id=d.start_address_id
      left join geofences g2 on g2.id=d.end_geofence_id left join addresses a2 on a2.id=d.end_address_id
      left join positions sp on sp.id=d.start_position_id left join positions ep on ep.id=d.end_position_id
      where d.car_id=%s and d.end_date is not null"""


def drives(car, limit, offset):
    return q(DRIVE_SQL + " order by d.start_date desc limit %s offset %s", (car, limit, offset))


def drives_by_ids(car, ids):
    return q(DRIVE_SQL + " and d.id = any(%s) order by d.start_date", (car, list(ids)))


def drive_points(did):
    rows = q("select date, latitude, longitude, speed, power, battery_level, elevation from positions where drive_id=%s order by date", (did,))
    step = max(1, len(rows) // 500)
    return [[r['date'], r['latitude'], r['longitude'], r['speed'], r['power'], r['battery_level'], r['elevation']] for r in rows[::step]]


def charges(car, limit, offset):
    return q(f"""select cp.id, cp.start_date, cp.end_date, cp.charge_energy_added, cp.charge_energy_used, cp.duration_min, cp.cost,
        cp.start_battery_level as start_soc, cp.end_battery_level as end_soc, cp.outside_temp_avg,
        (select max(charger_power) from charges ch where ch.charging_process_id=cp.id) as power_max,
        coalesce((select bool_or(fast_charger_present) from charges ch where ch.charging_process_id=cp.id), false) as dc,
        {NAME_A} as name
      from charging_processes cp left join geofences g on g.id=cp.geofence_id left join addresses a on a.id=cp.address_id
      where cp.car_id=%s and cp.end_date is not null order by cp.start_date desc limit %s offset %s""", (car, limit, offset))


def charge_points(cid):
    rows = q("select date, charger_power, battery_level, charger_voltage, charger_actual_current, charge_energy_added from charges where charging_process_id=%s order by date", (cid,))
    step = max(1, len(rows) // 400)
    return [[r['date'], r['charger_power'], r['battery_level'], r['charger_voltage'], r['charger_actual_current'], r['charge_energy_added']] for r in rows[::step]]


TRIP_GAP = dt.timedelta(hours=2)     # curse cu pauza mai mica de 2 h = aceeasi calatorie


def _dtp(x):
    return dt.datetime.fromisoformat(x)


def trip(car, did):
    """Calatorie = cursa ceruta + cursele vecine cu pauza < 2 h. Intoarce segmentele cu puncte si opririle dintre ele (oprire / incarcare)."""
    rows = q("""select id, start_date, end_date from drives where car_id=%s and end_date is not null
        and start_date between (select start_date - interval '3 days' from drives where id=%s) and (select end_date + interval '3 days' from drives where id=%s)
        order by start_date""", (car, did, did))
    idx = next((i for i, r in enumerate(rows) if r['id'] == did), None)
    if idx is None:
        return dict(segments=[], stops=[])
    lo = hi = idx
    while lo > 0 and hi - lo < 11 and _dtp(rows[lo]['start_date']) - _dtp(rows[lo - 1]['end_date']) < TRIP_GAP:
        lo -= 1
    while hi < len(rows) - 1 and hi - lo < 11 and _dtp(rows[hi + 1]['start_date']) - _dtp(rows[hi]['end_date']) < TRIP_GAP:
        hi += 1
    chain = rows[lo:hi + 1]
    info = {d['id']: d for d in drives_by_ids(car, [r['id'] for r in chain])}
    per = max(120, 1400 // len(chain))
    segs = []
    for r in chain:
        pts = q("select date, latitude, longitude, speed, power, battery_level, elevation from positions where drive_id=%s order by date", (r['id'],))
        step = max(1, -(-len(pts) // per))
        sel = pts[::step]
        if pts and sel[-1] is not pts[-1]:
            sel.append(pts[-1])
        segs.append(dict(drive=info.get(r['id'], r), points=[[p['date'], p['latitude'], p['longitude'], p['speed'], p['power'], p['battery_level'], p['elevation']] for p in sel]))
    stops = []
    for a, b in zip(segs, segs[1:]):
        if not a['points']:
            continue
        t0, t1 = _dtp(a['drive']['end_date']), _dtp(b['drive']['start_date'])
        lat, lon = a['points'][-1][1], a['points'][-1][2]
        ch = q(f"""select cp.id, cp.start_date, cp.end_date, cp.charge_energy_added kwh, cp.start_battery_level s0, cp.end_battery_level s1,
            coalesce((select bool_or(fast_charger_present) from charges x where x.charging_process_id=cp.id), false) dc, {NAME_A} as name
            from charging_processes cp left join geofences g on g.id=cp.geofence_id left join addresses a on a.id=cp.address_id
            where cp.car_id=%s and cp.end_date is not null and cp.start_date between %s and %s order by cp.start_date limit 1""",
               (car, t0 - dt.timedelta(minutes=10), t1))
        if ch:
            c = ch[0]
            stops.append(dict(kind='charge', lat=lat, lon=lon, start=c['start_date'], end=c['end_date'], kwh=c['kwh'], s0=c['s0'], s1=c['s1'], dc=c['dc'], name=c['name']))
        else:
            stops.append(dict(kind='stop', lat=lat, lon=lon, start=a['drive']['end_date'], end=b['drive']['start_date'], name=a['drive'].get('end_name')))
    return dict(segments=segs, stops=stops)


def demo_trip(did):
    d1 = next((d for d in DEMO['drives'] if d['id'] == did), DEMO['drives'][0])
    p1 = demo_points(d1['id'])
    t_end = _dtp(p1[-1][0])
    r = random.Random(did + 99)
    lat, lon, soc, hd = p1[-1][1], p1[-1][2], 34.0, r.uniform(0, 6.28)
    start2 = t_end + dt.timedelta(minutes=24)
    p2 = []
    for k in range(140):
        hd += r.uniform(-.14, .14)
        v = 70 + 30 * math.sin(k / 12) + r.uniform(-8, 8)
        step = max(v, 5) / 3600 * 20 / 111
        lat += math.cos(hd) * step
        lon += math.sin(hd) * step * .72
        soc -= .09
        p2.append([(start2 + dt.timedelta(seconds=k * 20)).isoformat(), lat, lon, max(0, round(v)), round(v * 1.3 - 30 + r.uniform(-25, 15)), round(soc, 1), 120 + 40 * math.sin(k / 18)])
    end2 = _dtp(p2[-1][0])
    mk = lambda i, a, b, pts, n0, n1: dict(id=i, start_date=a.isoformat(), end_date=b.isoformat(), distance=round(len(pts) * 0.33, 1), duration_min=round((b - a).total_seconds() / 60),
                                          start_name=n0, end_name=n1, start_soc=pts[0][5], end_soc=pts[-1][5], kwh=round(len(pts) * 0.33 * 0.15, 1))
    segs = [dict(drive=mk(d1['id'], _dtp(p1[0][0]), t_end, p1, d1['start_name'], 'Supercharger Pitești'), points=p1),
            dict(drive=mk(d1['id'] + 1000, start2, end2, p2, 'Supercharger Pitești', 'Sibiu'), points=p2)]
    stops = [dict(kind='charge', lat=p1[-1][1], lon=p1[-1][2], start=t_end.isoformat(), end=start2.isoformat(), kwh=17.9, s0=round(p1[-1][5]), s1=round(p1[-1][5] + 28), dc=True, name='Supercharger Pitești')]
    return dict(segments=segs, stops=stops)


def overview(car, days):
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    d = q("""select count(*) n, coalesce(sum(d.distance),0) km, coalesce(sum(d.duration_min),0) minutes,
        coalesce(sum((d.start_ideal_range_km-d.end_ideal_range_km)*c.efficiency),0) kwh, coalesce(max(d.speed_max),0) vmax
        from drives d join cars c on c.id=d.car_id where d.car_id=%s and d.start_date>=%s and d.end_date is not null""", (car, since))[0]
    ch = q("""select count(*) n, coalesce(sum(charge_energy_added),0) kwh, coalesce(sum(cost),0) cost, coalesce(sum(duration_min),0) minutes
        from charging_processes where car_id=%s and start_date>=%s and end_date is not null""", (car, since))[0]
    byday = q("""select to_char(date_trunc('day', d.start_date),'YYYY-MM-DD') as day, sum(d.distance) km,
        sum((d.start_ideal_range_km-d.end_ideal_range_km)*c.efficiency) kwh from drives d join cars c on c.id=d.car_id
        where d.car_id=%s and d.start_date>=%s group by 1 order by 1""", (car, since))
    chday = q("""select to_char(date_trunc('day', start_date),'YYYY-MM-DD') as day, sum(charge_energy_added) kwh, sum(cost) cost
        from charging_processes where car_id=%s and start_date>=%s group by 1 order by 1""", (car, since))
    odo = q("select max(odometer) odo from positions where car_id=%s", (car,))
    return dict(days=days, drives=d, charges=ch, by_day=byday, charge_by_day=chday, odometer=(odo[0]['odo'] if odo else None))


def sleep_info(car):
    """Somn din tabelul states TeslaMate. Atentie: la aceasta masina 'offline' = adormita (confirmat cu senzorul BLE), deci asleep+offline = somn;
    randurile consecutive se contopesc intr-un singur interval de somn."""
    rows = q("select state::text as s, start_date, end_date from states where car_id=%s order by start_date desc limit 120", (car,))
    if not rows:
        return None
    now = dt.datetime.utcnow()
    P = lambda x: dt.datetime.fromisoformat(x) if x else now
    runs = []                                    # (sleeping?, start, end|None) de la cel mai nou la cel mai vechi
    for r in rows:
        sl = r['s'] in ('asleep', 'offline')
        if runs and runs[-1][0] == sl:
            runs[-1][1] = r['start_date']
        else:
            runs.append([sl, r['start_date'], r['end_date']])
    cur = runs[0]
    prev = next((x for x in runs[1:] if x[0] and x[2]), None) if cur[0] else next((x for x in runs if x[0] and x[2]), None)
    lo = now - dt.timedelta(hours=24)
    sec24 = sum(max(0, (min(P(x[2]), now) - max(P(x[1]), lo)).total_seconds()) for x in runs if x[0])
    return dict(state='asleep' if cur[0] else 'online', since=cur[1], last=dict(start=prev[1], end=prev[2]) if prev else None, sec24=sec24)


def battery(car):
    rng = q("""select to_char(date_trunc('week', date),'YYYY-MM-DD') week, avg(ideal_battery_range_km*100.0/battery_level) as range100,
        avg(rated_battery_range_km*100.0/battery_level) as rated100 from positions
        where car_id=%s and battery_level>=20 and ideal_battery_range_km is not null and date>now() - interval '2 years' group by 1 order by 1""", (car,))
    states = q("""select state::text as s, sum(extract(epoch from (coalesce(end_date, now()) - start_date)))/3600 as hours from states
        where car_id=%s and start_date>now() - interval '30 days' group by 1""", (car,))
    upd = q("select start_date, version from updates where car_id=%s order by start_date desc limit 8", (car,))
    return dict(range100=rng, states=states, updates=upd)


# ---------------------------------------------------------------- demo
def demo_data():
    r = random.Random(7)
    now = dt.datetime.utcnow().replace(microsecond=0)
    places = ['Acasă', 'Birou', 'Mega Mall', 'Kaufland', 'Părinți', 'Aeroport', 'Benzinărie Petrom', 'Supercharger Pitești', 'Piața Centrală', 'Sala de sport']
    ds, base_km = [], 18432.0
    t = now - dt.timedelta(days=30)
    i = 1
    cur = 'Acasă'
    while t < now - dt.timedelta(hours=3):
        t += dt.timedelta(hours=r.choice([5, 9, 14, 26]), minutes=r.randint(0, 50))
        dist = round(r.choice([3, 6, 9, 12, 18, 24, 35, 60, 120, 210]) * r.uniform(.8, 1.2), 1)
        dur = max(6, round(dist / r.uniform(28, 75) * 60))
        eff = r.uniform(125, 165)
        dst = r.choice([p for p in places if p != cur])
        ds.append(dict(id=i, start_date=t.isoformat(), end_date=(t + dt.timedelta(minutes=dur)).isoformat(), distance=dist, duration_min=dur,
                       speed_max=round(dist / dur * 60 * r.uniform(1.4, 2.1)), power_max=r.randint(60, 190), kwh=round(dist * eff / 1000, 1),
                       start_name=cur, end_name=dst, start_soc=0, end_soc=0, outside_temp_avg=round(r.uniform(2, 17), 1), ascent=r.randint(5, 220), descent=r.randint(5, 220)))
        cur = dst
        i += 1
    soc = 82
    for d in ds:
        d['start_soc'] = soc
        soc = max(12, soc - round(d['kwh'] / 0.6))
        d['end_soc'] = soc
        if soc < 30:
            soc = r.randint(78, 92)
    cs = []
    for n, d in enumerate(ds[::5]):
        kwh = round(r.uniform(9, 46), 1)
        dc = r.random() < .25
        pw = r.randint(95, 165) if dc else 11
        cs.append(dict(id=n + 1, start_date=d['end_date'], end_date=(dt.datetime.fromisoformat(d['end_date']) + dt.timedelta(minutes=round(kwh / pw * 60 * 1.1))).isoformat(),
                       charge_energy_added=kwh, charge_energy_used=round(kwh * 1.07, 1), duration_min=round(kwh / pw * 60 * 1.1), cost=round(kwh * (2.4 if dc else 1.15), 2),
                       start_soc=r.randint(14, 42), end_soc=r.randint(70, 95), outside_temp_avg=round(r.uniform(2, 15), 1), power_max=pw, dc=dc,
                       name='Supercharger Pitești' if dc else 'Acasă'))
    ds.reverse()
    cs.reverse()
    return dict(drives=ds, charges=cs)


DEMO = demo_data()
DEMO_CAR = dict(id=1, name='Tesla Model 3', model='3', trim='Long Range RWD', marketing_name='Model 3 Highland', color='PearlWhite', efficiency=0.143)
DEMO_LIVE = dict(display_name='Tesla Model 3', state='online', healthy=True, version='2026.14.3', update_available=False, geofence='Acasă',
                 battery_level=78, usable_battery_level=78, ideal_battery_range_km=421.0, est_battery_range_km=396.0, rated_battery_range_km=421.0, charge_limit_soc=90,
                 plugged_in=False, charging_state=None, charger_power=0, time_to_full_charge=0, locked=True, sentry_mode=True, doors_open=False, windows_open=False,
                 trunk_open=False, frunk_open=False, is_climate_on=False, is_preconditioning=False, inside_temp=19.0, outside_temp=11.0, odometer=18432.4, speed=None,
                 shift_state=None, power=0, latitude=44.4268, longitude=26.1025, tpms_pressure_fl=2.9, tpms_pressure_fr=2.9, tpms_pressure_rl=2.8, tpms_pressure_rr=2.9,
                 since=(dt.datetime.utcnow() - dt.timedelta(hours=2)).isoformat() + 'Z')


_n = dt.datetime.utcnow()
DEMO_SLEEP = dict(state='online', since=(_n - dt.timedelta(minutes=47)).isoformat(), sec24=11.5 * 3600,
                  last=dict(start=(_n - dt.timedelta(hours=9, minutes=40)).isoformat(), end=(_n - dt.timedelta(minutes=47)).isoformat()))


def demo_points(did):
    r = random.Random(did)
    lat, lon, soc = 44.4268 + r.uniform(-.05, .05), 26.1025 + r.uniform(-.08, .08), 80
    hd = r.uniform(0, 6.28)
    n, t0, pts = 140, dt.datetime.utcnow() - dt.timedelta(days=1), []
    for k in range(n):
        hd += r.uniform(-.18, .18)
        v = 40 + 35 * math.sin(k / 14) + r.uniform(-6, 6)
        step = max(v, 5) / 3600 * 15 / 111
        lat += math.cos(hd) * step
        lon += math.sin(hd) * step * .72
        soc -= .035
        pts.append([(t0 + dt.timedelta(seconds=k * 15)).isoformat(), lat, lon, max(0, round(v)), round(v * 1.3 - 20 + r.uniform(-12, 12)), round(soc, 1), 80 + 6 * math.sin(k / 22)])
    return pts


def demo_charge_points(cid):
    r = random.Random(cid)
    dc = DEMO['charges'][cid - 1]['dc'] if 0 < cid <= len(DEMO['charges']) else False
    n, soc, e, pts = 60, r.randint(14, 40), 0.0, []
    t0 = dt.datetime.utcnow() - dt.timedelta(hours=3)
    for k in range(n):
        p = (150 * (1 - soc / 105) ** 1.4 if dc else 10.8) + r.uniform(-.4, .4)
        soc = min(95, soc + p * .02 * 5 / 1.0 * (60 / n) / 3)
        e += p * 3 / 60
        pts.append([(t0 + dt.timedelta(minutes=k * 3)).isoformat(), round(max(p, 1), 1), round(soc, 1), 400 if dc else 230, round(p * 1000 / (400 if dc else 230), 1), round(e, 1)])
    return pts


def demo_overview(days):
    by_day = {}
    for d in DEMO['drives']:
        k = d['start_date'][:10]
        x = by_day.setdefault(k, dict(day=k, km=0, kwh=0))
        x['km'] += d['distance']
        x['kwh'] += d['kwh']
    ch = {}
    for c in DEMO['charges']:
        k = c['start_date'][:10]
        x = ch.setdefault(k, dict(day=k, kwh=0, cost=0))
        x['kwh'] += c['charge_energy_added']
        x['cost'] += c['cost']
    D = DEMO['drives']
    C = DEMO['charges']
    return dict(days=days, drives=dict(n=len(D), km=sum(d['distance'] for d in D), minutes=sum(d['duration_min'] for d in D), kwh=sum(d['kwh'] for d in D), vmax=max(d['speed_max'] for d in D)),
                charges=dict(n=len(C), kwh=sum(c['charge_energy_added'] for c in C), cost=sum(c['cost'] for c in C), minutes=sum(c['duration_min'] for c in C)),
                by_day=sorted(by_day.values(), key=lambda x: x['day']), charge_by_day=sorted(ch.values(), key=lambda x: x['day']), odometer=18432.4)


DEMO_VD = dict(climate_state=dict(driver_temp_setting=21.0, passenger_temp_setting=21.0, is_climate_on=False, seat_heater_left=0, seat_heater_right=0, seat_heater_rear_left=0,
                                   seat_heater_rear_center=0, seat_heater_rear_right=0, steering_wheel_heater=False, is_front_defroster_on=False, defrost_mode=0,
                                   cabin_overheat_protection='On', cop_activation_temperature='High'),
               charge_state=dict(charge_current_request=16, charge_current_request_max=32, charge_limit_soc=90, scheduled_charging_mode='StartAt',
                                 scheduled_charging_start_time_minutes=120, scheduled_departure_time_minutes=450, preconditioning_enabled=True, off_peak_charging_enabled=False),
               charge_schedules=[dict(id=1, name='Acasă', days_of_week=127, start_enabled=True, start_time=120, end_enabled=True, end_time=360, enabled=True, one_time=False)],
               precondition_schedules=[dict(id=2, days_of_week=62, precondition_time=435, enabled=True, one_time=False)])


def demo_battery():
    now = dt.date.today()
    rng = [dict(week=(now - dt.timedelta(weeks=w)).isoformat(), range100=round(540 - (52 - w) * .06 + random.Random(w).uniform(-3, 3), 1), rated100=0) for w in range(52, -1, -4)]
    return dict(range100=rng, states=[dict(s='online', hours=214), dict(s='asleep', hours=412), dict(s='offline', hours=6)],
                updates=[dict(start_date=(dt.datetime.utcnow() - dt.timedelta(days=12)).isoformat(), version='2026.14.3'), dict(start_date=(dt.datetime.utcnow() - dt.timedelta(days=45)).isoformat(), version='2026.8.6')])



# ---------------------------------------------------------------- Tesla Fleet API (comenzi)
FL = dict(cid=os.environ.get('FLEET_CLIENT_ID', ''), secret=os.environ.get('FLEET_CLIENT_SECRET', ''),
          domain=os.environ.get('FLEET_DOMAIN', ''), pin=os.environ.get('APP_PIN', ''),
          base=os.environ.get('FLEET_BASE', 'https://fleet-api.prd.eu.vn.cloud.tesla.com'),
          proxy=os.environ.get('FLEET_PROXY', 'https://proxy:4443'), cert=os.environ.get('FLEET_PROXY_CERT', '/fleet/tls-cert.pem'))
TOKENS = '/data/tokens.json'
KEYPUB = '/fleet/public-key.pem'
SCOPES = 'openid offline_access vehicle_device_data vehicle_cmds vehicle_charging_cmds'
STATES = {}      # state -> expiry (OAuth CSRF)
TLOCK = threading.Lock()


def tok_load():
    try:
        return json.load(open(TOKENS))
    except Exception:
        return {}


def tok_save(d):
    os.makedirs(os.path.dirname(TOKENS), exist_ok=True)
    fd = os.open(TOKENS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(d, f)


def http(url, data=None, headers=None, form=False, ctx=None, timeout=25, method=None):
    h = dict(headers or {})
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            h['Content-Type'] = 'application/x-www-form-urlencoded'
        else:
            body = json.dumps(data).encode()
            h['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, headers=h, method=method or ('POST' if body is not None else 'GET'))
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        raw, code = e.read(), e.code
    try:
        return code, json.loads(raw or b'{}')
    except ValueError:
        return code, {'raw': raw[:300].decode('utf-8', 'replace')}


def proxy_ctx():
    c = ssl.create_default_context()
    try:
        c.load_verify_locations(FL['cert'])
    except Exception:
        c.check_hostname, c.verify_mode = False, ssl.CERT_NONE
    return c


def fleet_status():
    t = tok_load()
    return dict(configured=bool(FL['cid'] and FL['secret'] and FL['domain']), key=os.path.isfile(KEYPUB), authorized=bool(t.get('refresh_token')),
                registered=bool(t.get('registered')), pin=bool(FL['pin']), domain=FL['domain'],
                ready=bool(FL['cid'] and FL['secret'] and FL['domain'] and t.get('refresh_token') and FL['pin']))


def access_token():
    with TLOCK:
        t = tok_load()
        if t.get('access_token') and t.get('exp', 0) > time.time() + 120:
            return t['access_token']
        if not t.get('refresh_token'):
            raise RuntimeError('Contul Tesla nu e autorizat (apasă "Conectează contul Tesla").')
        code, r = http('https://auth.tesla.com/oauth2/v3/token', dict(grant_type='refresh_token', client_id=FL['cid'], refresh_token=t['refresh_token']), form=True)
        if code != 200 or 'access_token' not in r:
            raise RuntimeError('Reînnoirea token-ului a eșuat (%s). Reautorizează contul.' % code)
        t.update(access_token=r['access_token'], exp=time.time() + int(r.get('expires_in', 28800)))
        if r.get('refresh_token'):
            t['refresh_token'] = r['refresh_token']
        tok_save(t)
        return t['access_token']


def login_url():
    st = secrets.token_urlsafe(18)
    now = time.time()
    for k in [k for k, v in STATES.items() if v < now]:
        STATES.pop(k, None)
    STATES[st] = now + 600
    q = dict(client_id=FL['cid'], locale='ro-RO', prompt='login', redirect_uri='https://%s/auth/callback' % FL['domain'], response_type='code', scope=SCOPES, state=st)
    return 'https://auth.tesla.com/oauth2/v3/authorize?' + urllib.parse.urlencode(q, quote_via=urllib.parse.quote)


def oauth_callback(code, state):
    if STATES.pop(state, 0) < time.time():
        return False, 'Sesiune de autorizare expirată sau invalidă. Reia de la "Conectează contul Tesla".'
    c, r = http('https://auth.tesla.com/oauth2/v3/token', dict(grant_type='authorization_code', client_id=FL['cid'], client_secret=FL['secret'], code=code,
                                                               audience=FL['base'], redirect_uri='https://%s/auth/callback' % FL['domain']), form=True)
    if c != 200 or 'refresh_token' not in r:
        return False, 'Tesla a refuzat schimbul de cod (%s).' % c
    t = tok_load()
    t.update(access_token=r['access_token'], refresh_token=r['refresh_token'], exp=time.time() + int(r.get('expires_in', 28800)))
    tok_save(t)
    return True, 'Contul Tesla este conectat.'


def partner_register():
    c, r = http('https://auth.tesla.com/oauth2/v3/token', dict(grant_type='client_credentials', client_id=FL['cid'], client_secret=FL['secret'],
                                                               scope=SCOPES, audience=FL['base']), form=True)
    if c != 200 or 'access_token' not in r:
        return dict(ok=False, step='token', code=c, detail=r)
    c, r = http(FL['base'] + '/api/1/partner_accounts', dict(domain=FL['domain']), headers={'Authorization': 'Bearer ' + r['access_token']})
    if c in (200, 201):
        t = tok_load()
        t['registered'] = True
        tok_save(t)
    return dict(ok=c in (200, 201), step='register', code=c, detail=r)


def vin_for(car):
    r = q('select vin from cars where id=%s', (car,))
    return r[0]['vin'] if r and r[0].get('vin') else None


CMDS = {  # nume -> (endpoint, payload)
    'lock': ('door_lock', {}), 'unlock': ('door_unlock', {}),
    'climate_on': ('auto_conditioning_start', {}), 'climate_off': ('auto_conditioning_stop', {}),
    'charge_start': ('charge_start', {}), 'charge_stop': ('charge_stop', {}),
    'port_open': ('charge_port_door_open', {}), 'port_close': ('charge_port_door_close', {}),
    'sentry_on': ('set_sentry_mode', {'on': True}), 'sentry_off': ('set_sentry_mode', {'on': False}),
    'frunk': ('actuate_trunk', {'which_trunk': 'front'}), 'trunk': ('actuate_trunk', {'which_trunk': 'rear'}),
    'flash': ('flash_lights', {}), 'honk': ('honk_horn', {}),
    'vent': ('window_control', {'command': 'vent'}), 'close_windows': ('window_control', {'command': 'close'}),
}


def vehicle_call(vin, path, data=None, method=None):
    tk = access_token()
    return http('%s/api/1/vehicles/%s/%s' % (FL['proxy'], vin, path), data, headers={'Authorization': 'Bearer ' + tk}, ctx=proxy_ctx(), timeout=40, method=method)


def _num(a, k, lo, hi, default=None):
    try:
        v = float(a[k] if k in a else default)
    except (TypeError, ValueError, KeyError):
        raise ValueError('valoare invalidă: %s' % k)
    return max(lo, min(hi, v))


def _min(a, k):
    return int(_num(a, k, 0, 1439, 0))


def _days(a):
    d = str(a.get('days') or 'ALL').upper()
    return d if d in ('ALL', 'WEEKDAYS') else ','.join(x for x in d.split(',') if x in ('SUN', 'MON', 'TUES', 'WED', 'THURS', 'FRI', 'SAT')) or 'ALL'


def build_cmd(name, arg, lv):
    """nume intern -> (endpoint Fleet, payload). Valideaza si limiteaza toate valorile primite de la client."""
    a = arg if isinstance(arg, dict) else {}
    loc = dict(lat=lv.get('latitude') or 0, lon=lv.get('longitude') or 0)
    if name in CMDS:
        ep, pl = CMDS[name]
        pl = dict(pl)
        if name in ('vent', 'close_windows'):
            pl.update(loc)
        return ep, pl
    if name == 'charge_limit':
        return 'set_charge_limit', {'percent': int(_num({'v': arg}, 'v', 50, 100))}
    if name == 'set_temps':
        t = _num(a, 'driver', 15, 28)
        return 'set_temps', {'driver_temp': t, 'passenger_temp': _num(a, 'passenger', 15, 28, t)}
    if name == 'seat_heater':
        seat = int(_num(a, 'seat', 0, 6))
        if seat not in (0, 1, 2, 4, 5):
            raise ValueError('scaun invalid')
        return 'remote_seat_heater_request', {'seat_position': seat, 'level': int(_num(a, 'level', 0, 3))}
    if name == 'steering_heater':
        return 'remote_steering_wheel_heater_request', {'on': bool(a.get('on'))}
    if name == 'defrost':
        return 'set_preconditioning_max', {'on': bool(a.get('on')), 'manual_override': True}
    if name == 'cop':
        return 'set_cabin_overheat_protection', {'on': bool(a.get('on')), 'fan_only': bool(a.get('fan_only'))}
    if name == 'cop_temp':
        return 'set_cop_temp', {'cop_temp': int(_num(a, 'level', 0, 2))}
    if name == 'charging_amps':
        return 'set_charging_amps', {'charging_amps': int(_num(a, 'amps', 1, 48))}
    if name == 'sched_charging':
        return 'set_scheduled_charging', {'enable': bool(a.get('enable')), 'time': _min(a, 'time')}
    if name == 'sched_departure':
        if not a.get('enable'):
            return 'set_scheduled_departure', {'enable': False}
        return 'set_scheduled_departure', {'enable': True, 'departure_time': _min(a, 'time'), 'preconditioning_enabled': bool(a.get('precond')),
                                           'preconditioning_weekdays_only': bool(a.get('weekdays')), 'off_peak_charging_enabled': bool(a.get('offpeak')),
                                           'off_peak_charging_weekdays_only': bool(a.get('weekdays')), 'end_off_peak_time': _min(a, 'end_offpeak')}
    if name == 'charge_schedule_add':
        pl = dict(loc, days_of_week=_days(a), start_enabled=bool(a.get('start_on', True)), start_time=_min(a, 'start'),
                  end_enabled=bool(a.get('end_on')), end_time=_min(a, 'end'), enabled=True, one_time=bool(a.get('one_time')))
        if a.get('id'):
            pl['id'] = int(_num(a, 'id', 1, 2 ** 53))
        return 'add_charge_schedule', pl
    if name == 'charge_schedule_del':
        return 'remove_charge_schedule', {'id': int(_num(a, 'id', 1, 2 ** 53))}
    if name == 'precond_add':
        pl = dict(loc, days_of_week=_days(a), precondition_time=_min(a, 'time'), enabled=True, one_time=bool(a.get('one_time')))
        if a.get('id'):
            pl['id'] = int(_num(a, 'id', 1, 2 ** 53))
        return 'add_precondition_schedule', pl
    if name == 'precond_del':
        return 'remove_precondition_schedule', {'id': int(_num(a, 'id', 1, 2 ** 53))}
    if name == 'homelink':
        if lv.get('latitude') is None or lv.get('longitude') is None:
            raise RuntimeError('Nu cunosc poziția mașinii (HomeLink are nevoie de ea).')
        return 'trigger_homelink', loc
    raise ValueError('comandă necunoscută')


def ensure_awake(vin, lv):
    if lv.get('state') in ('asleep', 'offline', None):
        vehicle_call(vin, 'wake_up', {})
        for _ in range(12):
            c, r = vehicle_call(vin, '', method='GET')
            if (r.get('response') or {}).get('state') == 'online':
                break
            time.sleep(2.5)


def run_command(car, name, arg=None):
    lv = LIVE.get(car, {})
    ep, pl = ('wake_up', {}) if name == 'wake' else build_cmd(name, arg, lv)       # valideaza inainte sa trezeasca masina
    vin = vin_for(car)
    if not vin:
        raise RuntimeError('Nu există VIN în TeslaMate (conectează mașina în TeslaMate).')
    ensure_awake(vin, lv)
    if name == 'wake':
        return dict(ok=True, code=200, reason='')
    c, r = vehicle_call(vin, 'command/' + ep, pl)
    resp = r.get('response') or {}
    ok = c == 200 and resp.get('result', True) is not False
    VD.pop(car, None)                       # starea citita din masina nu mai e valabila
    return dict(ok=ok, code=c, reason=resp.get('reason') or r.get('error') or r.get('raw') or '')


VD = {}   # car -> (ts, data): ultima stare citita direct din masina (clima/incarcare/programari)
VD_KEYS = {
    'climate_state': ('driver_temp_setting', 'passenger_temp_setting', 'inside_temp', 'outside_temp', 'is_climate_on', 'seat_heater_left', 'seat_heater_right',
                      'seat_heater_rear_left', 'seat_heater_rear_center', 'seat_heater_rear_right', 'steering_wheel_heater', 'is_front_defroster_on',
                      'is_rear_defroster_on', 'defrost_mode', 'cabin_overheat_protection', 'cop_activation_temperature', 'climate_keeper_mode'),
    'charge_state': ('charge_current_request', 'charge_current_request_max', 'charge_limit_soc', 'charging_state', 'scheduled_charging_mode',
                     'scheduled_charging_pending', 'scheduled_charging_start_time_minutes', 'scheduled_departure_time_minutes', 'preconditioning_enabled',
                     'preconditioning_times', 'off_peak_charging_enabled', 'off_peak_charging_times', 'off_peak_hours_end_time', 'charger_actual_current',
                     'charger_voltage', 'charger_phases', 'charger_pilot_current'),
}


def vehicle_data(car, force=False):
    """Citeste starea direct din masina. NU trezeste masina (ca sa nu strice somnul) - doar daca TeslaMate o vede online."""
    c = VD.get(car)
    if c and time.time() - c[0] < 45 and not force:
        return dict(c[1], cached=True)
    lv = LIVE.get(car, {})
    if lv.get('state') in ('asleep', 'offline', None):
        return dict(c[1], stale=True, asleep=True) if c else dict(asleep=True)
    vin = vin_for(car)
    if not vin:
        raise RuntimeError('Nu există VIN în TeslaMate.')
    ep = urllib.parse.quote('charge_state;climate_state;charge_schedule_data;preconditioning_schedule_data', safe='')
    code, r = vehicle_call(vin, 'vehicle_data?endpoints=' + ep, method='GET')
    resp = r.get('response') or {}
    if code != 200 or not resp:
        return dict(c[1], stale=True, error=r.get('error') or code) if c else dict(error=r.get('error') or code, asleep=code == 408)
    out = {k: {x: (resp.get(k) or {}).get(x) for x in keys} for k, keys in VD_KEYS.items()}
    out['charge_schedules'] = (resp.get('charge_schedule_data') or {}).get('charge_schedules') or []
    out['precondition_schedules'] = (resp.get('preconditioning_schedule_data') or {}).get('precondition_schedules') or []
    VD[car] = (time.time(), out)
    return dict(out)


# ---------------------------------------------------------------- notificari (cablu, incarcare gata, usi) -> telefon prin webhook Home Assistant + istoric in aplicatie
NFILE = '/data/notify.json'
NHOOK = os.environ.get('NOTIFY_WEBHOOK', '')
NDEFAULT = dict(plugged=True, charge_done=True, door=True)
EVENTS = []          # cele mai noi primele, max 60
NLOCK = threading.Lock()
LAST_SENT = {}


def nset_load():
    try:
        return dict(NDEFAULT, **{k: bool(v) for k, v in json.load(open(NFILE)).items() if k in NDEFAULT})
    except Exception:
        return dict(NDEFAULT)


def nset_save(d):
    try:
        os.makedirs(os.path.dirname(NFILE), exist_ok=True)
        json.dump(d, open(NFILE, 'w'))
    except Exception as e:  # noqa
        print('notify save:', e, flush=True)


def notify(kind, title, msg):
    ev = dict(t=dt.datetime.utcnow().replace(microsecond=0).isoformat(), kind=kind, title=title, msg=msg)
    with NLOCK:
        EVENTS.insert(0, ev)
        del EVENTS[60:]
    if NHOOK:
        threading.Thread(target=lambda: http(NHOOK, dict(title=title, message=msg, kind=kind), timeout=10), daemon=True).start()
    return bool(NHOOK)


def _once(kind, secs=90):
    now = time.time()
    if now - LAST_SENT.get(kind, 0) < secs:
        return False
    LAST_SENT[kind] = now
    return True


OPEN_KEYS = {'doors_open': 'o ușă', 'trunk_open': 'portbagajul', 'frunk_open': 'frunk-ul', 'windows_open': 'un geam'}


def notify_check(car, key, old, new):
    if old is None or old == new:
        return
    lv = LIVE.get(car, {})
    nm = lv.get('display_name') or 'Tesla'
    st = nset_load()
    soc = lv.get('battery_level')
    if key == 'plugged_in' and new is True and st['plugged'] and _once('plugged'):
        notify('plugged', '🔌 Cablu conectat', '%s: cablul a fost conectat%s.' % (nm, ' (baterie %s%%)' % soc if soc is not None else ''))
    elif key == 'charging_state' and new == 'Complete' and st['charge_done'] and _once('charge_done', 600):
        notify('charge_done', '🔋 Încărcare terminată', '%s: baterie %s%%%s.' % (nm, soc if soc is not None else '?', ', limita %s%%' % lv['charge_limit_soc'] if lv.get('charge_limit_soc') else ''))
    elif key in OPEN_KEYS and new is True and st['door']:
        what = OPEN_KEYS[key]
        if lv.get('locked') and key != 'windows_open' and _once('door_locked:' + key, 120):
            notify('door', '⚠️ Deschis cât mașina e blocată', '%s: s-a deschis %s deși mașina e blocată.' % (nm, what))
            return

        def later():
            l2 = LIVE.get(car, {})
            if l2.get(key) is True and l2.get('shift_state') in (None, 'P') and _once('door_left:' + key, 1800):
                notify('door', '🚪 Lăsat deschis', '%s: %s e deschis(ă) de peste 5 minute.' % (nm, what))
        t = threading.Timer(300, later)
        t.daemon = True
        t.start()


# ---------------------------------------------------------------- acces din internet (parola + cookie semnat)
import hashlib, hmac
AUTH = dict(pw=os.environ.get('APP_PASSWORD', ''), secret=(os.environ.get('SESSION_SECRET') or secrets.token_hex(32)).encode())
FAILS = {}   # ip -> [timestamps]
LOGIN = {
    'ro': dict(title='Autentificare', pw='Parolă', go='Intră', bad='Parolă greșită.', lock='Prea multe încercări. Reia peste câteva minute.', off='Accesul din internet nu este configurat.'),
    'en': dict(title='Sign in', pw='Password', go='Sign in', bad='Wrong password.', lock='Too many attempts. Try again in a few minutes.', off='Internet access is not configured.'),
}


def sess_make():
    ts = str(int(time.time()))
    return ts + '.' + hmac.new(AUTH['secret'], ts.encode(), hashlib.sha256).hexdigest()


def sess_ok(v):
    try:
        ts, sig = v.split('.', 1)
        good = hmac.new(AUTH['secret'], ts.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and time.time() - int(ts) < 30 * 86400
    except Exception:
        return False


ACCESS = dict(team=os.environ.get('ACCESS_TEAM', ''), aud=os.environ.get('ACCESS_AUD', ''), email=os.environ.get('ACCESS_EMAIL', ''))
_JWKS = []


def access_ok(token):
    """Valideaza JWT-ul Cloudflare Access (semnatura, audienta, emitent) - cererea a trecut deci prin autentificarea Access."""
    if not (ACCESS['team'] and ACCESS['aud'] and token):
        return False
    try:
        import jwt
        if not _JWKS:
            _JWKS.append(jwt.PyJWKClient('https://%s/cdn-cgi/access/certs' % ACCESS['team'], cache_keys=True, lifespan=3600))
        key = _JWKS[0].get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=['RS256'], audience=ACCESS['aud'], issuer='https://' + ACCESS['team'])
        return not ACCESS['email'] or claims.get('email') == ACCESS['email']
    except Exception as e:  # noqa
        print('access jwt:', e, flush=True)
        return False


def login_html(lang, msg=''):
    t = LOGIN['ro' if lang.lower().startswith('ro') else 'en']
    note = '<p class="m">%s</p>' % msg if msg else ''
    return ('<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>%s</title>'
            '<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0d10;color:#eceff3;font-family:system-ui,sans-serif}'
            'form{width:min(86vw,340px);background:#14181d;border:1px solid #ffffff12;border-radius:22px;padding:26px}h1{margin:0 0 16px;font-size:22px}'
            'input,button{width:100%%;box-sizing:border-box;border-radius:14px;border:1px solid #ffffff1a;background:#0b0d10;color:#eceff3;font:inherit;padding:13px;margin-top:10px}'
            'button{background:#6fd6b8;color:#06231b;font-weight:800;border:0;cursor:pointer}.m{color:#ffb3b3;margin:10px 0 0;font-size:14px}</style>'
            '<form method=post action=/login><h1>%s</h1><input type=password name=password placeholder="%s" autofocus autocomplete=current-password>'
            '<button>%s</button>%s</form>') % (t['title'], t['title'], t['pw'], t['go'], note)


# ---------------------------------------------------------------- HTTP
def has_cars():
    if DEMO_ONLY:
        return False
    try:
        return bool(q('select 1 from cars limit 1'))
    except Exception:
        return None  # DB inaccesibil


def car_image(c):
    """Imaginea masinii e servita la /car.png: /data/car.png (a utilizatorului), apoi static/car.png, apoi desenul generic car-default.svg."""
    return '/car.png'


def live_for(car_id):
    return dict(LIVE.get(car_id, {}))


def api_state():
    cl = has_cars()
    if cl:
        out = []
        for c in cars():
            lv = live_for(c['id'])
            if not lv:
                p = q("select date, latitude, longitude, battery_level, usable_battery_level, ideal_battery_range_km, est_battery_range_km, rated_battery_range_km, odometer, outside_temp, inside_temp, "
                      "tpms_pressure_fl, tpms_pressure_fr, tpms_pressure_rl, tpms_pressure_rr, is_climate_on from positions where car_id=%s order by date desc limit 1", (c['id'],))
                if p:
                    lv = {k: v for k, v in p[0].items() if k != 'date'}
                    lv['since'] = p[0]['date']
                    lv['state'] = 'offline'
            if lv.get('tpms_pressure_fl') is None:
                try:
                    tp = q("select tpms_pressure_fl, tpms_pressure_fr, tpms_pressure_rl, tpms_pressure_rr, date from positions "
                           "where car_id=%s and tpms_pressure_fl is not null order by date desc limit 1", (c['id'],))
                    if tp:
                        lv = dict(lv, **{k: v for k, v in tp[0].items() if k.startswith('tpms_')})
                        lv['tpms_date'] = tp[0]['date']
                except Exception:
                    pass
            try:
                c['sleep'] = sleep_info(c['id'])
            except Exception:
                c['sleep'] = None
            c['live'] = lv
            c['image'] = car_image(c)
            c['live_age'] = (time.time() - LIVE_TS[c['id']]) if c['id'] in LIVE_TS else None
            out.append(c)
        return dict(demo=False, cars=out, links=LINKS, mqtt=bool(LIVE), currency=CURRENCY)
    return dict(demo=True, public_demo=DEMO_ONLY, cars=[dict(DEMO_CAR, live=DEMO_LIVE, live_age=0, image=car_image(DEMO_CAR), sleep=DEMO_SLEEP)],
                links=({} if DEMO_ONLY else LINKS), mqtt=False, currency=CURRENCY, db_error=(cl is None and not DEMO_ONLY))


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'

    def log_message(self, *a):
        pass

    def via_internet(self):
        return any(k in self.headers for k in ('Cf-Connecting-Ip', 'Cf-Ray', 'Cf-Visitor', 'X-Forwarded-For'))

    def client_ip(self):
        return self.headers.get('Cf-Connecting-Ip') or self.headers.get('X-Forwarded-For', '').split(',')[0].strip() or self.client_address[0]

    def authed(self):
        if DEMO_ONLY or not self.via_internet():
            return True            # LAN: ca pana acum
        if access_ok(self.headers.get('Cf-Access-Jwt-Assertion', '')):
            return True            # a trecut de Cloudflare Access (verificat criptografic)
        if not AUTH['pw']:
            return False           # din internet fara parola configurata: totul inchis
        for part in self.headers.get('Cookie', '').split(';'):
            k, _, v = part.strip().partition('=')
            if k == 'sess' and sess_ok(v):
                return True
        return False

    def lang(self):
        return (self.headers.get('Accept-Language') or 'en')[:2]

    def page(self, code, html, extra=None):
        b = html.encode()
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(b)))
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def do_login(self):
        t = LOGIN['ro' if self.lang().lower().startswith('ro') else 'en']
        ip, now = self.client_ip(), time.time()
        FAILS[ip] = [x for x in FAILS.get(ip, []) if now - x < 600]
        if not AUTH['pw']:
            return self.page(403, login_html(self.lang(), t['off']))
        if len(FAILS[ip]) >= 5:
            return self.page(429, login_html(self.lang(), t['lock']))
        n = int(self.headers.get('Content-Length') or 0)
        form = parse_qs(self.rfile.read(min(n, 2048)).decode('utf-8', 'replace'))
        pw = (form.get('password') or [''])[0]
        if secrets.compare_digest(pw, AUTH['pw']):
            FAILS.pop(ip, None)
            ck = 'sess=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict%s' % (sess_make(), 30 * 86400, '; Secure' if self.via_internet() else '')
            self.send_response(303)
            self.send_header('Location', '/')
            self.send_header('Set-Cookie', ck)
            self.end_headers()
            return
        FAILS[ip].append(now)
        return self.page(401, login_html(self.lang(), t['bad']))

    def send_json(self, obj, code=200):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        a = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        if p == '/login':
            return self.page(200, login_html(self.lang()))
        if p == '/logout':
            self.send_response(303)
            self.send_header('Location', '/login')
            self.send_header('Set-Cookie', 'sess=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict')
            self.end_headers()
            return
        if p != '/api/health' and not self.authed():
            if p.startswith('/api/'):
                return self.send_json(dict(error='auth'), 401)
            return self.page(401, login_html(self.lang()))
        try:
            if p == '/api/health':
                return self.send_json(dict(ok=True, mqtt=bool(LIVE)))
            if p == '/api/state':
                return self.send_json(api_state())
            if p == '/api/stream':
                return self.stream()
            if p.startswith('/api/fleet/') and DEMO_ONLY:
                return self.send_json(dict(error='disabled in demo'), 404)
            if p == '/api/fleet/status':
                return self.send_json(fleet_status())
            if p == '/api/fleet/login':
                if not (FL['cid'] and FL['domain']):
                    return self.send_json(dict(error='Fleet API nu e configurat.'), 400)
                self.send_response(302)
                self.send_header('Location', login_url())
                self.end_headers()
                return
            if p.startswith('/api/'):
                return self.send_json(self.api(p, a))
        except Exception as e:  # noqa
            return self.send_json(dict(error=str(e)), 500)
        return self.static(p)

    def do_POST(self):
        u = urlparse(self.path)
        if DEMO_ONLY:
            return self.send_json(dict(ok=False, reason='demo'), 403)
        if u.path == '/login':
            return self.do_login()
        if not self.authed():
            return self.send_json(dict(ok=False, reason='auth'), 401)
        try:
            n = int(self.headers.get('Content-Length') or 0)
            body = json.loads(self.rfile.read(n) or b'{}') if n else {}
            if u.path == '/api/notify/settings':
                st = nset_load()
                st.update({k: bool(v) for k, v in body.items() if k in NDEFAULT})
                nset_save(st)
                return self.send_json(dict(ok=True, settings=st))
            if u.path == '/api/notify/test':
                return self.send_json(dict(ok=True, sent=notify('test', '🔔 Test notificare', 'Notificările din aplicația Tesla funcționează.')))
            if not FL['pin'] or not secrets.compare_digest(self.headers.get('X-Pin', ''), FL['pin']):
                return self.send_json(dict(ok=False, reason='PIN greșit sau neconfigurat.'), 403)
            if u.path == '/api/fleet/register':
                return self.send_json(partner_register())
            if u.path.startswith('/api/cmd/'):
                return self.send_json(run_command(int(body.get('car', 1)), u.path.rsplit('/', 1)[1], body.get('arg')))
        except Exception as e:  # noqa
            return self.send_json(dict(ok=False, reason=str(e)), 500)
        return self.send_json(dict(error='not found'), 404)

    def api(self, p, a):
        demo = not has_cars()
        car = int(a.get('car', 1))
        lim, off = min(int(a.get('limit', 40)), 200), int(a.get('offset', 0))
        if p == '/api/drives':
            return DEMO['drives'][off:off + lim] if demo else drives(car, lim, off)
        if p.startswith('/api/drive/'):
            did = int(p.rsplit('/', 1)[1])
            return dict(points=demo_points(did) if demo else drive_points(did))
        if p.startswith('/api/trip/'):
            did = int(p.rsplit('/', 1)[1])
            return demo_trip(did) if demo else trip(car, did)
        if p == '/api/charges':
            return DEMO['charges'][off:off + lim] if demo else charges(car, lim, off)
        if p.startswith('/api/charge/'):
            cid = int(p.rsplit('/', 1)[1])
            return dict(points=demo_charge_points(cid) if demo else charge_points(cid))
        if p == '/api/overview':
            days = int(a.get('days', 30))
            return demo_overview(days) if demo else overview(car, days)
        if p == '/api/battery':
            return demo_battery() if demo else battery(car)
        if p == '/api/vdata':
            return DEMO_VD if demo else vehicle_data(car, a.get('force') == '1')
        if p == '/api/notify':
            with NLOCK:
                ev = list(EVENTS)
            return dict(events=ev, settings=nset_load(), hook=bool(NHOOK))
        return dict(error='not found')

    def stream(self):
        qu = queue.Queue(maxsize=500)
        with CLOCK:
            CLIENTS.add(qu)
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        try:
            self.wfile.write(b'retry: 3000\n\n')
            self.wfile.flush()
            while True:
                try:
                    m = qu.get(timeout=15)
                    self.wfile.write(b'data: ' + json.dumps(m).encode() + b'\n\n')
                except queue.Empty:
                    self.wfile.write(b': ping\n\n')
                self.wfile.flush()
        except Exception:
            pass
        finally:
            with CLOCK:
                CLIENTS.discard(qu)

    def static(self, p):
        if p in ('/', ''):
            p = '/index.html'
        f = os.path.normpath(os.path.join(STATIC, p.lstrip('/')))
        if p == '/car.png':
            user = os.path.join(os.path.dirname(TOKENS), 'car.png')
            f = user if os.path.isfile(user) else (f if os.path.isfile(f) else os.path.join(STATIC, 'car-default.svg'))
        elif not f.startswith(STATIC):
            f = ''
        if not f or not os.path.isfile(f):
            self.send_response(404)
            self.end_headers()
            return
        ct = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml',
              '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.png': 'image/png'}.get(os.path.splitext(f)[1], 'application/octet-stream')
        b = open(f, 'rb').read()
        self.send_response(200)
        self.send_header('Content-Type', ct)
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class PublicH(BaseHTTPRequestHandler):
    """Singurul lucru expus public (prin tunel): cheia publica Tesla + callback-ul OAuth. Nimic altceva."""
    protocol_version = 'HTTP/1.0'

    def log_message(self, *a):
        pass

    def out(self, code, body, ct='text/plain; charset=utf-8'):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/.well-known/appspecific/com.tesla.3p.public-key.pem' and os.path.isfile(KEYPUB):
            return self.out(200, open(KEYPUB, 'rb').read(), 'application/x-pem-file')
        if u.path == '/auth/callback':
            a = {k: v[0] for k, v in parse_qs(u.query).items()}
            if a.get('code') and a.get('state'):
                ok, msg = oauth_callback(a['code'], a['state'])
            else:
                ok, msg = False, a.get('error_description') or a.get('error') or 'Lipseste codul de autorizare.'
            msg = msg.replace('<', '').replace('>', '')
            html = ('<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
                    '<body style="font-family:system-ui;background:#0b0d10;color:#eceff3;padding:40px;text-align:center">'
                    '<h2>%s %s</h2><p style="color:#8f99a4">Poti inchide pagina si reveni in aplicatie.</p>' % ('&#10003;' if ok else '&#9888;', msg))
            return self.out(200 if ok else 400, html, 'text/html; charset=utf-8')
        return self.out(404, 'not found')

    def do_POST(self):
        return self.out(405, 'method not allowed')


def serve_public():
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PUBLIC_PORT', '4101'))), PublicH).serve_forever()


if __name__ == '__main__':
    if not DEMO_ONLY:
        threading.Thread(target=mqtt_thread, daemon=True).start()
        threading.Thread(target=serve_public, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()

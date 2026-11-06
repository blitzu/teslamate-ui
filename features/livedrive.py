"""Cursa in desfasurare (#/live): traseul parcurs pana acum, unde e masina, destinatia navigatiei (TeslaMate o publica in `active_route`), cat mai e pana acolo si ora sosirii,
plus distanta, durata, energia si costul de pana acum. Totul vine din starea live (MQTT) si din pozitiile cursei deschise din TeslaMate (drives.end_date NULL); nu se scrie nimic."""
import datetime as dt
import math
import time

MILE = 1.609344
PRICE_TTL = 600
_price = {}


def hav_km(a, b, c, d):
    r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742 * math.asin(min(1, math.sqrt(x)))


def num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def driving(lv):
    return lv.get('state') == 'driving' or lv.get('shift_state') in ('D', 'R', 'N')


def route_info(lv, now):
    """Destinatia navigatiei: nume, coordonate, minute si km pana acolo, ora sosirii, energia la sosire. None fara navigatie activa (sau cu eroare)."""
    r = lv.get('active_route') if isinstance(lv.get('active_route'), dict) else {}
    if r.get('error'):
        return None
    loc = r.get('location') if isinstance(r.get('location'), dict) else {}
    lat, lon = num(loc.get('latitude')), num(loc.get('longitude'))
    if lat is None:
        lat, lon = num(lv.get('active_route_latitude')), num(lv.get('active_route_longitude'))
    name = r.get('destination') or lv.get('active_route_destination')
    mins = num(r.get('minutes_to_arrival'))
    if not name and lat is None and mins is None:
        return None
    km = num(r.get('miles_to_arrival'))
    km = km * MILE if km is not None else None
    me = (num(lv.get('latitude')), num(lv.get('longitude')))
    if km is None and lat is not None and None not in me:
        km = hav_km(me[0], me[1], lat, lon)                                 # fara distanta de la masina: in linie dreapta (aproximativ)
    return dict(name=name or None, lat=lat, lon=lon, min=round(mins, 1) if mins is not None else None, eta=int(now + mins * 60) if mins is not None else None,
                km=round(km, 1) if km is not None else None, soc_arrival=num(r.get('energy_at_arrival')), delay=num(r.get('traffic_minutes_delay')))


def started_ts(s):
    d = dt.datetime.fromisoformat(str(s))
    return (d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)).timestamp()


def build(lv, drv, pts, now, eff, price):
    """Raspunsul paginii: lv = starea live, drv = randul cursei deschise (sau None), pts = punctele ei, eff = kWh/km de autonomie, price = pret estimat kWh (sau None)."""
    out = dict(active=driving(lv), now=int(now), lat=num(lv.get('latitude')), lon=num(lv.get('longitude')), heading=num(lv.get('heading')), speed=num(lv.get('speed')),
               soc=num(lv.get('battery_level')), power=num(lv.get('power')), route=route_info(lv, now), points=pts, drive_id=drv['id'] if drv else None)
    if not drv:
        return out
    t0 = started_ts(drv['start_date'])
    out['started'] = int(t0)
    out['min'] = max(0, round((now - t0) / 60))
    odo, o0 = num(lv.get('odometer')), num(drv.get('start_km'))
    km = max(0.0, odo - o0) if odo is not None and o0 is not None else None
    r0, r1 = num(drv.get('start_ideal_range_km')), num(lv.get('ideal_battery_range_km'))
    kwh = max(0.0, (r0 - r1) * eff) if None not in (r0, r1) and eff else None
    out['km'] = round(km, 2) if km is not None else None
    out['kwh'] = round(kwh, 2) if kwh is not None else None
    out['wh_km'] = round(kwh * 1000 / km) if kwh is not None and km and km >= 0.5 else None
    out['cost'] = round(kwh * price, 2) if kwh is not None and price else None
    out['price'] = price
    return out


def init(S):
    def price_now(car):
        """Pretul estimat al kWh din ultima cursa terminata (aceeasi regula ca la costul curselor); tinut 10 minute ca sa nu recalculam la fiecare sondaj."""
        hit = _price.get(car)
        if hit and time.time() - hit[0] < PRICE_TTL:
            return hit[1]
        p = None
        try:
            if S.DRIVECOST:
                rows = S.drives(car, 1, 0)
                S.DRIVECOST.annotate(car, rows)
                p = (rows[0].get('price_kwh') if rows else None)
        except Exception as e:  # noqa
            S.log('livedrive pret:', e, flush=True)
        _price[car] = (time.time(), p)
        return p

    @S.route('GET', '/api/livedrive')
    def api_live(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        car = int(a.get('car', 1))
        lv = dict(S.LIVE.get(car, {}))
        if hc is False or not driving(lv):
            return dict(active=False, route=None, points=[])
        drv = (S.q('select id, start_date, start_km, start_ideal_range_km from drives where car_id=%s and end_date is null order by start_date desc limit 1', (car,)) or [None])[0]
        pts = S.drive_points(drv['id']) if drv else []
        eff = ((S.q('select efficiency from cars where id=%s', (car,)) or [{}])[0].get('efficiency')) or 0.15
        return build(lv, drv, pts, time.time(), eff, price_now(car))

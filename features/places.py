"""Locuri salvate cu pret pe kWh: dai un nume, o raza si un pret locului unde incarci, iar toate incarcarile de acolo (si cele vechi) primesc automat un cost = kWh x pret.
Ordinea costului efectiv: introdus manual > cost real din reteaua de acasa (Home Assistant) > pretul locului salvat > costul din TeslaMate. Nu se scrie nimic in TeslaMate."""
import math
import re
import time

MAX_PLACES = 100


def hav_m(a, b, c, d):
    r = math.pi / 180
    x = math.sin((c - a) * r / 2) ** 2 + math.cos(a * r) * math.cos(c * r) * math.sin((d - b) * r / 2) ** 2
    return 12742000 * math.asin(min(1, math.sqrt(x)))


def nearest(places, lat, lon):
    """Cel mai apropiat loc salvat care contine punctul (dupa raza lui), sau None."""
    best = None
    for p in places:
        d = hav_m(lat, lon, p['lat'], p['lon'])
        if d <= p['radius'] and (best is None or d < best[0]):
            best = (d, p)
    return best[1] if best else None


def clean(b):
    name = re.sub(r'[<>\r\n]', '', str(b.get('name', ''))).strip()[:60]
    if not name:
        raise ValueError('numele locului')
    try:
        lat, lon = float(b.get('lat')), float(b.get('lon'))
        price = float(str(b.get('price')).replace(',', '.'))
        radius = int(float(b.get('radius') or 150))
    except (TypeError, ValueError):
        raise ValueError('coordonate, preț și rază: numere')
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('coordonate invalide')
    if not 0 <= price <= 50:
        raise ValueError('prețul pe kWh: între 0 și 50')
    return dict(name=name, lat=lat, lon=lon, price=price, radius=max(30, min(radius, 2000)))


def init(S):
    S.OWN.migrate('places', ['create table places (id integer primary key, name text not null, lat real not null, lon real not null, radius integer not null default 150, price real not null, ts real)'])
    cache = {'t': 0, 'rows': []}

    def rows():
        if time.time() - cache['t'] > 30:
            cache['rows'], cache['t'] = S.OWN.rows('select id, name, lat, lon, radius, price from places'), time.time()
        return cache['rows']

    class Places:
        def match(self, lat, lon):
            if lat is None or lon is None:
                return None
            return nearest(rows(), float(lat), float(lon))

    S.PLACES = Places()

    @S.route('GET', '/api/places')
    def listing(h, a):
        return dict(places=S.OWN.rows('select id, name, lat, lon, radius, price from places order by name collate nocase'))

    @S.route('POST', '/api/places/save', pin=True, role='user')
    def save(h, b):
        p = clean(b)
        if b.get('id'):
            S.OWN.run('update places set name=?, lat=?, lon=?, radius=?, price=?, ts=? where id=?', (p['name'], p['lat'], p['lon'], p['radius'], p['price'], time.time(), int(b['id'])))
        else:
            if S.OWN.one('select count(*) n from places')['n'] >= MAX_PLACES:
                raise ValueError('Maxim %d locuri salvate.' % MAX_PLACES)
            S.OWN.run('insert into places(name, lat, lon, radius, price, ts) values(?,?,?,?,?,?)', (p['name'], p['lat'], p['lon'], p['radius'], p['price'], time.time()))
        cache['t'] = 0

    @S.route('POST', '/api/places/delete', pin=True, role='user')
    def delete(h, b):
        S.OWN.run('delete from places where id=?', (int(b.get('id', 0)),))
        cache['t'] = 0

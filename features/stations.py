"""Cauta statia de incarcare de la locul unei incarcari, in OpenStreetMap (Overpass): propune furnizorul si, cand statia are pretul pe kWh, un cost estimat.
Se apeleaza doar cand apesi "Cauta statia" (coordonatele incarcarii pleaca la serverul Overpass), fara cheie; raspunsul se tine 24 h in memorie. Nu se scrie nimic automat:
tu alegi daca folosesti furnizorul sau costul propus."""
import json
import re
import threading
import time
import urllib.parse

from .places import hav_m

ENDPOINTS = ['https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter', 'https://overpass.openstreetmap.fr/api/interpreter']      # serverele publice cad uneori: le incercam pe rand
FETCH_TIMEOUT = 9
RADIUS = 250                    # metri in jurul punctului incarcarii
MAX_RESULTS = 5
TTL = 24 * 3600
CACHE = {}
PRICE_RX = [re.compile(r'(lei|ron|eur|euro|€|usd|\$|gbp|£)\s*(\d+(?:[.,]\d+)?)\s*(?:/|per)\s*kwh', re.I),
            re.compile(r'(\d+(?:[.,]\d+)?)\s*(lei|ron|eur|euro|€|usd|\$|gbp|£)?\s*(?:/|per)\s*kwh', re.I)]
SOCKETS = [('socket:type2_combo', 'CCS'), ('socket:type2', 'Type 2'), ('socket:chademo', 'CHAdeMO'), ('socket:tesla_supercharger', 'Tesla'), ('socket:tesla_destination', 'Tesla'),
           ('socket:type2_cable', 'Type 2')]
CODES = {'lei': 'RON', 'ron': 'RON', 'eur': 'EUR', 'euro': 'EUR', '€': 'EUR', 'usd': 'USD', '$': 'USD', 'gbp': 'GBP', '£': 'GBP'}


def build_query(lat, lon):
    a = '(around:%d,%.6f,%.6f)' % (RADIUS, lat, lon)
    return '[out:json][timeout:8];(node%s[amenity=charging_station];way%s[amenity=charging_station];);out center tags 20;' % (a, a)


def clean(s, n=60):
    return re.sub(r'[<>"\r\n]', '', str(s or '')).strip()[:n]


def price_of(text):
    """(valoare, cod moneda) din text liber tip "2.5 RON/kWh" sau "EUR 0.69/kWh"; None daca nu se intelege."""
    for i, rx in enumerate(PRICE_RX):                       # intai tiparul cu moneda in fata ("EUR 0.69/kWh"), apoi cel cu numarul primul
        m = rx.search(str(text or ''))
        if m:
            num, cur = (m.group(2), m.group(1)) if i == 0 else (m.group(1), m.group(2))
            try:
                return float(num.replace(',', '.')), CODES.get((cur or '').lower())
            except ValueError:
                return None
    return None


def provider_guess(t, auto):
    """Furnizorul propus: numele cunoscut din lista aplicatiei (operator / brand / retea / nume), altfel operatorul asa cum e in harta."""
    raw = clean(t.get('operator') or t.get('brand') or t.get('network') or t.get('name'), 40)
    if re.search(r'tesla', raw, re.I):
        return 'Tesla Supercharger'
    for src in (t.get('operator'), t.get('brand'), t.get('network'), t.get('name')):
        hit = auto(src or '')
        if hit:
            return hit
    return raw


def parse(data, lat, lon, auto, cur_code=None, kwh=None):
    """Candidatele din raspunsul Overpass, cele mai apropiate primele."""
    out = []
    for e in (data or {}).get('elements') or []:
        t = e.get('tags') or {}
        c = e.get('center') or e
        if c.get('lat') is None or c.get('lon') is None:
            continue
        txt = t.get('charge') or t.get('charge:fee') or ''
        p = price_of(txt)
        socks = []
        for k, label in SOCKETS:
            if t.get(k) and label not in socks:
                socks.append(label)
        cost = None
        if p and kwh and cur_code and p[1] == cur_code:
            cost = round(p[0] * kwh, 2)
        out.append(dict(id='%s/%s' % (e.get('type'), e.get('id')), name=clean(t.get('name') or t.get('operator') or t.get('brand') or ''), provider=provider_guess(t, auto),
                        operator=clean(t.get('operator')), network=clean(t.get('network') or t.get('brand')), dist=round(hav_m(lat, lon, c['lat'], c['lon'])),
                        fee=t.get('fee') or '', price_text=clean(txt, 80), price=p[0] if p else None, price_cur=p[1] if p else None, cost_est=cost,
                        capacity=t.get('capacity') or '', sockets=socks, hours=clean(t.get('opening_hours'), 60)))
    out.sort(key=lambda x: x['dist'])
    return out[:MAX_RESULTS]


LINK_RADIUS = 150               # asocierea automata accepta doar statii la cel mult 150 m


def convert(S, cands, kwh=None):
    """Aduce preturile statiilor in moneda aplicatiei (curs BCE / open.er-api.com, cu cache); pastreaza pretul original (orig_price / orig_cur) ca sa se vada. Fara curs, ramane neschimbat."""
    to = S.CUR_CODES.get(str(S.CURRENCY).strip().lower())
    fx = getattr(S, 'fx_rate', None)
    if not to or not fx:
        return cands
    for c in cands:
        for t in c.get('tariffs') or []:
            cur = str(t.get('cur') or '').upper()
            if cur and cur != to and t.get('price'):
                r = fx(cur, to)
                if r:
                    t['orig_price'], t['orig_cur'] = t['price'], cur
                    t['price'], t['per_h'], t['cur'] = round(t['price'] * r, 3), round((t.get('per_h') or 0) * r, 2), to
        pc = str(c.get('price_cur') or '').upper()
        if c.get('price') and pc and pc != to:
            r = fx(pc, to)
            if r:
                orig = '%g %s' % (c['price'], pc)
                c['price'], c['price_cur'] = round(c['price'] * r, 3), to
                c['price_text'] = '%.2f %s/kWh (%s)' % (c['price'], to, orig)
        if c.get('price') and kwh and c.get('price_cur') == to:
            c['cost_est'] = round(c['price'] * kwh, 2)
    return cands


def link_row(S, row, force=False):
    """Asociaza o incarcare cu cea mai apropiata statie din sursa optionala (furnizor, tarife, tariful potrivit AC/DC). Nu atinge costul si nu schimba un furnizor ales de tine.
    Intoarce statia gasita sau None (fara sursa, fara coordonate, deja asociata, nicio statie in raza)."""
    extra = getattr(S, 'STATION_SOURCE', None)
    if not extra or row.get('lat') is None or row.get('lon') is None:
        return None
    if (S.meta_load().get(str(row['id'])) or {}).get('station') and not force:
        return None
    kwh = row.get('charge_energy_used') or row.get('charge_energy_added')
    found = extra.find(float(row['lat']), float(row['lon']), LINK_RADIUS, dc=row.get('dc'), power=row.get('power_max'), kwh=kwh, cur_code=S.CUR_CODES.get(str(S.CURRENCY).strip().lower()))
    if not found:
        return None
    convert(S, found, kwh)
    s = found[0]
    S.meta_update(row['id'], dict(station=dict(name=s['name'], provider=s.get('provider') or '', address=s.get('address') or '', tariffs=s.get('tariffs') or [],
                                               sel=s.get('matched', -1), auto=True, src=getattr(extra, 'name', ''))))
    return s


def autolink(S, car, force=False):
    """Asociaza toate incarcarile fara statie. Intoarce [(id, data, statie, furnizor, distanta m)] pentru ce s-a asociat."""
    out = []
    for r in S.decorate(S._charges_rows(car, 5000, 0)):
        s = link_row(S, r, force)
        if s:
            out.append((r['id'], str(r['start_date'])[:10], s['name'], s.get('provider'), s['dist']))
    return out


BACKFILL_KEY = 'stations_backfill'


def backfill_once(S):
    """Prima data cand exista o sursa de statii utilizabila: asociaza incarcarile deja existente (o singura data, apoi se tine minte in baza proprie).
    True = gata (sau nimic de facut); False = sursa nu e inca gata (oprita / fara date), se reincearca mai tarziu."""
    if S.OWN.kv_get(BACKFILL_KEY):
        return True
    extra = getattr(S, 'STATION_SOURCE', None)
    if not extra:
        return True
    ready = getattr(extra, 'ready', None)
    if ready and not ready():
        return False
    n, failed_before = 0, getattr(extra, 'last_fail', 0)
    for car in [r['id'] for r in S.q('select id from cars order by id')]:
        n += len(autolink(S, car))
    if getattr(extra, 'last_fail', 0) > failed_before:
        return False                                                          # o descarcare a esuat in timpul asocierii: nu marcam, reluam mai tarziu
    S.OWN.kv_set(BACKFILL_KEY, dict(at=time.strftime('%Y-%m-%dT%H:%M:%S'), linked=n))
    S.log('statii: %d incarcari existente asociate cu statia lor (o singura data)' % n, flush=True)
    return True


def init(S):
    S.STATION_LINK = lambda row: link_row(S, row)

    def backfill_loop():
        time.sleep(90)                                                        # dupa ce porneste baza de date si restul aplicatiei
        while True:
            try:
                if backfill_once(S):
                    return
            except Exception as e:  # noqa
                S.log('asociere statii (prima pornire):', str(e)[:100], flush=True)
            time.sleep(6 * 3600)

    if hasattr(S, 'OWN') and hasattr(S, 'q'):
        threading.Thread(target=backfill_loop, daemon=True).start()

    @S.route('POST', '/api/stations/autolink', pin=True, role='admin')
    def autolink_route(h, b):
        if not getattr(S, 'STATION_SOURCE', None):
            return dict(ok=False, reason='Nu e configurată nicio sursă de stații.')
        res = autolink(S, int(b.get('car', 1)), bool(b.get('force')))
        return dict(ok=True, linked=len(res))

    def fetch(lat, lon):
        key = (round(lat, 4), round(lon, 4))
        hit = CACHE.get(key)
        if hit and time.time() - hit[0] < TTL:
            return hit[1]
        q = urllib.parse.urlencode({'data': build_query(lat, lon)})
        err = None
        for ep in ENDPOINTS:
            try:
                data = json.loads(S._get_text(ep + '?' + q, FETCH_TIMEOUT))
                CACHE[key] = (time.time(), data)
                if len(CACHE) > 200:
                    CACHE.pop(next(iter(CACHE)))
                return data
            except Exception as e:  # noqa
                err = e
        raise RuntimeError('Serverele OpenStreetMap (Overpass) nu răspund acum (%s). Încearcă mai târziu.' % str(err)[:60])

    @S.route('GET', '/api/station', role='user')
    def station(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        cid, car = int(a['id']), int(a.get('car', 1))
        if hc is False:                                                            # demo: nimic nu pleaca spre exterior
            return dict(ok=True, radius=RADIUS, source='demo', candidates=[dict(id='node/1', name='Demo Charge', provider='Ionity', operator='Ionity', network='', dist=35, fee='yes',
                        price_text='1.99 RON/kWh', price=1.99, price_cur='RON', cost_est=None, capacity='4', sockets=['CCS'], hours='24/7')])
        rows = S._charges_rows(car, 1, 0, cid)
        if not rows:
            raise S.NotFound()
        r = rows[0]
        if r.get('lat') is None or r.get('lon') is None:
            return dict(ok=False, reason='Încărcarea nu are coordonate.')
        kwh = r.get('charge_energy_used') or r.get('charge_energy_added')
        cur = S.CUR_CODES.get(str(S.CURRENCY).strip().lower(), None)
        extra = getattr(S, 'STATION_SOURCE', None)                               # sursa optionala (obiect cu .name si .find(lat, lon, raza, ...)), intrebata inaintea OpenStreetMap
        if extra:
            try:
                found = extra.find(float(r['lat']), float(r['lon']), RADIUS, dc=r.get('dc'), power=r.get('power_max'), kwh=kwh, cur_code=cur)
            except Exception as e:  # noqa
                S.log('sursa de statii:', str(e)[:100], flush=True)
                found = None
            if found:
                return dict(ok=True, radius=RADIUS, source=getattr(extra, 'name', '?'), prices_now=True, candidates=convert(S, found, kwh))
        try:
            data = fetch(float(r['lat']), float(r['lon']))
        except RuntimeError as e:
            return dict(ok=False, reason=str(e))
        return dict(ok=True, radius=RADIUS, source='OpenStreetMap', candidates=convert(S, parse(data, float(r['lat']), float(r['lon']), S.provider_auto, cur, kwh), kwh))

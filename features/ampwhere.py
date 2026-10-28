"""Statii de incarcare din AmpWhere (ampwhere.com): furnizor + tarife pe kWh (AC/DC) pentru statia unde ai incarcat. PORNIT implicit; se opreste din Setari -> Afisare sau cu AMPWHERE=0.

NU e un API oficial si nu suntem afiliati: folosim aceeasi cerere pe care o face harta lor (fara cheie), cu acordul proprietarului. De aceea: pe tara, cel mult o descarcare pe zi
(instantaneul se tine pe disc, in /data), cautarea dupa coordonate se face LOCAL (nicio coordonata a ta nu pleaca spre ei), User-Agent care ne identifica, iar daca raspund
403/429/503 nu mai incercam 24 h. In modul implicit ("auto") se descarca doar tarile in care ai incarcat (dupa coordonate), nu toate cele 14; AMPWHERE_COUNTRY="ro,hu" le fixeaza.
Pretul e cel de la ultima descarcare, nu cel din ziua incarcarii. Daca formatul se schimba sau pornesc blocarea, cautarea cade pe OpenStreetMap (features/stations.py)."""
import gzip
import json
import os
import time
import urllib.request

from .places import hav_m

URL = 'https://ampwhere.com/api/locations/%s'
TTL = 24 * 3600                  # un instantaneu pe zi, pe tara
RETRY = 3600                     # dupa o eroare nu mai incercam o ora
RETRY_REFUSED = 24 * 3600        # ...iar daca ne refuza (403/429/503), o zi
MAX_BYTES = 30_000_000
RADIUS_MAX = 600
# Tarile AmpWhere (lista din harta lor) cu dreptunghiul aproximativ (lat min, lat max, lon min, lon max): decide ce tari se descarca pentru o incarcare. La granite pot fi doua.
COUNTRIES = {
    'ro': (43.6, 48.3, 20.2, 29.7), 'bg': (41.2, 44.2, 22.3, 28.7), 'lt': (53.9, 56.5, 20.9, 26.9), 'gr': (34.8, 41.8, 19.3, 28.3), 'hu': (45.7, 48.6, 16.1, 22.9),
    'cz': (48.5, 51.1, 12.0, 18.9), 'sk': (47.7, 49.7, 16.8, 22.6), 'hr': (42.3, 46.6, 13.4, 19.5), 'si': (45.4, 46.9, 13.3, 16.6), 'it': (35.4, 47.1, 6.6, 18.6),
    'cy': (34.5, 35.8, 32.2, 34.7), 'md': (45.4, 48.5, 26.6, 30.2), 'tr': (35.8, 42.2, 25.6, 44.9), 'rs': (42.2, 46.2, 18.8, 23.0),
}


def fetch_raw(url, ua):
    """Descarca (cu limita de marime) si intoarce textul JSON."""
    req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': 'application/json', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError('raspuns prea mare')
        if r.headers.get('Content-Encoding') == 'gzip':
            raw = gzip.decompress(raw)
    return raw.decode('utf-8')


def compact(data):
    """Pastreaza doar ce folosim: [{n, a, lat, lon, p, ch: [[putere, ac/dc, pret, pret_pe_ora, moneda, conector]]}]; None daca formatul nu seamana cu cel asteptat."""
    if not isinstance(data, dict) or not isinstance(data.get('data'), list):
        return None
    names = {str(k): (v or {}).get('name') for k, v in (data.get('providers_data') or {}).items()}
    out = []
    for s in data['data']:
        try:
            lat, lon = s['coordinates'][0], s['coordinates'][1]
            ch = []
            for c in s.get('chargers') or []:
                pr = c.get('price') or {}
                ch.append([c.get('power'), c.get('current_type'), pr.get('value'), pr.get('value_per_h'), pr.get('currency'), (c.get('connector') or {}).get('type')])
            out.append(dict(n=str(s.get('name') or '')[:80], a=str(s.get('address') or '')[:120], lat=float(lat), lon=float(lon), p=names.get(str(s.get('provider_id'))) or '',
                            h=bool((s.get('schedule') or {}).get('is_always_open')), ch=ch))
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return out or None


def pick(chargers, dc, power):
    """Incarcatorul care seamana cel mai mult cu incarcarea (AC/DC, apoi puterea cea mai apropiata); None daca statia n-are incarcatoare."""
    if not chargers:
        return None
    kind = None if dc is None else ('dc' if dc else 'ac')
    same = [c for c in chargers if kind and str(c[1] or '').lower() == kind] or chargers
    return min(same, key=lambda c: abs((c[0] or 0) - (power or 0))) if power else same[0]


def tariffs(chargers):
    """Tarifele distincte ale statiei (AC/DC, pret pe kWh, pe ora), cele DC si cele mai puternice primele: [{kind, price, per_h, cur, power, n}]."""
    groups = {}
    for c in chargers:
        key = (str(c[1] or '').lower(), c[2] or 0, c[3] or 0, c[4] or '')
        g = groups.setdefault(key, dict(kind=key[0], price=key[1], per_h=key[2], cur=key[3], power=0, n=0))
        g['power'] = max(g['power'], c[0] or 0)
        g['n'] += 1
    return sorted(groups.values(), key=lambda g: (g['kind'] != 'dc', -g['power']))[:8]


def price_text(c):
    if c is None or not c[2]:
        return ''
    t = '%g %s/kWh' % (c[2], c[4] or '')
    return t + (' · +%s %s/h' % (c[3], c[4] or '') if c[3] else '')


def candidates(stations, lat, lon, radius, dc=None, power=None, kwh=None, cur_code=None, auto=lambda n: '', limit=5):
    """Statiile din raza, cele mai apropiate primele, in forma folosita de butonul "Cauta statia"."""
    out = []
    for s in stations:
        d = hav_m(lat, lon, s['lat'], s['lon'])
        if d > radius:
            continue
        c = pick(s['ch'], dc, power)
        price = c[2] if c and c[2] else None
        cur = (c[4] if c else None) or None
        sock = []
        for x in s['ch']:
            lab = '%s %s kW' % ((x[5] or '').replace('_', ' ').replace('type2', 'Type 2').replace('ccs', 'CCS').strip() or str(x[1] or '').upper(), x[0] or '?')
            if lab not in sock:
                sock.append(lab)
        tar = tariffs(s['ch'])
        matched = next((i for i, t in enumerate(tar) if c and (t['kind'], t['price'], t['per_h'], t['cur']) == (str(c[1] or '').lower(), c[2] or 0, c[3] or 0, c[4] or '')), -1)
        out.append(dict(id='ampwhere', tariffs=tar, matched=matched, name=s['n'], provider=auto(s['p']) or s['p'], operator=s['p'], network='', dist=round(d), fee='yes' if price else '',
                        price_text=price_text(c), price=price, price_cur=cur, cost_est=round(price * kwh, 2) if price and kwh and cur and cur == cur_code else None,
                        capacity=str(len(s['ch'])) if s['ch'] else '', sockets=sock[:3], hours='24/7' if s['h'] else '', address=s['a']))
    out.sort(key=lambda x: x['dist'])
    return out[:limit]


def countries_at(lat, lon):
    """Tarile AmpWhere al caror dreptunghi contine punctul (de obicei una; la granita doua)."""
    return [cc for cc, (a, b, c, d) in COUNTRIES.items() if a <= lat <= b and c <= lon <= d]


def init(S):
    class Amp:
        def __init__(self):
            self.snaps = {}                  # cod tara -> dict(stations, ts)
            self.fail = {}                   # cod tara -> momentul ultimei esecuri (+ pauza lunga daca ne-au refuzat)
            self.last_fail = 0.0
            for cc in COUNTRIES:
                try:
                    with open(self.path(cc), encoding='utf-8') as f:
                        j = json.load(f)
                    self.snaps[cc] = dict(stations=j['stations'], ts=float(j['ts']))
                except (OSError, ValueError, KeyError, TypeError):
                    pass

        @staticmethod
        def path(cc):
            return os.path.join(S.DATA_DIR, 'ampwhere_%s.json' % cc)

        def enabled(self):
            return str(S.cget('ampwhere', 'AMPWHERE', '1')).strip().lower() in ('1', 'true', 'yes', 'on')

        def fixed(self):
            """Tarile fixate prin AMPWHERE_COUNTRY ("ro,hu"); [] = auto (dupa locul incarcarii)."""
            raw = str(S.cget('ampwhere_country', 'AMPWHERE_COUNTRY', 'auto')).lower().replace(';', ',')
            return [c for c in (x.strip() for x in raw.split(',')) if c in COUNTRIES]

        def refresh(self, cc):
            """Descarca instantaneul tarii daca cel de pe disc are peste 24 h (si nu am esuat de curand). Intoarce True daca avem date pentru tara."""
            now = time.time()
            snap = self.snaps.get(cc)
            if snap and now - snap['ts'] < TTL:
                return True
            if now < self.fail.get(cc, 0) + RETRY:
                return bool(snap)
            try:
                st = compact(json.loads(fetch_raw(URL % cc, 'teslamate-ui/%s (+https://github.com/blitzu/teslamate-ui; self-hosted, one snapshot per day)' % S.APP_VERSION)))
                if not st:
                    raise ValueError('format neasteptat')
                self.snaps[cc] = dict(stations=st, ts=now)
                tmp = self.path(cc) + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(dict(ts=now, stations=st), f, separators=(',', ':'))
                os.replace(tmp, self.path(cc))
            except Exception as e:  # noqa
                self.last_fail = now
                self.fail[cc] = now + (RETRY_REFUSED - RETRY if getattr(e, 'code', 0) in (403, 429, 503) else 0)           # refuzat: asteptam o zi, nu o ora
                S.log('ampwhere (%s):' % cc, str(e)[:120], flush=True)
            return bool(self.snaps.get(cc))

        def ready(self):
            """True cand sursa e pornita (tarile necesare se descarca la prima cautare)."""
            return self.enabled()

        def find(self, lat, lon, radius=250, **kw):
            """Candidati din instantaneele tarilor in care se afla punctul, sau None daca e oprit / nu avem date (atunci se foloseste OpenStreetMap). [] = nicio statie in raza."""
            if not self.enabled():
                return None
            ccs = self.fixed() or countries_at(lat, lon)
            if not ccs:
                return []                                                       # in afara tarilor AmpWhere
            stations, got = [], False
            for cc in ccs:
                if self.refresh(cc):
                    stations += self.snaps[cc]['stations']
                    got = True
            if not got:
                return None
            return candidates(stations, lat, lon, min(radius, RADIUS_MAX), auto=S.provider_auto, **kw)

    Amp.name = 'AmpWhere'
    S.STATION_SOURCE = Amp()                                                    # features/stations.py il intreaba primul

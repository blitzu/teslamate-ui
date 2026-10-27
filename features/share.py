"""Link public de urmarire in timp real ("sunt in drum, ajung la 14:30"): o pagina cu harta, valabila putin timp, pe care o poti retrage oricand.
Se serveste de pe portul PUBLIC (acelasi domeniu public ca Fleet, fara Cloudflare Access), deci tokenul e singura aparare: 32 de octeti aleatori, in baza se tine doar amprenta lui,
expira (max 48 h), se revoca, e limitat ca frecventa de cereri. Pagina primeste doar pozitia/ETA/destinatia permise; implicit ascunde pozitia cand esti in geofence-ul de acasa."""
import hashlib
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque

HOME = 'acas|home'
CSP = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src https://tile.openstreetmap.org data:; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
TOKEN = re.compile(r'^[A-Za-z0-9_-]{43}$')
ASSETS = {'app.js': ('share.js', 'text/javascript; charset=utf-8'), 'leaflet.js': ('vendor/leaflet.js', 'text/javascript; charset=utf-8'), 'leaflet.css': ('vendor/leaflet.css', 'text/css; charset=utf-8')}


def readf(p):
    with open(p, 'rb') as f:
        return f.read()


def digest(tok):
    return hashlib.sha256(tok.encode()).hexdigest()


_HOME_SEEN = {}                                  # id link -> ultima data cand masina era "acasa" (un geofence gol trecator nu trebuie sa-i arate pozitia exacta)


def view(share, live, now=None, home=HOME):
    """Ce vede cel care are linkul. Aici se decide ce iese din aplicatie: nimic altceva decat campurile de mai jos."""
    now = now or time.time()
    out = dict(ok=True, name=share['label'] or '', expires=share['expires'], now=now)
    state = 'driving' if live.get('shift_state') in ('D', 'R', 'N') else 'parked'
    geo = str(live.get('geofence') or '')
    at_home = bool(share['hide_home']) and bool(re.search(home, geo, re.I))
    sid = share.get('id') if hasattr(share, 'get') else None
    if share['hide_home'] and sid is not None:
        if at_home:
            _HOME_SEEN[sid] = now
        elif not geo and now - _HOME_SEEN.get(sid, 0) < 180:
            at_home = True                                                  # geofence necunoscut chiar dupa ce era acasa: ramane ascuns cateva minute
    out['state'] = 'home' if at_home else state
    if not at_home and live.get('latitude') is not None and live.get('longitude') is not None:
        out['lat'], out['lon'] = round(float(live['latitude']), 5), round(float(live['longitude']), 5)
        out['heading'] = live.get('heading')
        out['speed'] = round(live['speed']) if isinstance(live.get('speed'), (int, float)) else None
    route = live.get('active_route') if isinstance(live.get('active_route'), dict) else None
    if route and not route.get('error') and isinstance(route.get('minutes_to_arrival'), (int, float)) and state == 'driving' and not at_home:
        out['eta_min'] = round(route['minutes_to_arrival'])
        out['eta_ts'] = int(now + route['minutes_to_arrival'] * 60)
        if share['show_dest'] and route.get('destination'):
            out['dest'] = str(route['destination'])[:120]
    return out


def init(S):
    S.OWN.migrate('share', ['create table shares (id integer primary key, h text not null unique, created real not null, expires real not null, car integer, label text, hide_home integer default 1, show_dest integer default 1, revoked integer default 0, views integer default 0, last_view real, by text)'])
    hits, bad = defaultdict(deque), defaultdict(deque)
    lock = threading.Lock()

    def too_many(book, key, limit, per=60):
        now = time.time()
        with lock:
            d = book[key]
            while d and d[0] < now - per:
                d.popleft()
            if len(d) >= limit:
                return True
            d.append(now)
            if len(book) > 5000:
                book.clear()
        return False

    def strike(ip):
        with lock:
            bad[ip].append(time.time())
            if len(bad) > 5000:
                bad.clear()

    def blocked(ip):
        with lock:
            d = bad.get(ip)
            if not d:
                return False
            while d and d[0] < time.time() - 600:
                d.popleft()
            if not d:
                bad.pop(ip, None)                              # nu pastram intrari goale pentru fiecare IP vazut
                return False
            return len(d) >= 20

    def base():
        b = S.cget('share_base', 'SHARE_BASE', '')
        if b:
            return b.rstrip('/')
        dom = S.cget('fleet_domain', 'FLEET_DOMAIN', '')
        return ('https://' + dom) if dom else ''

    def home_re():
        return re.sub(r'[^\w|\s-]', '', str((S.OWN.kv_get('alerts_cfg', {}) or {}).get('not_plugged_night', {}).get('home') or HOME))[:60] or HOME

    def asset(name):
        f, ct = ASSETS[name]
        p = os.path.join(S.STATIC, f)
        return (200, readf(p), ct, CSP) if os.path.isfile(p) else (404, 'not found', 'text/plain', CSP)

    def public(h, path, q):
        if not path.startswith('/share/'):
            return None
        ip = (h.headers.get('CF-Connecting-IP') or h.client_address[0])[:45]
        if too_many(hits, ip, 120):
            return (429, 'prea multe cereri', 'text/plain', CSP)
        rest = path[len('/share/'):]
        if rest in ASSETS:
            return asset(rest)
        tok, _, tail = rest.partition('/')
        if blocked(ip):                                                         # prea multe incercari cu token gresit: oprit 10 minute
            return (429, 'prea multe cereri', 'text/plain', CSP)
        sh = S.OWN.one('select * from shares where h=?', (digest(tok),)) if TOKEN.match(tok) and tail in ('', 'data') else None
        if not sh:
            strike(ip)
            return (404, 'not found', 'text/plain', CSP)
        if sh['revoked'] or sh['expires'] < time.time():
            if tail == 'data':
                return (410, json.dumps(dict(ok=False, gone=True)), 'application/json', CSP)
            return (410, '<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><body style="font-family:system-ui;background:#0b0d10;color:#eceff3;padding:40px;text-align:center"><h2>Linkul a expirat</h2><p style="color:#8f99a4">Cere unul nou.</p>', 'text/html; charset=utf-8', CSP)
        if tail == 'data':
            S.OWN.run('update shares set views=views+1, last_view=? where id=?', (time.time(), sh['id']))
            return (200, json.dumps(view(sh, S.live_for(sh['car'] or 1), home=home_re())), 'application/json', CSP)
        p = os.path.join(S.STATIC, 'share.html')
        return (200, readf(p), 'text/html; charset=utf-8', CSP) if os.path.isfile(p) else (404, 'not found', 'text/plain', CSP)

    S.PUBLIC_ROUTES.append(public)
    S.share_view = view

    @S.route('GET', '/api/share', role='user')
    def listing(h, a):
        rows = S.OWN.rows('select id, created, expires, car, label, hide_home, show_dest, revoked, views, last_view, by from shares where created > ? order by created desc limit 30', (time.time() - 14 * 86400,))
        return dict(shares=rows, base=base(), now=time.time())

    @S.route('POST', '/api/share/create', pin=True, role='user')
    def create(h, b):
        if not base():
            raise ValueError('Lipsește domeniul public (Fleet API → „Domeniu public”) pe care se poate servi linkul.')
        try:
            hours = float(b.get('hours', 2))
        except (TypeError, ValueError):
            raise ValueError('durata în ore, între 0,25 și 48')
        if not 0.25 <= hours <= 48:
            raise ValueError('durata în ore, între 0,25 și 48')
        active = S.OWN.one('select count(*) n from shares where revoked=0 and expires > ?', (time.time(),))['n']
        if active >= 10:
            raise ValueError('Ai deja 10 linkuri active; retrage unul.')
        tok = secrets.token_urlsafe(32)
        label = re.sub(r'[<>\r\n]', '', str(b.get('label', '')))[:40]
        S.OWN.run('insert into shares(h, created, expires, car, label, hide_home, show_dest, by) values(?,?,?,?,?,?,?,?)',
                  (digest(tok), time.time(), time.time() + hours * 3600, int(b.get('car', 1)), label, 1 if b.get('hide_home', True) else 0, 1 if b.get('show_dest', True) else 0, getattr(h, 'role', None) or 'user'))
        S.audit('share', actor=getattr(h, 'role', None))
        return dict(ok=True, url='%s/share/%s' % (base(), tok))

    @S.route('POST', '/api/share/revoke', pin=True, role='user')
    def revoke(h, b):
        S.audit('share_revoke', actor=getattr(h, 'role', None), all=bool(b.get('all')))
        if b.get('all'):
            S.OWN.run('update shares set revoked=1 where revoked=0')
        else:
            S.OWN.run('update shares set revoked=1 where id=?', (int(b.get('id', 0)),))

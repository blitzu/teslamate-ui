#!/usr/bin/env python3
"""TeslaMate UI (stil Tessie): backend. MQTT (live) + Postgres TeslaMate (istoric) -> JSON/SSE. Fara date demo cat timp TeslaMate nu are masini => mod DEMO."""
import builtins, collections, sys, json, math, os, re, queue, random, secrets, shutil, socket, ssl, threading, time, datetime as dt
import urllib.request, urllib.error, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

def log(*a, **k):
    builtins.print(time.strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)


DATA_DIR = os.environ.get('DATA_DIR', '/data')


def drop_privileges():
    """Pornit ca root (implicit in Docker): da /data utilizatorului aplicatiei si renunta la root INAINTE de orice altceva (fisierele create dupa aceea sunt ale lui)."""
    if os.name != 'posix' or os.getuid() != 0:
        return
    uid = int(os.environ.get('APP_UID', '10001'))
    gid = int(os.environ.get('APP_GID', str(uid)))
    if uid == 0:
        return
    try:
        if os.path.isdir(DATA_DIR):
            os.lchown(DATA_DIR, uid, gid)
            for root, dirs, files in os.walk(DATA_DIR):
                for n in dirs + files:
                    os.lchown(os.path.join(root, n), uid, gid)
    except OSError as e:
        log('chown %s: %s' % (DATA_DIR, e))
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    os.environ.setdefault('HOME', '/tmp')
    log('rulez ca uid %d (nu root)' % uid)


drop_privileges()

PORT = int(os.environ.get('PORT', '4100'))
DEMO_ONLY = os.environ.get('DEMO_ONLY') == '1'   # instanta publica: doar date fictive, fara DB/MQTT/comenzi
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
DB = dict(host=os.environ.get('DATABASE_HOST', 'database'), user=os.environ.get('DATABASE_USER', 'teslamate'),
          password=os.environ.get('DATABASE_PASS', ''), dbname=os.environ.get('DATABASE_NAME', 'teslamate'), connect_timeout=5)
MQ_STATE = dict(up=False)
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


def live_apply(car, key, val):
    """O valoare noua pentru starea live (din MQTT sau din BLE): actualizeaza, transmite in aplicatie si declanseaza notificari, reguli si module."""
    d = LIVE.setdefault(car, {})
    known = key in d
    if not known and val is None:
        d[key] = None                         # "gol" cunoscut (ex. in afara oricarui geofence): intrarea ulterioara intr-un geofence conteaza ca sosire
        return
    if d.get(key) != val:
        prev = d.get(key)
        d[key] = val
        LIVE_TS[car] = time.time()
        broadcast({'car': car, 'k': key, 'v': val})
        try:
            notify_check(car, key, prev, val)
            rules_check(car, key, prev, val, known)
            for fn in MQTT_HOOKS:
                try:
                    fn(car, key, prev, val, known)
                except Exception as e:  # noqa
                    log('mqtt hook: %s' % e)
        except Exception as e:  # noqa
            log('notify:', e, flush=True)


def mqtt_thread():
    if not MQ['host']:
        return
    import paho.mqtt.client as mqtt
    prefix = (MQ['ns'] + '/' if MQ['ns'] else '') + 'teslamate/cars/'

    def on_connect(c, *a):
        MQ_STATE['up'] = True
        c.subscribe(prefix + '#')

    def on_disconnect(c, *a):
        MQ_STATE['up'] = False

    def on_message(c, u, m):
        parts = m.topic[len(prefix):].split('/')
        if len(parts) != 2 or not parts[0].isdigit():
            return
        live_apply(int(parts[0]), parts[1], conv(m.payload.decode('utf-8', 'replace')))

    try:
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    except Exception:
        c = mqtt.Client()
    if MQ['user']:
        c.username_pw_set(MQ['user'], MQ['pw'])
    c.on_connect, c.on_message, c.on_disconnect = on_connect, on_message, on_disconnect
    c.reconnect_delay_set(2, 30)
    while True:
        try:
            c.connect(MQ['host'], MQ['port'], 60)
            c.loop_forever(retry_first_connection=True)
        except Exception as e:
            log('mqtt:', e, flush=True)
            time.sleep(5)


# ---------------------------------------------------------------- DB
DB_SEM = threading.BoundedSemaphore(int(os.environ.get('DB_MAX_CONN', '8')))     # cel mult atatea conexiuni simultane catre Postgres-ul TeslaMate


def q(sql, args=()):
    import psycopg2, psycopg2.extras
    if not DB_SEM.acquire(timeout=20):
        raise RuntimeError('baza de date e ocupată')
    try:
        cn = psycopg2.connect(options='-c statement_timeout=20000', **DB)
        try:
            with cn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, args)
                rows = cur.fetchall()
            return [{k: (v.isoformat() if isinstance(v, (dt.datetime, dt.date)) else (float(v) if hasattr(v, 'quantize') else v)) for k, v in r.items()} for r in rows]
        finally:
            cn.close()
    finally:
        DB_SEM.release()


NAME_A = "coalesce(nullif(g.name,''), nullif(trim(both ', ' from concat_ws(', ', a.name, a.road, a.city)),''), a.display_name, '—')"
NAME_B = NAME_A.replace('g.', 'g2.').replace('a.', 'a2.')


def cars():
    return q("select c.id, coalesce(c.name,'Tesla') as name, c.model, c.trim_badging as trim, c.marketing_name, c.exterior_color as color, c.efficiency, c.vin, c.wheel_type from cars c order by c.display_priority, c.id")


DRIVE_SQL = f"""select d.id, d.start_date, d.end_date, d.distance, d.duration_min, d.speed_max, d.power_max, d.start_km, d.end_km,
        d.outside_temp_avg, d.inside_temp_avg, d.ascent, d.descent,
        (d.start_ideal_range_km - d.end_ideal_range_km) * c.efficiency as kwh,
        {NAME_A} as start_name, {NAME_B} as end_name, sp.battery_level as start_soc, ep.battery_level as end_soc,
        sp.latitude as start_lat, sp.longitude as start_lon, ep.latitude as end_lat, ep.longitude as end_lon
      from drives d join cars c on c.id=d.car_id
      left join geofences g on g.id=d.start_geofence_id left join addresses a on a.id=d.start_address_id
      left join geofences g2 on g2.id=d.end_geofence_id left join addresses a2 on a2.id=d.end_address_id
      left join positions sp on sp.id=d.start_position_id left join positions ep on ep.id=d.end_position_id
      where d.car_id=%s and d.end_date is not null"""


def _dtparam(s):
    """Data/ora din parametrul unei cereri (ISO, UTC); None daca lipseste sau e gresita."""
    try:
        return dt.datetime.fromisoformat(str(s).replace('Z', '')).replace(tzinfo=None) if s else None
    except ValueError:
        return None


def list_filters(a, kind):
    """(de la, pana la, id-uri) din ?from=&to=&tag= ; id-uri None = fara filtru pe tag."""
    tag = str(a.get('tag') or '').strip()
    ids = None
    if tag:
        ids = TAGS.ids(kind, tag) if TAGS else []
    return _dtparam(a.get('from')), _dtparam(a.get('to')), ids


def drives(car, limit, offset, lo=None, hi=None, ids=None):
    sql, par = DRIVE_SQL, [car]
    if lo:
        sql += ' and d.start_date >= %s'
        par.append(lo)
    if hi:
        sql += ' and d.start_date < %s'
        par.append(hi)
    if ids is not None:
        sql += ' and d.id = any(%s)'
        par.append(list(ids))
    return q(sql + " order by d.start_date desc limit %s offset %s", tuple(par) + (limit, offset))


def drives_by_ids(car, ids):
    return q(DRIVE_SQL + " and d.id = any(%s) order by d.start_date", (car, list(ids)))


def drive_points(did):
    rows = q("select date, latitude, longitude, speed, power, battery_level, elevation from positions where drive_id=%s order by date", (did,))
    step = max(1, len(rows) // 500)
    pick = rows[::step] + ([rows[-1]] if rows and (len(rows) - 1) % step else [])         # mereu si ultimul punct (destinatia)
    return [[r['date'], r['latitude'], r['longitude'], r['speed'], r['power'], r['battery_level'], r['elevation']] for r in pick]


RC_CACHE = {}        # (id, senzor, pret) -> cost real; incarcarile terminate nu se mai schimba


def real_cost(row, allow_fetch=True):
    """Cost real estimat al unei incarcari AC de acasa: energia importata din retea (istoric HA) x tarif. None daca nu se aplica / nu e in cache si nu se mai poate interoga."""
    try:
        price = float(cget('price_grid', 'PRICE_GRID', '') or 0) or float(row.get('tariff') or 0)
    except (TypeError, ValueError):
        price = float(row.get('tariff') or 0)
    if not price or row.get('dc') or (row.get('power_max') or 0) > 25 or not row.get('end_date') or not re.search(r'acas|home', row.get('name') or '', re.I):
        return None, False
    k = (row['id'], HA['grid'], price)
    if k in RC_CACHE:
        return RC_CACHE[k], False
    if not allow_fetch:
        return None, False
    t0, t1 = _dtp(row['start_date']), _dtp(row['end_date'])
    a, b = t0.replace(tzinfo=dt.timezone.utc).timestamp(), t1.replace(tzinfo=dt.timezone.utc).timestamp()
    hist = ha_history(HA['grid'], t0 - dt.timedelta(minutes=1), t1)
    if not hist:                                      # eroare/lipsa istoric: nu cacha "0,00" pana la repornire
        return None, True
    grid = _integral(hist, a, b)
    cap = row.get('charge_energy_used') or row.get('charge_energy_added')
    if cap:
        grid = min(grid, cap)                          # importul casei nu poate depasi energia luata de masina
    RC_CACHE[k] = round(grid * price, 2)
    return RC_CACHE[k], True


# ---------------------------------------------------------------- cost / furnizor per incarcare (doar in aplicatie) + pret combustibil zilnic
METAFILE = DATA_DIR + '/charge_meta.json'     # {id_incarcare: {cost: total, provider: nume}} - nu se scrie nimic in TeslaMate
FUELFILE = DATA_DIR + '/fuel_prices.json'     # {days: {YYYY-MM-DD: {euro95: EUR/l, diesel: EUR/l, rate: EUR->moneda, cur: cod, upd: data sursei, ts: cand am citit}}}
MLOCK = threading.Lock()
PROV_AUTO = [(r'supercharger', 'Tesla Supercharger'), (r'acas|home', 'Acasă'), (r'ionity', 'Ionity'), (r'renovatio', 'Renovatio'), (r'enel', 'Enel X'), (r'eldrive', 'Eldrive'),
             (r'electrica', 'Electrica'), (r'\bmol\b', 'MOL'), (r'omv', 'OMV'), (r'petrom', 'Petrom'), (r'kaufland', 'Kaufland'), (r'lidl', 'Lidl'), (r'mega image', 'Mega Image'),
             (r'fastned', 'Fastned'), (r'allego', 'Allego'), (r'shell', 'Shell Recharge'), (r'virta', 'Virta'), (r'nelion', 'Nelion'), (r'plugpoint|plug point', 'PlugPoint'),
             (r'rompetrol', 'Rompetrol'), (r'lukoil', 'Lukoil'), (r'socar', 'Socar'), (r'electra', 'Electra'), (r'atlante', 'Atlante')]
CUR_CODES = {'lei': 'RON', 'ron': 'RON', '€': 'EUR', 'eur': 'EUR', '$': 'USD', 'usd': 'USD', '£': 'GBP', 'gbp': 'GBP', 'zł': 'PLN', 'pln': 'PLN', 'kč': 'CZK', 'czk': 'CZK',
             'ft': 'HUF', 'huf': 'HUF', 'лв': 'BGN', 'bgn': 'BGN', 'chf': 'CHF', 'sek': 'SEK', 'dkk': 'DKK', 'nok': 'NOK'}
FUEL_STATE = dict(last=0, err='')


def provider_auto(name):
    for rx, nm in PROV_AUTO:
        if re.search(rx, name or '', re.I):
            return nm
    return ''


FLOCK = threading.RLock()      # un singur lock pentru citire-modificare-scriere pe fisierele din /data


def jload(path, default):
    """JSON din fisier. Lipsa fisierului = valoarea implicita. Fisier corupt: pastreaza o copie .bad, incearca copia .bak si abia apoi valoarea implicita (cu log)."""
    if not os.path.exists(path):
        return default
    for p in (path, path + '.bak'):
        try:
            with open(p) as f:
                return json.load(f)
        except FileNotFoundError:
            continue
        except Exception as e:  # noqa
            log('json corupt %s: %s' % (p, e), flush=True)
            if p == path:
                try:
                    shutil.copy2(p, p + '.bad')
                except OSError:
                    pass
    return default


def jsave(path, obj):
    """Scriere atomica: fisier temporar + fsync + replace; versiunea anterioara ramane in .bak (o oprire in timpul scrierii nu mai trunchiaza fisierul)."""
    with FLOCK:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(obj, f)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):
            try:
                shutil.copy2(path, path + '.bak')
            except OSError:
                pass
        os.replace(tmp, path)


def _json_file(path, default):
    return jload(path, default)


def _json_save(path, obj):
    jsave(path, obj)


def meta_load():
    return _json_file(METAFILE, {})


def meta_update(cid, body):
    """Seteaza/sterge costul total si furnizorul unei incarcari (cheie lipsa = neschimbat; '' sau null = sterge)."""
    cid = str(int(cid))
    with MLOCK:
        m = meta_load()
        e = dict(m.get(cid) or {})
        if 'cost' in body:
            v = body['cost']
            if v is None or str(v).strip() == '':
                e.pop('cost', None)
            else:
                v = float(str(v).replace(',', '.'))
                if not (0 <= v < 100000):
                    raise ValueError('cost invalid')
                e['cost'] = round(v, 2)
        if 'provider' in body:
            p = re.sub(r'[<>"]', '', str(body['provider'] or '')).strip()[:40]
            if p:
                e['provider'] = p
            else:
                e.pop('provider', None)
        if e:
            m[cid] = e
        else:
            m.pop(cid, None)
        _json_save(METAFILE, m)
    return e


def decorate(rows):
    """Adauga furnizorul (manual sau dedus din locatie) si costul efectiv: manual > real (energie din retea) > TeslaMate."""
    m = meta_load()
    for r in rows:
        e = m.get(str(r['id'])) or {}
        r['cost_manual'] = e.get('cost')
        r['provider_set'] = bool(e.get('provider'))
        r['provider'] = e.get('provider') or provider_auto(r.get('name'))
        r['cost_place'] = r['place_name'] = r['place_price'] = None
        if PLACES and r.get('lat') is not None and r.get('lon') is not None:         # loc salvat cu pret pe kWh: kWh x pret (acelasi kWh ca la TeslaMate: consumati din retea, altfel adaugati)
            pl = PLACES.match(r['lat'], r['lon'])
            kwh = r.get('charge_energy_used') or r.get('charge_energy_added')
            if pl and kwh:
                r['cost_place'], r['place_name'], r['place_price'] = round(float(kwh) * pl['price'], 2), pl['name'], pl['price']
        r['cost_eff'] = e['cost'] if e.get('cost') is not None else (r['cost_real'] if r.get('cost_real') is not None else (r['cost_place'] if r['cost_place'] is not None else r.get('cost')))
    return rows


def _fnum(x, d=0.0):
    try:
        return float(str(x).replace(',', '.'))
    except (TypeError, ValueError):
        return d


def local_today():
    """Data de azi in fusul orar al aplicatiei (TZ), nu cel al sistemului: preturile si zilele din statistici se grupeaza pe aceeasi zi locala."""
    try:
        import zoneinfo
        return dt.datetime.now(zoneinfo.ZoneInfo(LOCAL_TZ)).date()
    except Exception:  # noqa
        return dt.date.today()


def fuel_conf():
    ft = str(cget('fuel_type', 'FUEL_TYPE', 'euro95')).lower()
    return dict(type=ft if ft in ('euro95', 'diesel', 'manual') else 'euro95', manual=_fnum(cget('fuel_price', 'FUEL_PRICE', '')),
                l100=_fnum(cget('ice_l100', 'ICE_L100', '')), country=str(cget('fuel_country', 'FUEL_COUNTRY', 'Romania')) or 'Romania')


def fuel_book(fc=None):
    """Pretul pe litru (in moneda aplicatiei) pentru fiecare zi stocata, pentru combustibilul ales: [(zi, pret)] sortat."""
    fc = fc or fuel_conf()
    out = []
    if fc['type'] != 'manual':
        code = CUR_CODES.get(str(CURRENCY).strip().lower(), '')
        slug = re.sub(r'[^A-Za-z-]', '', fc['country'].strip().replace(' ', '-')) or 'Romania'
        for day, d in sorted((_json_file(FUELFILE, {}).get('days') or {}).items()):
            if (d.get('cur') or code) != code or (d.get('country') or slug) != slug:
                continue                                  # citiri facute pentru alta moneda/tara nu se amesteca
            eur, rate = d.get(fc['type']), d.get('rate')
            if eur and rate:
                out.append((day, round(eur * rate, 3)))
    return out


def fuel_lookup(book, day, manual=0.0):
    """(pret, tip): exact = citit in ziua respectiva; carry = ultimul pret cunoscut dinainte; early = primul pret cunoscut (zile anterioare primei citiri); manual."""
    import bisect
    if book:
        i = bisect.bisect_left(book, (day, -1))
        if i < len(book) and book[i][0] == day:
            return book[i][1], 'exact'
        if i > 0:
            return book[i - 1][1], 'carry'
        return book[0][1], 'early'
    return (manual, 'manual') if manual else (None, None)


def _get_text(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': 'teslamate-ui/%s' % APP_VERSION, 'Accept': 'text/plain,application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(400_000).decode('utf-8', 'replace')


# ---------------------------------------------------------------- versiune si actualizari (GitHub Releases)
def _read_version():
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'VERSION')) as f:
            return f.read().strip() or '0.0.0'
    except OSError:
        return '0.0.0'


APP_VERSION = _read_version()                        # semver; "-private" la sfarsit = build local fara verificare de versiuni noi
BUILD_COMMIT = (os.environ.get('BUILD_COMMIT') or '')[:7]
UPDATE_REPO = os.environ.get('UPDATE_REPO', 'blitzu/teslamate-ui')
UPDFILE = DATA_DIR + '/update.json'
UPD = dict(latest='', url='', notes='', published='', checked=0, error='', notified='')
ULOCK = threading.Lock()


def ver_tuple(v):
    s = str(v or '').replace('-private', '')
    m = re.match(r'^\s*v?(\d+)(?:\.(\d+))?(?:\.(\d+))?', s)
    base = tuple(int(x or 0) for x in m.groups()) if m else (0, 0, 0)
    return base + (0 if re.match(r'^\s*v?\d+(?:\.\d+){0,2}-', s) else 1,)          # 1.6.0-rc1 < 1.6.0


def update_cfg_on():
    return str(cget('update_check', 'UPDATE_CHECK', '1')).lower() in ('1', 'true')


def update_enabled():
    return update_cfg_on() and not APP_VERSION.endswith('-private')


def update_newer():
    return bool(UPD['latest']) and ver_tuple(UPD['latest']) > ver_tuple(APP_VERSION)


def update_check():
    """Intreaba GitHub care e ultimul release (o cerere fara date personale); notifica o singura data per versiune noua."""
    try:
        r = json.loads(_get_text('https://api.github.com/repos/%s/releases/latest' % UPDATE_REPO, 20))
        tag = str(r.get('tag_name') or '')
        if not tag:
            raise ValueError('niciun release publicat')
        with ULOCK:
            UPD.update(latest=tag.lstrip('v'), url=str(r.get('html_url') or ''), notes=str(r.get('body') or '')[:2000], published=str(r.get('published_at') or ''), checked=int(time.time()), error='')
            newer = update_newer()
            first = newer and UPD['notified'] != UPD['latest']
            if first:
                UPD['notified'] = UPD['latest']
            jsave(UPDFILE, dict(UPD))
        if first and nset_load().get('app_update', True):
            notify('app_update', '🆕 Versiune nouă: v%s' % UPD['latest'], 'Ai v%s. Deschide Setări → Versiune și actualizări%s.' % (APP_VERSION, ' și apasă „Actualizează acum”' if updater_conn()[0] else ' ca să vezi ce s-a schimbat'))
        return dict(ok=True, latest=UPD['latest'], newer=newer)
    except Exception as e:  # noqa
        msg = 'niciun release publicat încă' if (isinstance(e, urllib.error.HTTPError) and e.code == 404) else str(e)[:200]
        with ULOCK:
            UPD.update(error=msg, checked=int(time.time()))
        log('verificare versiune: %s' % msg)
        return dict(ok=False, reason=msg)


def update_loop():
    time.sleep(90)
    while True:
        if update_enabled():
            update_check()
        time.sleep(12 * 3600)


UPD_TOKEN_FILE = DATA_DIR + '/updater.token'
UPD_DEFAULT_URL = 'http://updater:8080/update'


def updater_conn():
    """(adresa, token) al updater-ului: cel setat de utilizator (ex. Watchtower); altfel updater-ul inclus in stack, gasit prin fisierul de token pe care si-l creeaza singur."""
    url = str(cget('update_webhook', 'UPDATE_WEBHOOK', ''))
    tok = str(cget('update_token', 'UPDATE_TOKEN', ''))
    if not url and not tok:
        try:
            with open(UPD_TOKEN_FILE) as f:
                t = f.read().strip()
            if t:
                return UPD_DEFAULT_URL, t
        except OSError:
            pass
    return url, tok


def update_apply():
    """Cere actualizarea unui updater extern (ex. Watchtower HTTP API): aplicatia nu are acces la Docker si nu isi poate inlocui singura containerul."""
    url, tok = updater_conn()
    if not url:
        return dict(ok=False, reason='Nu e configurat niciun updater (Setări → Actualizări).')
    try:
        c, r = http(url, None, headers=({'Authorization': 'Bearer ' + tok} if tok else {}), method='POST', timeout=300)
    except Exception as e:  # noqa
        import http.client as _hc
        cause = getattr(e, 'reason', e)
        if isinstance(cause, (ConnectionRefusedError, socket.gaierror)) or (isinstance(e, urllib.error.URLError) and not isinstance(cause, (TimeoutError, ConnectionResetError, BrokenPipeError, _hc.RemoteDisconnected, _hc.IncompleteRead))):
            return dict(ok=False, reason='Nu pot ajunge la updater (%s). Verifică dacă rulează (docker compose ps).' % str(e)[:100])
        return dict(ok=True, reason='Cererea a fost trimisă; conexiunea s-a întrerupt (normal dacă aplicația se repornește): %s' % str(e)[:120])
    return dict(ok=c < 300, code=c, reason='' if c < 300 else 'Updater-ul a răspuns %s.' % c)


def changelog_entries(limit=8):
    """Intrarile din CHANGELOG.md (de langa server.py): [{version, date, notes}], cele mai noi primele."""
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CHANGELOG.md'), encoding='utf-8') as f:
            txt = f.read()
    except OSError:
        return []
    out = []
    for m in re.finditer(r'^## +v?(\d+(?:\.\d+){0,2})(?: *[-–—] *([0-9-]+))?[ \t]*\n(.*?)(?=^## |\Z)', txt, re.M | re.S):
        out.append(dict(version=m.group(1), date=m.group(2) or '', notes=m.group(3).strip()))
    return out[:limit]


def version_info():
    with ULOCK:
        u = dict(UPD)
    return dict(version=APP_VERSION, commit=BUILD_COMMIT, repo=UPDATE_REPO, check=update_cfg_on(), private=APP_VERSION.endswith('-private'), latest=u['latest'], newer=update_newer(),
                url=u['url'], notes=u['notes'], published=u['published'], checked=u['checked'], error=u['error'], can_apply=bool(updater_conn()[0]), builtin_updater=updater_conn()[0] == UPD_DEFAULT_URL)


_BUILD = [0.0, '']


def static_build():
    """Amprenta fisierelor aplicatiei (cale, marime, data) + versiunea: se schimba la orice deploy. Clientul o compara si se reincarca singur."""
    if time.time() - _BUILD[0] < 10 and _BUILD[1]:
        return _BUILD[1]
    h = hashlib.sha1(APP_VERSION.encode())
    try:
        for root, _, files in sorted(os.walk(STATIC)):
            for f in sorted(files):
                p = os.path.join(root, f)
                st = os.stat(p)
                h.update(('%s|%d|%d;' % (os.path.relpath(p, STATIC), st.st_size, int(st.st_mtime))).encode())
    except OSError:
        pass
    _BUILD[0], _BUILD[1] = time.time(), h.hexdigest()[:10]
    return _BUILD[1]


def app_brief():
    return dict(version=APP_VERSION, commit=BUILD_COMMIT, build=static_build(), latest=UPD['latest'] if (update_enabled() and update_newer()) else '')


UPD.update({k: v for k, v in (jload(UPDFILE, {}) or {}).items() if k in UPD})


def parse_llms(txt):
    """(Euro 95 EUR/l, Diesel EUR/l, data sursei) din pagina llms.txt a fuel-prices.eu."""
    e95 = re.search(r'^Euro 95\s+€\s*([0-9]+\.[0-9]+)', txt, re.M)
    dsl = re.search(r'^Diesel\s+€\s*([0-9]+\.[0-9]+)', txt, re.M)
    upd = re.search(r'^Last updated:\s*(\d{4}-\d{2}-\d{2})', txt, re.M)
    if not (e95 and dsl):
        raise ValueError('format necunoscut')
    return float(e95.group(1)), float(dsl.group(1)), (upd.group(1) if upd else '')


def fuel_fetch():
    """Citeste pretul national mediu (Euro 95 / Diesel, EUR/l) de pe fuel-prices.eu - pentru Romania vine din Monitorul Preturilor Carburantilor - si il stocheaza pe ziua de azi."""
    fc = fuel_conf()
    slug = re.sub(r'[^A-Za-z-]', '', fc['country'].strip().replace(' ', '-')) or 'Romania'
    try:
        txt = _get_text('https://www.fuel-prices.eu/%s/llms.txt' % slug)
        try:
            e95v, dslv, updv = parse_llms(txt)
        except ValueError:
            raise ValueError('format necunoscut la fuel-prices.eu/%s' % slug)
        code = CUR_CODES.get(str(CURRENCY).strip().lower(), '')
        rate = None
        if code == 'EUR':
            rate = 1.0
        elif code:
            rate = float(json.loads(_get_text('https://api.frankfurter.dev/v1/latest?base=EUR&symbols=' + code))['rates'][code])
        day = local_today().isoformat()
        with MLOCK:
            data = _json_file(FUELFILE, {})
            data.setdefault('days', {})[day] = dict(euro95=e95v, diesel=dslv, rate=rate, cur=code, upd=updv, ts=int(time.time()), country=slug)
            _json_save(FUELFILE, data)
        FUEL_STATE.update(last=time.time(), err='')
        return dict(ok=True, day=day, euro95=e95v, diesel=dslv, rate=rate, cur=code)
    except Exception as e:  # noqa
        FUEL_STATE['err'] = str(e)[:200]
        log('fuel:', e, flush=True)
        return dict(ok=False, reason=str(e)[:200])


def fuel_loop():
    time.sleep(25)
    while True:
        if fuel_conf()['type'] != 'manual':
            fuel_fetch()
        time.sleep(6 * 3600)


def fuel_info():
    fc = fuel_conf()
    book = fuel_book(fc)
    return dict(type=fc['type'], country=fc['country'], l100=fc['l100'], manual=fc['manual'] or None, currency=CURRENCY, convertible=bool(CUR_CODES.get(str(CURRENCY).strip().lower())),
                today=fuel_lookup(book, local_today().isoformat(), fc['manual'])[0], days=[dict(day=d, price=p) for d, p in book[-120:]], last=FUEL_STATE['last'] or None, error=FUEL_STATE['err'] or None,
                source='fuel-prices.eu (Monitorul Prețurilor Carburanților)' if fc['country'].lower() == 'romania' else 'fuel-prices.eu')


def ice_calc(by_day, ev_kwh, ev_cost, kwh_charged, l100=None, book=None, manual=None):
    """Compara km parcursi cu o masina termica: litri = km/100 x l/100km, la pretul combustibilului din fiecare zi (stocat zilnic)."""
    fc = fuel_conf()
    l100 = fc['l100'] if l100 is None else l100
    if not l100 or l100 <= 0:
        return dict(enabled=False, type=fc['type'], currency=CURRENCY)
    book = fuel_book(fc) if book is None else book
    manual = fc['manual'] if manual is None else manual
    cost = liters = km_tot = 0.0
    miss = 0
    est_all = []
    days = []
    for x in by_day:
        km = x.get('km') or 0
        p, kind = fuel_lookup(book, x['day'], manual)
        if p is None:
            miss += 1
            continue
        lit = km / 100 * l100
        cost += lit * p
        liters += lit
        km_tot += km
        est_all.append(kind in ('carry', 'early'))
        days.append(dict(day=x['day'], km=round(km, 1), price=round(p, 3), cost=round(lit * p, 2), kind=kind))
    all_km = sum((x.get('km') or 0) for x in by_day)
    ev = None
    if kwh_charged and ev_cost is not None and ev_kwh and km_tot > 0 and all_km > 0:
        ev = round(ev_kwh * ev_cost / kwh_charged * min(1.0, km_tot / all_km), 2)      # EV pe aceleasi zile ca termica (cele fara pret nu intra in niciuna)
    avg = round(cost / liters, 3) if liters else None
    return dict(enabled=True, type=fc['type'], l100=l100, currency=CURRENCY, km=round(km_tot, 1), liters=round(liters, 1), cost=round(cost, 2), avg_price=avg,
                ev_cost=ev, saving=round(cost - ev, 2) if ev is not None else None, per100_ice=round(l100 * avg, 2) if avg else None,
                per100_ev=round(ev / km_tot * 100, 2) if (ev is not None and km_tot) else None, est_days=sum(est_all[-90:]), missing_days=miss, days=days[-90:],
                prices=[dict(day=d, price=p) for d, p in book if not by_day or d >= by_day[0]['day']][-200:])


def charges(car, limit, offset, cid=None, lo=None, hi=None, ids=None):
    rows = _charges_rows(car, limit, offset, cid, lo, hi, ids)
    if ha_ok() and HA['grid']:
        budget = 20                                   # max. interogari HA noi per cerere; restul se completeaza la urmatoarea deschidere a paginii
        for r in rows:
            try:
                val, fetched = real_cost(r, budget > 0)
                budget -= 1 if fetched else 0
                r['cost_real'] = val
            except Exception as e:  # noqa
                budget = 0                            # HA nu raspunde: nu mai incerca pentru restul randurilor (altfel cererea dureaza minute)
                log('real cost:', e, flush=True)
    return decorate(rows)


def _charges_rows(car, limit, offset, cid=None, lo=None, hi=None, ids=None):
    extra, par = '', []
    if lo:
        extra += ' and cp.start_date >= %s'
        par.append(lo)
    if hi:
        extra += ' and cp.start_date < %s'
        par.append(hi)
    if ids is not None:
        extra += ' and cp.id = any(%s)'
        par.append(list(ids))
    return q(f"""select cp.id, cp.start_date, cp.end_date, cp.charge_energy_added, cp.charge_energy_used, cp.duration_min, cp.cost, g.cost_per_unit as tariff,
        coalesce(pp.latitude, a.latitude) as lat, coalesce(pp.longitude, a.longitude) as lon,
        cp.start_battery_level as start_soc, cp.end_battery_level as end_soc, cp.outside_temp_avg,
        (select max(charger_power) from charges ch where ch.charging_process_id=cp.id) as power_max,
        coalesce((select bool_or(fast_charger_present) from charges ch where ch.charging_process_id=cp.id), false) as dc,
        {NAME_A} as name
      from charging_processes cp left join geofences g on g.id=cp.geofence_id left join addresses a on a.id=cp.address_id left join positions pp on pp.id=cp.position_id
      where cp.car_id=%s and cp.end_date is not null {'and cp.id=%s' if cid else ''}{extra} order by cp.start_date desc limit %s offset %s""", (car,) + ((cid,) if cid else ()) + tuple(par) + (limit, offset))


def charge_points(cid):
    rows = q("select date, charger_power, battery_level, charger_voltage, charger_actual_current, charge_energy_added from charges where charging_process_id=%s order by date", (cid,))
    step = max(1, len(rows) // 400)
    pick = rows[::step] + ([rows[-1]] if rows and (len(rows) - 1) % step else [])
    return [[r['date'], r['charger_power'], r['battery_level'], r['charger_voltage'], r['charger_actual_current'], r['charge_energy_added']] for r in pick]


TRIP_GAP = dt.timedelta(hours=2)     # curse cu pauza mai mica de 2 h = aceeasi calatorie


def _dtp(x):
    return dt.datetime.fromisoformat(x)


TRIP_MAX = 30                                                     # curse legate intr-o calatorie (la fel ca in pagina Journey, fara plafon de 12)


def trip(car, did):
    """Calatorie = cursa ceruta + cursele vecine cu pauza < 2 h. Intoarce segmentele cu puncte si opririle dintre ele (oprire / incarcare)."""
    rows = q("""select id, start_date, end_date from drives where car_id=%s and end_date is not null
        and start_date between (select start_date - interval '3 days' from drives where id=%s) and (select end_date + interval '3 days' from drives where id=%s)
        order by start_date""", (car, did, did))
    idx = next((i for i, r in enumerate(rows) if r['id'] == did), None)
    if idx is None:
        return dict(segments=[], stops=[])
    lo = hi = idx
    while lo > 0 and hi - lo < TRIP_MAX - 1 and _dtp(rows[lo]['start_date']) - _dtp(rows[lo - 1]['end_date']) < TRIP_GAP:
        lo -= 1
    while hi < len(rows) - 1 and hi - lo < TRIP_MAX - 1 and _dtp(rows[hi + 1]['start_date']) - _dtp(rows[hi]['end_date']) < TRIP_GAP:
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


def _runs(rows, now):
    """Contopeste randurile din states in intervale (sleep = asleep+offline, awake = online), cronologic."""
    out = []
    for r in rows:
        k = 'sleep' if r['s'] in ('asleep', 'offline') else 'awake'
        st, en = r['start_date'], r['end_date']
        if out and out[-1]['s'] == k and out[-1]['end'] == st:
            out[-1]['end'] = en
        else:
            out.append(dict(s=k, start=st, end=en))
    return out


def sleep_report(car, days, full=False):
    """Somn si consum in repaus: intervale de somn/veghe, scurgere de baterie intre activitati (curse/incarcari), tipar de treziri."""
    now = dt.datetime.utcnow()
    since = now - dt.timedelta(days=days)
    P = lambda x: dt.datetime.fromisoformat(x) if x else now
    rows = q("select state::text as s, start_date, end_date from states where car_id=%s and coalesce(end_date, now() at time zone 'utc') > %s order by start_date", (car, since))
    runs = _runs(rows, now)
    for r in runs:                                   # taie la fereastra ceruta
        if P(r['start']) < since:
            r['start'] = since.isoformat()
    sleep_s = sum((min(P(r['end']), now) - P(r['start'])).total_seconds() for r in runs if r['s'] == 'sleep')
    win = max((now - since).total_seconds(), 1)
    # trezirile scurte repetate (tipar de tip 'ciclu BLE'): perioade veghe intre doua somnuri, fara curse/incarcari
    eff = (q("select efficiency from cars where id=%s", (car,)) or [{'efficiency': 0.15}])[0]['efficiency'] or 0.15
    acts = q(f"""select 'd' as k, d.start_date, d.end_date, sp.battery_level as s0, ep.battery_level as s1, sp.ideal_battery_range_km as r0, ep.ideal_battery_range_km as r1, {NAME_B} as place
        from drives d left join positions sp on sp.id=d.start_position_id left join positions ep on ep.id=d.end_position_id
        left join geofences g2 on g2.id=d.end_geofence_id left join addresses a2 on a2.id=d.end_address_id
        where d.car_id=%s and d.end_date is not null and d.end_date > %s
        union all select 'c', cp.start_date, cp.end_date, cp.start_battery_level, cp.end_battery_level, cp.start_ideal_range_km, cp.end_ideal_range_km, {NAME_A} as place
        from charging_processes cp left join geofences g on g.id=cp.geofence_id left join addresses a on a.id=cp.address_id
        where cp.car_id=%s and cp.end_date is not null and cp.end_date > %s order by 2""", (car, since, car, since))
    busy = [(P(a['start_date']), P(a['end_date'])) for a in acts]
    awake = [(P(r['end']) - P(r['start'])).total_seconds() / 60 for i, r in enumerate(runs)
             if r['s'] == 'awake' and r['end'] and 0 < i < len(runs) - 1 and not any(b0 < P(r['end']) and b1 > P(r['start']) for b0, b1 in busy)]      # fara curse/incarcari in ele
    short = [m for m in awake if 8 <= m <= 16]
    idle = []
    for a, b in zip(acts, acts[1:]):
        t0, t1 = P(a['end_date']), P(b['start_date'])
        hrs = (t1 - t0).total_seconds() / 3600
        if hrs < 0.5 or a['s1'] is None or b['s0'] is None:
            continue
        sl = sum(max(0, (min(P(r['end']), t1) - max(P(r['start']), t0)).total_seconds()) for r in runs if r['s'] == 'sleep') / 3600
        drop = a['s1'] - b['s0']
        kwh = ((a['r1'] or 0) - (b['r0'] or 0)) * eff if a['r1'] is not None and b['r0'] is not None else None
        idle.append(dict(place=a.get('place'), start=a['end_date'], end=b['start_date'], hours=round(hrs, 2), sleep_h=round(sl, 2), drop=drop, kwh=round(kwh, 2) if kwh is not None else None,
                         per_h=round(drop / hrs, 3), pct_sleep=round(sl / hrs * 100)))
    tot_h = sum(i['hours'] for i in idle)
    tot_drop = sum(i['drop'] for i in idle)
    tot_kwh = sum(i['kwh'] for i in idle if i['kwh'] is not None)
    by_day = {}
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(LOCAL_TZ)
    except Exception:  # noqa
        tz = dt.timezone.utc
    for r in runs:                                                   # zilele se taie la miezul noptii LOCAL (ca restul statisticilor), durata din timestamp-uri (corect si la schimbarea orei)
        if r['s'] != 'sleep':
            continue
        a, b = P(r['start']).replace(tzinfo=dt.timezone.utc).astimezone(tz), min(P(r['end']), now).replace(tzinfo=dt.timezone.utc).astimezone(tz)
        while a < b:
            d0 = a.replace(hour=0, minute=0, second=0, microsecond=0)
            e = min(b, (d0 + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0))
            if e <= a:
                break
            k = d0.date().isoformat()
            by_day[k] = by_day.get(k, 0) + (e.timestamp() - a.timestamp())
            a = e
    return dict(days=days, runs=runs[-300:], sleep_pct=round(sleep_s / win * 100, 1), sleep_h=round(sleep_s / 3600, 1),
                wakes=len([r for r in runs if r['s'] == 'awake']), short_wakes=len(short), short_med=round(sorted(short)[len(short) // 2], 1) if short else None,
                idle=idle[::-1][:30], **(dict(idle_all=idle[::-1]) if full else {}), idle_hours=round(tot_h, 1), idle_drop=tot_drop, idle_kwh=round(tot_kwh, 1), per_h=round(tot_drop / tot_h, 3) if tot_h else None,
                kwh_day=round(tot_kwh / (tot_h / 24), 2) if tot_h else None, by_day=[dict(day=k, pct=round(v / 864, 1)) for k, v in sorted(by_day.items())])


def activity(car, days, limit):
    """Cronologie unificata: curse, incarcari, stationari (>= 1 h), update-uri software, evenimente/automatizari din aplicatie."""
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    ev = []
    for d in drives(car, 2000, 0, since):
        if _dtp(d['start_date']) >= since:
            ev.append(dict(type='drive', t=d['start_date'], end=d['end_date'], id=d['id'], title='%s → %s' % (d['start_name'], d['end_name']),
                           km=d['distance'], kwh=d['kwh'], soc0=d['start_soc'], soc1=d['end_soc']))
    for c in charges(car, 2000, 0, None, since):               # acelasi cost ca in lista de incarcari (inclusiv costul real)
        if _dtp(c['start_date']) >= since:
            ev.append(dict(type='charge', t=c['start_date'], end=c['end_date'], id=c['id'], title=c['name'], kwh=c['charge_energy_added'], soc0=c['start_soc'], soc1=c['end_soc'], dc=c['dc'], cost=c['cost_eff']))
    try:
        for i in sleep_report(car, min(days, 30), full=True)['idle_all']:
            if i['hours'] >= 1:
                ev.append(dict(type='parked', t=i['start'], end=i['end'], title=i['place'] or '—', hours=i['hours'], drop=i['drop'], sleep_pct=i['pct_sleep'], kwh=i['kwh']))
    except Exception as e:  # noqa
        log('activity parked:', e, flush=True)
    for u in q("select start_date, version from updates where car_id=%s and start_date > %s", (car, since)):
        ev.append(dict(type='update', t=u['start_date'], title=u['version']))
    with NLOCK:
        app_ev = list(EVENTS)
    for e in app_ev:
        if _dtp(e['t']) >= since:
            ev.append(dict(type='app', t=e['t'], title=e['title'], msg=e['msg'], kind=e['kind']))
    ev.sort(key=lambda x: x['t'], reverse=True)
    return ev[:limit]


def demo_activity():
    now = dt.datetime.utcnow()
    ev = []
    for d in DEMO['drives'][:12]:
        ev.append(dict(type='drive', t=d['start_date'], end=d['end_date'], id=d['id'], title='%s → %s' % (d['start_name'], d['end_name']), km=d['distance'], kwh=d['kwh'], soc0=d['start_soc'], soc1=d['end_soc']))
    for c in DEMO['charges'][:5]:
        ev.append(dict(type='charge', t=c['start_date'], end=c['end_date'], id=c['id'], title=c['name'], kwh=c['charge_energy_added'], soc0=c['start_soc'], soc1=c['end_soc'], dc=c['dc'], cost=c['cost']))
    ev.append(dict(type='update', t=(now - dt.timedelta(days=12)).isoformat(), title='2026.14.3'))
    ev.append(dict(type='parked', t=(now - dt.timedelta(hours=20)).isoformat(), end=(now - dt.timedelta(hours=8)).isoformat(), title='Acasă', hours=12, drop=1, sleep_pct=78, kwh=0.6))
    ev.sort(key=lambda x: x['t'], reverse=True)
    return ev


def battery_health(car):
    """Capacitate utilizabila estimata din incarcari, curbe de incarcare comparate, consum in functie de temperatura si viteza."""
    ses = q("""select cp.id, cp.start_date, cp.charge_energy_added as kwh, cp.start_battery_level as s0, cp.end_battery_level as s1,
        (select bool_or(fast_charger_present) from charges ch where ch.charging_process_id=cp.id) as dc
        from charging_processes cp where cp.car_id=%s and cp.end_date is not null and cp.charge_energy_added > 3 and cp.end_battery_level - cp.start_battery_level >= 15
        order by cp.start_date""", (car,))
    cap = [dict(date=x['start_date'], cap=round(x['kwh'] / (x['s1'] - x['s0']) * 100, 1)) for x in ses]
    vals = [c['cap'] for c in cap]
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    now_c, first_c = (med(vals[-8:]), med(vals[:8])) if len(vals) >= 16 else (med(vals), None)     # sub 16 sesiuni esantioanele s-ar suprapune: nu pretindem o degradare
    last = [x for x in ses[-12:]][-6:]
    curves = []
    for x in last:
        pts = q("""select battery_level as soc, avg(charger_power) as kw from charges where charging_process_id=%s and battery_level is not null and charger_power is not null
            group by battery_level order by 1""", (x['id'],))
        bucket = {}
        for p in pts:
            bucket.setdefault(int(p['soc']) // 5 * 5, []).append(p['kw'])
        curves.append(dict(id=x['id'], date=x['start_date'], dc=bool(x['dc']), pts=[[k, round(sum(v) / len(v), 1)] for k, v in sorted(bucket.items())]))
    eff = (q("select efficiency from cars where id=%s", (car,)) or [{'efficiency': 0.15}])[0]['efficiency'] or 0.15
    dr = q("""select d.distance, d.duration_min, d.outside_temp_avg as t, (d.start_ideal_range_km - d.end_ideal_range_km) as rng from drives d
        where d.car_id=%s and d.end_date is not null and d.distance > 5 and d.duration_min > 3 and d.start_date > (now() at time zone 'utc') - interval '1 year'""", (car,))
    bt, bs = {}, {}
    for d in dr:
        if d['rng'] is None or d['distance'] is None or d['distance'] <= 0:
            continue
        wh = d['rng'] * eff * 1000 / d['distance']
        if not 40 < wh < 400:
            continue
        if d['t'] is not None:
            bt.setdefault(int(d['t'] // 5 * 5), []).append(wh)
        sp = d['distance'] / d['duration_min'] * 60
        bs.setdefault(int(sp // 20 * 20), []).append(wh)
    f = lambda b: [dict(x=k, wh=round(sum(v) / len(v)), n=len(v)) for k, v in sorted(b.items())]
    return dict(capacity=cap, cap_now=now_c, cap_first=first_c, degradation=round((1 - now_c / first_c) * 100, 1) if now_c and first_c else None,
                curves=curves, by_temp=f(bt), by_speed=f(bs))


HARD_WIN, HARD_BRAKE, HARD_ACCEL = 1.5, 3.0, 3.5     # fereastra (s) si pragurile (m/s2) pentru franare/accelerare brusca
SCORE_REF_KM = 30                                    # cursele mai lungi de atat au penalizarea micsorata proportional


def hard_events(pts, win=HARD_WIN, brake=HARD_BRAKE, accel=HARD_ACCEL):
    """pts = [(secunde, km/h)]. Numara EPISOADE de franare/accelerare brusca, cu acceleratia masurata pe o fereastra de ~1,5 s: viteza vine in km/h intregi
    si punctele pot fi la 0,25 s, iar intre doua puncte vecine o treapta de 1-2 km/h ar parea 1-2 m/s2 (zgomot de cuantizare)."""
    n, k = len(pts), 0
    acc = brk = 0
    in_acc = in_brk = False
    for i in range(n):
        k = max(k, i)
        while k < n and pts[k][0] - pts[i][0] < win:
            k += 1
        if k >= n:
            break
        dtt = pts[k][0] - pts[i][0]
        if dtt > 6:
            continue                                     # gol in date: nu estimam
        g = (pts[k][1] - pts[i][1]) / 3.6 / dtt
        if g > accel:
            if not in_acc:
                acc, in_acc = acc + 1, True
        elif g < accel * 0.5:
            in_acc = False
        if g < -brake:
            if not in_brk:
                brk, in_brk = brk + 1, True
        elif g > -brake * 0.5:
            in_brk = False
    return acc, brk


def drive_score(acc, brk, km):
    """100 - (5 x franari + 3 x accelerari), cu penalizarea scazuta proportional pentru cursele mai lungi de 30 km."""
    scale = SCORE_REF_KM / max(float(km or 0), SCORE_REF_KM)
    return max(0, round(100 - (5 * brk + 3 * acc) * scale))


def drive_events(did):
    """Evenimente din puncte brute: franari/accelerari bruste, energie recuperata, scor de conducere."""
    rows = q("select date, speed, power from positions where drive_id=%s and speed is not null order by date", (did,))
    regen = 0.0
    pts = []
    for r in rows:
        pts.append((_dtp(r['date']).timestamp(), r['speed']))
    for a, b in zip(rows, rows[1:]):
        dtt = (_dtp(b['date']) - _dtp(a['date'])).total_seconds()
        if 0 < dtt <= 6 and b['power'] is not None and b['power'] < 0:
            regen += -b['power'] * dtt / 3600
    acc, brk = hard_events(pts)
    d = q("select distance from drives where id=%s", (did,))
    return dict(hard_accel=acc, hard_brake=brk, regen_kwh=round(regen, 2), score=drive_score(acc, brk, d[0]['distance'] if d else 0))


def overview(car, days):
    since = dt.datetime.utcnow() - dt.timedelta(days=days)
    d = q("""select count(*) n, coalesce(sum(d.distance),0) km, coalesce(sum(d.distance) filter (where d.start_ideal_range_km is not null and d.end_ideal_range_km is not null),0) km_e,
        coalesce(sum(d.duration_min),0) minutes,
        coalesce(sum((d.start_ideal_range_km-d.end_ideal_range_km)*c.efficiency),0) kwh, coalesce(max(d.speed_max),0) vmax
        from drives d join cars c on c.id=d.car_id where d.car_id=%s and d.start_date>=%s and d.end_date is not null""", (car, since))[0]
    ch = q("""select count(*) n, coalesce(sum(charge_energy_added),0) kwh, coalesce(sum(cost),0) cost, coalesce(sum(duration_min),0) minutes
        from charging_processes where car_id=%s and start_date>=%s and end_date is not null""", (car, since))[0]
    byday = q(f"""select to_char(date_trunc('day', d.start_date at time zone 'UTC' at time zone '{LOCAL_TZ}'),'YYYY-MM-DD') as day, sum(d.distance) km,
        sum((d.start_ideal_range_km-d.end_ideal_range_km)*c.efficiency) kwh from drives d join cars c on c.id=d.car_id
        where d.car_id=%s and d.start_date>=%s and d.end_date is not null group by 1 order by 1""", (car, since))
    chday = q(f"""select to_char(date_trunc('day', start_date at time zone 'UTC' at time zone '{LOCAL_TZ}'),'YYYY-MM-DD') as day, sum(charge_energy_added) kwh, sum(cost) cost
        from charging_processes where car_id=%s and start_date>=%s and end_date is not null group by 1 order by 1""", (car, since))
    try:                                                      # cost efectiv: acelasi lant ca in lista de incarcari (manual > real > loc salvat > TeslaMate), prin decorate()
        budget, tot, man, kwh_c = 60, 0.0, 0, 0.0         # kwh_c = kWh doar din sesiunile cu cost cunoscut (pentru pretul mediu pe kWh)
        rows = _charges_rows(car, 5000, 0, lo=since)
        if ha_ok() and HA['grid']:
            for r in rows:
                try:
                    val, fetched = real_cost(r, budget > 0)
                    budget -= 1 if fetched else 0
                    r['cost_real'] = val
                except Exception as ex:  # noqa
                    budget = 0
                    log('overview real cost:', ex, flush=True)
        import zoneinfo
        ltz = zoneinfo.ZoneInfo(LOCAL_TZ)
        per_day = {}
        for r in decorate(rows):
            if r['cost_eff'] is not None:
                tot += r['cost_eff']
                kwh_c += r['charge_energy_added'] or 0
                day = _dtp(r['start_date']).replace(tzinfo=dt.timezone.utc).astimezone(ltz).strftime('%Y-%m-%d')
                per_day[day] = per_day.get(day, 0.0) + r['cost_eff']
            man += 1 if r.get('cost_manual') is not None else 0
        ch['cost_eff'] = round(tot, 2)
        ch['manual_n'] = man
        ch['kwh_c'] = round(kwh_c, 2)
        for x in chday:                                       # barele zilnice folosesc aceleasi costuri ca totalul
            x['cost'] = round(per_day.get(x['day'], 0.0), 2)
        if ha_ok() and HA['grid']:
            ch['cost_real'] = ch['cost_eff']
    except Exception as e:  # noqa
        log('overview cost:', e, flush=True)
    odo = q("select max(odometer) odo from positions where car_id=%s", (car,))
    ice = ice_calc(byday, d['kwh'], ch.get('cost_eff', ch['cost']), ch.get('kwh_c', ch['kwh']))
    return dict(days=days, drives=d, charges=ch, by_day=byday, charge_by_day=chday, odometer=(odo[0]['odo'] if odo else None), ice=ice)


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
                charges=dict(n=len(C), kwh=sum(c['charge_energy_added'] for c in C), cost=sum(c['cost'] for c in C), cost_eff=sum(c['cost'] for c in C), kwh_c=sum(c['charge_energy_added'] for c in C), manual_n=0, minutes=sum(c['duration_min'] for c in C)),
                by_day=sorted(by_day.values(), key=lambda x: x['day']), charge_by_day=sorted(ch.values(), key=lambda x: x['day']), odometer=18432.4,
                ice=ice_calc(sorted(by_day.values(), key=lambda x: x['day']), sum(d['kwh'] for d in D), sum(c['cost'] for c in C), sum(c['charge_energy_added'] for c in C), l100=7.2, book=[(x['day'], round(7.3 + .3 * math.sin(i / 3), 3)) for i, x in enumerate(sorted(by_day.values(), key=lambda x: x['day']))], manual=0))


DEMO_VD = dict(caps=dict(rear_seats=True), climate_state=dict(driver_temp_setting=21.0, passenger_temp_setting=21.0, is_climate_on=False, seat_heater_left=0, seat_heater_right=0, seat_heater_rear_left=0,
                                   seat_heater_rear_center=0, seat_heater_rear_right=0, steering_wheel_heater=False, is_front_defroster_on=False, defrost_mode=0,
                                   cabin_overheat_protection='On', cop_activation_temperature='High'),
               charge_state=dict(charge_current_request=16, charge_current_request_max=32, charge_limit_soc=90, scheduled_charging_mode='StartAt',
                                 scheduled_charging_start_time_minutes=120, scheduled_departure_time_minutes=450, preconditioning_enabled=True, off_peak_charging_enabled=False),
               charge_schedules=[dict(id=1, name='Acasă', days_of_week=127, start_enabled=True, start_time=120, end_enabled=True, end_time=360, enabled=True, one_time=False)],
               precondition_schedules=[dict(id=2, days_of_week=62, precondition_time=435, enabled=True, one_time=False)])


def demo_sleep(days):
    r = random.Random(3)
    now = dt.datetime.utcnow()
    runs, t = [], now - dt.timedelta(days=days)
    sleeping = True
    while t < now:
        m = r.choice([25, 38, 90, 200, 420]) if sleeping else r.choice([12, 12, 13, 25, 60])
        e = min(t + dt.timedelta(minutes=m), now)
        runs.append(dict(s='sleep' if sleeping else 'awake', start=t.isoformat(), end=e.isoformat() if e < now else None))
        t, sleeping = e, not sleeping
    return dict(days=days, runs=runs, sleep_pct=72.4, sleep_h=round(days * 24 * .724, 1), wakes=19, short_wakes=9, short_med=12.1,
                idle=[dict(start=(now - dt.timedelta(hours=30 + 20 * i)).isoformat(), end=(now - dt.timedelta(hours=18 + 20 * i)).isoformat(), hours=12 + i, sleep_h=9 + i * .5, drop=1 + i % 2, kwh=round(.6 + i * .2, 2), per_h=round((1 + i % 2) / (12 + i), 3), pct_sleep=75) for i in range(5)],
                idle_hours=88, idle_drop=7, idle_kwh=4.8, per_h=.08, kwh_day=1.3, by_day=[dict(day=(now - dt.timedelta(days=d)).date().isoformat(), pct=round(60 + 25 * random.Random(d).random(), 1)) for d in range(days - 1, -1, -1)])


def demo_health():
    r = random.Random(5)
    now = dt.datetime.utcnow()
    cap = [dict(date=(now - dt.timedelta(days=60 - i * 3)).isoformat(), cap=round(57.4 - i * .03 + r.uniform(-.5, .5), 1)) for i in range(20)]
    curves = [dict(id=i, date=(now - dt.timedelta(days=5 * i)).isoformat(), dc=i % 2 == 0, pts=[[s, round((150 * (1 - s / 105) ** 1.4 if i % 2 == 0 else 10.8) + r.uniform(-3, 3), 1)] for s in range(10, 95, 5)]) for i in range(4)]
    return dict(capacity=cap, cap_now=57.0, cap_first=57.5, degradation=0.9, curves=curves, by_temp=[dict(x=t, wh=int(128 + (15 - t) * 1.4), n=6) for t in range(-5, 30, 5)], by_speed=[dict(x=s, wh=int(110 + abs(s - 60) * 1.1), n=8) for s in range(20, 140, 20)])


def demo_battery():
    now = dt.date.today()
    rng = [dict(week=(now - dt.timedelta(weeks=w)).isoformat(), range100=round(540 - (52 - w) * .06 + random.Random(w).uniform(-3, 3), 1), rated100=0) for w in range(52, -1, -4)]
    return dict(range100=rng, states=[dict(s='online', hours=214), dict(s='asleep', hours=412), dict(s='offline', hours=6)],
                updates=[dict(start_date=(dt.datetime.utcnow() - dt.timedelta(days=12)).isoformat(), version='2026.14.3'), dict(start_date=(dt.datetime.utcnow() - dt.timedelta(days=45)).isoformat(), version='2026.8.6')])



# ---------------------------------------------------------------- Home Assistant (comenzi locale prin ESP32 BLE + date solare)
HA = dict(url=os.environ.get('HA_URL', '').rstrip('/'), token=os.environ.get('HA_TOKEN', ''), prefix=os.environ.get('HA_BLE_PREFIX', 'tesla_ble'),
          ble=os.environ.get('BLE_FIRST', '1') == '1', grid=os.environ.get('HA_GRID_IMPORT', ''), pv=os.environ.get('HA_PV_POWER', ''))


def ha_ok():
    return bool(HA['url'] and HA['token'])


def ha_req(method, path, data=None, timeout=12):
    return http(HA['url'] + path, data, headers={'Authorization': 'Bearer ' + HA['token']}, method=method, timeout=timeout)


def ha_state(eid):
    try:
        c, r = ha_req('GET', '/api/states/' + eid, timeout=6)
        return r if c == 200 else None
    except Exception:
        return None


def ble_plan(name, arg):
    """comanda -> (domeniu, serviciu, date) pentru entitatile esphome-tesla-ble din HA; None = nu exista cale BLE (se foloseste Fleet API)."""
    p, a = HA['prefix'], (arg if isinstance(arg, dict) else {})
    E = lambda d, x: {'entity_id': '%s.%s_%s' % (d, p, x)}
    if name == 'lock':
        return 'lock', 'lock', E('lock', 'doors')
    if name == 'unlock':
        return 'lock', 'unlock', E('lock', 'doors')
    if name in ('climate_on', 'climate_off'):
        return 'climate', 'set_hvac_mode', dict(E('climate', 'climate'), hvac_mode='heat_cool' if name == 'climate_on' else 'off')
    if name in ('charge_start', 'charge_stop'):
        return 'switch', 'turn_on' if name == 'charge_start' else 'turn_off', E('switch', 'charger')
    if name in ('sentry_on', 'sentry_off'):
        return 'switch', 'turn_on' if name == 'sentry_on' else 'turn_off', E('switch', 'sentry_mode')
    if name in ('flash', 'honk', 'wake'):
        return 'button', 'press', E('button', {'flash': 'flash_lights', 'honk': 'sound_horn', 'wake': 'wake_up'}[name])
    if name in ('frunk', 'trunk'):
        return 'cover', 'open_cover', E('cover', name)
    if name in ('port_open', 'port_close'):
        return 'cover', 'open_cover' if name == 'port_open' else 'close_cover', E('cover', 'charge_port_door')
    if name == 'charge_limit':
        return 'number', 'set_value', dict(E('number', 'charging_limit'), value=int(max(50, min(100, float(arg)))))
    if name == 'charging_amps':
        return 'number', 'set_value', dict(E('number', 'charging_amps'), value=int(max(1, min(48, float(a.get('amps', 0))))))
    if name == 'set_temps':
        return 'climate', 'set_temperature', dict(E('climate', 'climate'), temperature=_num(a, 'driver', 15, 28, 21))
    if name == 'steering_heater':
        return 'switch', 'turn_on' if a.get('on') else 'turn_off', E('switch', 'heated_steering')
    if name == 'defrost':
        return 'climate', 'set_preset_mode', dict(E('climate', 'climate'), preset_mode='Defrost' if a.get('on') else 'Normal')
    if name == 'cop':
        return 'select', 'select_option', dict(E('select', 'cabin_overheat_protection'), option='Off' if not a.get('on') else ('Fan only' if a.get('fan_only') else 'On'))
    if name == 'cop_temp':
        return 'select', 'select_option', dict(E('select', 'cabin_overheat_temperature'), option=['Low', 'Medium', 'High'][int(_num(a, 'level', 0, 2, 2))])
    if name == 'seat_heater' and int(a.get('seat', -1)) in (0, 1):
        return 'select', 'select_option', dict(E('select', 'front_left_seat_climate' if int(a['seat']) == 0 else 'front_right_seat_climate'),
                                                option=['Off', 'Low heat', 'Medium heat', 'High heat'][int(_num(a, 'level', 0, 3, 0))])
    return None


TOGGLES = ('trunk', 'frunk')       # comenzi care inverseaza starea: la un timeout nu le repetam automat pe alta cale


def ble_run(name, arg):
    """Incearca comanda local prin ESP32 BLE (prin HA). None => foloseste Fleet API. Dict => rezultat (ok/eroare) pe calea BLE."""
    if not (ha_ok() and HA['ble']):
        return None
    plan = ble_plan(name, arg)
    if not plan:
        return None
    st = ha_state('binary_sensor.%s_status' % HA['prefix'])
    if not st or st.get('state') != 'on':
        if _once('ble-off', 600):
            log('ble: ESP32 indisponibil sau Home Assistant nu raspunde -> comenzile merg pe Fleet API (pot trezi masina)', flush=True)
        return None
    last = lambda: (ha_state('sensor.%s_last_command' % HA['prefix']) or {}).get('state')
    before = last()
    try:
        c, r = ha_req('POST', '/api/services/%s/%s' % plan[:2], plan[2])
    except Exception as e:  # noqa
        log('ble: apelul catre HA a esuat (%s): %s' % (name, e), flush=True)
        if name in TOGGLES:
            return dict(ok=False, via='ble', code=0, reason='Home Assistant nu a răspuns la timp — comanda poate fi totuși executată. Verifică starea înainte s-o repeți.')
        return None
    if c >= 300:
        if _once('ble-http', 300):
            log('ble: HA a raspuns %s la %s -> Fleet API' % (c, name), flush=True)
        return None
    for _ in range(9):
        time.sleep(.7)
        now = last()
        if now and now != before:
            if 'success' in now.lower():
                return dict(ok=True, via='ble', code=200, reason=now)
            return None                       # BLE a esuat -> incearca Fleet
    return dict(ok=True, via='ble', code=200, reason='trimis prin BLE (fără confirmare)')


def ha_history(eid, t0, t1):
    """Serie (timp UNIX, valoare) pentru un senzor numeric, din istoricul HA."""
    q_ = urllib.parse.urlencode(dict(filter_entity_id=eid, end_time=t1.isoformat() + '+00:00', minimal_response='1', no_attributes='1'))
    c, r = ha_req('GET', '/api/history/period/%s+00:00?%s' % (t0.isoformat(), q_), timeout=25)
    out = []
    if c == 200 and r and isinstance(r, list) and r[0]:
        for x in r[0]:
            try:
                out.append((dt.datetime.fromisoformat(x['last_changed'].replace('Z', '+00:00')).timestamp(), float(x['state'])))
            except (ValueError, KeyError, TypeError):
                pass
    return out


def _integral(series, t0, t1):
    """kWh dintr-o serie de puteri (W), functie constanta pe portiuni."""
    if not series:
        return 0.0
    pts = [(max(t, t0), max(v, 0.0)) for t, v in series]           # valorile negative (export) nu scad costul
    pts.append((t1, pts[-1][1]))
    e = 0.0
    for (ta, v), (tb, _) in zip(pts, pts[1:]):
        if tb > ta:
            e += v * (min(tb, t1) - ta) / 3600 / 1000
    return e


def charge_solar(cid):
    """Estimare: cat din energia unei incarcari a venit din retea (import invertor) vs. restul (solar/baterie casa)."""
    if not (ha_ok() and HA['grid']):
        return dict(available=False)
    cp = q(f"""select cp.start_date, cp.end_date, cp.charge_energy_used, cp.charge_energy_added, cp.cost, g.cost_per_unit as tariff, {NAME_A} as name,
        coalesce((select bool_or(fast_charger_present) from charges ch where ch.charging_process_id=cp.id), false) as dc,
        coalesce((select max(charger_power) from charges ch where ch.charging_process_id=cp.id), 0) as pmax
        from charging_processes cp left join geofences g on g.id=cp.geofence_id left join addresses a on a.id=cp.address_id where cp.id=%s""", (cid,))
    if not cp or not cp[0]['end_date']:
        return dict(available=False)
    cp = cp[0]
    if cp['dc'] or (cp['pmax'] or 0) > 25 or not re.search(r'acas|home', cp['name'] or '', re.I):
        return dict(available=False, reason='Estimarea se face doar pentru încărcări AC acasă.')
    t0, t1 = _dtp(cp['start_date']), _dtp(cp['end_date'])
    car_kwh = cp['charge_energy_used'] or cp['charge_energy_added'] or 0
    gh = ha_history(HA['grid'], t0 - dt.timedelta(minutes=1), t1)
    if not gh:
        return dict(available=False, reason='Istoricul din Home Assistant nu e disponibil acum.')
    grid = _integral(gh, t0.replace(tzinfo=dt.timezone.utc).timestamp(), t1.replace(tzinfo=dt.timezone.utc).timestamp())
    pv = _integral(ha_history(HA['pv'], t0 - dt.timedelta(minutes=1), t1), t0.replace(tzinfo=dt.timezone.utc).timestamp(), t1.replace(tzinfo=dt.timezone.utc).timestamp()) if HA['pv'] else None
    share = max(0.0, min(1.0, 1 - grid / car_kwh)) if car_kwh else None
    try:
        price = float(cget('price_grid', 'PRICE_GRID', '') or 0) or float(cp.get('tariff') or 0)
    except (TypeError, ValueError):
        price = float(cp.get('tariff') or 0)
    return dict(available=True, cost_tm=cp.get('cost'), price=price or None, cost_real=round(grid * price, 2) if price else None, car_kwh=round(car_kwh, 2), grid_kwh=round(grid, 2), pv_kwh=round(pv, 2) if pv is not None else None, solar_share=round(share * 100) if share is not None else None)


# ---------------------------------------------------------------- Tesla Fleet API (comenzi)
FL = dict(cid=os.environ.get('FLEET_CLIENT_ID', ''), secret=os.environ.get('FLEET_CLIENT_SECRET', ''),
          domain=os.environ.get('FLEET_DOMAIN', ''), pin=os.environ.get('APP_PIN', ''),
          base=os.environ.get('FLEET_BASE', 'https://fleet-api.prd.eu.vn.cloud.tesla.com'),
          proxy=os.environ.get('FLEET_PROXY', 'https://proxy:4443'), cert=os.environ.get('FLEET_PROXY_CERT', '/fleet/tls-cert.pem'))
TOKENS = DATA_DIR + '/tokens.json'
KEYPUB = '/fleet/public-key.pem'
SCOPES = 'openid offline_access vehicle_device_data vehicle_cmds vehicle_charging_cmds'
STATES = {}      # state -> expiry (OAuth CSRF)
TLOCK = threading.Lock()


def tok_load():
    return jload(TOKENS, {})


def tok_save(d):
    jsave(TOKENS, d)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Un redirect nu se urmeaza: antetul Authorization (token HA, updater) nu trebuie sa ajunga pe alt host."""
    def redirect_request(self, *a, **k):
        return None


def _OPENER(ctx=None):
    hs = [_NoRedirect()]
    if ctx is not None:
        hs.append(urllib.request.HTTPSHandler(context=ctx))
    return urllib.request.build_opener(*hs)


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
        with _OPENER(ctx).open(req, timeout=timeout) as r:
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
    except Exception as e:  # noqa
        raise RuntimeError('Nu pot încărca certificatul proxy-ului de comenzi (%s): %s' % (FL['cert'], e))   # nu mai trimitem tokenul fara verificarea TLS
    return c


def fleet_status():
    t = tok_load()
    return dict(ble=bool(ha_ok() and HA['ble']), configured=bool(FL['cid'] and FL['secret'] and FL['domain']), key=os.path.isfile(KEYPUB), authorized=bool(t.get('refresh_token')),
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
    with TLOCK:
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
        with TLOCK:
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
    for attempt in (0, 1):
        tk = access_token()
        c, r = http('%s/api/1/vehicles/%s/%s' % (FL['proxy'], vin, path), data, headers={'Authorization': 'Bearer ' + tk}, ctx=proxy_ctx(), timeout=40, method=method)
        if c == 401 and attempt == 0:                   # token revocat/invalid inainte de expirare: il reinnoim o data si reincercam
            with TLOCK:
                t = tok_load()
                t['exp'] = 0
                tok_save(t)
            continue
        return c, r


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


def _pin4(a):
    p = str(a.get('pin', ''))
    if not re.fullmatch(r'\d{4}', p):
        raise ValueError('PIN-ul mașinii: exact 4 cifre')
    return p


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
    if name in ('charge_schedule_add', 'precond_add') and (lv.get('latitude') is None or lv.get('longitude') is None):
        raise RuntimeError('Nu cunosc poziția mașinii (programările au nevoie de locație).')
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
    if name in ('valet_on', 'valet_off'):
        return 'set_valet_mode', {'on': name == 'valet_on', 'password': _pin4(a)}        # PIN-ul trece doar prin memorie: nu se salveaza si nu intra in jurnal
    if name == 'valet_reset':
        return 'reset_valet_pin', {}
    if name in ('guest_on', 'guest_off'):
        return 'guest_mode', {'enable': name == 'guest_on'}
    if name == 'speed_limit_set':
        return 'speed_limit_set_limit', {'limit_mph': int(_num(a, 'mph', 50, 90))}
    if name in ('speed_limit_on', 'speed_limit_off', 'speed_limit_clear'):
        return {'speed_limit_on': 'speed_limit_activate', 'speed_limit_off': 'speed_limit_deactivate', 'speed_limit_clear': 'speed_limit_clear_pin'}[name], {'pin': _pin4(a)}
    raise ValueError('comandă necunoscută')


def ensure_awake(vin, lv):
    if lv.get('state') in ('asleep', 'offline', None):
        vehicle_call(vin, 'wake_up', {})
        for _ in range(12):
            c, r = vehicle_call(vin, '', method='GET')
            if (r.get('response') or {}).get('state') == 'online':
                break
            time.sleep(2.5)


NOREPEAT = {'homelink': 8, 'trunk': 6, 'frunk': 6, 'charge_start': 5, 'charge_stop': 5, 'lock': 3, 'unlock': 3, 'flash': 3, 'honk': 3, 'port_open': 5, 'port_close': 5}
CMD_LAST = {}
CMD_LOCK = threading.Lock()


def run_command(car, name, arg=None):
    """Ocolire dublu-tap / retry: aceeasi comanda (cu aceiasi parametri) nu se retrimite in fereastra NOREPEAT (poarta/portbagajul sunt toggle)."""
    gap = NOREPEAT.get(name)
    key = (car, name, json.dumps(arg, sort_keys=True, default=str))
    if gap:
        with CMD_LOCK:
            now = time.time()
            for k in [k for k, v in CMD_LAST.items() if now - v > 60]:
                del CMD_LAST[k]
            if now - CMD_LAST.get(key, 0) < gap:
                return dict(ok=False, code=429, reason='Comanda a fost trimisă acum câteva secunde — n-o repet ca să nu inverseze efectul. Așteaptă %d s.' % gap)
            CMD_LAST[key] = now
    actor = getattr(CTX, 'actor', 'system')
    try:
        res = _run_command(car, name, arg)
    except Exception as e:
        if gap:
            CMD_LAST.pop(key, None)
        audit('cmd', car=car, name=name, actor=actor, ok=False, via='', note=str(e))
        raise
    audit('cmd', car=car, name=name, actor=actor, ok=bool((res or {}).get('ok')), via=(res or {}).get('via', 'fleet'), note=(res or {}).get('reason', ''))
    if gap and not (res or {}).get('ok'):
        CMD_LAST.pop(key, None)                       # a esuat: reincercarea e permisa imediat
    return res


def _run_command(car, name, arg=None):
    lv = LIVE.get(car, {})
    ep, pl = ('wake_up', {}) if name == 'wake' else build_cmd(name, arg, lv)       # valideaza inainte sa trezeasca masina
    ble = ble_run(name, arg)
    if ble:
        VD.pop(car, None)
        return ble
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


CAPFILE = DATA_DIR + '/caps.json'


def caps_load(car):
    return (jload(CAPFILE, {}) or {}).get(str(car)) or {}


def caps_save(car, d):
    try:
        with FLOCK:
            allc = jload(CAPFILE, {}) or {}
            allc[str(car)] = dict(allc.get(str(car)) or {}, **d)
            jsave(CAPFILE, allc)
    except Exception as e:  # noqa
        log('caps:', e, flush=True)


def caps_infer(car):
    """Dotari: din ce a raportat masina cand a fost online (persistat) sau, cat doarme, din entitatile ESP32 BLE din HA (necunoscut = lipseste)."""
    caps = caps_load(car)
    if caps.get('source') == 'car' or not ha_ok() or ('rear_seats' in caps and 'wheel_heater' in caps):
        return caps
    try:
        bad = ('unknown', 'unavailable', None)
        st = lambda e: (ha_state(e % HA['prefix']) or {}).get('state')
        if st('select.%s_front_left_seat_climate') not in bad:                 # ESP32 vede masina: ce lipseste din entitati = nu exista pe masina
            upd = dict(source='ha')
            if 'rear_seats' not in caps and st('select.%s_rear_left_seat_heat') in bad and st('select.%s_rear_right_seat_heat') in bad:
                upd['rear_seats'] = False
            if 'wheel_heater' not in caps and st('switch.%s_heated_steering') in bad and st('sensor.%s_steering_heat_mode') in bad:
                upd['wheel_heater'] = False
            if len(upd) > 1:
                caps_save(car, upd)
                caps = caps_load(car)
    except Exception:
        pass
    return caps


def vehicle_data(car, force=False):
    d = _vehicle_data(car, force)
    caps = caps_infer(car)
    d['caps'] = caps
    return d


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


def _vehicle_data(car, force=False):
    """Citeste starea direct din masina. NU trezeste masina (ca sa nu strice somnul) - doar daca TeslaMate o vede online."""
    c = VD.get(car)
    if c and time.time() - c[0] < 45 and not force:
        return dict(c[1], cached=True)
    lv = LIVE.get(car, {})
    if lv.get('state') in ('asleep', 'offline', 'suspended', None):          # si "suspended": interogarea ar tine masina trează
        return dict(c[1], stale=True, asleep=True) if c else dict(asleep=True)
    vin = vin_for(car)
    if not vin:
        raise RuntimeError('Nu există VIN în TeslaMate.')
    ep = urllib.parse.quote('charge_state;climate_state;charge_schedule_data;preconditioning_schedule_data;vehicle_config;vehicle_state', safe='')
    code, r = vehicle_call(vin, 'vehicle_data?endpoints=' + ep, method='GET')
    resp = r.get('response') or {}
    if code != 200 or not resp:
        return dict(c[1], stale=True, error=r.get('error') or code) if c else dict(error=r.get('error') or code, asleep=code == 408)
    out = {k: {x: (resp.get(k) or {}).get(x) for x in keys} for k, keys in VD_KEYS.items()}
    vc = resp.get('vehicle_config') or {}
    if vc:
        out['config'] = {k: vc.get(k) for k in ('rear_seat_heaters', 'has_seat_cooling', 'seat_type', 'steering_wheel_type', 'plg', 'sun_roof_installed', 'third_row_seats', 'car_type', 'trim_badging', 'wheel_type', 'can_actuate_trunks', 'motorized_charge_port')}
        caps = dict(rear_seats=bool(vc.get('rear_seat_heaters')), seat_cooling=bool(vc.get('has_seat_cooling')), source='car', updated=time.time())
        hl = (resp.get('vehicle_state') or {}).get('homelink_device_count')
        if hl is not None:
            caps['homelink'] = hl > 0
        caps_save(car, caps)
    vs = resp.get('vehicle_state') or {}
    out['openings'] = {k: vs.get(k) for k in ('df', 'dr', 'pf', 'pr', 'ft', 'rt', 'fd_window', 'fp_window', 'rd_window', 'rp_window')}
    out['charge_schedules'] = (resp.get('charge_schedule_data') or {}).get('charge_schedules') or []
    out['precondition_schedules'] = (resp.get('preconditioning_schedule_data') or {}).get('precondition_schedules') or []
    VD[car] = (time.time(), out)
    return dict(out)


# ---------------------------------------------------------------- configurare din aplicatie (/data/config.json; suprascrie valorile din .env)
CFGFILE = DATA_DIR + '/config.json'
CFG = {}
CFG_SECRETS = ('fleet_secret', 'pin', 'ha_token', 'notify_webhook', 'app_password', 'tessie_token', 'update_token', 'telegram_token')
CFG_KEYS = CFG_SECRETS + ('telegram_chat', 'update_check', 'update_webhook', 'app_url', 'price_grid', 'fleet_id', 'fleet_domain', 'fleet_base', 'ha_url', 'ha_prefix', 'ha_ble', 'ha_grid', 'ha_pv', 'currency', 'ice_l100', 'fuel_type', 'fuel_price', 'fuel_country', 'link_tm', 'link_gf', 'acc_team', 'acc_aud', 'acc_email', 'roles')
EU_BASE = 'https://fleet-api.prd.eu.vn.cloud.tesla.com'
_tz = os.environ.get('TZ', '') or 'UTC'
LOCAL_TZ = _tz if re.fullmatch(r'[A-Za-z0-9_+\-/]{1,40}', _tz) else 'UTC'      # zilele din statistici se grupeaza pe ora locala, nu UTC


def cfg_load():
    global CFG
    CFG = jload(CFGFILE, {}) or {}


def cfg_save():
    jsave(CFGFILE, CFG)


def cget(k, env='', d=''):
    v = CFG.get(k)
    if v not in (None, ''):
        return v
    return os.environ.get(env, d) if env else d


def apply_config():
    """Aplica configuratia (aplicatie > .env) pe dictionarele folosite de restul serverului, fara repornire."""
    global NHOOK, CURRENCY, APPURL
    FL.update(cid=cget('fleet_id', 'FLEET_CLIENT_ID'), secret=cget('fleet_secret', 'FLEET_CLIENT_SECRET'), domain=cget('fleet_domain', 'FLEET_DOMAIN'),
              pin=cget('pin', 'APP_PIN'), base=cget('fleet_base', 'FLEET_BASE', EU_BASE))
    HA.update(url=str(cget('ha_url', 'HA_URL')).rstrip('/'), token=cget('ha_token', 'HA_TOKEN'), prefix=cget('ha_prefix', 'HA_BLE_PREFIX', 'tesla_ble'),
              ble=str(cget('ha_ble', 'BLE_FIRST', '1')).lower() in ('1', 'true'), grid=cget('ha_grid', 'HA_GRID_IMPORT'), pv=cget('ha_pv', 'HA_PV_POWER'))
    NHOOK = cget('notify_webhook', 'NOTIFY_WEBHOOK')
    APPURL = str(cget('app_url', 'APP_URL')).rstrip('/')
    CURRENCY = cget('currency', 'CURRENCY', '€')
    LINKS.update(teslamate=cget('link_tm', 'TESLAMATE_URL'), grafana=cget('link_gf', 'GRAFANA_URL'))
    AUTH['pw'] = cget('app_password', 'APP_PASSWORD')
    ACCESS.update(team=cget('acc_team', 'ACCESS_TEAM'), aud=cget('acc_aud', 'ACCESS_AUD'), email=cget('acc_email', 'ACCESS_EMAIL'))
    if not os.environ.get('SESSION_SECRET'):          # secret persistent pentru cookie-urile de sesiune (supravietuiesc repornirii)
        try:
            sf = os.path.join(os.path.dirname(CFGFILE), 'session_secret')
            try:
                with open(sf) as fh:
                    sec = fh.read().strip()
            except OSError:
                sec = ''
            if len(sec) < 32:                                  # lipsa sau trunchiat (oprire in timpul scrierii): regeneram, atomic
                sec = secrets.token_hex(32)
                os.makedirs(os.path.dirname(sf), exist_ok=True)
                fd = os.open(sf + '.tmp', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, 'w') as f:
                    f.write(sec)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(sf + '.tmp', sf)
            AUTH['secret'] = sec.encode()
        except Exception:
            pass
    _JWKS.clear()
    ROLES.clear()
    ROLES.update({k.strip().lower(): (v.strip().lower() if v.strip().lower() in ('admin', 'family', 'viewer') else 'viewer')        # rol necunoscut/typo = cel mai mic (viewer)
                  for k, _, v in (x.partition(':') for x in str(cget('roles', 'ROLES')).split(',') if ':' in x)})


def cfg_public():
    g = lambda k, env='', d='': cget(k, env, d)
    return dict(
        fleet=dict(id=g('fleet_id', 'FLEET_CLIENT_ID'), domain=g('fleet_domain', 'FLEET_DOMAIN'), base=g('fleet_base', 'FLEET_BASE', EU_BASE), secret_set=bool(FL['secret']), pin_set=bool(FL['pin'])),
        ha=dict(url=HA['url'], token_set=bool(HA['token']), prefix=HA['prefix'], ble=HA['ble'], grid=HA['grid'], pv=HA['pv']),
        notify=dict(webhook_set=bool(NHOOK)), tessie=dict(token_set=bool(cget('tessie_token', 'TESSIE_TOKEN'))),
        telegram=dict(token_set=bool(cget('telegram_token', 'TELEGRAM_TOKEN')), chat=cget('telegram_chat', 'TELEGRAM_CHAT', '')),
        update=dict(check=update_cfg_on(), webhook=cget('update_webhook', 'UPDATE_WEBHOOK', ''), token_set=bool(cget('update_token', 'UPDATE_TOKEN', '')), private=APP_VERSION.endswith('-private')),
        display=dict(app_url=APPURL, price_grid=cget('price_grid', 'PRICE_GRID', ''), currency=CURRENCY, ice_l100=cget('ice_l100', 'ICE_L100', ''), fuel_type=fuel_conf()['type'], fuel_price=cget('fuel_price', 'FUEL_PRICE', ''), fuel_country=fuel_conf()['country'], teslamate=LINKS['teslamate'], grafana=LINKS['grafana']),
        access=dict(team=ACCESS['team'], aud=ACCESS['aud'], email=ACCESS['email'], roles=str(cget('roles', 'ROLES')), password_set=bool(AUTH['pw'])))


def cfg_update(b):
    errs = []
    new = dict(CFG)
    if 'update_webhook' in b:                          # idem pentru tokenul updater-ului
        nw = str(b['update_webhook'] or '').strip()
        if nw and nw != str(cget('update_webhook', 'UPDATE_WEBHOOK', '')) and cget('update_token', 'UPDATE_TOKEN', '') and not str(b.get('update_token') or '').strip():
            errs.append('Ai schimbat adresa updater-ului: introdu din nou și tokenul.')
    if 'ha_url' in b:                                  # tokenul HA nu trebuie sa ajunga la un alt server fara sa-l introduci din nou
        nu = str(b['ha_url'] or '').strip().rstrip('/')
        if nu and nu != str(HA['url']).rstrip('/') and HA['token'] and not str(b.get('ha_token') or '').strip():
            errs.append('Ai schimbat adresa Home Assistant: introdu din nou și tokenul de acces (nu îl trimit către o adresă nouă fără să-l reconfirmi).')
    for k in CFG_KEYS:
        if k not in b:
            continue
        v = b[k]
        v = '' if v is None else (str(v).strip() if not isinstance(v, bool) else ('1' if v else '0'))
        if k in CFG_SECRETS and v == '':
            continue                                   # camp secret lasat gol = pastreaza
        if v == '__clear__':
            new.pop(k, None)
            continue
        if k in ('ha_url', 'link_tm', 'link_gf', 'app_url', 'update_webhook') and v and not v.startswith(('http://', 'https://')):
            errs.append('%s trebuie să înceapă cu http:// sau https://' % k)
        if k == 'notify_webhook' and not v.startswith(('http://', 'https://')):
            errs.append('webhook invalid')
        if k == 'fleet_domain' and ('/' in v or ' ' in v):
            errs.append('domeniul se scrie fără https:// și fără /')
        if k in ('ice_l100', 'fuel_price') and v:
            try:
                x = float(v.replace(',', '.'))
                if not (0 <= x <= (60 if k == 'ice_l100' else 1000)):
                    raise ValueError
                v = v.replace(',', '.')
            except ValueError:
                errs.append('valoare invalidă pentru %s' % k)
        if k == 'telegram_chat' and v and not re.fullmatch(r'-?\d{3,20}|@\w{4,40}', v):
            errs.append('chat Telegram: număr (ex. 123456789 sau -100123…) sau @canal')
        if k == 'telegram_token' and v and v != '__clear__' and not re.fullmatch(r'\d{6,12}:[\w-]{20,60}', v):
            errs.append('token Telegram invalid (arată ca 123456789:AA…)')
        if k == 'update_check' and v not in ('', '0', '1'):
            errs.append('update_check invalid')
        if k == 'fuel_type' and v not in ('', 'euro95', 'diesel', 'manual'):
            errs.append('tip combustibil invalid')
        if k == 'fuel_country' and v and not re.fullmatch(r'[A-Za-z -]{2,40}', v):
            errs.append('țara se scrie cu litere (ex. Romania, Germany)')
        if k == 'price_grid' and v:
            try:
                float(v.replace(',', '.'))
                v = v.replace(',', '.')
            except ValueError:
                errs.append('preț invalid')
        if k == 'pin' and len(v) < 6:
            errs.append('PIN-ul trebuie să aibă minim 6 caractere')
        if k == 'app_password' and len(v) < 12:
            errs.append('parola trebuie să aibă minim 12 caractere')
        if k == 'fleet_base' and v and v not in (EU_BASE, 'https://fleet-api.prd.na.vn.cloud.tesla.com', 'https://fleet-api.prd.cn.vn.cloud.tesla.cn'):
            errs.append('regiune invalidă')
        if k == 'roles' and v and any((':' not in x or x.split(':')[1].strip() not in ('admin', 'family', 'viewer')) for x in v.split(',')):
            errs.append('roluri: email:family,email2:viewer')
        if len(v) > 600:
            errs.append('%s prea lung' % k)
        new[k] = v
    if errs:
        return False, '; '.join(errs)
    CFG.clear()
    CFG.update(new)
    cfg_save()
    apply_config()
    if fuel_conf()['type'] != 'manual':
        threading.Thread(target=fuel_fetch, daemon=True).start()          # pret nou imediat dupa schimbarea tipului/tarii
    return True, ''


def ha_entities():
    """Senzori de putere (W) din HA + sugestii automate pentru importul din retea si productia fotovoltaica."""
    c, r = ha_req('GET', '/api/states', timeout=15)
    if c != 200 or not isinstance(r, list):
        return dict(ok=False, msg='HA a răspuns %s' % c, entities=[])
    ents = []
    for x in r:
        eid = x.get('entity_id', '')
        at = x.get('attributes') or {}
        if eid.startswith('sensor.') and at.get('unit_of_measurement') == 'W':
            ents.append(dict(id=eid, name=at.get('friendly_name') or eid, state=x.get('state')))
    def best(pats, bad=()):
        sc = []
        for e in ents:
            t = (e['id'] + ' ' + e['name']).lower()
            if any(b in t for b in bad):
                continue
            pts = sum(1 for pat in pats if re.search(pat, t))
            if pts:
                sc.append((pts, -len(e['id']), e['id']))
        return max(sc)[2] if sc else ''
    return dict(ok=True, entities=sorted(ents, key=lambda e: e['id'])[:600],
                grid=best([r'grid', r'import', r'retea|rețea|reteaua', r'power'], bad=('export', 'l1_', 'l2_', 'l3_', 'ct1', 'frequency', 'voltage')),
                pv=best([r'pv', r'solar|fotovolt', r'power'], bad=('pv1', 'pv2', 'pv3', 'pv4', 'today', 'total', 'voltage', 'current', 'battery', 'grid', 'forecast', 'solcast', 'helios', 'estimat', 'power_production', 'next_')))


def cfg_test(what):
    if what == 'ha':
        if not ha_ok():
            return dict(ok=False, msg='Home Assistant nu e configurat.')
        try:
            c, r = ha_req('GET', '/api/', timeout=6)
        except Exception as e:  # noqa
            return dict(ok=False, msg='Nu mă pot conecta: %s' % e)
        if c != 200:
            return dict(ok=False, msg='HA a răspuns %s (token invalid?).' % c)
        st = ha_state('binary_sensor.%s_status' % HA['prefix'])
        ble = 'ESP32 BLE conectat la mașină' if st and st.get('state') == 'on' else ('ESP32 găsit, dar nu e conectat la mașină' if st else 'entitățile BLE nu există (verifică prefixul)')
        return dict(ok=True, msg='Conectat la Home Assistant. %s.' % ble)
    if what == 'notify':
        return dict(ok=True, msg='Trimis.' if notify('test', '🔔 Test notificare', 'Notificările din aplicația Tesla funcționează.') else 'Salvat doar în istoric (nu e configurat webhook-ul).')
    return dict(ok=False, msg='necunoscut')


# ---------------------------------------------------------------- Profiler (flux live Fleet Telemetry: 200+ semnale, pe sesiuni scurte)
PF_ALL = ['Unknown', 'DriveRail', 'ChargeState', 'BmsFullchargecomplete', 'VehicleSpeed', 'Odometer', 'PackVoltage', 'PackCurrent', 'Soc', 'DCDCEnable', 'Gear', 'IsolationResistance', 'PedalPosition', 'BrakePedal', 'DiStateR', 'DiHeatsinkTR', 'DiAxleSpeedR', 'DiTorquemotor', 'DiStatorTempR', 'DiVBatR', 'DiMotorCurrentR', 'Location', 'GpsState', 'GpsHeading', 'NumBrickVoltageMax', 'BrickVoltageMax', 'NumBrickVoltageMin', 'BrickVoltageMin', 'NumModuleTempMax', 'ModuleTempMax', 'NumModuleTempMin', 'ModuleTempMin', 'RatedRange', 'Hvil', 'DCChargingEnergyIn', 'DCChargingPower', 'ACChargingEnergyIn', 'ACChargingPower', 'ChargeLimitSoc', 'FastChargerPresent', 'EstBatteryRange', 'IdealBatteryRange', 'BatteryLevel', 'TimeToFullCharge', 'ScheduledChargingStartTime', 'ScheduledChargingPending', 'ScheduledDepartureTime', 'PreconditioningEnabled', 'ScheduledChargingMode', 'ChargeAmps', 'ChargeEnableRequest', 'ChargerPhases', 'ChargePortColdWeatherMode', 'ChargeCurrentRequest', 'ChargeCurrentRequestMax', 'BatteryHeaterOn', 'NotEnoughPowerToHeat', 'SuperchargerSessionTripPlanner', 'DoorState', 'Locked', 'FdWindow', 'FpWindow', 'RdWindow', 'RpWindow', 'VehicleName', 'SentryMode', 'SpeedLimitMode', 'CurrentLimitMph', 'Version', 'TpmsPressureFl', 'TpmsPressureFr', 'TpmsPressureRl', 'TpmsPressureRr', 'SemitruckTpmsPressureRe1L0', 'SemitruckTpmsPressureRe1L1', 'SemitruckTpmsPressureRe1R0', 'SemitruckTpmsPressureRe1R1', 'SemitruckTpmsPressureRe2L0', 'SemitruckTpmsPressureRe2L1', 'SemitruckTpmsPressureRe2R0', 'SemitruckTpmsPressureRe2R1', 'TpmsLastSeenPressureTimeFl', 'TpmsLastSeenPressureTimeFr', 'TpmsLastSeenPressureTimeRl', 'TpmsLastSeenPressureTimeRr', 'InsideTemp', 'OutsideTemp', 'SeatHeaterLeft', 'SeatHeaterRight', 'SeatHeaterRearLeft', 'SeatHeaterRearRight', 'SeatHeaterRearCenter', 'AutoSeatClimateLeft', 'AutoSeatClimateRight', 'DriverSeatBelt', 'PassengerSeatBelt', 'DriverSeatOccupied', 'SemitruckPassengerSeatFoldPosition', 'LateralAcceleration', 'LongitudinalAcceleration', 'Deprecated_2', 'CruiseSetSpeed', 'LifetimeEnergyUsed', 'LifetimeEnergyUsedDrive', 'SemitruckTractorParkBrakeStatus', 'SemitruckTrailerParkBrakeStatus', 'BrakePedalPos', 'RouteLastUpdated', 'RouteLine', 'MilesToArrival', 'MinutesToArrival', 'OriginLocation', 'DestinationLocation', 'CarType', 'Trim', 'ExteriorColor', 'RoofColor', 'ChargePort', 'ChargePortLatch', 'Experimental_1', 'Experimental_2', 'Experimental_3', 'Experimental_4', 'GuestModeEnabled', 'PinToDriveEnabled', 'PairedPhoneKeyAndKeyFobQty', 'CruiseFollowDistance', 'AutomaticBlindSpotCamera', 'BlindSpotCollisionWarningChime', 'SpeedLimitWarning', 'ForwardCollisionWarning', 'LaneDepartureAvoidance', 'EmergencyLaneDepartureAvoidance', 'AutomaticEmergencyBrakingOff', 'LifetimeEnergyGainedRegen', 'DiStateF', 'DiStateREL', 'DiStateRER', 'DiHeatsinkTF', 'DiHeatsinkTREL', 'DiHeatsinkTRER', 'DiAxleSpeedF', 'DiAxleSpeedREL', 'DiAxleSpeedRER', 'DiSlaveTorqueCmd', 'DiTorqueActualR', 'DiTorqueActualF', 'DiTorqueActualREL', 'DiTorqueActualRER', 'DiStatorTempF', 'DiStatorTempREL', 'DiStatorTempRER', 'DiVBatF', 'DiVBatREL', 'DiVBatRER', 'DiMotorCurrentF', 'DiMotorCurrentREL', 'DiMotorCurrentRER', 'EnergyRemaining', 'ServiceMode', 'BMSState', 'GuestModeMobileAccessState', 'Deprecated_1', 'DestinationName', 'DiInverterTR', 'DiInverterTF', 'DiInverterTREL', 'DiInverterTRER', 'Experimental_5', 'Experimental_6', 'Experimental_7', 'Experimental_8', 'Experimental_9', 'Experimental_10', 'Experimental_11', 'Experimental_12', 'Experimental_13', 'Experimental_14', 'Experimental_15', 'DetailedChargeState', 'CabinOverheatProtectionMode', 'CabinOverheatProtectionTemperatureLimit', 'CenterDisplay', 'ChargePortDoorOpen', 'ChargerVoltage', 'ChargingCableType', 'ClimateKeeperMode', 'DefrostForPreconditioning', 'DefrostMode', 'EfficiencyPackage', 'EstimatedHoursToChargeTermination', 'EuropeVehicle', 'ExpectedEnergyPercentAtTripArrival', 'FastChargerType', 'HomelinkDeviceCount', 'HomelinkNearby', 'HvacACEnabled', 'HvacAutoMode', 'HvacFanSpeed', 'HvacFanStatus', 'HvacLeftTemperatureRequest', 'HvacPower', 'HvacRightTemperatureRequest', 'HvacSteeringWheelHeatAuto', 'HvacSteeringWheelHeatLevel', 'OffroadLightbarPresent', 'PowershareHoursLeft', 'PowershareInstantaneousPowerKW', 'PowershareStatus', 'PowershareStopReason', 'PowershareType', 'RearDisplayHvacEnabled', 'RearSeatHeaters', 'RemoteStartEnabled', 'RightHandDrive', 'RouteTrafficMinutesDelay', 'SoftwareUpdateDownloadPercentComplete', 'SoftwareUpdateExpectedDurationMinutes', 'SoftwareUpdateInstallationPercentComplete', 'SoftwareUpdateScheduledStartTime', 'SoftwareUpdateVersion', 'TonneauOpenPercent', 'TonneauPosition', 'TonneauTentMode', 'TpmsHardWarnings', 'TpmsSoftWarnings', 'ValetModeEnabled', 'WheelType', 'WiperHeatEnabled', 'LocatedAtHome', 'LocatedAtWork', 'LocatedAtFavorite', 'SettingDistanceUnit', 'SettingTemperatureUnit', 'Setting24HourTime', 'SettingTirePressureUnit', 'SettingChargeUnit', 'ClimateSeatCoolingFrontLeft', 'ClimateSeatCoolingFrontRight', 'LightsHazardsActive', 'LightsTurnSignal', 'LightsHighBeams', 'MediaPlaybackStatus', 'MediaPlaybackSource', 'MediaAudioVolume', 'MediaNowPlayingDuration', 'MediaNowPlayingElapsed', 'MediaNowPlayingArtist', 'MediaNowPlayingTitle', 'MediaNowPlayingAlbum', 'MediaNowPlayingStation', 'MediaAudioVolumeIncrement', 'MediaAudioVolumeMax', 'SunroofInstalled', 'SeatVentEnabled', 'RearDefrostEnabled', 'ChargeRateMilePerHour', 'Deprecated_3', 'MilesSinceReset', 'SelfDrivingMilesSinceReset', 'GpsAccuracyMeters', 'LifetimeEnergyChargedKwh', 'BrickSocMinPercent', 'NominalFullPackEnergyKwh', 'GradeEstimatePercent', 'MaxSpeedToReachDestinationMph', 'SoftwareUpdateAvailable', 'SoftwareUpdateInProgress', 'RemoteStartActive', 'SemiCruiseSpeedLimitMph', 'Cabin12vPortKeepOn', 'Cabin48vPortKeepOn']
PF_EXCLUDE = re.compile(r'^(Unknown|Experimental_|Deprecated_|Semitruck|Tonneau|Powershare|OffroadLightbar|Cabin12v|Cabin48v|SemiCruise|SuperchargerSessionTripPlanner)')
PF_CATS = [
    ('perf', re.compile(r'^(VehicleSpeed|Odometer|PedalPosition|BrakePedal|BrakePedalPos|Gear|Di[A-Z]\w*|LateralAcceleration|LongitudinalAcceleration|CruiseSetSpeed|CruiseFollowDistance|LifetimeEnergyUsed\w*|LifetimeEnergyGainedRegen|DriveRail|IsolationResistance|DCDCEnable|GradeEstimatePercent|SelfDrivingMilesSinceReset|MilesSinceReset|Hvil|EnergyRemaining)$')),
    ('charge', re.compile(r'(Charg|^Soc$|BatteryLevel|Brick|Module|BatteryHeater|NotEnough|Bms|^Pack|EstBattery|IdealBattery|RatedRange|NominalFull|TimeToFull|Scheduled|Preconditioning|FastCharger|EstimatedHoursToCharge|^DC|^AC)')),
    ('climate', re.compile(r'(Hvac|SeatHeater|SeatClimate|ClimateKeeper|CabinOverheat|Defrost|InsideTemp|OutsideTemp|SeatVent|ClimateSeatCooling|RearSeatHeaters|WiperHeat|RearDisplayHvac)')),
    ('body', re.compile(r'(Door|Locked|Window|ChargePort|Light|Sunroof|CenterDisplay|RemoteStart|Homelink|VehicleName|CarType|Trim|ExteriorColor|RoofColor|WheelType|EfficiencyPackage|RightHandDrive|EuropeVehicle|Version|Setting)')),
    ('safety', re.compile(r'(SentryMode|SeatBelt|SeatOccupied|Tpms|Collision|LaneDeparture|BlindSpot|AutomaticEmergency|SpeedLimit|CurrentLimit|GuestMode|PinToDrive|PairedPhone|ServiceMode|SoftwareUpdate|ValetMode)')),
    ('nav', re.compile(r'(Location|Gps|Route|Destination|ToArrival|Media|ExpectedEnergyPercent|MaxSpeedToReach|LocatedAt|Origin)')),
]
PF_PROFILES = {
    'performance': dict(ro='Performanță și condus', en='Performance & driving', cats=['perf']),
    'charging': dict(ro='Încărcare și baterie', en='Charging & battery', cats=['charge']),
    'climate': dict(ro='Climă', en='Climate', cats=['climate']),
    'body': dict(ro='Caroserie și lumini', en='Body & lighting', cats=['body']),
    'safety': dict(ro='Siguranță și securitate', en='Safety & security', cats=['safety']),
    'nav': dict(ro='Navigație și media', en='Navigation & media', cats=['nav']),
    'turbo': dict(ro='Turbo (tot)', en='Turbo (everything)', cats=['perf', 'charge', 'climate', 'body', 'safety', 'nav', 'other']),
}
MILES = {'VehicleSpeed', 'Odometer', 'RatedRange', 'IdealBatteryRange', 'EstBatteryRange', 'MilesSinceReset', 'SelfDrivingMilesSinceReset', 'MilesToArrival', 'CruiseSetSpeed',
         'CurrentLimitMph', 'ChargeRateMilePerHour', 'MaxSpeedToReachDestinationMph'}


def pf_cat(name):
    for c, rx in PF_CATS:
        if rx.search(name):
            return c
    return 'other'


def pf_unit(name):
    if name in MILES:
        return 'km/h' if name in ('VehicleSpeed', 'CruiseSetSpeed', 'CurrentLimitMph', 'MaxSpeedToReachDestinationMph', 'ChargeRateMilePerHour') else 'km'
    for rx, u in ((r'Temp|Heatsink', '°C'), (r'Voltage|VBat', 'V'), (r'Current|Amps', 'A'), (r'Pressure', 'bar'), (r'Kwh|EnergyIn|EnergyUsed|EnergyGained|EnergyRemaining', 'kWh'),
                  (r'Percent|^Soc$|BatteryLevel|ChargeLimitSoc|SocMin', '%'), (r'Power', 'kW'), (r'Acceleration', 'm/s²'), (r'Torque', 'Nm'), (r'Heading', '°'), (r'Resistance', 'kΩ'), (r'Minutes', 'min')):
        if re.search(rx, name):
            return u
    return ''


PF_META = {n: dict(cat=pf_cat(n), unit=pf_unit(n), miles=n in MILES) for n in PF_ALL if not PF_EXCLUDE.search(n)}
PF = dict(values={}, hist={}, log=collections.deque(maxlen=300000), session=None, clients=set(), lock=threading.Lock(), last_rx=0.0, sim=False, conn=None, diag=(0, None))
PFILE = DATA_DIR + '/profiler.json'


def pf_fields(profile):
    cats = PF_PROFILES[profile]['cats']
    return [n for n, m in PF_META.items() if m['cat'] in cats]


def pf_norm(v):
    """Valoare decodata din record -> (numar | text). Obiecte cu un singur camp se aplatizeaza (ex. SentryMode)."""
    if isinstance(v, dict):
        if len(v) == 1:
            v = next(iter(v.values()))                                   # {"booleanValue": true} / {"doorValue": {...}} -> continutul
        if isinstance(v, dict):
            return {k: (round(x, 6) if isinstance(x, float) else x) for k, x in v.items()}
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return round(v, 4) if isinstance(v, float) else v
    return str(v)


TEL_VIN_CAR = {}                                                   # VIN -> id masina (retinut: nu interogam baza la fiecare inregistrare)
TEL_WINDOWS = {}                                                  # (masina, camp) -> inchis? (pentru "un geam e deschis" = oricare dintre cele 4)


def tel_live(vin, updates):
    """Campurile de inchideri/incuietori trimise de masina prin Fleet Telemetry (DoorState, Locked, *Window) -> starea live, pe acelasi drum ca MQTT.
    Masina le trimite singura, oriunde ar fi si cat ar dormi TeslaMate (care atunci nu o mai intreaba)."""
    car = TEL_VIN_CAR.get(vin)
    if car is None:
        car = next((c for c in list(LIVE) if vin_for(c) == vin), None) if vin else (next(iter(LIVE), None) if len(LIVE) == 1 else None)
        if car is None:
            return
        if vin:
            TEL_VIN_CAR[vin] = car
    norm = lambda s: str(s).lower().replace('_', '')
    for k, v in updates:
        if k == 'Locked' and isinstance(v, bool):
            live_apply(car, 'locked', v)
        elif k == 'DoorState' and isinstance(v, dict):
            d = {norm(a): b for a, b in v.items() if isinstance(b, bool)}
            doors = [d[x] for x in ('driverfront', 'driverrear', 'passengerfront', 'passengerrear') if x in d]
            if doors:
                live_apply(car, 'doors_open', any(doors))
            if 'trunkfront' in d:
                live_apply(car, 'frunk_open', d['trunkfront'])
            if 'trunkrear' in d:
                live_apply(car, 'trunk_open', d['trunkrear'])
        elif k in ('FdWindow', 'FpWindow', 'RdWindow', 'RpWindow') and isinstance(v, str):
            s = norm(v)
            if 'unknown' in s:
                continue
            TEL_WINDOWS[(car, k)] = 'closed' in s
            if all((car, w) in TEL_WINDOWS for w in ('FdWindow', 'FpWindow', 'RdWindow', 'RpWindow')):
                live_apply(car, 'windows_open', not all(TEL_WINDOWS[(car, w)] for w in ('FdWindow', 'FpWindow', 'RdWindow', 'RpWindow')))


TEL_LIVE_FIELDS = ('DoorState', 'Locked', 'FdWindow', 'FpWindow', 'RdWindow', 'RpWindow')


def pf_ingest(records):
    now = time.time()
    batch = {}
    tel = {}
    with PF['lock']:
        for rec in records[:200]:
            if isinstance(rec, dict) and isinstance(rec.get('conn'), dict):
                PF['conn'] = dict(status=rec['conn'].get('Status'), net=rec['conn'].get('NetworkInterface'), at=now)
                continue
            d = rec.get('data') if isinstance(rec, dict) else None
            if not isinstance(d, dict):
                continue
            for k, v in d.items():
                if k in ('CreatedAt', 'IsResend', 'Vin') or k not in PF_META:
                    continue
                v = pf_norm(v)
                if k in TEL_LIVE_FIELDS:
                    tel.setdefault(str(d.get('Vin') or ''), []).append((k, v))
                if PF_META[k]['miles'] and isinstance(v, (int, float)):
                    v = round(v * 1.609344, 2)
                PF['values'][k] = (v, now)
                batch[k] = v
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    h = PF['hist'].setdefault(k, [])
                    h.append((now, v))
                    del h[:-600]
                if PF['session']:
                    PF['log'].append((now, k, v))                # deque cu maxlen: taierea e O(1)
        PF['last_rx'] = now
    for vin, ups in tel.items():
        try:
            tel_live(vin, ups)
        except Exception as e:  # noqa
            log('telemetrie -> live:', e, flush=True)
    if batch:
        pf_broadcast(dict(t=now, d=batch))


def pf_broadcast(msg):
    for q_ in list(PF['clients']):
        try:
            q_.put_nowait(msg)
        except queue.Full:
            pass


def pf_status():
    se = PF['session']
    return dict(active=bool(se), session=se, last_rx=PF['last_rx'], conn=PF['conn'], sim=PF['sim'], fields=len(PF_META),
                profiles={k: dict(ro=v['ro'], en=v['en'], count=len(pf_fields(k))) for k, v in PF_PROFILES.items()})


def pf_session_load():
    PF['session'] = (jload(PFILE, {}) or {}).get('session')


def pf_session_save():
    try:
        jsave(PFILE, dict(session=PF['session']))
    except Exception as e:  # noqa
        log('profiler save:', e, flush=True)


def pf_cfg_get(vin):
    c, r = vehicle_call(vin, 'fleet_telemetry_config', method='GET')
    resp = r.get('response') or {}
    return (resp.get('config') if c == 200 else None), resp, c


def pf_cfg_post(vin, cfg):
    cfg = {k: v for k, v in cfg.items() if k not in ('iss', 'aud')}
    c, r = http(FL['proxy'] + '/api/1/vehicles/fleet_telemetry_config', {'config': cfg, 'vins': [vin]}, headers={'Authorization': 'Bearer ' + access_token()}, ctx=proxy_ctx(), timeout=40)
    resp = r.get('response') or {}
    ok = c == 200 and resp.get('updated_vehicles', 0) >= 1
    return ok, (resp.get('skipped_vehicles') or r.get('error') or r.get('raw') or resp or r)


def pf_post_safe(vin, cfg, base):
    """Trimite configuratia; daca apelul expira/esueaza (nu stim daca Tesla a aplicat-o), incearca sa readuca configuratia de baza."""
    try:
        return pf_cfg_post(vin, cfg)
    except Exception as e:  # noqa
        try:
            pf_cfg_post(vin, base)
        except Exception as e2:  # noqa
            log('profiler: revenirea dupa eroare a esuat:', e2, flush=True)
        raise RuntimeError('Tesla nu a răspuns la timp (%s); am încercat să revin la configurația de bază.' % e)


def pf_start(car, profile, minutes):
    if profile not in PF_PROFILES:
        raise ValueError('profil necunoscut')
    minutes = int(max(1, min(minutes, 30)))
    if PF['session']:
        raise RuntimeError('Există deja o sesiune activă — oprește-o mai întâi.')
    if not (PF['sim'] or DEMO_ONLY):
        hc = has_cars()
        if hc is None:
            raise RuntimeError('Baza de date TeslaMate nu răspunde — nu pornesc profilerul.')
        if not hc:
            PF['sim'] = True
    names = pf_fields(profile)
    if PF['sim'] or DEMO_ONLY:
        PF['session'] = dict(profile=profile, started=time.time(), until=time.time() + minutes * 60, fields=len(names), sim=True)
        PF['values'].clear(); PF['hist'].clear(); PF['log'].clear()
        threading.Thread(target=pf_simulate, args=(profile,), daemon=True).start()
        pf_broadcast(dict(status=pf_status()))
        return dict(ok=True, sim=True, fields=len(names))
    vin = vin_for(car)
    if not vin:
        raise RuntimeError('Nu există VIN în TeslaMate.')
    base, resp, code = pf_cfg_get(vin)
    if not base:
        raise RuntimeError('Nu pot citi configurația de telemetrie a mașinii (%s). Telemetria trebuie configurată întâi (hostname/ca).' % code)
    prof_like = sum(1 for f in ((base or {}).get('fields') or {}).values() if isinstance(f, dict) and f.get('interval_seconds') == 1) >= 40
    have_base = os.path.exists(DATA_DIR + '/profiler_base.json')
    if prof_like and not have_base:
        raise RuntimeError('Mașina pare să fie încă pe configurația profilerului, iar configurația de bază (Sentry) nu mai există. Nu pornesc o sesiune nouă: restabilește telemetria din serverul de telemetrie.')
    if not (prof_like and have_base):                  # daca masina e inca pe config. de profiler dintr-o sesiune nerestaurata, pastram baza veche
        try:
            jsave(DATA_DIR + '/profiler_base.json', base)    # configuratia de dinainte (Sentry), la care se revine la oprire
        except Exception as e:  # noqa
            log('profiler base save:', e, flush=True)
    fields = {n: {'interval_seconds': 1} for n in names}
    fields['SentryMode'] = {'interval_seconds': 1}                      # alerta Sentry ramane activa
    dropped = []
    for _ in range(80):                     # Tesla refuza campurile problematice pe rand: corectam automat (delta minim / scope lipsa / camp neacceptat)
        ok, info = pf_post_safe(vin, dict(base, fields=fields), base)
        if ok:
            break
        msg = info if isinstance(info, str) else json.dumps(info)
        m = re.match(r'^"?(\w+) requires minimum delta', msg)
        if m and m.group(1) in fields:
            fields[m.group(1)]['minimum_delta'] = 1
            continue
        if 'missing scopes vehicle_location' in msg:
            loc = [n for n in fields if re.search(r'Location|Gps|Route|Destination|Origin|LocatedAt|GradeEstimate|MinutesToArrival|MilesToArrival', n)]
            if loc:
                for n in loc:
                    fields.pop(n)
                dropped += loc
                continue
        m = re.match(r'^"?(\w+) (is not|not supported|unsupported|invalid)', msg)
        if m and m.group(1) in fields and m.group(1) != 'SentryMode':
            fields.pop(m.group(1))
            dropped.append(m.group(1))
            continue
        raise RuntimeError('Tesla a refuzat configurația: %s' % msg[:400])
    else:
        raise RuntimeError('Tesla a refuzat configurația (prea multe corecturi).')
    asleep = LIVE.get(car, {}).get('state') in ('asleep', 'offline', None)
    PF['session'] = dict(profile=profile, started=time.time(), until=time.time() + minutes * 60, fields=len(fields), vin_tail=vin[-4:], dropped=dropped[:60], waking=asleep)
    if asleep:                                  # masina adormita nu aplica configuratia si nu trimite nimic: o trezim (BLE sau Fleet), ca Tessie
        def wake():
            try:
                run_command(car, 'wake')
            except Exception as e:  # noqa
                log('profiler wake:', e, flush=True)
            if PF['session']:
                PF['session']['waking'] = False
        threading.Thread(target=wake, daemon=True).start()
    PF['values'].clear(); PF['hist'].clear(); PF['log'].clear()
    pf_session_save()
    pf_broadcast(dict(status=pf_status()))
    return dict(ok=True, fields=len(fields))


def pf_stop(car=1, reason='', force=False):
    se = PF['session']
    if not se:
        return dict(ok=True, was_active=False)
    if force and not se.get('sim'):                    # iesire de urgenta cand restaurarea nu reuseste: inchide sesiunea FARA sa mai atinga masina
        PF['session'] = None
        pf_session_save()
        pf_broadcast(dict(status=pf_status()))
        return dict(ok=True, was_active=True, warning='Sesiunea a fost închisă fără să restabilesc configurația mașinii. Verifică telemetria (Sentry) din serverul de telemetrie.')
    err = ''
    if not se.get('sim'):
        try:
            vin = vin_for(car)
            base = jload(DATA_DIR + '/profiler_base.json', None)
            if not base:
                raise RuntimeError('lipseste configuratia de baza a telemetriei (profiler_base.json)')
            ok, info = pf_cfg_post(vin, base)
            if not ok:
                err = 'Revenirea la configurația Sentry a eșuat: %s' % json.dumps(info)[:300]
        except Exception as e:  # noqa
            err = 'Revenirea la configurația Sentry a eșuat: %s' % e
    if not err:
        PF['session'] = None
        pf_session_save()
    PF['sim'] = False if not DEMO_ONLY and has_cars() else PF['sim']
    pf_broadcast(dict(status=pf_status()))
    return dict(ok=not err, reason=err, was_active=True)


def pf_watch():
    """Opreste automat sesiunea la expirare (si readuce configuratia Sentry). Daca restaurarea esueaza, reincearca cu pauze tot mai mari (max. 30 min)."""
    fails, nxt = 0, 0.0
    while True:
        time.sleep(15)
        try:
            se = PF['session']
            if not se:
                fails, nxt = 0, 0.0
            elif time.time() > se['until'] and time.time() >= nxt:
                log('profiler: auto-stop', flush=True)
                r = pf_stop(1, 'timp expirat')
                if r.get('ok'):
                    fails, nxt = 0, 0.0
                else:
                    fails += 1
                    nxt = time.time() + min(1800, 30 * 2 ** fails)
                    if PF['session']:
                        PF['session']['stop_fails'] = fails
                    log('profiler: auto-stop esuat (%d): %s' % (fails, r.get('reason')), flush=True)
        except Exception as e:  # noqa
            log('profiler watch:', e, flush=True)


def pf_simulate(profile):
    """Date fictive pentru demo / fara masina: mers aleator pe campurile profilului."""
    r = random.Random(11)
    names = pf_fields(profile)
    state = {n: r.uniform(20, 80) for n in names}
    while PF['session'] and PF['session'].get('sim'):
        recs = {}
        for n in names:
            m = PF_META[n]
            state[n] += r.uniform(-1.2, 1.2)
            recs[n] = (round(state[n], 2) if m['unit'] else ('Armed' if r.random() > .5 else 'Off')) if not m['unit'] == '' or n.endswith('State') else r.choice(['On', 'Off', 'Idle'])
        pf_ingest([dict(data=recs)])
        time.sleep(1)


def pf_csv():
    import io, csv
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(['time_utc', 'field', 'value'])
    for t, k, v in PF['log']:
        w.writerow([dt.datetime.utcfromtimestamp(t).isoformat(timespec='milliseconds'), k, v])
    return out.getvalue()


# ---------------------------------------------------------------- import din Tessie (vezi importer.py)
IMP = dict(running=False, phase='', done=0, total=0, result=None, error='', dry=False, started=0)
ILOCK = threading.Lock()


def imp_conn():
    import psycopg2
    return psycopg2.connect(**DB)


def imp_action(car, body):
    import importer
    token = cget('tessie_token', 'TESSIE_TOKEN')
    act = body.get('action')
    if act == 'undo':
        if not (os.path.isfile(importer.LEDGER) or os.path.isfile(importer.LEDGER + '.pending')):
            return dict(ok=False, reason='Nu există niciun import de anulat.')
        with ILOCK:
            if IMP['running']:
                return dict(ok=False, reason='Un import rulează acum; așteaptă să se termine.')
            cn = imp_conn()
            try:
                return dict(ok=True, undone=importer.undo(cn))
            finally:
                cn.close()
    if not token:
        return dict(ok=False, reason='Salvează mai întâi tokenul Tessie în Setări.')
    if act == 'vehicles':
        try:
            vs = importer.vehicles(token)
        except importer.TessieError as e:
            return dict(ok=False, reason=str(e))
        return dict(ok=True, vehicles=[dict(vin_tail=v['vin'][-6:], name=v['name'], match=(v['vin'] == vin_for(car))) for v in vs])
    vin = vin_for(car)
    if not vin:
        return dict(ok=False, reason='Nu există VIN în TeslaMate.')
    mode = 'older' if body.get('mode') == 'older' else 'gaps'
    if act == 'preview':
        cn = imp_conn()
        try:
            r = importer.preview(cn, token, vin, car, mode=mode)
        except importer.TessieError as e:
            return dict(ok=False, reason=str(e))
        finally:
            cn.close()
        r['already'] = os.path.isfile(importer.LEDGER) or os.path.isfile(importer.LEDGER + '.pending')
        return r
    if act in ('dry', 'run'):
        if act == 'run' and not body.get('confirm'):
            return dict(ok=False, reason='Confirmă importul.')
        with ILOCK:
            if IMP['running']:
                return dict(ok=False, reason='Un import rulează deja.')
            IMP.update(running=True, phase='Pornesc…', done=0, total=0, result=None, error='', dry=(act == 'dry'), started=time.time())

        def work():
            cn = None
            try:
                cn = imp_conn()
                IMP['result'] = importer.run(cn, token, vin, car, IMP, dry_run=(act == 'dry'), mode=mode)
            except Exception as e:  # noqa
                if cn:
                    cn.rollback()
                IMP['error'] = str(e)[:400]
                log('import tessie:', e, flush=True)
            finally:
                if cn:
                    cn.close()
                IMP['running'] = False
        threading.Thread(target=work, daemon=True).start()
        return dict(ok=True, started=True)
    return dict(ok=False, reason='acțiune necunoscută')


# ---------------------------------------------------------------- notificari (cablu, incarcare gata, usi) -> telefon prin webhook Home Assistant + istoric in aplicatie
NFILE = DATA_DIR + '/notify.json'
NHOOK = os.environ.get('NOTIFY_WEBHOOK', '')
APPURL = os.environ.get('APP_URL', '').rstrip('/')
KIND_ROUTE = dict(plugged='#/charges', charge_done='#/charges', door='#/car', update='#/car', low_batt='#/car', rule='#/auto', live='#/car', test='#/notifications', app_update='#/settings')


KIND_ACTIONS = {           # butoane pe notificarile obisnuite (Live Activity nu are butoane); executate de automatizarea din HA prin ESP32 BLE
    'plugged': [('TESLA_CHARGE_START', 'Pornește încărcarea'), ('TESLA_CHARGE_STOP', 'Oprește încărcarea'), ('TESLA_CABLE_RELEASE', 'Deblochează cablul')],
    'charge_done': [('TESLA_CABLE_RELEASE', 'Deblochează cablul'), ('TESLA_CLIMATE_ON', 'Pornește clima')],
    'door': [('TESLA_LOCK', 'Încuie mașina')],
}


def app_link(kind='live'):
    return (APPURL + '/' + KIND_ROUTE.get(kind, '#/car')) if APPURL else None
NDEFAULT = dict(plugged=True, charge_done=True, door=True, update=True, low_batt=True, live=True, live_drive=False, actions=True, app_update=True, away_only=False)
AWAY_KINDS = ('plugged', 'door')                                    # cu "doar in afara casei": notificarile astea (si cardurile 'open'/'plugged') nu se trimit cat masina e acasa


def at_home(car=None):
    lv = LIVE.get(car if car is not None else next(iter(LIVE), None), {}) or {}
    rx = 'acas|home'
    try:
        rx = ALERTS.cfg()['not_plugged_night']['home']
    except Exception:  # noqa
        pass
    return bool(re.search(rx, str(lv.get('geofence') or ''), re.I))
EVENTS = []          # cele mai noi primele, max 60
NLOCK = threading.Lock()
LAST_SENT = {}


def nset_load():
    try:
        return dict(NDEFAULT, **{k: bool(v) for k, v in (jload(NFILE, {}) or {}).items() if k in NDEFAULT})
    except Exception:
        return dict(NDEFAULT)


def nset_save(d):
    try:
        jsave(NFILE, d)
    except Exception as e:  # noqa
        log('notify save:', e, flush=True)


def notify(kind, title, msg, data=None, log=True):
    ev = dict(t=dt.datetime.utcnow().replace(microsecond=0).isoformat(), kind=kind, title=title, msg=msg)
    if log:
        with NLOCK:
            EVENTS.insert(0, ev)
            del EVENTS[60:]
    if kind in AWAY_KINDS and nset_load().get('away_only') and at_home():
        return False                                                        # acasa: nu trimitem (ramane in istoricul din aplicatie)
    if NHOOK:
        payload = dict(title=title, message=msg, kind=kind)
        if data is None:
            data = {}
            if app_link(kind):
                data['url'] = app_link(kind)                                # atingerea notificarii deschide aplicatia
            if kind in STATE_KINDS:
                data['tag'] = 'tesla_' + kind                                # poate fi inlocuita si stearsa automat cand evenimentul a trecut
            if KIND_ACTIONS.get(kind) and nset_load().get('actions', True):
                data['actions'] = [dict(action=a, title=t) for a, t in KIND_ACTIONS[kind]]
                data['tag'] = 'tesla_' + kind
        if data:
            payload['data'] = data
        threading.Thread(target=lambda: http(NHOOK, payload, timeout=10), daemon=True).start()
    for sink in list(NOTIFY_SINKS):
        threading.Thread(target=sink, args=(kind, title, msg, data), daemon=True).start()
    return bool(NHOOK) or bool(NOTIFY_SINKS)


def _once(kind, secs=90):
    now = time.time()
    if now - LAST_SENT.get(kind, 0) < secs:
        return False
    LAST_SENT[kind] = now
    return True


OPEN_KEYS = {'doors_open': 'o ușă', 'trunk_open': 'portbagajul', 'frunk_open': 'frunk-ul', 'windows_open': 'un geam'}


STATE_KINDS = ('plugged', 'charge_done', 'door', 'low_batt', 'update')       # notificari care descriu o stare: dispar singure cand starea trece


def notify_clear_check(car, key, new):
    """Sterge de pe telefon notificarile al caror eveniment a trecut: cablu scos, usa inchisa, baterie refacuta, update instalat."""
    lv = LIVE.get(car, {})
    if key == 'plugged_in' and new is False:
        notify_clear('tesla_plugged', 'plugged')
        notify_clear('tesla_charge_done', 'charge_done')
    elif key in OPEN_KEYS and new is False and not any(lv.get(k) is True for k in OPEN_KEYS):
        notify_clear('tesla_door', 'door')
    elif key == 'battery_level' and isinstance(new, (int, float)) and new >= 20:
        notify_clear('tesla_low_batt', 'low_batt')
    elif key == 'update_available' and new is False:
        notify_clear('tesla_update', 'update')
    if key == 'plugged_in' and new is True:
        notify_clear('tesla_low_batt', 'low_batt')


def notify_check(car, key, old, new):
    if key in ('charging_state', 'plugged_in', 'battery_level', 'shift_state', 'doors_open', 'trunk_open', 'frunk_open', 'windows_open', 'locked', 'charge_limit_soc', 'time_to_full_charge'):
        la_poke(car)
    if old is None or old == new:
        return
    notify_clear_check(car, key, new)
    lv = LIVE.get(car, {})
    nm = lv.get('display_name') or 'Tesla'
    st = nset_load()
    soc = lv.get('battery_level')
    if key == 'plugged_in' and new is True and st['plugged'] and _once('plugged'):
        notify('plugged', '🔌 Cablu conectat', '%s: cablul a fost conectat%s.' % (nm, ' (baterie %s%%)' % soc if soc is not None else ''))
    elif key == 'charging_state' and new == 'Complete' and st['charge_done'] and _once('charge_done', 600):
        notify('charge_done', '🔋 Încărcare terminată', '%s: baterie %s%%%s.' % (nm, soc if soc is not None else '?', ', limita %s%%' % lv['charge_limit_soc'] if lv.get('charge_limit_soc') else ''))
    elif key == 'update_available' and new is True and st['update'] and _once('update', 6 * 3600):
        notify('update', '⬇️ Update software disponibil', '%s: versiune nouă %s.' % (nm, lv.get('update_version') or ''))
    elif key == 'battery_level' and isinstance(new, (int, float)) and 1 <= new < 20 <= (old or 0) and st['low_batt'] and not lv.get('plugged_in') and lv.get('shift_state') in (None, 'P') and _once('low_batt', 12 * 3600):
        notify('low_batt', '🪫 Baterie scăzută', '%s: baterie %s%% și nu e conectată la priză.' % (nm, new))
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



# ---------------------------------------------------------------- automatizari (reguli salvate in /data/rules.json)
RFILE = DATA_DIR + '/rules.json'
RULE_TYPES = ('arrive_gate', 'depart_climate', 'plug_limit')
RLOG = []            # ultimele executii
RLOCK = threading.Lock()


def rules_load():
    r = jload(RFILE, [])
    return r if isinstance(r, list) else []


def rules_save(rs):
    jsave(RFILE, rs)


def rule_log(msg, ok=True):
    with RLOCK:
        RLOG.insert(0, dict(t=dt.datetime.utcnow().replace(microsecond=0).isoformat(), msg=msg, ok=ok))
        del RLOG[40:]
    notify('rule', '⚙️ Automatizare', msg)


def rule_exec(car, rule, name, arg=None):
    def go():
        CTX.actor = 'rule:%s' % (rule.get('name') or rule.get('id') or rule.get('type'))
        try:
            r = run_command(car, name, arg)
            rule_log('%s: %s %s%s' % (rule.get('name') or rule['type'], name, 'OK' if r.get('ok') else 'EȘUAT', ' (BLE)' if r.get('via') == 'ble' else ''), bool(r.get('ok')))
        except Exception as e:  # noqa
            rule_log('%s: %s eșuat - %s' % (rule.get('name') or rule['type'], name, e), False)
    threading.Thread(target=go, daemon=True).start()


def rules_check(car, key, old, new, known=True):
    """Evenimente MQTT -> reguli de tip eveniment. `known` = valoarea veche chiar a fost vazuta (nu e primul mesaj dupa repornire).
    Fereastra anti-repetare (_once) se consuma doar cand regula chiar se potriveste, nu la orice mesaj MQTT."""
    if old == new or not known:
        return
    lv = LIVE.get(car, {})
    for r in rules_load():
        if not r.get('enabled'):
            continue
        t = r.get('type')
        if t == 'arrive_gate' and key == 'geofence' and str(new) == str(r.get('geofence')) and old != new:
            if _once('rule:%s' % r['id'], 600):
                rule_exec(car, r, 'homelink')
        elif t == 'plug_limit' and key == 'plugged_in' and new is True and (not r.get('geofence') or str(lv.get('geofence')) == str(r.get('geofence'))):
            if _once('rule:%s' % r['id'], 600):
                rule_exec(car, r, 'charge_limit', int(r.get('limit', 80)))


def rules_clock():
    """Reguli cu ora (clima inainte de plecare): verificate la fiecare 30 s."""
    last = {}
    tz = None
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(os.environ.get('TZ', 'UTC'))
    except Exception:
        pass
    while True:
        time.sleep(30)
        try:
            now = dt.datetime.now(tz) if tz else dt.datetime.now()
            for r in rules_load():
                if r.get('enabled') and r.get('type') == 'depart_climate':
                    days = r.get('days') or 'ALL'
                    wd = now.weekday()
                    if days == 'WEEKDAYS' and wd > 4 or days == 'WEEKEND' and wd < 5:
                        continue
                    if now.strftime('%H:%M') == r.get('time') and last.get(r['id']) != now.strftime('%Y-%m-%d'):
                        last[r['id']] = now.strftime('%Y-%m-%d')
                        for c in list(LIVE):
                            rule_exec(c, r, 'climate_on')
        except Exception as e:  # noqa
            log('rules clock:', e, flush=True)


def rule_clean(b):
    t = b.get('type')
    if t not in RULE_TYPES:
        raise ValueError('tip invalid')
    r = dict(id=secrets.token_hex(4), type=t, enabled=True, name=str(b.get('name') or '')[:60])
    if t in ('arrive_gate', 'plug_limit'):
        r['geofence'] = str(b.get('geofence') or '')[:80]
        if t == 'arrive_gate' and not r['geofence']:
            raise ValueError('alege locul (geofence)')
    if t == 'plug_limit':
        r['limit'] = int(max(50, min(100, float(b.get('limit', 80)))))
    if t == 'depart_climate':
        hh = str(b.get('time') or '07:30')
        if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', hh):
            raise ValueError('ora invalida')
        r['time'] = hh
        r['days'] = b.get('days') if b.get('days') in ('ALL', 'WEEKDAYS', 'WEEKEND') else 'ALL'
    return r


# ---------------------------------------------------------------- Live Activities iOS (prin webhook HA -> notify.mobile_app_*: live_update + tag)
LA_TAG = 'tesla_status'
SUP = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')
LA_CLEAR_GAP = 2.0                                                  # pauza intre inchiderea cardului vechi si pornirea celui nou (secunde)
LA = dict(kind='unknown', sent=0.0, soc=None, since=0.0, timer=None)       # 'unknown' = dupa repornire nu stim ce arata telefonul: daca nu mai e nimic de aratat, il stergem o data


def notify_clear(tag, kind='clear'):
    """Cere telefonului sa stearga notificarea cu acest tag (automatizarea din HA o trece la clear_notification)."""
    if NHOOK:
        threading.Thread(target=lambda: http(NHOOK, dict(clear=True, tag=tag, kind=kind), timeout=10), daemon=True).start()


def la_clear():
    notify_clear(LA_TAG, 'live')


def la_payload(car):
    """Starea curenta -> (tip, titlu, mesaj, data pentru Live Activity) sau None cand nu e nimic de aratat."""
    lv = LIVE.get(car, {})
    st = nset_load()
    nm = lv.get('display_name') or 'Tesla'
    soc = lv.get('battery_level')
    lim = lv.get('charge_limit_soc') or 100
    base = dict(tag=LA_TAG, live_update=True)
    if app_link('live'):
        base['url'] = app_link('live')
    if soc is None:
        return None
    shift = lv.get('shift_state')
    opened = [w for k, w in OPEN_KEYS.items() if lv.get(k) is True]
    quiet_home = bool(st.get('away_only')) and at_home(car)               # "doar in afara casei": fara carduri 'deschis' / 'conectata' acasa
    if opened and shift in (None, 'P') and lv.get('locked') is not False and not quiet_home:
        return 'open', 'Deschis', opened[0].capitalize(), dict(base, critical_text='Deschis', notification_icon='mdi:car-door', notification_icon_color='#FFB15C', progress=soc, progress_max=100, progress_bar_color='#FFB15C')
    cs = lv.get('charging_state')
    if cs == 'Charging':
        tl = lv.get('time_to_full_charge') or 0
        kwf = float(lv.get('charger_power') or 0)                  # TeslaMate da kW intregi: rafinam cu tensiune x curent (1 sau 3 faze, cea mai apropiata de valoarea raportata)
        v_, a_ = lv.get('charger_voltage'), lv.get('charger_actual_current')
        if v_ and a_:
            kwf = min((v_ * a_ * ph / 1000.0 for ph in (1, 3)), key=lambda x: abs(x - kwf))
        kw = ('%.1f' % kwf).replace('.', ',')
        rest = ('%d h %02d min' % (int(tl), int(tl % 1 * 60))) if tl >= 1 else ('%d min' % max(1, round(tl * 60))) if tl else ''
        d = dict(base, critical_text=rest or '%s%%' % soc, notification_icon='mdi:ev-station', notification_icon_color='#4CC2A0', progress=soc, progress_max=max(lim, soc + 1), progress_bar_color='#4CC2A0',
                 background_color='#0B0D10', text_color='#FFFFFF')
        added = lv.get('charge_energy_added')
        parts = [('%s rămase' % rest) if rest else 'Se încarcă']
        if added:
            parts.append('+%s kWh' % ('%.1f' % float(added)).replace('.', ','))
        return 'charge', '%s%% · %s kW' % (soc, kw), ' · '.join(parts), d
    if cs == 'Complete' and lv.get('plugged_in'):
        return 'complete', 'Încărcare terminată', '%s%%' % soc, dict(base, critical_text='%s%%' % soc, notification_icon='mdi:battery-check', notification_icon_color='#4CC2A0', progress=soc, progress_max=100, progress_bar_color='#4CC2A0')
    if st.get('live_drive') and shift in ('D', 'R', 'N'):
        v = lv.get('speed') or 0
        return 'drive', 'În mers', '%d km/h' % round(v), dict(base, critical_text='%d km/h' % round(v), notification_icon='mdi:car', notification_icon_color='#7AA8FF', progress=soc, progress_max=100, progress_bar_color='#7AA8FF', silent=True)
    if lv.get('plugged_in') and cs in ('Stopped', 'NoPower', 'Starting', None, 'Disconnected') and shift in (None, 'P') and not quiet_home:
        return 'plugged', 'Conectată', '%s%%' % soc, dict(base, critical_text='%s%%' % soc, notification_icon='mdi:ev-plug-type2', notification_icon_color='#8F99A4', progress=soc, progress_max=100, progress_bar_color='#8F99A4')
    return None


def la_sync(car=1):
    """Trimite/actualizeaza/inchide Live Activity-ul in functie de starea masinii (apelat dupa evenimente MQTT si periodic)."""
    st = nset_load()
    if not NHOOK:
        return
    if not st.get('live'):                                          # oprit din setari cat timp un card era afisat: il sterg
        if LA['kind'] not in (None, 'cleared'):
            la_clear()
            LA.update(kind=None, soc=None)
        return
    now = time.time()
    pl = la_payload(car)
    if pl is None:
        if LA['kind'] not in (None, 'cleared'):                    # inclusiv 'unknown' (dupa repornire)
            la_clear()
        LA.update(kind=None, soc=None)
        return
    kind, title, msg, data = pl
    soc = LIVE.get(car, {}).get('battery_level')
    if kind == 'complete' and LA['kind'] == 'complete' and now - LA['since'] > 900:       # dupa 15 min incheie cardul "terminat"
        la_clear()
        LA.update(kind='cleared', soc=None)
        return
    if LA['kind'] == 'cleared' and kind == 'complete':
        return
    changed = kind != LA['kind']
    min_gap = 55 if kind == 'drive' else 90
    if changed or (soc != LA['soc'] and now - LA['sent'] > min_gap) or (kind == 'charge' and now - LA['sent'] > 120) or (kind == 'drive' and now - LA['sent'] > 240):
        if changed:
            LA['since'] = now
            if LA['kind'] in (None, 'cleared', 'unknown'):
                # Pornire "din nimic": iOS poate tine un card vechi cu acelasi tag (jeton pierdut) si atunci nici actualizarea, nici cardul nou nu apar. Il inchidem intai (nu consuma din bugetul de pornire).
                try:
                    http(NHOOK, dict(clear=True, tag=LA_TAG, kind='live'), timeout=10)
                    time.sleep(LA_CLEAR_GAP)
                except Exception as e:  # noqa
                    log('live activity clear:', e, flush=True)
        LA.update(kind=kind, sent=now, soc=soc)
        notify('live', title, msg, data, log=False)


def la_poke(car):
    """Debounce: dupa un eveniment MQTT asteapta 4 s (sa se adune mai multe campuri) si abia apoi sincronizeaza."""
    if LA['timer']:
        return

    def go():
        LA['timer'] = None
        try:
            la_sync(car)
        except Exception as e:  # noqa
            log('live activity:', e, flush=True)
    LA['timer'] = threading.Timer(4.0, go)
    LA['timer'].daemon = True
    LA['timer'].start()


def notify_reconcile(car):
    """O data dupa pornire: sterge de pe telefon notificarile de stare ramase de dinainte (repornire, cablu scos cat aplicatia era oprita etc.), daca starea lor nu mai e adevarata."""
    lv = LIVE.get(car, {})
    if not lv:
        return
    if lv.get('plugged_in') is False:
        notify_clear('tesla_plugged', 'plugged')
        notify_clear('tesla_charge_done', 'charge_done')
    if not any(lv.get(k) is True for k in OPEN_KEYS):
        notify_clear('tesla_door', 'door')
    soc = lv.get('battery_level')
    if (isinstance(soc, (int, float)) and soc >= 20) or lv.get('plugged_in') is True:
        notify_clear('tesla_low_batt', 'low_batt')
    if lv.get('update_available') is False:
        notify_clear('tesla_update', 'update')


# TeslaMate nu intreaba masina cat timp doarme sau e "suspended", deci un frunk deschis/inchis sau o incuiere nu apar in MQTT (valorile retinute raman vechi).
# ESP32 BLE (prin HA) vede masina fara s-o trezeasca: schimbarile lui trec prin acelasi drum ca cele din MQTT, deci apar si cardurile Live Activity.
BLE_CLOSURES = (('cover.%s_frunk', 'frunk_open', {'open': True, 'closed': False}), ('cover.%s_trunk', 'trunk_open', {'open': True, 'closed': False}),
                ('lock.%s_doors', 'locked', {'locked': True, 'unlocked': False}))
BLE_SEEN = {}


def ble_state_sync(car=1):
    """O trecere: citeste din HA starea frunk/portbagaj/incuietori BLE si o aplica daca a aparut o schimbare (sau la prima citire, daca difera de ce stim)."""
    if not (ha_ok() and HA['ble']) or not LIVE.get(car):
        return 0
    n = 0
    for tpl, key, vals in BLE_CLOSURES:
        eid = tpl % HA['prefix']
        st = ha_state(eid)
        if not st or st.get('state') not in vals:
            continue                                                  # unknown / unavailable / opening / closing
        marker = st.get('last_changed')
        first = eid not in BLE_SEEN
        changed = BLE_SEEN.get(eid) != marker
        BLE_SEEN[eid] = marker
        val = vals[st['state']]
        if (first or changed) and LIVE[car].get(key) != val:
            live_apply(car, key, val)
            n += 1
    return n


def ble_state_loop():
    while True:
        time.sleep(15)
        try:
            ble_state_sync()
        except Exception as e:  # noqa
            log('ble stare:', e, flush=True)


def la_loop():
    reconciled = False
    while True:
        time.sleep(45)
        try:
            for c in list(LIVE):
                la_sync(c)
                if not reconciled and NHOOK and LIVE.get(c):
                    notify_reconcile(c)
                    reconciled = True
        except Exception as e:  # noqa
            log('live loop:', e, flush=True)


# ---------------------------------------------------------------- acces din internet (parola + cookie semnat)
import hashlib, hmac, html as html_mod, ipaddress
AUTH = dict(pw=os.environ.get('APP_PASSWORD', ''), secret=(os.environ.get('SESSION_SECRET') or secrets.token_hex(32)).encode())
FAILS = {}   # ip -> [timestamps]
LOGIN = {
    'ro': dict(title='Autentificare', pw='Parolă', go='Intră', bad='Parolă greșită.', lock='Prea multe încercări. Reia peste câteva minute.', off='Accesul din internet nu este configurat.'),
    'en': dict(title='Sign in', pw='Password', go='Sign in', bad='Wrong password.', lock='Too many attempts. Try again in a few minutes.', off='Internet access is not configured.'),
}


def _sess_key():
    return AUTH['secret'] + hashlib.sha256(str(AUTH['pw']).encode('utf-8', 'replace')).digest()


SESS = dict(epoch=None)                                           # sesiunile emise INAINTE de acest moment nu mai sunt valide ("iesire de pe toate dispozitivele")


def sess_epoch():
    if SESS['epoch'] is None:
        try:
            SESS['epoch'] = int(float(OWN.kv_get('sess_epoch', 0) or 0)) if OWN else 0
        except Exception:  # noqa
            SESS['epoch'] = 0
    return SESS['epoch']


def sess_revoke_all():
    SESS['epoch'] = int(time.time())
    if OWN:
        OWN.kv_set('sess_epoch', SESS['epoch'])
    return SESS['epoch']


def sess_make():
    body = '%d.%s' % (int(time.time()), secrets.token_hex(8))        # nonce: doua sesiuni emise in aceeasi secunda au valori diferite
    return body + '.' + hmac.new(_sess_key(), body.encode(), hashlib.sha256).hexdigest()


def sess_ok(v):
    try:
        ts, nonce, sig = v.split('.', 2)
        good = hmac.new(_sess_key(), ('%s.%s' % (ts, nonce)).encode(), hashlib.sha256).hexdigest()
        t = int(ts)
        return hmac.compare_digest(sig, good) and time.time() - t < 30 * 86400 and t >= sess_epoch()
    except Exception:
        return False


ACCESS = dict(team=os.environ.get('ACCESS_TEAM', ''), aud=os.environ.get('ACCESS_AUD', ''), email=os.environ.get('ACCESS_EMAIL', ''))
# roluri pe e-mail (doar prin Cloudflare Access): ROLES='sotia@example.com:family,musafir@example.com:viewer'; ACCESS_EMAIL = administratorul
ROLES = {k.strip().lower(): v.strip() for k, _, v in (x.partition(':') for x in os.environ.get('ROLES', '').split(',') if ':' in x)}
FAMILY_OK = {'lock', 'unlock', 'climate_on', 'climate_off', 'set_temps', 'seat_heater', 'steering_heater', 'defrost', 'charge_start', 'charge_stop', 'flash', 'honk', 'wake', 'sentry_on', 'sentry_off'}
_JWKS = []


_JWT_BAD = {}                                                     # amprenta tokenului respins -> momentul (memorie scurta)


def access_ok(token):
    """Valideaza JWT-ul Cloudflare Access (semnatura, audienta, emitent) - cererea a trecut deci prin autentificarea Access."""
    if not (ACCESS['team'] and ACCESS['aud'] and token):
        return False
    bad_key = hashlib.sha256(token.encode('utf-8', 'replace')).hexdigest()[:20]
    if time.time() - _JWT_BAD.get(bad_key, 0) < 60:
        return False                                              # acelasi token respins acum: nu mai cerem certificatele si nu mai umplem jurnalul
    try:
        import jwt
        if not _JWKS:
            _JWKS.append(jwt.PyJWKClient('https://%s/cdn-cgi/access/certs' % ACCESS['team'], cache_keys=True, lifespan=3600))
        key = _JWKS[0].get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=['RS256'], audience=ACCESS['aud'], issuer='https://' + ACCESS['team'])
        em = str(claims.get('email') or '').lower()
        return (em or '__noemail__') if (ROLES or not ACCESS['email'] or em == ACCESS['email'].lower()) else False     # fara email in JWT (service token) = viewer, nu admin
    except Exception as e:  # noqa
        log('access jwt:', e, flush=True)
        if len(_JWT_BAD) > 500:
            _JWT_BAD.clear()
        _JWT_BAD[bad_key] = time.time()
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
_HC = [0.0, None, False]      # momentul, rezultatul, valid


def has_cars():
    """True/False = exista/nu exista masini; None = baza de date inaccesibila. Rezultatul se retine 10 s (3 s cand e None) ca o baza cazuta sa nu incetineasca fiecare cerere."""
    if DEMO_ONLY:
        return False
    now = time.time()
    if _HC[2] and now - _HC[0] < (3 if _HC[1] is None else 10):
        return _HC[1]
    try:
        v = bool(q('select 1 from cars limit 1'))
    except Exception:
        v = None  # DB inaccesibil
    _HC[:] = [now, v, True]
    return v


# Model 3 "Highland" (2024+) si Model Y "Juniper" (2025+): codurile actuale din configuratorul Tesla (caroserie, jante de baza, interior, vedere 3/4).
# Doar codurile care raspund (altfel serverul Tesla da 412); culorile fara cod valid cad pe cea mai apropiata.
COMPOSITOR = {
    '3': dict(model='m3', base='$MT367', wheel='$W38C', interior='$IBB8', view='STUD_FRONT34',
              paints={'PearlWhite': '$PPSW', 'StealthGrey': '$PN01', 'Quicksilver': '$PN00', 'RedMulticoat': '$PR01'}, fallback='$PN01'),
    'Y': dict(model='my', base='$MTY61', wheel='$WY18P', interior='$IBB6', view='FRONT34',
              paints={'PearlWhite': '$PPSW', 'SolidBlack': '$PBSB', 'DeepBlue': '$PPSB', 'DeepBlueMetallic': '$PPSB', 'StealthGrey': '$PN01', 'Quicksilver': '$PN00', 'RedMulticoat': '$PR01'}, fallback='$PN01'),
}


def compositor_url(c, view=None):
    """Poza 3/4 a masinii de la configuratorul Tesla (decupata pe masina), pentru Model 3 / Model Y; None pentru restul modelelor."""
    k = COMPOSITOR.get(str(c.get('model') or '').upper())
    if not k or os.environ.get('TESLA_RENDERS', '0') != '1':           # 0 = nu cerem imagini de la Tesla (implicit in versiunea publica)
        return None
    paint = k['paints'].get(str(c.get('color') or ''), k['fallback'])
    return ('https://static-assets.tesla.com/configurator/compositor?context=design_studio_2&options=%s,%s,%s,%s&view=%s&model=%s&size=1920&bkba_opt=1&crop=1200,700,370,230&overlay=0&'
            % (k['base'], paint, k['wheel'], k['interior'], view or k['view'], k['model']))


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
            c['image34'] = compositor_url(c) if not os.environ.get('CAR_OPTIONS') else None                 # vederea 3/4 (Model 3 / Y)
            c['live_age'] = (time.time() - LIVE_TS[c['id']]) if c['id'] in LIVE_TS else None
            out.append(c)
        return dict(demo=False, cars=out, links=LINKS, mqtt=bool(LIVE), lan_open=not AUTH['pw'] and not DEMO_ONLY, currency=CURRENCY, app=app_brief())
    return dict(demo=True, public_demo=DEMO_ONLY, cars=[dict(DEMO_CAR, live=DEMO_LIVE, live_age=0, image=car_image(DEMO_CAR), image34=compositor_url(DEMO_CAR), sleep=DEMO_SLEEP)],
                links=({} if DEMO_ONLY else LINKS), mqtt=False, db_error=(cl is None and not DEMO_ONLY), lan_open=not AUTH['pw'] and not DEMO_ONLY, currency=CURRENCY, app=app_brief())


CSP = os.environ.get('CSP') or (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://tile.openstreetmap.org https://static-assets.tesla.com; "
    "connect-src 'self' https://tile.openstreetmap.org https://api.open-meteo.com https://archive-api.open-meteo.com; "
    "worker-src 'self' blob:; child-src blob:; font-src 'self' data:; manifest-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'")
SEC_HEADERS = [('Content-Security-Policy', CSP if 'frame-ancestors' in CSP else CSP + "; frame-ancestors 'none'"), ('X-Frame-Options', 'DENY'), ('X-Content-Type-Options', 'nosniff'), ('Referrer-Policy', 'strict-origin-when-cross-origin'),
               ('Permissions-Policy', 'geolocation=(), camera=(), microphone=(), payment=()')]


class DBDown(Exception):
    pass


class NotFound(Exception):
    pass


# ---- extensii: modulele din features/ isi inregistreaza rute, hook-uri si sarcini de fundal
ROUTES = {}                      # (metoda, cale) -> (functie, optiuni)
PREFIX_ROUTES = []               # [(metoda, prefix, functie, optiuni)], cele mai lungi prefixe primele
MQTT_HOOKS = []                  # fn(car, key, vechi, nou, cunoscut) - in thread-ul MQTT, trebuie sa fie rapide
NOTIFY_SINKS = []                # fn(kind, title, msg, data) - receptori suplimentari de notificari (push, Telegram)
AUDIT_HOOKS = []                 # fn(kind, **kw)
BG_TASKS = []                    # sarcini de fundal pornite (supravegheat) la start
PUBLIC_ROUTES = []               # fn(handler, cale, parametri) -> (cod, corp, content-type[, csp]) sau None - pe portul PUBLIC (fara autentificare: modulul isi face singur verificarile)
CTX = threading.local()          # CTX.actor = cine a dat comanda (user:rol / rule:id / system)
OWN = None                       # baza de date proprie (features.store.Store), setata de features.load()
PLACES = None                    # features.places: match(lat, lon) -> loc salvat cu pret pe kWh
TAGS = None                      # features.tags: ids(kind, nume) si attach(kind, randuri) pentru filtrarea/afisarea tag-urilor


class Raw:
    """Raspuns binar dintr-o ruta de modul: fie `body` (bytes), fie `path` (fisier trimis in bucati; sters dupa trimitere daca delete=True)."""
    def __init__(self, body=None, path=None, ctype='application/octet-stream', headers=None, code=200, delete=False):
        self.body, self.path, self.ctype, self.headers, self.code, self.delete = body, path, ctype, headers or {}, code, delete


def route(method, path, pin=False, role='user', prefix=False):
    """Inregistreaza o ruta: role = 'any' (orice utilizator autentificat), 'user' (nu viewer), 'family' (family+admin), 'admin'. pin=True cere PIN-ul (POST)."""
    def deco(fn):
        o = dict(pin=pin, role=role)
        if prefix:
            PREFIX_ROUTES.append((method, path, fn, o))
            PREFIX_ROUTES.sort(key=lambda r: -len(r[1]))
        else:
            ROUTES[(method, path)] = (fn, o)
        return fn
    return deco


def route_lookup(method, path):
    r = ROUTES.get((method, path))
    if r:
        return r
    for m, pre, fn, o in PREFIX_ROUTES:
        if m == method and path.startswith(pre):
            return fn, o
    return None


@route('POST', '/api/logout_all', pin=True, role='admin')
def _logout_all(h, b):
    sess_revoke_all()
    log('audit: toate sesiunile cu parola au fost revocate')
    return dict(ok=True)


def audit(kind, **kw):
    for fn in list(AUDIT_HOOKS):
        try:
            fn(kind, **kw)
        except Exception as e:  # noqa
            log('audit hook: %s' % e)


DB_ROUTES = ('/api/drives', '/api/charges', '/api/overview', '/api/battery', '/api/sleep', '/api/activity', '/api/health_battery', '/api/caps', '/api/vdata')
DB_PREFIXES = ('/api/drive/', '/api/drive_row/', '/api/trip/', '/api/charge/', '/api/charge_row/', '/api/charge_solar/')
PINF = {}                       # ip -> [momente cu PIN gresit]
PIN_LOCK = threading.Lock()
FAILS_LOCK = threading.Lock()


class H(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    timeout = 30                 # socket: o conexiune care nu trimite nimic nu mai tine un thread la nesfarsit
    role = 'admin'

    def log_message(self, *a):
        pass

    def via_internet(self):
        return any(k in self.headers for k in ('Cf-Connecting-Ip', 'Cf-Ray', 'Cf-Visitor', 'X-Forwarded-For'))

    def run_route(self, r, data):
        fn, o = r
        need = o['role']
        if DEMO_ONLY and need == 'admin':
            return self.send_json(dict(ok=False, reason='Indisponibil în demonstrație.'), 403)      # instanta publica: rutele de administrare ale modulelor (backup, zone, linkuri) nu raspund
        if (need == 'admin' and self.role != 'admin') or (need == 'family' and self.role not in ('admin', 'family')) or (need == 'user' and self.role == 'viewer'):
            return self.send_json(dict(ok=False, reason='Nu ai permisiunea pentru această acțiune (rol: %s).' % self.role), 403)
        CTX.actor = 'user:%s' % self.role                 # comenzile pornite din rute de module (valet, handoff...) se jurnalizeaza pe utilizator, nu pe "system"
        try:
            res = fn(self, data)
        finally:
            CTX.actor = 'system'
        if isinstance(res, Raw):
            return self.send_raw(res)
        return self.send_json(dict(ok=True) if res is None else res)

    def send_raw(self, r):
        size = os.path.getsize(r.path) if r.path else len(r.body or b'')
        try:
            self.send_response(r.code)
            self.send_header('Content-Type', r.ctype)
            self.send_header('Content-Length', str(size))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for k, v in r.headers.items():
                self.send_header(k, v)
            self.end_headers()
            if r.path:
                with open(r.path, 'rb') as f:
                    while True:
                        chunk = f.read(1 << 16)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            else:
                self.wfile.write(r.body or b'')
        finally:
            if r.path and r.delete:
                try:
                    os.remove(r.path)
                except OSError:
                    pass

    def host_ok(self):
        """Din LAN (fara header-ele Cloudflare) accepta doar Host = IP, localhost, nume simplu/.local/.lan sau din ALLOWED_HOSTS / APP_URL: un domeniu strain care a fost rezolvat la IP-ul tau local (DNS rebinding) e refuzat."""
        if DEMO_ONLY or self.via_internet():
            return True
        h = (self.headers.get('Host') or '').strip().lower()
        host = (h.split(']')[0] + ']') if h.startswith('[') else h.rsplit(':', 1)[0] if ':' in h else h
        host = host.strip('[]')
        if not host or re.fullmatch(r'[0-9.]+', host) or ':' in host or '.' not in host or host == 'localhost' or host.endswith(('.localhost', '.local', '.lan', '.home.arpa', '.internal')):
            return True
        allowed = {x.strip().lower() for x in str(os.environ.get('ALLOWED_HOSTS', '')).split(',') if x.strip()}
        if APPURL:
            allowed.add((urlparse(APPURL).hostname or '').lower())
        return host in allowed

    def origin_ok(self):
        """POST din browser: Origin (daca exista) trebuie sa fie chiar aplicatia. Prin Cloudflare Host poate fi rescris de tunel, deci acolo nu se verifica."""
        o = self.headers.get('Origin')
        if not o or DEMO_ONLY or self.via_internet():
            return True
        return (urlparse(o).netloc or '').lower() == (self.headers.get('Host') or '').strip().lower()

    def client_ip(self):
        return self.headers.get('Cf-Connecting-Ip') or self.client_address[0]     # X-Forwarded-For nu mai e crezut (il poate scrie orice client)

    def read_body(self, limit=1 << 20):
        try:
            n = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            raise ValueError('Content-Length invalid')
        if n < 0 or n > limit:
            raise ValueError('corpul cererii e prea mare')
        return self.rfile.read(n) if n else b''

    def pin_check(self):
        """(ok, motiv, cod HTTP). Max. 5 PIN-uri gresite / 10 min per IP si 30 in total; comparatie in timp constant, pe octeti."""
        ip, now = self.client_ip(), time.time()
        got = self.headers.get('X-Pin', '')
        wrong = False
        with PIN_LOCK:                                    # limita, compararea si inregistrarea esecului se fac sub acelasi lacat: N cereri paralele nu trec de limita
            for k in list(PINF):
                PINF[k] = [x for x in PINF[k] if now - x < 600]
                if not PINF[k]:
                    del PINF[k]
            if len(PINF.get(ip, [])) >= 5 or sum(len(v) for v in PINF.values()) >= 30:
                return False, 'Prea multe încercări greșite. Reia peste 10 minute.', 429
            if FL['pin'] and secrets.compare_digest(got.encode('utf-8', 'replace'), FL['pin'].encode('utf-8', 'replace')):
                return True, '', 200
            if FL['pin'] and got:
                PINF.setdefault(ip, []).append(now)
                wrong = True
        if wrong:
            log('audit: PIN gresit ip=%s' % ip)
        return False, 'PIN greșit.' if FL['pin'] else 'PIN greșit sau neconfigurat.', 403

    def private_peer(self):
        try:
            ip = ipaddress.ip_address(self.client_address[0].split('%')[0])
            if getattr(ip, 'ipv4_mapped', None):
                ip = ip.ipv4_mapped
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            return False

    def authed(self):
        if DEMO_ONLY:
            return True
        if self.via_internet():
            em = access_ok(self.headers.get('Cf-Access-Jwt-Assertion', ''))
            if em:
                self.role = ROLES.get(em, 'admin' if (ACCESS['email'] and em == ACCESS['email'].lower()) else 'viewer')
                return True            # a trecut de Cloudflare Access (verificat criptografic)
            if not AUTH['pw']:
                return False           # din internet fara parola configurata: totul inchis
        elif not AUTH['pw']:
            return self.private_peer()  # fara parola: deschis doar pentru adrese private/locale (UI avertizeaza); un port expus direct pe internet nu mai e accesibil; cu parola setata cere autentificare peste tot
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
        for k, v in SEC_HEADERS:
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(b)))
        for k, v in (extra or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(b)

    def do_login(self):
        t = LOGIN['ro' if self.lang().lower().startswith('ro') else 'en']
        ip, now = self.client_ip(), time.time()
        if not AUTH['pw']:
            return self.page(403, login_html(self.lang(), t['off']))
        with FAILS_LOCK:                                       # rezervam incercarea inainte de verificare: cererile paralele nu mai trec de limita
            for k in list(FAILS):
                FAILS[k] = [x for x in FAILS[k] if now - x < 600]
                if not FAILS[k]:
                    del FAILS[k]
            if len(FAILS.get(ip, [])) >= 5 or sum(len(v) for v in FAILS.values()) >= 50:
                return self.page(429, login_html(self.lang(), t['lock']))
            FAILS.setdefault(ip, []).append(now)
        try:
            form = parse_qs(self.read_body(4096).decode('utf-8', 'replace'))
        except ValueError:
            return self.page(400, login_html(self.lang(), t['bad']))
        pw = (form.get('password') or [''])[0]
        if secrets.compare_digest(pw.encode('utf-8', 'replace'), AUTH['pw'].encode('utf-8', 'replace')):
            with FAILS_LOCK:
                FAILS.pop(ip, None)
            ck = 'sess=%s; Path=/; Max-Age=%d; HttpOnly; SameSite=Strict%s' % (sess_make(), 30 * 86400, '; Secure' if self.via_internet() else '')
            self.send_response(303)
            self.send_header('Location', '/')
            self.send_header('Set-Cookie', ck)
            self.end_headers()
            return
        log('audit: parola gresita ip=%s' % ip)
        return self.page(401, login_html(self.lang(), t['bad']))

    def send_json(self, obj, code=200):
        b = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        a = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        if not self.host_ok():
            return self.send_json(dict(error='host', reason='Adresă necunoscută. Adaugă-o în ALLOWED_HOSTS sau intră prin IP.'), 421)
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
                db = True if DEMO_ONLY else (has_cars() is not None)
                if not self.authed():                         # fara autentificare: doar starea (healthcheck-ul Docker), fara versiune/fire de executie
                    return self.send_json(dict(ok=db, db=db), 200 if db else 503)
                return self.send_json(dict(ok=db, db=db, version=APP_VERSION, mqtt=(MQ_STATE['up'] if MQ['host'] else None), threads={k: t.is_alive() for k, t in THREADS.items()}), 200 if db else 503)
            if p == '/api/state':
                d = api_state()
                d['role'] = self.role
                return self.send_json(d)
            if p == '/api/stream':
                return self.stream()
            if p == '/api/profiler/stream':
                return self.stream(PF['clients'])
            if p == '/api/profiler/export.csv':
                b = pf_csv().encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/csv; charset=utf-8')
                self.send_header('Content-Disposition', 'attachment; filename="profiler.csv"')
                self.send_header('Content-Length', str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return
            if p.startswith('/api/fleet/') and DEMO_ONLY:
                return self.send_json(dict(error='disabled in demo'), 404)
            if p == '/api/fleet/status':
                return self.send_json(fleet_status())
            if p == '/api/fleet/login':
                if self.role != 'admin':
                    return self.send_json(dict(error='Doar administratorul poate conecta contul Tesla.'), 403)
                if not (FL['cid'] and FL['domain']):
                    return self.send_json(dict(error='Fleet API nu e configurat.'), 400)
                self.send_response(302)
                self.send_header('Location', login_url())
                self.end_headers()
                return
            r = route_lookup('GET', p)
            if r:
                return self.run_route(r, a)
            if p.startswith('/api/'):
                return self.send_json(self.api(p, a))
        except DBDown:
            return self.send_json(dict(error='db', reason='Baza de date TeslaMate nu răspunde.'), 503)
        except NotFound:
            return self.send_json(dict(error='not found'), 404)
        except (ValueError, TypeError) as e:                     # parametri gresiti (int('abc') etc.): 400, nu 500
            log('GET %s: cerere invalida: %s' % (p, e), flush=True)
            return self.send_json(dict(error='cerere invalidă', reason=str(e)[:120]), 400)
        except Exception as e:  # noqa
            log('GET %s: %s' % (p, e), flush=True)
            return self.send_json(dict(error='eroare internă'), 500)
        return self.static(p)

    def do_POST(self):
        u = urlparse(self.path)
        if not self.host_ok():
            return self.send_json(dict(ok=False, reason='Adresă necunoscută. Adaugă-o în ALLOWED_HOSTS sau intră prin IP.'), 421)
        if not self.origin_ok():
            return self.send_json(dict(ok=False, reason='Origine interzisă.'), 403)
        if u.path == '/api/profiler/ingest':
            tok = os.environ.get('INGEST_TOKEN', '')
            if not tok or not secrets.compare_digest(self.headers.get('X-Ingest-Token', '').encode('utf-8', 'replace'), tok.encode('utf-8', 'replace')):
                return self.send_json(dict(ok=False), 401)
            try:
                pf_ingest((json.loads(self.read_body(2_000_000) or b'{}')).get('records') or [])
            except Exception as e:  # noqa
                log('profiler ingest: %s' % e, flush=True)
                return self.send_json(dict(ok=False, error='cerere invalidă'), 400)
            return self.send_json(dict(ok=True))
        if DEMO_ONLY and u.path in ('/api/profiler/start', '/api/profiler/stop'):
            try:
                raw = self.read_body(65536)
                body = json.loads(raw) if raw else {}
                return self.send_json(pf_start(1, body.get('profile'), body.get('minutes', 5)) if u.path.endswith('start') else pf_stop())
            except RuntimeError as e:
                return self.send_json(dict(ok=False, reason=str(e)[:300]), 400)
            except Exception as e:  # noqa
                log('profiler demo: %s' % e, flush=True)
                return self.send_json(dict(ok=False, reason='cerere invalidă'), 400)
        if DEMO_ONLY:
            return self.send_json(dict(ok=False, reason='demo'), 403)
        if u.path == '/login':
            return self.do_login()
        if not self.authed():
            return self.send_json(dict(ok=False, reason='auth'), 401)
        try:
            if not self.headers.get('Content-Type', '').lower().startswith('application/json'):
                return self.send_json(dict(ok=False, reason='Content-Type trebuie să fie application/json.'), 415)
            raw = self.read_body()
            body = json.loads(raw) if raw else {}
            if not isinstance(body, dict):
                raise ValueError('se aștepta un obiect JSON')
            r = route_lookup('POST', u.path)
            if r and not r[1]['pin']:
                return self.run_route(r, body)
            if u.path.startswith('/api/notify/') and self.role == 'viewer':
                return self.send_json(dict(ok=False, reason='Rolul tău nu poate schimba notificările.'), 403)
            if u.path == '/api/notify/settings':
                st = nset_load()
                st.update({k: bool(v) for k, v in body.items() if k in NDEFAULT})
                nset_save(st)
                return self.send_json(dict(ok=True, settings=st))
            if u.path == '/api/notify/test':
                return self.send_json(dict(ok=True, sent=notify('test', '🔔 Test notificare', 'Notificările din aplicația Tesla funcționează.')))
            if u.path in ('/api/config', '/api/config/test'):
                if self.role != 'admin':
                    return self.send_json(dict(ok=False, reason='Doar administratorul poate schimba setările.'), 403)
                if FL['pin']:
                    pok, why, pcode = self.pin_check()
                    if not pok:
                        return self.send_json(dict(ok=False, reason=why), pcode)
                if not FL['pin'] and self.via_internet():
                    return self.send_json(dict(ok=False, reason='Setează mai întâi PIN-ul din rețeaua locală (acasă).'), 403)
                if u.path == '/api/config/test':
                    return self.send_json(cfg_test(body.get('what')))
                ok, err = cfg_update(body)
                return self.send_json(dict(ok=ok, reason=err, config=cfg_public()) if ok else dict(ok=False, reason=err), 200 if ok else 400)
            if self.role == 'viewer':
                return self.send_json(dict(ok=False, reason='Nu ai permisiunea pentru această acțiune (rol: viewer).'), 403)
            # Actualizarea din aplicatie merge si cat timp nu ai setat inca un PIN (administratorul e deja verificat mai sus); cu PIN setat se cere ca oricare alta comanda.
            pin_free = u.path in ('/api/update/check', '/api/update/apply') and not FL['pin'] and self.role == 'admin'
            pok, why, pcode = (True, '', 200) if pin_free else self.pin_check()
            if not pok:
                return self.send_json(dict(ok=False, reason=why), pcode)
            if r and r[1]['pin']:
                return self.run_route(r, body)
            name = u.path.rsplit('/', 1)[1] if u.path.startswith('/api/cmd/') else ''
            if self.role != 'admin' and not (self.role == 'family' and name in FAMILY_OK):
                return self.send_json(dict(ok=False, reason='Nu ai permisiunea pentru această acțiune (rol: %s).' % self.role), 403)
            if u.path == '/api/import/tessie':
                return self.send_json(imp_action(int(body.get('car', 1)), body))
            if u.path == '/api/charge/meta':
                try:
                    cid = int(body.get('id'))
                    if not q('select 1 from charging_processes where id=%s', (cid,)):
                        return self.send_json(dict(ok=False, reason='Încărcare inexistentă'), 404)
                    return self.send_json(dict(ok=True, meta=meta_update(cid, body)))
                except (TypeError, ValueError) as e:
                    return self.send_json(dict(ok=False, reason='Valoare invalidă (%s)' % e), 400)
            if u.path == '/api/fuel/refresh':
                return self.send_json(fuel_fetch())
            if u.path == '/api/update/check':
                return self.send_json(dict(update_check(), info=version_info()))
            if u.path == '/api/update/apply':
                res = update_apply()
                log('audit: update apply rol=%s ip=%s ok=%s' % (self.role, self.client_ip(), res.get('ok')))
                return self.send_json(res)
            if u.path == '/api/profiler/start':
                return self.send_json(pf_start(int(body.get('car', 1)), body.get('profile'), body.get('minutes', 5)))
            if u.path == '/api/profiler/stop':
                return self.send_json(pf_stop(int(body.get('car', 1)), force=bool(body.get('force'))))
            if u.path == '/api/rules':
                with FLOCK:                                   # doua cereri simultane nu mai pierd o modificare
                    rs = rules_load()
                    if body.get('delete'):
                        rs = [r for r in rs if r['id'] != body['delete']]
                    elif body.get('toggle'):
                        for r in rs:
                            if r['id'] == body['toggle']:
                                r['enabled'] = not r.get('enabled')
                    else:
                        rs.append(rule_clean(body))
                    rules_save(rs[:30])
                return self.send_json(dict(ok=True, rules=rs))
            if u.path == '/api/fleet/register':
                return self.send_json(partner_register())
            if u.path.startswith('/api/cmd/'):
                CTX.actor = 'user:%s' % self.role
                try:
                    res = run_command(int(body.get('car', 1)), u.path.rsplit('/', 1)[1], body.get('arg'))
                finally:
                    CTX.actor = 'system'
                log('audit: cmd=%s rol=%s ip=%s ok=%s via=%s' % (u.path.rsplit('/', 1)[1], self.role, self.client_ip(), (res or {}).get('ok'), (res or {}).get('via', 'fleet')))
                return self.send_json(res)
        except ValueError as e:
            return self.send_json(dict(ok=False, reason='Cerere invalidă: %s' % e), 400)
        except NotFound:
            return self.send_json(dict(ok=False, reason='Nu există.'), 404)
        except KeyError as e:
            return self.send_json(dict(ok=False, reason='Cerere invalidă: lipsește câmpul %s' % e), 400)
        except RuntimeError as e:                         # mesajele RuntimeError sunt scrise pentru utilizator ("contul Tesla nu e autorizat", "baza e ocupata"...)
            log('POST %s: %s' % (u.path, e), flush=True)
            return self.send_json(dict(ok=False, reason=str(e)[:300]), 500)
        except Exception as e:  # noqa                    # SQL / cai de fisiere / biblioteci: doar in jurnal, clientul primeste un mesaj general
            log('POST %s: %s: %s' % (u.path, type(e).__name__, e), flush=True)
            return self.send_json(dict(ok=False, reason='Eroare internă (detalii în jurnalul aplicației).'), 500)
        return self.send_json(dict(error='not found'), 404)

    def api(self, p, a):
        hc = has_cars()
        if hc is None and (p in DB_ROUTES or p.startswith(DB_PREFIXES)):
            raise DBDown()                              # baza TeslaMate nu raspunde: eroare 503, NU date demo
        demo = hc is False
        car = int(a.get('car', 1))
        lim, off = min(int(a.get('limit', 40)), 200), int(a.get('offset', 0))
        if p == '/api/drives':
            if demo:
                return DEMO['drives'][off:off + lim]
            lo, hi, ids = list_filters(a, 'drive')
            rows = drives(car, lim, off, lo, hi, ids)
            return TAGS.attach('drive', rows) if TAGS else rows
        if p.startswith('/api/drive/'):
            did = int(p.rsplit('/', 1)[1])
            return dict(points=demo_points(did) if demo else drive_points(did), events=dict(hard_accel=2, hard_brake=1, regen_kwh=0.9, score=89) if demo else drive_events(did))
        if p.startswith('/api/trip/'):
            did = int(p.rsplit('/', 1)[1])
            return demo_trip(did) if demo else trip(car, did)
        if p == '/api/charges':
            if demo:
                return decorate([dict(x) for x in DEMO['charges'][off:off + lim]])
            lo, hi, ids = list_filters(a, 'charge')
            rows = charges(car, lim, off, None, lo, hi, ids)
            return TAGS.attach('charge', rows) if TAGS else rows
        if p.startswith('/api/charge_row/'):
            cid = int(p.rsplit('/', 1)[1])
            rows = decorate([dict(x) for x in DEMO['charges'] if x['id'] == cid]) if demo else charges(car, 1, 0, cid)
            if not rows:
                raise NotFound()
            if TAGS and not demo:
                TAGS.attach('charge', rows)
            return rows[0]
        if p.startswith('/api/drive_row/'):
            did = int(p.rsplit('/', 1)[1])
            rows = [x for x in DEMO['drives'] if x['id'] == did] if demo else drives_by_ids(car, [did])
            if not rows:
                raise NotFound()
            if TAGS and not demo:
                TAGS.attach('drive', rows)
            return rows[0]
        if p.startswith('/api/charge/'):
            cid = int(p.rsplit('/', 1)[1])
            return dict(points=demo_charge_points(cid) if demo else charge_points(cid))
        if p == '/api/overview':
            days = max(1, min(int(a.get('days', 30)), 730))
            return demo_overview(days) if demo else overview(car, days)
        if p == '/api/fuel':
            return fuel_info()
        if p == '/api/version':
            return version_info()
        if p == '/api/changelog':
            return changelog_entries(max(1, min(int(a.get('limit', 8)), 50)))
        if p == '/api/battery':
            return demo_battery() if demo else battery(car)
        if p == '/api/sleep':
            n = max(1, min(int(a.get('days', 7)), 60))
            return demo_sleep(n) if demo else sleep_report(car, n)
        if p == '/api/activity':
            return demo_activity() if demo else activity(car, min(int(a.get('days', 30)), 90), min(int(a.get('limit', 120)), 300))
        if p == '/api/health_battery':
            return demo_health() if demo else battery_health(car)
        if p.startswith('/api/charge_solar/'):
            return dict(available=False) if demo else charge_solar(int(p.rsplit('/', 1)[1]))
        if p == '/api/caps':
            return dict(rear_seats=True) if demo else caps_infer(car)
        if p == '/api/vdata':
            return DEMO_VD if demo else vehicle_data(car, a.get('force') == '1' and self.role != 'viewer')
        if p == '/api/import/tessie/status':
            return dict(IMP)
        if p == '/api/profiler/diag':
            if DEMO_ONLY or PF['sim']:
                return dict(ok=True, sim=True)
            if time.time() - PF['diag'][0] < 8 and PF['diag'][1]:
                return PF['diag'][1]
            vin = vin_for(car)
            b, resp, c = pf_cfg_get(vin) if vin else (None, {}, 0)
            nf = len((b or {}).get('fields') or {})
            base = jload(DATA_DIR + '/profiler_base.json', None) or {}
            nb = len(base.get('fields') or {}) or 1                       # configuratia de baza (Sentry + usi/incuiere/geamuri), nu doar Sentry
            out = dict(ok=bool(b), synced=resp.get('synced'), fields=nf, base_fields=nb, normal=nf <= nb, state=LIVE.get(car, {}).get('state'), code=c)
            PF['diag'] = (time.time(), out)
            return out
        if p == '/api/profiler':
            with PF['lock']:                                  # pf_ingest modifica dictionarele din alt thread
                vals = {k: [v[0], v[1]] for k, v in PF['values'].items()}
                hist = {k: [x[1] for x in list(v)[-120:]] for k, v in PF['hist'].items()}
            return dict(pf_status(), meta=PF_META, values=vals, hist=hist)
        if p == '/api/config':
            if self.role != 'admin':
                return dict(error='forbidden')
            return dict(demo=True) if demo else dict(cfg_public(), role=self.role)
        if p == '/api/config/ha_entities':
            if self.role != 'admin' or not ha_ok():
                return dict(ok=False, entities=[])
            return ha_entities()
        if p == '/api/rules':
            fg = []
            try:
                fg = [x['n'] for x in q("select distinct name as n from geofences where name is not null order by 1")]
            except Exception:
                pass
            with RLOCK:
                lg = list(RLOG)
            return dict(rules=[] if demo else rules_load(), log=lg, geofences=fg or ['Acasă'], ha=ha_ok())
        if p == '/api/notify':
            with NLOCK:
                ev = list(EVENTS)
            return dict(events=ev, settings=nset_load(), hook=bool(NHOOK))
        return dict(error='not found')

    def stream(self, group=None):
        group = CLIENTS if group is None else group
        qu = queue.Queue(maxsize=500)
        with CLOCK:
            if len(CLIENTS) + len(PF['clients']) >= int(os.environ.get('MAX_SSE', '60')):
                self.send_response(503)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            group.add(qu)
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
                group.discard(qu)

    def static(self, p):
        if p in ('/', ''):
            p = '/index.html'
        f = os.path.normpath(os.path.join(STATIC, p.lstrip('/')))
        if p == '/car.png':
            user = os.path.join(os.path.dirname(TOKENS), 'car.png')
            f = user if os.path.isfile(user) else (f if os.path.isfile(f) else os.path.join(STATIC, 'car-default.svg'))
        elif not (f == STATIC or f.startswith(STATIC + os.sep)):
            f = ''
        if not f or not os.path.isfile(f):
            self.send_response(404)
            self.end_headers()
            return
        ct = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml',
              '.json': 'application/json', '.webmanifest': 'application/manifest+json', '.png': 'image/png'}.get(os.path.splitext(f)[1], 'application/octet-stream')
        b = open(f, 'rb').read()
        cc = 'no-cache'
        if os.path.basename(f) == 'index.html':          # scripturile/stilurile primesc ?v=<amprenta>: un telefon cu o copie veche in memorie nu le mai poate refolosi
            v = static_build()
            b = re.sub(rb'(src|href)="((?!https?:|/)[\w./-]+\.(?:js|css))"', lambda m: m.group(1) + b'="' + m.group(2) + b'?v=' + v.encode() + b'"', b)
            cc = 'no-store'
        self.send_response(200)
        self.send_header('Content-Type', ct)
        self.send_header('Cache-Control', cc)
        for k, v in SEC_HEADERS:
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)


class PublicH(BaseHTTPRequestHandler):
    """Singurul lucru expus public (prin tunel): cheia publica Tesla + callback-ul OAuth. Nimic altceva."""
    protocol_version = 'HTTP/1.0'
    timeout = 30

    def log_message(self, *a):
        pass

    def out(self, code, body, ct='text/plain; charset=utf-8', csp=None):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(b)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', csp or "default-src 'none'; style-src 'unsafe-inline'")
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
            msg = html_mod.escape(msg)
            html = ('<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">'
                    '<body style="font-family:system-ui;background:#0b0d10;color:#eceff3;padding:40px;text-align:center">'
                    '<h2>%s %s</h2><p style="color:#8f99a4">Poti inchide pagina si reveni in aplicatie.</p>' % ('&#10003;' if ok else '&#9888;', msg))
            return self.out(200 if ok else 400, html, 'text/html; charset=utf-8')
        for fn in list(PUBLIC_ROUTES):
            try:
                r = fn(self, u.path, {k: v[0] for k, v in parse_qs(u.query).items()})
            except Exception as e:  # noqa
                log('ruta publica: %s' % e)
                return self.out(500, 'eroare')
            if r:
                return self.out(*r)
        return self.out(404, 'not found')

    def do_POST(self):
        return self.out(405, 'method not allowed')


def serve_public():
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PUBLIC_PORT', '4101'))), PublicH).serve_forever()


cfg_load()
apply_config()
pf_session_load()


THREADS = {}

import features                                        # noqa: E402  (modulele isi inregistreaza rutele/hook-urile la incarcare)
FEATURES = features.load(sys.modules[__name__])


def supervise(fn):
    """Porneste fn intr-un thread si o relanseaza (cu pauza 2..60 s) daca iese cu exceptie; iesirea normala (ex. fara MQTT configurat) nu se relanseaza."""
    def run():
        delay = 2
        while True:
            try:
                fn()
                return
            except Exception as e:  # noqa
                log('thread %s a cazut: %s' % (fn.__name__, e))
                time.sleep(delay)
                delay = min(delay * 2, 60)
    t = threading.Thread(target=run, daemon=True, name=fn.__name__)
    t.start()
    THREADS[fn.__name__] = t
    return t


if __name__ == '__main__':
    log('pornit: demo=%s mqtt=%s ha=%s pin=%s parola=%s access=%s module=%s' % (DEMO_ONLY, bool(MQ['host']), bool(HA['url']), bool(FL['pin']), bool(AUTH['pw']), bool(ACCESS['team']), ','.join(FEATURES)))
    if not DEMO_ONLY:
        for fn in [mqtt_thread, rules_clock, pf_watch, la_loop, ble_state_loop, fuel_loop, update_loop, serve_public] + BG_TASKS:
            supervise(fn)
    ThreadingHTTPServer(('0.0.0.0', PORT), H).serve_forever()

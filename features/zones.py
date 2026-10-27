"""Reguli de zona / viteza / program: te anunta cand masina (sau cine o conduce) iese din tipare. Doar notificari, nu comenzi.
Tipuri: viteza peste N km/h; intrare sau iesire dintr-un geofence TeslaMate (dupa nume); miscare in afara unui program (ex. 23:00-06:00).
O regula poate fi activa mereu sau doar cat tine o predare (valet / oaspete / prieten)."""
import datetime as dt
import re
import time

KINDS = ('speed', 'enter', 'leave', 'curfew')


def in_window(now_hm, window):
    """now_hm 'HH:MM', window 'HH:MM-HH:MM' (poate trece peste miezul noptii)."""
    m = re.fullmatch(r'(\d{2}:\d{2})-(\d{2}:\d{2})', str(window))
    if not m:
        return False
    a, b = m.groups()
    return (a <= now_hm < b) if a <= b else (now_hm >= a or now_hm < b)


def evaluate(rule, key, prev, val, known, live, now_hm):
    """Intoarce textul alertei sau None. rule: kind, pattern (regex geofence), limit (km/h), window."""
    k = rule['kind']
    if k == 'speed' and key == 'speed' and known and isinstance(val, (int, float)):
        lim = rule['limit'] or 0
        if lim and val > lim and not (isinstance(prev, (int, float)) and prev > lim):
            return 'Viteză %d km/h (limita ta: %d).' % (round(val), lim)
    elif k in ('enter', 'leave') and key == 'geofence' and known:
        rx = rule['pattern'] or ''
        if not rx:
            return None
        was, now = bool(prev and re.search(rx, str(prev), re.I)), bool(val and re.search(rx, str(val), re.I))
        if k == 'enter' and now and not was:
            return 'A intrat în „%s”.' % val
        if k == 'leave' and was and not now:
            return 'A ieșit din „%s”.' % prev
    elif k == 'curfew' and key in ('shift_state', 'speed'):
        moving = (key == 'shift_state' and val in ('D', 'R') and prev not in ('D', 'R', 'N')) or (key == 'speed' and isinstance(val, (int, float)) and val > 5 and not (isinstance(prev, (int, float)) and prev > 5))
        if moving and in_window(now_hm, rule['window']):
            return 'Mașina se mișcă în afara programului (%s).' % rule['window']
    return None


def clean(b):
    kind = b.get('kind')
    if kind not in KINDS:
        raise ValueError('tip: ' + ', '.join(KINDS))
    name = re.sub(r'[<>\r\n]', '', str(b.get('name', '')))[:60].strip() or {'speed': 'Viteză', 'enter': 'Intrare în zonă', 'leave': 'Ieșire din zonă', 'curfew': 'Program'}[kind]
    r = dict(name=name, kind=kind, pattern='', limit=None, window='', scope='handoff' if b.get('scope') == 'handoff' else 'always',
             enabled=0 if b.get('enabled') is False else 1, cooldown=max(1, min(int(b.get('cooldown', 10) or 10), 1440)))
    if kind == 'speed':
        try:
            r['limit'] = int(float(b.get('limit')))
        except (TypeError, ValueError):
            raise ValueError('limita de viteză în km/h')
        if not 30 <= r['limit'] <= 250:
            raise ValueError('limita de viteză: 30–250 km/h')
    if kind in ('enter', 'leave'):
        r['pattern'] = '|'.join(x.strip() for x in re.sub(r'[^\w|\s.-]', '', str(b.get('pattern', '')))[:60].split('|') if x.strip())      # fara alternative goale ("a|" ar potrivi orice)
        if not r['pattern']:
            raise ValueError('numele zonei (geofence din TeslaMate)')
    if kind == 'curfew':
        w = str(b.get('window', '')).strip()
        if not re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d', w):
            raise ValueError('program de forma 23:00-06:00')
        r['window'] = w
    return r


def init(S):
    S.OWN.migrate('zones', ['create table zone_rules (id integer primary key, name text, kind text, pattern text, lim integer, win text, scope text, enabled integer, cooldown integer, last_fired real, fired integer default 0)',
                            'create table zone_log (id integer primary key, ts real, rule integer, name text, msg text)'])
    S.KIND_ROUTE.setdefault('rule', '#/auto')

    def tz():
        try:
            import zoneinfo
            return zoneinfo.ZoneInfo(S.LOCAL_TZ)
        except Exception:  # noqa
            return dt.timezone.utc

    def hook(car, key, prev, val, known):
        if key not in ('speed', 'geofence', 'shift_state'):
            return
        rules = S.OWN.rows('select * from zone_rules where enabled=1')
        if not rules:
            return
        handoff = bool(S.OWN.one('select 1 x from handoffs where ended is null')) if S.OWN.one("select 1 x from sqlite_master where name='handoffs'") else False
        now = time.time()
        hm = dt.datetime.now(tz()).strftime('%H:%M')
        for r in rules:
            if r['scope'] == 'handoff' and not handoff:
                continue
            if r['last_fired'] and now - r['last_fired'] < r['cooldown'] * 60:
                continue
            msg = evaluate(dict(kind=r['kind'], pattern=r['pattern'], limit=r['lim'], window=r['win']), key, prev, val, known, S.LIVE.get(car, {}), hm)
            if not msg:
                continue
            S.OWN.run('update zone_rules set last_fired=?, fired=fired+1 where id=?', (now, r['id']))
            S.OWN.run('insert into zone_log(ts, rule, name, msg) values(?,?,?,?)', (now, r['id'], r['name'], msg))
            S.OWN.run('delete from zone_log where ts < ?', (now - 90 * 86400,))
            S.notify('rule', '📍 ' + r['name'], '%s: %s' % ((S.LIVE.get(car, {}) or {}).get('display_name') or 'Tesla', msg))

    S.MQTT_HOOKS.append(hook)

    @S.route('GET', '/api/zones', role='admin')
    def listing(h, a):
        return dict(rules=S.OWN.rows('select id, name, kind, pattern, lim, win, scope, enabled, cooldown, last_fired, fired from zone_rules order by id'),
                    log=S.OWN.rows('select ts, name, msg from zone_log order by id desc limit 30'),
                    geofences=sorted({g for g in ((S.LIVE.get(c, {}) or {}).get('geofence') for c in S.LIVE) if g}))

    @S.route('POST', '/api/zones/rule', pin=True, role='admin')
    def save(h, b):
        r = clean(b)
        if b.get('id'):
            S.OWN.run('update zone_rules set name=?, kind=?, pattern=?, lim=?, win=?, scope=?, enabled=?, cooldown=? where id=?',
                      (r['name'], r['kind'], r['pattern'], r['limit'], r['window'], r['scope'], r['enabled'], r['cooldown'], int(b['id'])))
        else:
            if S.OWN.one('select count(*) n from zone_rules')['n'] >= 30:
                raise ValueError('Maxim 30 de reguli.')
            S.OWN.run('insert into zone_rules(name, kind, pattern, lim, win, scope, enabled, cooldown) values(?,?,?,?,?,?,?,?)',
                      (r['name'], r['kind'], r['pattern'], r['limit'], r['window'], r['scope'], r['enabled'], r['cooldown']))

    @S.route('POST', '/api/zones/delete', pin=True, role='admin')
    def delete(h, b):
        S.OWN.run('delete from zone_rules where id=?', (int(b.get('id', 0)),))

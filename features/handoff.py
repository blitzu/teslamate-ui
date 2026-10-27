"""Predare masina (valet / oaspete): pornesti modul Valet si/sau Guest, optional limita de viteza, cu un cronometru; la sfarsit primesti un raport cu ce s-a condus in acest timp.
PIN-ul de 4 cifre al masinii trece prin server doar ca sa ajunga la Tesla: nu se salveaza, nu intra in jurnale si trebuie dat din nou la oprire (aplicatia nu poate opri valet/limita fara el)."""
import datetime as dt
import json
import re
import time

MAX_MIN = 720


def utc_iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).replace(tzinfo=None).isoformat()


def summarize(drives):
    """Rezumat al curselor din timpul predarii."""
    if not drives:
        return dict(drives=0, km=0.0, speed_max=0, start=None, end=None, places=[])
    km = sum(d['distance'] or 0 for d in drives)
    places = []
    for d in drives:
        for n in (d.get('start_name'), d.get('end_name')):
            if n and (not places or places[-1] != n):
                places.append(n)
    return dict(drives=len(drives), km=round(km, 1), speed_max=max((d['speed_max'] or 0) for d in drives), start=drives[0]['start_date'], end=drives[-1]['end_date'], places=places[:12])


def init(S):
    S.OWN.migrate('handoff', ['create table handoffs (id integer primary key, car integer, started real, ends real, ended real, modes text, limit_mph integer, label text, report text)'])

    def active(car=None):
        a = S.OWN.one('select * from handoffs where ended is null' + (' and car=?' if car else ' order by id desc'), (car,) if car else ())
        return a

    def report(car, a, b):
        try:
            rows = S.q(S.DRIVE_SQL + ' and d.start_date >= %s and d.start_date < %s order by d.start_date', (car, utc_iso(a), utc_iso(b)))
        except Exception as e:  # noqa
            S.log('predare raport: %s' % e)
            return None
        return summarize(rows)

    def step(name, car, arg=None):
        try:
            r = S.run_command(car, name, arg) or {}
            return dict(step=name, ok=bool(r.get('ok')), reason=str(r.get('reason') or '')[:160])
        except Exception as e:  # noqa
            return dict(step=name, ok=False, reason=str(e)[:160])

    def pin4(b):
        p = str(b.get('pin4', ''))
        return p if re.fullmatch(r'\d{4}', p) else None

    def watcher():
        while True:
            try:
                for a in S.OWN.rows('select * from handoffs where ended is null and ends < ?', (time.time(),)):
                    if not S.OWN.kv_get('handoff_warned_%d' % a['id']):
                        S.OWN.kv_set('handoff_warned_%d' % a['id'], True)
                        S.notify('handoff', '⏱ Predarea mașinii a expirat', 'Timpul de %d min s-a încheiat. Deschide aplicația → Predare mașină → Încheie (cu PIN-ul mașinii) ca să dezactivezi %s.' % ((a['ends'] - a['started']) // 60, a['modes'].replace(',', ' + ')))
            except Exception as e:  # noqa
                S.log('predare watcher: %s' % e)
            time.sleep(30)

    S.BG_TASKS.append(watcher)
    S.KIND_ROUTE['handoff'] = '#/handoff'

    @S.route('GET', '/api/handoff', role='admin')
    def status(h, a):
        cur = active()
        if cur:
            cur = dict(cur, so_far=report(cur['car'], cur['started'], time.time()))
        past = S.OWN.rows('select id, car, started, ended, modes, limit_mph, label, report from handoffs where ended is not null order by id desc limit 15')
        for p in past:
            p['report'] = json.loads(p['report']) if p['report'] else None
        return dict(active=cur, past=past, now=time.time())

    @S.route('POST', '/api/handoff/start', pin=True, role='admin')
    def start(h, b):
        car = int(b.get('car', 1))
        if active(car):
            raise ValueError('Există deja o predare activă; încheie-o mai întâi.')
        valet, guest = bool(b.get('valet')), bool(b.get('guest'))
        try:
            mph = int(b.get('mph') or 0)
        except (TypeError, ValueError):
            raise ValueError('limita de viteză: număr de mile/oră (50–90)')
        if mph and not 50 <= mph <= 90:
            raise ValueError('limita de viteză: 50–90 mph (80–145 km/h)')
        if not (valet or guest or mph):
            raise ValueError('Alege cel puțin Valet, Guest sau o limită de viteză.')
        try:
            minutes = max(15, min(int(b.get('minutes', 120)), MAX_MIN))
        except (TypeError, ValueError):
            raise ValueError('durata în minute (15–720)')
        pin = pin4(b)
        if (valet or mph) and not pin:
            raise ValueError('PIN-ul mașinii (4 cifre) e necesar pentru Valet / limită de viteză. Nu se salvează.')
        res, modes = [], []
        if guest:
            r = step('guest_on', car)
            res.append(r)
            if r['ok']:
                modes.append('guest')
        if valet:
            r = step('valet_on', car, dict(pin=pin))
            res.append(r)
            if r['ok']:
                modes.append('valet')
        if mph:
            r1 = step('speed_limit_set', car, dict(mph=mph))
            res.append(r1)
            r2 = step('speed_limit_on', car, dict(pin=pin)) if r1['ok'] else dict(step='speed_limit_on', ok=False, reason='limita nu s-a setat')
            res.append(r2)
            if r1['ok'] and r2['ok']:
                modes.append('limită')
        if not modes:
            return dict(ok=False, reason='Nicio funcție nu s-a pornit: ' + '; '.join('%s: %s' % (x['step'], x['reason'] or 'eșuat') for x in res), steps=res)
        now = time.time()
        S.OWN.run('insert into handoffs(car, started, ends, modes, limit_mph, label) values(?,?,?,?,?,?)', (car, now, now + minutes * 60, ','.join(modes), mph or None, re.sub(r'[<>\r\n]', '', str(b.get('label', '')))[:40]))
        return dict(ok=True, steps=res, started=now, ends=now + minutes * 60, partial=len(modes) < sum(1 for x in (guest, valet, mph) if x))

    @S.route('POST', '/api/handoff/end', pin=True, role='admin')
    def end(h, b):
        car = int(b.get('car', 1))
        cur = active(car)
        if not cur:
            raise ValueError('Nu există nicio predare activă.')
        modes = cur['modes'].split(',')
        pin = pin4(b)
        res = []
        if 'limită' in modes:
            res.append(step('speed_limit_off', car, dict(pin=pin)) if pin else dict(step='speed_limit_off', ok=False, reason='fără PIN: dezactivează limita din mașină'))
        if 'valet' in modes:
            res.append(step('valet_off', car, dict(pin=pin)) if pin else dict(step='valet_off', ok=False, reason='fără PIN: dezactivează Valet din mașină'))
        if 'guest' in modes:
            res.append(step('guest_off', car))
        failed = [x for x in res if not x['ok']]
        if failed and not b.get('force'):                    # ceva nu s-a dezactivat (PIN gresit, masina adormita): predarea ramane deschisa ca sa poti reincerca
            return dict(ok=False, can_force=True, steps=res, reason='Nu s-a putut dezactiva: ' + '; '.join('%s (%s)' % (x['step'], x.get('reason') or 'eșuat') for x in failed) + '. Reîncearcă (cu PIN-ul corect, după ce mașina se trezește) sau încheie forțat.')
        now = time.time()
        rep = report(car, cur['started'], now)
        S.OWN.run('update handoffs set ended=?, report=? where id=?', (now, json.dumps(rep), cur['id']))
        S.OWN.kv_set('handoff_warned_%d' % cur['id'], None)
        leftover = [x for x in res if not x['ok']]
        lines = ['Predare încheiată după %d min.' % ((now - cur['started']) // 60)]
        if rep and rep['drives']:
            lines.append('%d curse, %s km, viteză maximă %s km/h%s.' % (rep['drives'], str(rep['km']).replace('.', ','), rep['speed_max'], (' · ' + ' → '.join(rep['places'])) if rep['places'] else ''))
        elif rep is not None:
            lines.append('Nicio cursă în acest timp.')
        if leftover:
            lines.append('⚠ De dezactivat manual: ' + ', '.join(x['step'] for x in leftover))
        S.notify('handoff', '🔑 Predare mașină încheiată', ' '.join(lines))
        return dict(ok=True, steps=res, report=rep, manual=bool(leftover))

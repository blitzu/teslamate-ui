"""Intretinere (remindere dupa km si timp, jurnal de service) si anvelope (seturi, km pe set, adancime profil, trend presiune si scurgeri lente).
Datele sunt in baza proprie (nu in TeslaMate). Odometrul vine din TeslaMate (max positions.odometer) sau din MQTT."""
import calendar
import datetime as dt
import math
import statistics
import time

_odo = [0.0, None]


def add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def due(item, odo, today):
    """Starea unui element: km/zile ramase, progres 0..1+, status ok/soon/overdue/unknown."""
    km_left = days_left = None
    prog = []
    if item.get('interval_km') and item.get('last_km') is not None and odo is not None:
        km_left = item['last_km'] + item['interval_km'] - odo
        prog.append((odo - item['last_km']) / item['interval_km'])
    if item.get('interval_months') and item.get('last_date'):
        nxt = add_months(dt.date.fromisoformat(item['last_date']), int(item['interval_months']))
        days_left = (nxt - today).days
        total = max(1, (nxt - dt.date.fromisoformat(item['last_date'])).days)
        prog.append(1 - days_left / total)
    if not prog:
        return dict(km_left=None, days_left=None, progress=0, status='unknown')
    late = (km_left is not None and km_left < 0) or (days_left is not None and days_left < 0)
    soon = (km_left is not None and item['interval_km'] and km_left < 0.1 * item['interval_km']) or (days_left is not None and days_left < min(30, total * 0.2))
    return dict(km_left=None if km_left is None else round(km_left), days_left=days_left, progress=round(max(prog), 3), status='overdue' if late else 'soon' if soon else 'ok')


def slope(points):
    """Panta (unitati/zi) a unei regresii liniare pe [(ziua, valoare)]."""
    n = len(points)
    if n < 4:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    mx, my = sum(xs) / n, sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else None


def norm_pressure(bar, temp_c):
    """Presiunea (manometrica, bar) readusa la 20 C, din legea gazelor pe presiunea absoluta."""
    return (bar + 1.013) * 293.15 / (temp_c + 273.15) - 1.013


def init(S):
    S.OWN.migrate('service', [
        'create table maint_items (id integer primary key, name text not null, interval_km integer, interval_months integer, last_date text, last_km real, notes text, notified_at real, notified_state text)',
        'create table service_log (id integer primary key, date text not null, odometer real, category text, description text, cost real, notes text)',
        'create table tire_sets (id integer primary key, name text not null, kind text, brand text, size text, mounted_date text, mounted_km real, removed_date text, removed_km real, notes text)',
        'create table tire_checks (id integer primary key, set_id integer not null references tire_sets(id) on delete cascade, date text not null, odometer real, d_fl real, d_fr real, d_rl real, d_rr real, notes text)',
    ])
    S.KIND_ROUTE['maint'] = '#/service'

    def odometer(car=1):
        now = time.time()
        if now - _odo[0] < 120 and _odo[1] is not None:
            return _odo[1]
        v = (S.LIVE.get(car) or {}).get('odometer')                  # valoarea live (MQTT) evita scanarea tabelei positions
        if v is None:
            try:
                r = S.q('select max(odometer) o from positions where car_id=%s', (car,))
                v = r[0]['o'] if r else None
            except Exception:  # noqa
                pass
        _odo[:] = [now, v]
        return v

    def num(x):
        if x in (None, ''):
            return None
        v = float(str(x).replace(',', '.'))
        if not math.isfinite(v) or v < 0:
            raise ValueError('valoare invalidă: %s' % x)
        return v

    def day(x):
        return dt.date.fromisoformat(str(x)).isoformat() if x else None

    def odometer_at(d, car=1):
        """Odometrul masinii dimineata in ziua d (ultima valoare inregistrata inaintea ei, ora locala) sau None daca TeslaMate nu are date atunci."""
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(S.LOCAL_TZ)
        except Exception:  # noqa
            tz = dt.timezone.utc
        start = dt.datetime(d.year, d.month, d.day, tzinfo=tz).astimezone(dt.timezone.utc).replace(tzinfo=None)
        r = S.q('select odometer from positions where car_id=%s and odometer is not null and date < %s order by date desc limit 1', (car, start))
        return float(r[0]['odometer']) if r else None

    # ------------------------------------------------------------- intretinere
    @S.route('GET', '/api/service')
    def overview(h, a):
        odo = odometer()
        today = dt.date.today()
        items = [dict(i, **due(i, odo, today)) for i in S.OWN.rows('select * from maint_items order by id')]
        order = {'overdue': 0, 'soon': 1, 'ok': 2, 'unknown': 3}
        items.sort(key=lambda i: (order[i['status']], i['name']))
        return dict(odometer=odo, items=items, log=S.OWN.rows('select * from service_log order by date desc, id desc limit 100'))

    @S.route('POST', '/api/service/item', pin=True, role='family')
    def item(h, b):
        if b.get('delete'):
            S.OWN.run('delete from maint_items where id=?', (int(b['id']),))
            return dict(ok=True)
        name = str(b.get('name') or '').strip()[:80]
        if not name:
            raise ValueError('nume lipsa')
        vals = (name, int(num(b.get('interval_km')) or 0) or None, int(num(b.get('interval_months')) or 0) or None, day(b.get('last_date')), num(b.get('last_km')), str(b.get('notes') or '')[:300])
        if b.get('id'):
            S.OWN.run('update maint_items set name=?, interval_km=?, interval_months=?, last_date=?, last_km=?, notes=?, notified_state=null where id=?', vals + (int(b['id']),))
        else:
            S.OWN.run('insert into maint_items(name, interval_km, interval_months, last_date, last_km, notes) values(?,?,?,?,?,?)', vals)
        return dict(ok=True)

    @S.route('POST', '/api/service/done', pin=True, role='family')
    def done(h, b):
        it = S.OWN.one('select * from maint_items where id=?', (int(b['id']),))
        if not it:
            raise S.NotFound()
        d = day(b.get('date')) or dt.date.today().isoformat()
        odo = num(b.get('odometer'))
        if odo is None and b.get('date') and d < dt.date.today().isoformat():           # facut in trecut: kilometrajul de atunci, nu cel de azi
            try:
                past = odometer_at(dt.date.fromisoformat(d))
                odo = None if past is None else round(past)
            except Exception:  # noqa
                odo = None
        elif odo is None:
            odo = odometer()
        S.OWN.run('update maint_items set last_date=?, last_km=?, notified_at=null, notified_state=null where id=?', (d, odo, it['id']))
        S.OWN.run('insert into service_log(date, odometer, category, description, cost, notes) values(?,?,?,?,?,?)', (d, odo, it['name'], it['name'], num(b.get('cost')), str(b.get('notes') or '')[:300]))
        return dict(ok=True)

    @S.route('POST', '/api/service/log', pin=True, role='family')
    def log_entry(h, b):
        if b.get('delete'):
            S.OWN.run('delete from service_log where id=?', (int(b['id']),))
            return dict(ok=True)
        desc = str(b.get('description') or '').strip()[:200]
        if not desc:
            raise ValueError('descriere lipsa')
        S.OWN.run('insert into service_log(date, odometer, category, description, cost, notes) values(?,?,?,?,?,?)',
                  (day(b.get('date')) or dt.date.today().isoformat(), num(b.get('odometer')) if b.get('odometer') not in (None, '') else odometer(), str(b.get('category') or '')[:60], desc, num(b.get('cost')), str(b.get('notes') or '')[:300]))
        return dict(ok=True)

    def reminders():
        time.sleep(180)
        while True:
            try:
                odo, today, now = odometer(), dt.date.today(), time.time()
                for i in S.OWN.rows('select * from maint_items'):
                    d = due(i, odo, today)
                    if d['status'] not in ('soon', 'overdue'):
                        continue
                    last = i['notified_at'] or 0
                    if i['notified_state'] == d['status'] and now - last < (7 if d['status'] == 'overdue' else 30) * 86400:
                        continue
                    left = []
                    if d['km_left'] is not None:
                        left.append('%d km' % d['km_left'] if d['km_left'] >= 0 else 'depășit cu %d km' % -d['km_left'])
                    if d['days_left'] is not None:
                        left.append('%d zile' % d['days_left'] if d['days_left'] >= 0 else 'depășit cu %d zile' % -d['days_left'])
                    S.notify('maint', '🔧 %s: %s' % (i['name'], 'scadent' if d['status'] == 'overdue' else 'în curând'), ', '.join(left) + '. Deschide Întreținere ca să marchezi ca făcut.')
                    S.OWN.run('update maint_items set notified_at=?, notified_state=? where id=?', (now, d['status'], i['id']))
            except Exception as e:  # noqa
                S.log('remindere intretinere: %s' % e)
            time.sleep(6 * 3600)

    S.BG_TASKS.append(reminders)

    # ------------------------------------------------------------- anvelope
    def sets_with_km(odo):
        out = []
        for s in S.OWN.rows('select * from tire_sets order by (removed_date is not null), mounted_date desc, id desc'):
            end = s['removed_km'] if s['removed_km'] is not None else (None if s['removed_date'] else odo)
            s['km'] = round(end - s['mounted_km']) if (end is not None and s['mounted_km'] is not None) else None
            s['active'] = s['mounted_date'] is not None and s['removed_date'] is None
            s['checks'] = S.OWN.rows('select * from tire_checks where set_id=? order by date desc, id desc limit 12', (s['id'],))
            out.append(s)
        return out

    def km_for(d, override, what):
        """Kilometrajul la data d: cel dat de utilizator, altfel din TeslaMate; eroare clara daca nu se poate afla."""
        if override not in (None, ''):
            return num(override)
        v = odometer_at(d)
        if v is None:
            raise ValueError('Nu am date despre odometru la %s (%s). Introdu kilometrajul de atunci manual.' % (d.isoformat(), what))
        return round(v)

    def apply_dates(sid, b):
        """Pune datele montarii/demontarii unui set si calculeaza kilometrajul din odometrul masinii; un set montat fara data de demontare e cel activ (cel activ de pana atunci se demonteaza la aceeasi data)."""
        today = dt.date.today()
        md = dt.date.fromisoformat(day(b.get('mounted_date'))) if b.get('mounted_date') else None
        rd = dt.date.fromisoformat(day(b.get('removed_date'))) if b.get('removed_date') else None
        if rd and not md:
            raise ValueError('Data demontării cere și data montării.')
        if (md and md > today) or (rd and rd > today):
            raise ValueError('Datele nu pot fi în viitor.')
        if md and rd and rd < md:
            raise ValueError('Demontarea nu poate fi înaintea montării.')
        if not md:
            if sid:
                S.OWN.run('update tire_sets set mounted_date=null, mounted_km=null, removed_date=null, removed_km=null where id=?', (sid,))
            return
        mkm = km_for(md, b.get('km_start'), 'montare')
        rkm = km_for(rd, b.get('km_end'), 'demontare') if rd else None
        if rkm is not None and rkm < mkm:
            raise ValueError('Kilometrajul la demontare e mai mic decât la montare.')
        if not sid:
            return
        explicit_end = bool(rd)
        if not rd:                                               # fara demontare: se opreste cand incepe urmatorul set (cel montat mai tarziu), daca exista
            nxt = S.OWN.one('select mounted_date, mounted_km from tire_sets where mounted_date > ? and id != ? order by mounted_date limit 1', (md.isoformat(), sid))
            if nxt:
                rd, rkm = dt.date.fromisoformat(nxt['mounted_date']), nxt['mounted_km']
        if not explicit_end:                                     # setul anterior ramas deschis se inchide la montarea acestuia (si cand mai exista un set ulterior)
            S.OWN.run('update tire_sets set removed_date=?, removed_km=? where mounted_date is not null and removed_date is null and id != ? and mounted_date <= ?', (md.isoformat(), mkm, sid, md.isoformat()))
        S.OWN.run('update tire_sets set mounted_date=?, mounted_km=?, removed_date=?, removed_km=? where id=?', (md.isoformat(), mkm, rd.isoformat() if rd else None, rkm, sid))

    @S.route('GET', '/api/tires')
    def tires(h, a):
        return dict(odometer=odometer(), sets=sets_with_km(odometer()))

    @S.route('POST', '/api/tires/set', pin=True, role='family')
    def tire_set(h, b):
        act = b.get('action')
        odo = odometer()
        if act == 'delete':
            S.OWN.run('delete from tire_sets where id=?', (int(b['id']),))
        elif act == 'mount' and b.get('date'):                       # montat la o data din trecut: kilometrajul vine din odometrul de atunci
            apply_dates(int(b['id']), dict(mounted_date=b.get('date'), km_start=b.get('km_start')))
        elif act == 'dates':                                         # seteaza/corecteaza datele unui set; kilometrajul se recalculeaza
            if not S.OWN.one('select 1 x from tire_sets where id=?', (int(b['id']),)):
                raise S.NotFound()
            apply_dates(int(b['id']), b)
        elif act == 'mount':                                         # monteaza setul acum si demonteaza automat pe cel activ
            today = dt.date.today().isoformat()
            S.OWN.run('update tire_sets set removed_date=?, removed_km=? where mounted_date is not null and removed_date is null and id != ?', (today, odo, int(b['id'])))
            S.OWN.run('update tire_sets set mounted_date=?, mounted_km=?, removed_date=null, removed_km=null where id=?', (today, odo, int(b['id'])))
        elif act == 'unmount':
            S.OWN.run('update tire_sets set removed_date=?, removed_km=? where id=? and mounted_date is not null and removed_date is null', (dt.date.today().isoformat(), odo, int(b['id'])))
        else:
            name = str(b.get('name') or '').strip()[:60]
            if not name:
                raise ValueError('nume lipsa')
            if b.get('mounted_date') or b.get('removed_date'):       # valideaza datele INAINTE de a crea setul
                apply_dates(0, b)
            cur = S.OWN.run('insert into tire_sets(name, kind, brand, size, notes) values(?,?,?,?,?)', (name, str(b.get('kind') or '')[:20], str(b.get('brand') or '')[:60], str(b.get('size') or '')[:30], str(b.get('notes') or '')[:200]))
            if b.get('mounted_date'):
                apply_dates(cur.lastrowid, b)
        return dict(ok=True)

    @S.route('POST', '/api/tires/check', pin=True, role='family')
    def tire_check(h, b):
        sid = int(b['set_id'])
        if not S.OWN.one('select 1 x from tire_sets where id=?', (sid,)):
            raise S.NotFound()
        cd = day(b.get('date')) or dt.date.today().isoformat()
        if cd < dt.date.today().isoformat():
            try:
                past = odometer_at(dt.date.fromisoformat(cd))
            except Exception:  # noqa
                past = None
            cod = None if past is None else round(past)
        else:
            cod = odometer()
        S.OWN.run('insert into tire_checks(set_id, date, odometer, d_fl, d_fr, d_rl, d_rr, notes) values(?,?,?,?,?,?,?,?)',
                  (sid, cd, cod, num(b.get('d_fl')), num(b.get('d_fr')), num(b.get('d_rl')), num(b.get('d_rr')), str(b.get('notes') or '')[:200]))
        return dict(ok=True)

    def pressure_series(car, days):
        """Pe zile: mediana presiunii normalizate la 20 C, pentru fiecare roata (doar esantioane cu masina oprita, valori > 0)."""
        if S.has_cars() in (None, False):
            return None
        since = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
        rows = S.q("""select to_char(date_trunc('day', date), 'YYYY-MM-DD') d, outside_temp t, tpms_pressure_fl fl, tpms_pressure_fr fr, tpms_pressure_rl rl, tpms_pressure_rr rr
                      from positions where car_id=%s and date >= %s and tpms_pressure_fl > 0 and outside_temp is not null and coalesce(speed, 0) = 0 order by date""", (car, since))
        by = {}
        for r in rows:
            for w in ('fl', 'fr', 'rl', 'rr'):
                if r[w]:
                    by.setdefault(w, {}).setdefault(r['d'], []).append(norm_pressure(r[w], r['t']))
        return {w: [[d, round(statistics.median(v), 3)] for d, v in sorted(dd.items())] for w, dd in by.items()}

    def leak_check(series):
        out = {}
        for w, pts in (series or {}).items():
            xs = [(dt.date.fromisoformat(d) - dt.date(2000, 1, 1)).days for d, _ in pts]
            sl = slope(list(zip(xs, [p for _, p in pts])))
            out[w] = dict(per_day=None if sl is None else round(sl, 4), leaking=bool(sl is not None and len(pts) >= 7 and sl < -0.008 and (pts[0][1] - pts[-1][1]) > 0.1))
        return out

    @S.route('GET', '/api/tires/pressure')
    def pressure(h, a):
        if S.has_cars() is None:
            raise S.DBDown()
        series = pressure_series(int(a.get('car', 1)), max(7, min(int(a.get('days', 60)), 365)))
        if series is None:                                           # demo
            today = dt.date.today()
            series = {w: [[(today - dt.timedelta(days=30 - i)).isoformat(), round(2.85 - (0.012 * i if w == 'rl' else 0.001 * i), 3)] for i in range(0, 31, 2)] for w in ('fl', 'fr', 'rl', 'rr')}
        return dict(series=series, leaks=leak_check(series))

    def leak_alerts():
        time.sleep(600)
        last = ''
        while True:
            today = dt.date.today().isoformat()
            if today != last and S.has_cars():
                last = today
                try:
                    lk = leak_check(pressure_series(1, 28))
                    names = dict(fl='față stânga', fr='față dreapta', rl='spate stânga', rr='spate dreapta')
                    bad = [(names[w], v['per_day']) for w, v in lk.items() if v['leaking']]
                    acfg = S.ALERTS.cfg()
                    if bad and acfg['enabled'] and acfg['tire_leak']['on'] and S.ALERTS.cool('tire_leak:1', time.time()):
                        S.ALERTS.fire('tire_leak', '🛞 Posibilă scurgere lentă la anvelope', '; '.join('%s: %.3f bar/zi' % b for b in bad) + ' (presiune adusă la 20°C).')
                except Exception as e:  # noqa
                    S.log('scurgeri anvelope: %s' % e)
            time.sleep(3600)

    S.BG_TASKS.append(leak_alerts)
    S.features_service_due = due

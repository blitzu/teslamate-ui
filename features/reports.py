"""Rapoarte periodice (saptamanal, lunar, anual) cu rezumat text pentru Telegram / notificari si pagina de rapoarte.
Folosesc doar date deja existente: curse, incarcari (cost efectiv), sursa energiei (cost real din HA), scurgere in repaus, comparatia cu masina termica."""
import datetime as dt
import json
import re
import time

MONTHS = ['ianuarie', 'februarie', 'martie', 'aprilie', 'mai', 'iunie', 'iulie', 'august', 'septembrie', 'octombrie', 'noiembrie', 'decembrie']
DEFAULT = dict(weekly=True, monthly=True, hour=8)


def pct(a, b):
    return None if not b else round((a - b) / b * 100)


def delta_txt(a, b):
    p = pct(a, b)
    return '' if p is None else ('%+d%%' % p)


def fmt(x, d=1):
    return ('%.*f' % (d, x)).replace('.', ',')


def init(S):
    S.OWN.migrate('reports', ['create table reports (id integer primary key, ts real not null, kind text not null, start text not null, end text not null, title text, text text, data text)'])
    S.KIND_ROUTE['report'] = '#/reports'

    def tz():
        try:
            import zoneinfo
            return zoneinfo.ZoneInfo(S.LOCAL_TZ)
        except Exception:  # noqa
            return dt.timezone.utc

    def to_utc(d):
        """Miezul noptii local al unei date -> datetime UTC naiv (ISO)."""
        loc = dt.datetime(d.year, d.month, d.day, tzinfo=tz())
        return loc.astimezone(dt.timezone.utc).replace(tzinfo=None).isoformat()

    def local_day(iso):
        return dt.datetime.fromisoformat(iso).replace(tzinfo=dt.timezone.utc).astimezone(tz()).strftime('%Y-%m-%d')

    def charges_in(car, a, b):
        rows = [r for r in S._charges_rows(car, 5000, 0, None, dt.datetime.fromisoformat(str(a)), dt.datetime.fromisoformat(str(b))) if a <= r['start_date'] < b]
        if S.ha_ok() and S.HA['grid']:
            budget = 15
            for r in rows:
                try:
                    val, fetched = S.real_cost(r, budget > 0)
                    budget -= 1 if fetched else 0
                    r['cost_real'] = val
                except Exception:  # noqa
                    budget = 0
        return S.decorate(rows)

    def core(car, start, end):
        a, b = to_utc(start), to_utc(end)
        drives = S.q(S.DRIVE_SQL + ' and d.start_date >= %s and d.start_date < %s order by d.start_date', (car, a, b))
        ch = charges_in(car, a, b)
        km = sum(d['distance'] or 0 for d in drives)
        kwh_d = sum(d['kwh'] or 0 for d in drives if d['kwh'] is not None)
        km_e = sum(d['distance'] or 0 for d in drives if d['kwh'] is not None)
        cost = sum(c['cost_eff'] or 0 for c in ch)
        kwh_c = sum(c['charge_energy_added'] or 0 for c in ch if c['cost_eff'] is not None)
        added = sum(c['charge_energy_added'] or 0 for c in ch)
        try:
            price = float(S.cget('price_grid', 'PRICE_GRID', '') or 0)
        except ValueError:
            price = 0
        solar = used = 0.0
        for c in ch:
            if c.get('cost_real') is not None and (price or c.get('tariff')):
                p = price or float(c['tariff'])
                use = c.get('charge_energy_used') or c['charge_energy_added'] or 0
                used += use
                solar += max(0.0, use - c['cost_real'] / p)
        by_day = {}
        for d in drives:
            k = local_day(d['start_date'])
            by_day[k] = by_day.get(k, 0) + (d['distance'] or 0)
        ev_total = S.DRIVECOST.total(car, [d['id'] for d in drives]) if S.DRIVECOST and drives else None
        ice = S.ice_calc([dict(day=k, km=v) for k, v in sorted(by_day.items())], kwh_d, cost, kwh_c, ev_total=ev_total) if by_day else dict(enabled=False)
        longest = max(drives, key=lambda d: d['distance'] or 0) if drives else None
        eff = [d for d in drives if d['kwh'] and d['kwh'] > 0 and (d['distance'] or 0) >= 10]
        best = min(eff, key=lambda d: d['kwh'] / d['distance']) if eff else None
        pw = S.q('select max(ch.charger_power) p from charges ch join charging_processes cp on cp.id = ch.charging_process_id where cp.car_id=%s and cp.start_date >= %s and cp.start_date < %s', (car, a, b))
        return dict(start=start.isoformat(), end=(end - dt.timedelta(days=1)).isoformat(), drives=len(drives), km=round(km, 1), kwh=round(kwh_d, 1), wh_km=round(kwh_d * 1000 / km_e) if km_e > 20 else None,
                    drive_min=round(sum(d['duration_min'] or 0 for d in drives)), speed_max=max([d['speed_max'] or 0 for d in drives] or [0]),
                    longest=dict(km=round(longest['distance'], 1), a=longest['start_name'], b=longest['end_name']) if longest else None,
                    best=dict(wh_km=round(best['kwh'] * 1000 / best['distance']), km=round(best['distance'], 1)) if best else None,
                    charges=len(ch), cost_n=sum(1 for c in ch if c['cost_eff'] is not None), charged=round(added, 1), cost=round(cost, 2), price=round(cost / kwh_c, 3) if kwh_c else None, dc=sum(1 for c in ch if c['dc']), power_max=(pw[0]['p'] if pw else None),
                    solar_pct=round(solar / used * 100) if used > 0 else None, ice=ice if ice.get('enabled') else None)

    def idle_drain(car, start, end):
        days = (dt.date.today() - start).days + 2
        if days > 60:
            return None
        try:
            rep = S.sleep_report(car, days, full=True)
            a, b = to_utc(start), to_utc(end)
            rows = [i for i in rep['idle_all'] if a <= i['start'] < b and i.get('kwh') is not None]
            return round(sum(i['kwh'] for i in rows), 1) if rows else None
        except Exception as e:  # noqa
            S.log('raport scurgere repaus: %s' % e)
            return None

    def period(kind, today=None):
        today = today or dt.date.today()
        if kind == 'week':
            mon = today - dt.timedelta(days=today.weekday())
            return mon - dt.timedelta(days=7), mon
        if kind == 'month':
            first = today.replace(day=1)
            prev = (first - dt.timedelta(days=1)).replace(day=1)
            return prev, first
        if kind == 'year':
            return today.replace(month=1, day=1), today + dt.timedelta(days=1)
        raise ValueError('kind = week | month | year')

    def text(kind, r, prev, drain):
        cu = S.CURRENCY if str(S.CURRENCY).lower() not in ('ron', 'lei') else 'lei'
        a, b = dt.date.fromisoformat(r['start']), dt.date.fromisoformat(r['end'])
        title = {'week': '📊 Raport săptămânal (%d %s – %d %s)' % (a.day, MONTHS[a.month - 1][:3], b.day, MONTHS[b.month - 1][:3]),
                 'month': '📊 Raport lunar – %s %d' % (MONTHS[a.month - 1], a.year), 'year': '📊 %d în cifre (până azi)' % a.year}[kind]
        L = []
        if r['drives']:
            L.append('🚗 %s km în %d curse · %s kWh%s' % (fmt(r['km'], 0), r['drives'], fmt(r['kwh']), (' · %d Wh/km' % r['wh_km']) if r['wh_km'] else ''))
        else:
            L.append('🚗 Nicio cursă în perioadă.')
        if r['charges']:
            part = (' (cost cunoscut la %d din %d)' % (r['cost_n'], r['charges'])) if r.get('cost_n') is not None and r['cost_n'] < r['charges'] else ''
            L.append('⚡ %d încărcări · +%s kWh · %s %s%s%s%s' % (r['charges'], fmt(r['charged']), fmt(r['cost'], 2), cu, (' (%s %s/kWh)' % (fmt(r['price'], 2), cu)) if r['price'] else '', part, (' · ~%d%% din soare' % r['solar_pct']) if r['solar_pct'] is not None else ''))
        if r.get('ice'):
            i = r['ice']
            L.append('⛽ Cu o termică (%s l/100 km, %s l): %s %s%s' % (fmt(i['l100']), fmt(i['liters']), fmt(i['cost'], 0), cu, (' → economie %s %s' % (fmt(i['saving'], 0), cu)) if i.get('saving') is not None else ''))
        if drain is not None:
            L.append('😴 Scurgere în repaus: %s kWh' % fmt(drain))
        rec = []
        if r['longest']:
            rec.append('cea mai lungă cursă %s km' % fmt(r['longest']['km'], 0))
        if r['best']:
            rec.append('cel mai bun consum %d Wh/km' % r['best']['wh_km'])
        if r['power_max']:
            rec.append('putere max la încărcare %s kW' % fmt(r['power_max'], 0))
        if rec:
            L.append('🏆 ' + ' · '.join(rec))
        if prev and prev['drives']:
            cmp = []
            for lab, k in (('km', 'km'), ('kWh', 'kwh'), ('cost', 'cost')):
                d = delta_txt(r[k], prev[k])
                if d:
                    cmp.append('%s %s' % (lab, d))
            if cmp:
                L.append('↔ față de perioada anterioară: ' + ', '.join(cmp))
        return title, '\n'.join(L)

    def prev_range(kind, a, b):
        """Perioada de comparatie: saptamana de dinainte, respectiv LUNA calendaristica de dinainte (nu \"aceeasi durata\": lunile au 28-31 de zile)."""
        if kind == 'month':
            return (a - dt.timedelta(days=1)).replace(day=1), a
        return a - (b - a), a

    def generate(kind, send=False, car=1, today=None):
        a, b = period(kind, today)
        r = core(car, a, b)
        prev = core(car, *prev_range(kind, a, b)) if kind != 'year' else None
        drain = idle_drain(car, a, b)
        title, body = text(kind, r, prev, drain)
        data = dict(report=r, previous=prev, drain=drain)
        S.OWN.run('insert into reports(ts, kind, start, end, title, text, data) values(?,?,?,?,?,?,?)', (time.time(), kind, r['start'], r['end'], title, body, json.dumps(data)))
        if send:
            S.notify('report', title, body)
        return dict(title=title, text=body, data=data)

    S.REPORTS = dict(generate=generate, period=period, core=core, text=text)

    def cfg():
        c = dict(DEFAULT)
        c.update({k: v for k, v in (S.OWN.kv_get('reports_cfg', {}) or {}).items() if k in DEFAULT})
        return c

    def scheduler():
        time.sleep(240)
        while True:
            try:
                now = dt.datetime.now()
                c = cfg()
                last = S.OWN.kv_get('reports_last', {}) or {}
                wk, mo = '%d-W%02d' % now.isocalendar()[:2], now.strftime('%Y-%m')
                if not last:                                           # prima rulare: nu genera acum rapoarte "restante", incepe de la urmatoarea saptamana/luna
                    S.OWN.kv_set('reports_last', {'weekly': wk, 'monthly': mo})
                elif now.hour >= int(c['hour']) and S.has_cars():
                    if c['weekly'] and last.get('weekly') != wk:       # luni, sau prima verificare dupa o zi ratata (aplicatia oprita)
                        generate('week', send=True)
                        last['weekly'] = wk
                        S.OWN.kv_set('reports_last', last)             # se noteaza DOAR dupa succes: o eroare trecatoare se reincearca
                    if c['monthly'] and last.get('monthly') != mo:
                        generate('month', send=True)
                        last['monthly'] = mo
                        S.OWN.kv_set('reports_last', last)
            except Exception as e:  # noqa
                S.log('rapoarte: %s' % e)
            time.sleep(600)

    S.BG_TASKS.append(scheduler)

    @S.route('GET', '/api/reports')
    def list_reports(h, a):
        rows = S.OWN.rows('select id, ts, kind, start, end, title, text, data from reports order by ts desc limit 40')
        for r in rows:
            r['data'] = json.loads(r['data']) if r['data'] else None
        return dict(reports=rows, config=cfg())

    @S.route('POST', '/api/reports/generate', pin=True, role='user')
    def gen(h, b):
        if S.has_cars() is None:
            raise S.DBDown()
        if S.has_cars() is False:
            raise ValueError('Raportul cere o mașină în TeslaMate (nu merge în demo).')
        return dict(ok=True, report=generate(b.get('kind', 'week'), bool(b.get('send'))))

    @S.route('POST', '/api/reports/config', pin=True, role='admin')
    def set_cfg(h, b):
        c = dict(weekly=bool(b.get('weekly')), monthly=bool(b.get('monthly')), hour=max(0, min(int(b.get('hour', 8)), 23)))
        S.OWN.kv_set('reports_cfg', c)
        return dict(ok=True, config=c)

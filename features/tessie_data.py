"""Datele aduse din Tessie care NU au loc in TeslaMate: staționari (consum cat stai parcat), sanatatea bateriei (capacitate in timp), alerte firmware, autopilot si putere ESTIMATA pe cursa,
locuri salvate. Importul (importer.py) le preda dupa commit; aici stau in baza proprie a aplicatiei (DATA_DIR/app.db) si au pagina lor (#/tessie). "Anuleaza importul" le sterge odata cu restul."""
import time

TABLES = ('tessie_idle', 'tessie_health', 'tessie_alert', 'tessie_drive', 'tessie_charge')
STEPS = [
    'create table tessie_idle (car_id integer not null, tessie_id integer not null, started_at real not null, ended_at real not null, lat real, lon real, place text, saved text, soc0 integer, soc1 integer,'
    ' range_used real, energy_used real, charger_energy real, climate_frac real, sentry_frac real, primary key (car_id, tessie_id))',
    'create index tessie_idle_t on tessie_idle(car_id, started_at)',
    'create table tessie_health (car_id integer not null, ts real not null, odometer real, max_range real, capacity real, primary key (car_id, ts))',
    'create table tessie_alert (car_id integer not null, ts real not null, name text not null, description text, impact text, cond text, clear_cond text, fleet_count integer, incidence real,'
    ' primary key (car_id, ts, name))',
    'create table tessie_drive (car_id integer not null, tessie_id integer not null, drive_id integer, started_at real, ended_at real, autopilot_km real, avg_speed real, energy_used real,'
    ' rated_range_used real, tag text, est_power_max real, est_power_min real, est_power_avg real, start_saved text, end_saved text, primary key (car_id, tessie_id))',
    'create index tessie_drive_d on tessie_drive(drive_id)',
    'create table tessie_charge (car_id integer not null, tessie_id integer not null, charge_id integer, started_at real, ended_at real, max_range real, capacity real, since_last_charge real,'
    ' saved text, fast integer, curve_points integer, primary key (car_id, tessie_id))',
]
MAX_ALERT_TEXT = 400


def num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def text(x, n=MAX_ALERT_TEXT):
    return str(x)[:n] if x not in (None, '') else None


def save(S, data):
    """Scrie (upsert) datele unei rulari de import. Idempotent: o a doua rulare le rescrie, nu le dubleaza."""
    car = int(data['car'])
    own = S.OWN
    with own.tx() as t:
        t.executemany('insert or replace into tessie_idle values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [
            (car, int(x['id']), x['started_at'], x['ended_at'], num(x.get('latitude')), num(x.get('longitude')), text(x.get('location'), 200), text(x.get('saved_location'), 80), x.get('starting_battery'),
             x.get('ending_battery'), num(x.get('rated_range_used')), num(x.get('energy_used')), num(x.get('charger_energy_used')), num(x.get('climate_fraction')), num(x.get('sentry_fraction')))
            for x in data.get('idles', []) if x.get('id') is not None])
        t.executemany('insert or replace into tessie_health values (?,?,?,?,?)', [(car, x['ts'], num(x.get('odometer')), num(x.get('max_range')), num(x.get('capacity'))) for x in data.get('health', [])])
        for c in data.get('charges', []):
            if c.get('max_range') and c.get('capacity'):                             # fiecare incarcare are si ea capacitatea masurata: completeaza graficul (fara sa suprascrie masuratorile dedicate)
                t.execute('insert or ignore into tessie_health values (?,?,?,?,?)', (car, c['ended_at'], num(c.get('odometer')), num(c.get('max_range')), num(c.get('capacity'))))
        t.executemany('insert or replace into tessie_alert values (?,?,?,?,?,?,?,?,?)', [
            (car, float(x['timestamp']), text(x.get('name'), 120) or '?', text(x.get('description')), text(x.get('impact')), text(x.get('condition')), text(x.get('clear_condition')),
             int(x['recent_fleet_count']) if x.get('recent_fleet_count') not in (None, '') else None, num(float(x['incidence_rate'])) if x.get('incidence_rate') not in (None, '') else None)
            for x in data.get('alerts', [])])
        t.executemany('insert or replace into tessie_drive values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', [
            (car, int(x['tessie_id']), x.get('drive_id'), x.get('started_at'), x.get('ended_at'), num(x.get('autopilot_km')), num(x.get('avg_speed')), num(x.get('energy_used')), num(x.get('rated_range_used')),
             text(x.get('tag'), 60), x.get('est_power_max'), x.get('est_power_min'), x.get('est_power_avg'), text(x.get('start_saved'), 80), text(x.get('end_saved'), 80)) for x in data.get('drives', [])])
        t.executemany('insert or replace into tessie_charge values (?,?,?,?,?,?,?,?,?,?,?)', [
            (car, int(x['tessie_id']), x.get('charge_id'), x.get('started_at'), x.get('ended_at'), num(x.get('max_range')), num(x.get('capacity')), num(x.get('since_last_charge')), text(x.get('saved'), 80),
             1 if x.get('fast') else 0, x.get('curve_points')) for x in data.get('charges', [])])
    tags = [(x['drive_id'], x['tag']) for x in data.get('drives', []) if x.get('tag') and x.get('drive_id')]
    if tags and getattr(S, 'TAGS', None):
        from .tags import clean_name
        with own.tx() as t:
            for drive_id, tag in tags:                                                    # eticheta cursei din Tessie devine eticheta din aplicatie (aceeasi regula de curatare ca la cele puse de mana)
                name = clean_name(tag)
                if not name:
                    continue
                t.execute('insert or ignore into tags(name) values(?)', (name,))
                tid = t.execute('select id from tags where name=?', (name,)).fetchone()[0]
                t.execute("insert or ignore into tag_links(kind, ref, tag_id) values('drive', ?, ?)", (drive_id, tid))
    return dict(idles=len(data.get('idles', [])), health=len(data.get('health', [])), alerts=len(data.get('alerts', [])))


def purge(S):
    """Sterge tot ce a adus importul in baza proprie (la "Anuleaza importul")."""
    with S.OWN.tx() as t:
        for name in TABLES:
            t.execute('delete from %s' % name)


def summary(S, car):
    own = S.OWN
    q = lambda sql: own.one(sql, (car,)) or {}
    idl = q('select count(*) n, min(started_at) first, max(ended_at) last, sum(energy_used) kwh, sum(ended_at-started_at) secs from tessie_idle where car_id=?')
    hl = q('select count(*) n, min(ts) first, max(ts) last from tessie_health where car_id=?')
    al = q('select count(*) n, count(distinct name) kinds, min(ts) first, max(ts) last from tessie_alert where car_id=?')
    dr = q('select count(*) n, sum(autopilot_km) autopilot_km, sum(est_power_max is not null) with_power from tessie_drive where car_id=?')
    ch = q('select count(*) n, sum(curve_points > 0) with_curve from tessie_charge where car_id=?')
    return dict(idles=idl, health=hl, alerts=al, drives=dr, charges=ch, any=bool((idl.get('n') or 0) + (hl.get('n') or 0) + (al.get('n') or 0) + (dr.get('n') or 0)))


def init(S):
    S.OWN.migrate('tessie_data', STEPS)
    cache = dict(t=0.0, v=False)

    def has_data():
        if time.time() - cache['t'] > 60:                                               # intrarea din meniu apare doar daca exista date Tessie (o numaratoare ieftina, tinuta 60 s)
            r = S.OWN.one('select (select count(*) from tessie_idle) + (select count(*) from tessie_health) + (select count(*) from tessie_alert) + (select count(*) from tessie_drive) n')
            cache.update(t=time.time(), v=bool(r and r['n']))
        return cache['v']
    S.tessie_has_data = has_data
    S.tessie_save = lambda data: (save(S, data), cache.update(t=0.0))[0]
    S.tessie_purge = lambda: (purge(S), cache.update(t=0.0))[0]

    def car_of(a):
        return int(a.get('car', 1))

    @S.route('GET', '/api/tessie/summary')
    def api_summary(h, a):
        return summary(S, car_of(a))

    @S.route('GET', '/api/tessie/idles')
    def api_idles(h, a):
        car = car_of(a)
        limit = max(1, min(500, int(a.get('limit', 100))))
        off = max(0, int(a.get('offset', 0)))
        rows = S.OWN.rows('select tessie_id id, started_at, ended_at, place, saved, soc0, soc1, range_used, energy_used, charger_energy, climate_frac, sentry_frac '
                          'from tessie_idle where car_id=? order by started_at desc limit ? offset ?', (car, limit, off))
        tot = S.OWN.one('select count(*) n, sum(energy_used) kwh, sum(ended_at-started_at) secs, sum(case when sentry_frac > 0.5 then energy_used else 0 end) sentry_kwh, '
                        'sum(case when climate_frac > 0.5 then energy_used else 0 end) climate_kwh from tessie_idle where car_id=?', (car,)) or {}
        return dict(rows=rows, total=tot)

    @S.route('GET', '/api/tessie/health')
    def api_health(h, a):
        return dict(points=S.OWN.rows('select ts, odometer, max_range, capacity from tessie_health where car_id=? order by ts', (car_of(a),)))

    @S.route('GET', '/api/tessie/alerts')
    def api_alerts(h, a):
        car = car_of(a)
        kinds = S.OWN.rows('select name, count(*) n, max(ts) last, min(ts) first, max(description) description, max(impact) impact, max(cond) cond, max(fleet_count) fleet from tessie_alert '
                           'where car_id=? group by name order by n desc limit 200', (car,))
        recent = S.OWN.rows('select ts, name from tessie_alert where car_id=? order by ts desc limit 40', (car,))
        return dict(kinds=kinds, recent=recent)

    @S.route('GET', '/api/tessie/drive')
    def api_drive(h, a):
        r = S.OWN.one('select autopilot_km, avg_speed, energy_used, rated_range_used, est_power_max, est_power_min, est_power_avg, start_saved, end_saved from tessie_drive where car_id=? and drive_id=?',
                      (car_of(a), int(a.get('id', 0))))
        return dict(found=bool(r), **(r or {}))

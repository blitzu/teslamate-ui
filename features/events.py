"""Jurnal de evenimente (tranzitii MQTT importante) si jurnal de comenzi. Baza pentru alerte, paznicul de somn si rapoarte."""
import time

WATCH = ('state', 'sentry_mode', 'plugged_in', 'charging_state', 'windows_open', 'doors_open', 'trunk_open', 'frunk_open', 'geofence', 'locked',
         'is_climate_on', 'charge_port_door_open', 'update_available', 'is_user_present', 'climate_keeper_mode')
KEEP_DAYS = 400


def init(S):
    S.OWN.migrate('events', [
        'create table events (id integer primary key, ts real not null, car integer not null, key text not null, old text, new text)',
        'create index events_key_ts on events(key, ts)',
        'create table cmd_log (id integer primary key, ts real not null, car integer, name text not null, actor text not null, ok integer, via text, note text)',
        'create index cmd_log_ts on cmd_log(ts)',
    ])

    def on_mqtt(car, key, old, new, known):
        if key in WATCH:                                   # si prima valoare dupa repornire (old=None): da starea de baza pentru intervale (ex. Sentry deja pornit)
            S.OWN.run('insert into events(ts, car, key, old, new) values(?,?,?,?,?)', (time.time(), car, key, None if old is None else str(old), None if new is None else str(new)))

    def on_audit(kind, **kw):
        if kind in ('share', 'share_revoke'):                # crearea/retragerea unui link de locatie apare in jurnalul de comenzi
            S.OWN.run('insert into cmd_log(ts, car, name, actor, ok, via, note) values(?,?,?,?,?,?,?)', (time.time(), None, kind, 'user:%s' % (kw.get('actor') or '?'), 1, 'app', 'toate' if kw.get('all') else ''))
        if kind == 'cmd':
            S.OWN.run('insert into cmd_log(ts, car, name, actor, ok, via, note) values(?,?,?,?,?,?,?)',
                      (time.time(), kw.get('car'), kw.get('name'), kw.get('actor', 'system'), 1 if kw.get('ok') else 0, kw.get('via'), (kw.get('note') or '')[:200]))

    def cleanup():
        time.sleep(120)                                      # prima curatare imediat dupa pornire: repornirile dese (ex. actualizari zilnice) nu trebuie sa o amane la nesfarsit
        while True:
            cut = time.time() - KEEP_DAYS * 86400
            S.OWN.run('delete from events where ts < ?', (cut,))
            S.OWN.run('delete from cmd_log where ts < ?', (cut,))
            for sql, args in (('delete from alerts_log where ts < ?', (time.time() - 400 * 86400,)),
                              ('delete from shares where expires < ?', (time.time() - 30 * 86400,)),
                              ("delete from kv where k like 'handoff_warned_%' and ts < ?", (time.time() - 30 * 86400,))):
                try:
                    S.OWN.run(sql, args)
                except Exception:  # noqa
                    pass                                     # modulul sau tabelul lipseste
            time.sleep(3600 * 6)

    S.MQTT_HOOKS.append(on_mqtt)
    S.AUDIT_HOOKS.append(on_audit)
    S.BG_TASKS.append(cleanup)

    @S.route('GET', '/api/events')
    def events_api(h, a):
        days = max(1, min(int(a.get('days', 7)), 90))
        key = a.get('key')
        sql = 'select ts, car, key, old, new from events where ts >= ?' + (' and key = ?' if key else '') + ' order by ts desc limit 500'
        return S.OWN.rows(sql, (time.time() - days * 86400,) + ((key,) if key else ()))

    @S.route('GET', '/api/cmdlog')
    def cmdlog_api(h, a):
        days = max(1, min(int(a.get('days', 7)), 90))
        return S.OWN.rows('select ts, car, name, actor, ok, via, note from cmd_log where ts >= ? order by ts desc limit 500', (time.time() - days * 86400,))

"""Alerte proactive: incarcare oprita, conectata dar nu incarca (cu motiv), nu e conectata seara, presiune anvelope, ploaie cu geam deschis,
cabina fierbinte in Dog/Camp Mode si "treaza fara motiv" (din paznicul de somn). Reguli si praguri reglabile, ore de liniste, jurnal."""
import datetime as dt
import json
import re
import time

DEFAULT = dict(
    enabled=True,
    quiet=dict(on=False, start='23:00', end='07:00'),
    charge_stopped=dict(on=True),
    plugged_not_charging=dict(on=True, minutes=20),
    not_plugged_night=dict(on=True, hour=22, min_soc=80, home='acas|home'),
    tpms_low=dict(on=True, bar=2.4),
    rain_window=dict(on=True),
    cabin_hot=dict(on=True, temp=32),
    awake_unexplained=dict(on=True, minutes=180),
    tire_leak=dict(on=True),
)
COOLDOWN = dict(tire_leak=24 * 3600, charge_stopped=1800, plugged_not_charging=6 * 3600, not_plugged_night=20 * 3600, tpms_low=24 * 3600, rain_window=3600, cabin_hot=1200, awake_unexplained=20 * 3600)
SEVERITY = dict(tire_leak='high', charge_stopped='normal', plugged_not_charging='normal', not_plugged_night='normal', tpms_low='high', rain_window='high', cabin_hot='critical', awake_unexplained='normal')


def merged(cfg):
    out = json.loads(json.dumps(DEFAULT))
    for k, v in (cfg or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k].update({a: b for a, b in v.items() if a in out[k]})
        elif k == 'enabled':
            out[k] = bool(v)
    return out


def clean(body):
    """Valideaza ce vine din UI: tipuri si limite."""
    cfg = merged(body)
    num = lambda x, lo, hi, d: max(lo, min(hi, float(x))) if x not in (None, '') else d
    cfg['plugged_not_charging']['minutes'] = int(num(cfg['plugged_not_charging']['minutes'], 5, 240, 20))
    cfg['not_plugged_night']['hour'] = int(num(cfg['not_plugged_night']['hour'], 0, 23, 22))
    cfg['not_plugged_night']['min_soc'] = int(num(cfg['not_plugged_night']['min_soc'], 1, 100, 80))
    cfg['not_plugged_night']['home'] = re.sub(r'[^\w|\s-]', '', str(cfg['not_plugged_night']['home']))[:60] or 'acas|home'
    cfg['tpms_low']['bar'] = round(num(cfg['tpms_low']['bar'], 1.5, 3.5, 2.4), 2)
    cfg['cabin_hot']['temp'] = int(num(cfg['cabin_hot']['temp'], 20, 60, 32))
    cfg['awake_unexplained']['minutes'] = int(num(cfg['awake_unexplained']['minutes'], 30, 1440, 180))
    for k in ('start', 'end'):
        v = str(cfg['quiet'][k])
        cfg['quiet'][k] = v if re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', v) else DEFAULT['quiet'][k]
    for k in cfg:
        if isinstance(cfg[k], dict) and 'on' in cfg[k]:
            cfg[k]['on'] = bool(cfg[k]['on'])
    return cfg


def in_quiet(q, now):
    if not q.get('on'):
        return False
    a, b = [int(x) * 60 + int(y) for x, y in (q['start'].split(':'), q['end'].split(':'))]
    m = now.hour * 60 + now.minute
    return (a <= m < b) if a <= b else (m >= a or m < b)


class Engine:
    def __init__(self, S):
        self.S = S
        self.since = {}
        self.fired = {}
        self.rain_checked = {}
        self.rain_alerted = {}
        self.now = None                                                      # ceasul ultimei verificari (tick/MQTT), folosit si de fire()
        self.held = set()                                                    # alerte retinute de orele de liniste (jurnalizate o singura data)

    def cfg(self):
        return merged(self.S.OWN.kv_get('alerts_cfg', {}))

    def cool(self, key, now):
        last = self.fired.get(key)
        if last is not None and now - last < COOLDOWN.get(key.split(':')[0], 3600):
            return False
        self.fired[key] = now
        return True

    def fire(self, key, title, msg, car=1, now_dt=None, cfg=None):
        S = self.S
        cfg = cfg or self.cfg()
        sev = SEVERITY.get(key.split(':')[0], 'normal')
        full = '%s:%s' % (key.split(':')[0], car)
        if key != 'test' and not cfg['enabled']:
            return False                                                     # alertele sunt oprite global: nu trimitem si nu jurnalizam
        quiet = in_quiet(cfg['quiet'], now_dt or dt.datetime.now())
        if quiet and sev != 'critical':
            if full not in self.held:
                self.held.add(full)
                S.OWN.run('insert into alerts_log(ts, car, key, severity, title, msg) values(?,?,?,?,?,?)', (time.time(), car, key.split(':')[0], sev, title, msg))
            # cooldown-ul nu trebuie "consumat" de o alerta netrimisa: reincercam peste ~10 min, cand orele de liniste s-ar putea sa se fi terminat
            self.fired[full] = (self.now or time.time()) - COOLDOWN.get(key.split(':')[0], 3600) + 600
            return False
        if full not in self.held:
            S.OWN.run('insert into alerts_log(ts, car, key, severity, title, msg) values(?,?,?,?,?,?)', (time.time(), car, key.split(':')[0], sev, title, msg))
        self.held.discard(full)
        S.notify('alert', title, msg)
        return True

    # ---- evenimente MQTT (tranzitii)
    def on_mqtt(self, car, key, old, new, known):
        cfg = self.cfg()
        if not cfg['enabled'] or not known:
            return
        now = self.now = time.time()
        if key == 'charging_state' and cfg['charge_stopped']['on'] and old == 'Charging' and new in ('Stopped', 'NoPower'):
            live = self.S.LIVE.get(car, {})
            soc, lim = live.get('battery_level'), live.get('charge_limit_soc')
            if soc is not None and lim and soc >= lim - 1:
                return                                                       # a atins limita: e normal
            recent_cmd = self.S.OWN.one("select 1 x from cmd_log where name in ('charge_stop','charging_amps','sched_charging') and ts > ? limit 1", (now - 300,))
            if recent_cmd:
                return                                                       # tocmai ai oprit-o tu / o regula
            if self.cool('charge_stopped:%s' % car, now):
                why = 'nu mai vine curent la încărcător' if new == 'NoPower' else 'oprită de mașină sau de încărcător'
                self.fire('charge_stopped', '⚠️ Încărcarea s-a oprit', 'Stare: %s (%s). Baterie %s%%.' % (new, why, soc if soc is not None else '?'), car, cfg=cfg)
        if key == 'windows_open' and not new:
            self.rain_alerted.pop(car, None)

    # ---- verificari periodice (la ~30 s)
    def tick(self, now=None, now_dt=None):
        cfg = self.cfg()
        if not cfg['enabled']:
            return
        now = self.now = now or time.time()
        now_dt = now_dt or dt.datetime.now()
        for car, live in list(self.S.LIVE.items()):
            self.check_plugged(car, live, cfg, now, now_dt)
            self.check_night(car, live, cfg, now, now_dt)
            self.check_tpms(car, live, cfg, now, now_dt)
            self.check_cabin(car, live, cfg, now, now_dt)
            self.check_rain(car, live, cfg, now, now_dt)

    def check_plugged(self, car, live, cfg, now, now_dt):
        c = cfg['plugged_not_charging']
        k = 'pnc:%s' % car
        soc, lim = live.get('battery_level'), live.get('charge_limit_soc') or 100
        scheduled = live.get('scheduled_charging_start_time')
        bad = live.get('plugged_in') and live.get('charging_state') in ('Stopped', 'NoPower') and soc is not None and soc < lim - 1 and not scheduled
        if not (c['on'] and bad):
            self.since.pop(k, None)
            return
        if self.S.OWN.one("select 1 x from cmd_log where name in ('charge_stop','charging_amps','sched_charging') and ts > ? limit 1", (now - 6 * 3600,)):
            self.since.pop(k, None)
            return                                                           # ai oprit-o tu (sau o regula) de curand: nu e o defectiune
        t0 = self.since.setdefault(k, now)
        if now - t0 >= c['minutes'] * 60 and self.cool('plugged_not_charging:%s' % car, now):
            why = 'nu vine curent (verifică invertorul/siguranța/priza)' if live.get('charging_state') == 'NoPower' else 'încărcarea e oprită (verifică programarea, limita sau curentul)'
            self.fire('plugged_not_charging', '🔌 Conectată dar nu încarcă', 'De %d min: %s. Baterie %s%%, limită %s%%.' % ((now - t0) // 60, why, soc, lim), car, now_dt, cfg)

    def check_night(self, car, live, cfg, now, now_dt):
        c = cfg['not_plugged_night']
        if not c['on'] or now_dt.hour != c['hour'] or now_dt.minute > 10:
            return
        geo = str(live.get('geofence') or '')
        soc = live.get('battery_level')
        if re.search(c['home'], geo, re.I) and not live.get('plugged_in') and soc is not None and soc < c['min_soc'] and live.get('state') not in ('driving',):
            if self.cool('not_plugged_night:%s' % car, now):
                self.fire('not_plugged_night', '🔋 Nu e conectată la încărcat', 'Ești acasă (%s), baterie %s%%, cablul nu e conectat.' % (geo, soc), car, now_dt, cfg)

    def check_tpms(self, car, live, cfg, now, now_dt):
        c = cfg['tpms_low']
        if not c['on']:
            return
        names = dict(fl='față stânga', fr='față dreapta', rl='spate stânga', rr='spate dreapta')
        low = [(names[w], live.get('tpms_pressure_' + w)) for w in names if live.get('tpms_pressure_' + w) and 0 < live.get('tpms_pressure_' + w) < c['bar']]
        soft = [names[w] for w in names if live.get('tpms_soft_warning_' + w)]
        if (low or soft) and self.cool('tpms_low:%s' % car, now):
            parts = ['%s %.2f bar' % (n, v) for n, v in low] + ['avertizare mașină: %s' % n for n in soft]
            self.fire('tpms_low', '🛞 Presiune scăzută la anvelope', '; '.join(parts) + ' (prag %.1f bar).' % c['bar'], car, now_dt, cfg)

    def check_cabin(self, car, live, cfg, now, now_dt):
        c = cfg['cabin_hot']
        mode = str(live.get('climate_keeper_mode') or '').lower()
        temp = live.get('inside_temp')
        if c['on'] and mode in ('dog', 'camp') and temp is not None and temp > c['temp'] and self.cool('cabin_hot:%s' % car, now):
            self.fire('cabin_hot', '🐕 Cabina e fierbinte în modul %s' % mode, 'Temperatura în cabină: %.0f°C (prag %d°C). Verifică imediat.' % (temp, c['temp']), car, now_dt, cfg)

    def check_rain(self, car, live, cfg, now, now_dt):
        if not (cfg['rain_window']['on'] and live.get('windows_open')) or self.rain_alerted.get(car):
            return
        if now - self.rain_checked.get(car, 0) < 600:
            return
        self.rain_checked[car] = now
        lat, lon = live.get('latitude'), live.get('longitude')
        if lat is None or lon is None:
            return
        try:
            r = json.loads(self.S._get_text('https://api.open-meteo.com/v1/forecast?latitude=%.1f&longitude=%.1f&current=precipitation&hourly=precipitation&forecast_hours=2' % (lat, lon), 15))
            now_p = float((r.get('current') or {}).get('precipitation') or 0)
            soon = max([float(x or 0) for x in (r.get('hourly') or {}).get('precipitation', [])] or [0])
        except Exception as e:  # noqa
            self.S.log('alerta ploaie: %s' % e)
            return
        if now_p > 0.1 or soon > 0.3:
            if self.fire('rain_window', '🌧️ Plouă (sau urmează) și un geam e deschis', ('Plouă acum' if now_p > 0.1 else 'Ploaie în următoarele 2 ore') + ' la locația mașinii.', car, now_dt, cfg):
                self.rain_alerted[car] = True                                # marcat doar dupa trimitere: in orele de liniste reincercam


def init(S):
    S.OWN.migrate('alerts', [
        'create table alerts_log (id integer primary key, ts real not null, car integer, key text not null, severity text, title text, msg text)',
        'create index alerts_log_ts on alerts_log(ts)',
    ])
    E = Engine(S)
    S.ALERTS = E
    S.KIND_ROUTE['alert'] = '#/alerts'
    S.MQTT_HOOKS.append(E.on_mqtt)

    def loop():
        time.sleep(30)
        while True:
            try:
                E.tick()
            except Exception as e:  # noqa
                S.log('alerte: %s' % e)
            time.sleep(30)

    S.BG_TASKS.append(loop)

    @S.route('GET', '/api/alerts/config')
    def get_cfg(h, a):
        return dict(config=E.cfg(), defaults=DEFAULT)

    @S.route('POST', '/api/alerts/config', pin=True, role='admin')
    def set_cfg(h, body):
        cfg = clean(body)
        S.OWN.kv_set('alerts_cfg', cfg)
        return dict(ok=True, config=cfg)

    @S.route('GET', '/api/alerts/log')
    def log_api(h, a):
        days = max(1, min(int(a.get('days', 30)), 365))
        return S.OWN.rows('select ts, car, key, severity, title, msg from alerts_log where ts >= ? order by ts desc limit 200', (time.time() - days * 86400,))

    @S.route('POST', '/api/alerts/test', pin=True, role='admin')
    def test(h, body):
        cfg = E.cfg()
        sent = E.fire('test', '🔔 Alertă de test', 'Alertele din aplicația Tesla funcționează.', 1, cfg=cfg)
        return dict(ok=True, sent=sent, quiet=in_quiet(cfg['quiet'], dt.datetime.now()))

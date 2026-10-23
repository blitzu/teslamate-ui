"""Paznic de somn: cat timp a stat masina treaza FARA sa conduca sau sa se incarce, si de ce (Sentry, comanda automata, utilizator, update, necunoscut).
Foloseste tabelul `states` din TeslaMate + jurnalul propriu de evenimente si comenzi. Nu trezeste niciodata masina."""
import datetime as dt
import time


# ---------------------------------------------------------------- intervale (momente UNIX, secunde)
def merge(iv):
    out = []
    for a, b in sorted(x for x in iv if x[1] > x[0]):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def subtract(iv, cut):
    cut = merge(cut)
    out = []
    for a, b in merge(iv):
        cur = a
        for c, d in cut:
            if d <= cur or c >= b:
                continue
            if c > cur:
                out.append([cur, c])
            cur = max(cur, d)
        if cur < b:
            out.append([cur, b])
    return out


def overlaps(a, b, iv):
    return any(c < b and d > a for c, d in iv)


def intersect(a, b):
    out = []
    for x, y in merge(a):
        for c, d in merge(b):
            lo, hi = max(x, c), min(y, d)
            if hi > lo:
                out.append([lo, hi])
    return merge(out)


def analyze(online, busy, sentry, user, updates, cmds, tz_offset=lambda t: 0, min_seconds=180, pad=300, cmd_window=(60, 720)):
    """online/busy/sentry/user/updates: liste de [start, end] (UNIX); cmds: [(ts, actor)]. Intoarce {zi: {'total': min, 'reasons': {motiv: min}, 'unexplained': min}}.
    Un interval "treaz fara motiv" = online care nu se suprapune cu condus/incarcare (+-pad s). Fiecare bucata e atribuita, in ordine, la: Sentry, comanda
    (masina ramane treaza ~12 min dupa o comanda), utilizator, update; ce ramane = necunoscut."""
    idle = subtract(online, [[a - pad, b + pad] for a, b in busy])
    idle = [iv for iv in idle if iv[1] - iv[0] >= min_seconds]
    segs, rest = [], idle
    for name, ivs in (('sentry', sentry), ('comanda', [[t - cmd_window[0], t + cmd_window[1]] for t, _ in cmds]), ('utilizator', user), ('update', updates)):
        hit = intersect(rest, ivs)
        segs += [(name, a, b) for a, b in hit]
        rest = subtract(rest, hit)
    segs += [('necunoscut', a, b) for a, b in rest if b - a >= 60]
    days = {}
    for reason, a, b in segs:
        cur = a
        while cur < b:
            off = tz_offset(cur)
            day_start = (int(cur + off) // 86400) * 86400 - off
            end = min(b, day_start + 86400)
            d = dt.datetime.utcfromtimestamp(cur + off).strftime('%Y-%m-%d')
            x = days.setdefault(d, dict(total=0.0, reasons={}, unexplained=0.0))
            m = (end - cur) / 60
            x['total'] += m
            x['reasons'][reason] = x['reasons'].get(reason, 0) + m
            if reason == 'necunoscut':
                x['unexplained'] += m
            cur = end
    for x in days.values():
        x['total'] = round(x['total'])
        x['unexplained'] = round(x['unexplained'])
        x['reasons'] = {k: round(v) for k, v in x['reasons'].items()}
    return days


def intervals_from_events(rows, on_value, now):
    """Din tranzitii (ts, new) construieste intervalele in care valoarea a fost `on_value`."""
    out, start = [], None
    for ts, new in rows:
        if str(new) == on_value and start is None:
            start = ts
        elif str(new) != on_value and start is not None:
            out.append([start, ts])
            start = None
    if start is not None:
        out.append([start, now])
    return out


def init(S):
    def tzoff():
        try:
            import zoneinfo
            z = zoneinfo.ZoneInfo(S.LOCAL_TZ)
            return lambda t: int(dt.datetime.fromtimestamp(t, z).utcoffset().total_seconds())
        except Exception:  # noqa
            return lambda t: 0

    def report(car, days):
        now = time.time()
        since = now - days * 86400
        sd = dt.datetime.utcfromtimestamp(since).isoformat()
        P = lambda x: x.replace(tzinfo=dt.timezone.utc).timestamp() if x else now
        ts = lambda s: P(dt.datetime.fromisoformat(s)) if s else now
        st = S.q("select state::text s, start_date, end_date from states where car_id=%s and coalesce(end_date, now() at time zone 'utc') > %s order by start_date", (car, sd))
        online = [[max(ts(r['start_date']), since), ts(r['end_date'])] for r in st if r['s'] == 'online']
        busy = [[ts(r['a']), ts(r['b'])] for r in S.q(
            "select start_date a, end_date b from drives where car_id=%s and coalesce(end_date, now() at time zone 'utc') > %s "
            "union all select start_date, end_date from charging_processes where car_id=%s and coalesce(end_date, now() at time zone 'utc') > %s", (car, sd, car, sd))]
        upd = [[ts(r['start_date']), ts(r['end_date'])] for r in S.q("select start_date, end_date from updates where car_id=%s and coalesce(end_date, now() at time zone 'utc') > %s", (car, sd))]
        ev = lambda key: [(r['ts'], r['new']) for r in S.OWN.rows('select ts, new from events where key=? and car=? and ts >= ? order by ts', (key, car, since - 86400))]
        sentry = intervals_from_events(ev('sentry_mode'), 'True', now)
        user = intervals_from_events(ev('is_user_present'), 'True', now)
        cmds = [(r['ts'], r['actor']) for r in S.OWN.rows('select ts, actor from cmd_log where car=? and ts >= ?', (car, since - 600))]
        return analyze(online, busy, sentry, user, upd, cmds, tzoff())

    S.SLEEPGUARD = report

    @S.route('GET', '/api/sleepguard')
    def api(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        days = max(1, min(int(a.get('days', 7)), 60))
        if hc is False:                                              # demo: date fictive
            today = dt.date.today()
            demo = [dict(day=(today - dt.timedelta(days=i)).isoformat(), total=t, unexplained=u, reasons=r) for i, (t, u, r) in enumerate([
                (95, 20, dict(sentry=40, comanda=35, necunoscut=20)), (210, 180, dict(necunoscut=180, utilizator=30)), (60, 0, dict(comanda=45, utilizator=15)),
                (40, 10, dict(comanda=30, necunoscut=10)), (120, 60, dict(sentry=60, necunoscut=60)), (30, 0, dict(update=30)), (75, 15, dict(comanda=60, necunoscut=15))])][:days]
            return dict(days=sorted(demo, key=lambda d: d['day']))
        rep = report(int(a.get('car', 1)), days)
        return dict(days=[dict(day=d, **v) for d, v in sorted(rep.items())])

    def daily_check():
        """O data pe zi (dimineata): daca ieri a fost treaza fara motiv peste prag, alerteaza."""
        time.sleep(120)
        last = ''
        while True:
            now = dt.datetime.now()
            today = now.strftime('%Y-%m-%d')
            if now.hour >= 8 and today != last and S.has_cars():
                last = today
                try:
                    cfg = S.ALERTS.cfg()['awake_unexplained']
                    y = (now - dt.timedelta(days=1)).strftime('%Y-%m-%d')
                    day = report(1, 3).get(y)
                    if cfg['on'] and day and day['unexplained'] >= cfg['minutes'] and S.ALERTS.cool('awake_unexplained:1', time.time()):
                        top = ', '.join('%s %d min' % (k, v) for k, v in sorted(day['reasons'].items(), key=lambda kv: -kv[1])[:3])
                        S.ALERTS.fire('awake_unexplained', '😴 Mașina a stat trează fără motiv', 'Ieri: %d min fără să conducă/încarce, din care %d min nelămurite (%s).' % (day['total'], day['unexplained'], top))
                except Exception as e:  # noqa
                    S.log('paznic somn: %s' % e)
            time.sleep(900)

    S.BG_TASKS.append(daily_check)

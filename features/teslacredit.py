"""Istoricul Supercharger din Tesla (Fleet API, doar citire: GET /api/1/dx/charging/history, cu scopul vehicle_charging_cmds pe care aplicatia il are deja).
Pentru fiecare sesiune Tesla da kilometrii de credit consumati EXACT (`credit.distance`), energia masurata de incarcator (taxa CHARGING, `usageBase`), tariful pe kWh si ce s-a platit
(`netDue`). Aplicatia le tine in baza proprie (fara VIN, fara token), le potriveste cu incarcarile din TeslaMate dupa ora si:
  - un pachet in km marcat "dupa Tesla" arata folosit/ramas exact si scade din fiecare incarcare kilometrii ei reali (fara factor de calibrare);
  - o incarcare Supercharger platita (nu din credit) primeste costul real platit la Tesla, in locul estimarii.
Sincronizarea ruleaza la cerere (buton) si o data pe zi, doar cu contul Tesla conectat; nu se scrie nimic la Tesla."""
import datetime as dt
import time

MILE = 1.609344
PAD = dt.timedelta(minutes=15)          # TeslaMate si Tesla nu pornesc sesiunea exact la aceeasi secunda
PAGE = 50
MAX_PAGES = 20
SYNC_EVERY = 20 * 3600


def utc(iso):
    """ISO cu fus orar (ex. 2026-10-17T15:09:51+03:00) -> datetime naiv UTC (ca in TeslaMate)."""
    d = dt.datetime.fromisoformat(str(iso))
    return d.astimezone(dt.timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def parse_session(s):
    """Sesiunea din raspunsul Tesla -> randul tinut in aplicatie (None daca nu are id sau ora de start)."""
    sid, start = s.get('sessionId'), s.get('chargeStartDateTime')
    if sid is None or not start:
        return None
    t0 = utc(start)
    t1 = utc(s.get('chargeStopDateTime') or s.get('unlatchDateTime') or start)
    cr = s.get('credit') or {}
    dist = float(cr.get('distance') or 0)
    km = dist * MILE if str(cr.get('distanceUnit') or 'km').lower().startswith('mi') else dist
    fees = s.get('fees') or []
    chg = [f for f in fees if f.get('feeType') == 'CHARGING']
    kwh = sum(float(f.get('usageBase') or 0) for f in chg) or float(cr.get('energyApplied') or 0)
    return dict(sid=int(sid), start=t0.isoformat(timespec='seconds'), stop=t1.isoformat(timespec='seconds'), site=str(s.get('siteLocationName') or '')[:80], country=str(s.get('countryCode') or '')[:3],
                credit_km=round(km, 1), kwh=round(kwh, 3), rate=(chg[0].get('rateBase') if chg else None), cur=next((f.get('currencyCode') for f in fees if f.get('currencyCode')), None),
                net_due=round(sum(float(f.get('netDue') or 0) for f in fees), 2), total_due=round(sum(float(f.get('totalDue') or 0) for f in fees), 2),
                paid=1 if fees and all(f.get('isPaid') for f in fees) else 0)


def fetch_all(http, base, token, vin):
    """Toate sesiunile din istoric (paginat). http(url, headers=) -> (cod, raspuns). Intoarce (sesiuni, eroare)."""
    out, total, page = [], None, 1
    while page <= MAX_PAGES:
        code, r = http('%s/api/1/dx/charging/history?vin=%s&pageNo=%d&pageSize=%d&sortBy=start_datetime&sortOrder=ASC' % (base, vin, page, PAGE), headers={'Authorization': 'Bearer ' + token})
        if code != 200 or not isinstance(r, dict):
            return out, 'Tesla a răspuns cu %s.' % code
        rows = r.get('data') or []
        total = r.get('totalResults', total)
        out += [x for x in (parse_session(s) for s in rows) if x]
        if not rows or (total is not None and len(out) >= total):
            break
        page += 1
    return out, None


def match(sessions, start, kwh=None):
    """Sesiunea Tesla a unei incarcari din TeslaMate (start = datetime UTC naiv al incarcarii): cea la care incarcarea incepe intre inceputul si sfarsitul ei (+- 15 min), cea mai apropiata.
    Intoarce (sesiune, parte) cu parte = ce fractiune din sesiune e incarcarea (cand TeslaMate a rupt-o in doua incarcari: dupa kWh), sau (None, None)."""
    best = None
    for s in sessions:
        a, b = dt.datetime.fromisoformat(s['start']), dt.datetime.fromisoformat(s['stop'])
        if a - PAD <= start <= b + PAD:
            d = abs((start - a).total_seconds())
            if best is None or d < best[0]:
                best = (d, s)
    if not best:
        return None, None
    s = best[1]
    share = 1.0
    if kwh and s['kwh'] and s['kwh'] > 0:
        share = max(0.0, min(1.0, float(kwh) / s['kwh']))
    return s, share


def init(S):
    S.OWN.migrate('teslacredit', ['create table tesla_sessions (sid integer primary key, car integer, start text, stop text, site text, country text, credit_km real, kwh real, rate real, cur text, '
                                  'net_due real, total_due real, paid integer, ts real)'])
    cache = {'t': 0, 'rows': []}

    def rows():
        if time.time() - cache['t'] > 30:
            cache['rows'], cache['t'] = S.OWN.rows('select sid, car, start, stop, site, country, credit_km, kwh, rate, cur, net_due, total_due, paid from tesla_sessions order by start'), time.time()
        return cache['rows']

    class Tesla:
        def match_row(self, r):
            """Pentru o incarcare: dict cu sesiunea Tesla potrivita si partea ei, in moneda aplicatiei; None daca nu exista."""
            try:
                st = dt.datetime.fromisoformat(str(r.get('start_date'))[:19])
            except (TypeError, ValueError):
                return None
            kwh = r.get('charge_energy_used') or r.get('charge_energy_added')
            s, share = match(rows(), st, kwh)
            if not s:
                return None
            net = self.money(s['net_due'], s['cur'])
            return dict(sid=s['sid'], start=s['start'], site=s['site'], kwh=s['kwh'], rate=s['rate'], cur=s['cur'], credit_km=s['credit_km'], share=share, paid=bool(s['paid']),
                        net_due=None if net is None else round(net * share, 2))

        def money(self, v, cur):
            """Suma din moneda Tesla in moneda aplicatiei (None fara curs)."""
            to = S.CUR_CODES.get(str(S.CURRENCY).strip().lower())
            if v is None or not cur or not to or cur.upper() == to:
                return v
            fx = getattr(S, 'fx_rate', None)
            r = fx(cur.upper(), to) if fx else None
            return v * r if r else None

        def cost(self, r):
            """Costul real platit la Tesla pentru o incarcare Supercharger NEacoperita de credit (credit 0): netDue x partea ei. None cand nu se aplica."""
            m = self.match_row(r)
            if not m or m['credit_km'] > 0 or not m['paid'] or m['net_due'] is None:
                return None
            return m['net_due']

        def usage(self, pack):
            """Din sesiunile Tesla din perioada pachetului: kilometri de credit folositi exact, cate sesiuni, kWh. None daca nu exista nicio sesiune cu credit."""
            lo, hi = (pack.get('since') or '0000')[:10], (pack.get('expires') or '9999')[:10]
            ss = [s for s in rows() if s['credit_km'] > 0 and lo <= s['start'][:10] <= hi]
            if not ss:
                return None
            return dict(n=len(ss), kwh=round(sum(s['kwh'] for s in ss), 1), used=round(sum(s['credit_km'] for s in ss), 1), tesla=True)

        def reset(self):
            cache['t'] = 0

        def status(self):
            fs = S.fleet_status() if hasattr(S, 'fleet_status') else {}
            rs = rows()
            return dict(available=bool(fs.get('authorized')), sessions=len(rs), last=S.OWN.kv_get('tesla_sync'))

    S.TESLA = Tesla()

    def sync():
        """Aduce istoricul Supercharger al fiecarei masini cu VIN (doar citire). Intoarce {ok, new, total, reason}."""
        fs = S.fleet_status()
        if not fs.get('authorized'):
            return dict(ok=False, reason='Contul Tesla nu e conectat (Setări → Comenzi Tesla).')
        try:
            token = S.access_token()
        except RuntimeError as e:
            return dict(ok=False, reason=str(e))
        known = {r['sid'] for r in S.OWN.rows('select sid from tesla_sessions')}
        new = total = 0
        for car in S.q('select id, vin from cars where vin is not null order by id'):
            sess, err = fetch_all(S.http, S.FL['base'], token, car['vin'])
            if err and not sess:
                return dict(ok=False, reason=err)
            for s in sess:
                S.OWN.run('insert or replace into tesla_sessions(sid, car, start, stop, site, country, credit_km, kwh, rate, cur, net_due, total_due, paid, ts) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (s['sid'], car['id'], s['start'], s['stop'], s['site'], s['country'], s['credit_km'], s['kwh'], s['rate'], s['cur'], s['net_due'], s['total_due'], s['paid'], time.time()))
                new += s['sid'] not in known
            total += len(sess)
        cache['t'] = 0
        S.OWN.kv_set('tesla_sync', dict(at=time.strftime('%Y-%m-%dT%H:%M:%S'), new=new, total=total))
        if hasattr(S, 'PROV_CACHE'):
            S.PROV_CACHE.clear()
        return dict(ok=True, new=new, total=total)

    @S.route('POST', '/api/credits/tesla-sync', pin=True, role='user')
    def sync_route(h, b):
        return sync()

    def loop():
        time.sleep(150)
        while True:
            try:
                last = S.OWN.kv_get('tesla_sync') or {}
                due = not last or time.time() - time.mktime(time.strptime(last['at'], '%Y-%m-%dT%H:%M:%S')) > SYNC_EVERY
                if due and S.fleet_status().get('authorized'):
                    sync()
            except Exception as e:  # noqa
                S.log('istoric Tesla:', str(e)[:100], flush=True)
            time.sleep(3600)

    S.BG_TASKS.append(loop)

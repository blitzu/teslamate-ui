"""Originea energiei din casa: cat din curentul pe care il ia masina (la incarcare) vine din retea si cat din solar sau din bateria casei, tinand cont de ce a incarcat bateria.

Modelul (trasare proportionala): la fiecare minut, tot ce produc sursele (panouri PV + import din retea + descarcarea bateriei) intra intr-o "bara" comuna din care iau toti
consumatorii (casa, masina, incarcarea bateriei, exportul) in aceeasi proportie. Partea din retea a barii e
    phi = (import + descarcare x g) / (PV + import + descarcare)
unde g = fractia din energia aflata in bateria casei care a venit din retea. Cand bateria se incarca, g se amesteca cu phi (ce intra e phi din retea, restul solar); cand se
descarca, g ramane. Asa: soarele costa 0, bateria incarcata din soare costa 0, iar bateria incarcata din retea (completarea de seara) sau curentul direct din retea costa tariful retelei.

Aplicatia isi tine singura minutele (HA pastreaza doar ~10 zile): la prima pornire umple din istoricul HA, apoi esantioneaza la 30 s. Citeste doar senzori din Home Assistant.
Pentru incarcarile din afara perioadei acoperite ramane calculul vechi (importul invertorului in timpul incarcarii)."""
import bisect
import datetime as dt
import threading
import time

MIN = 60
HA_KEEP_S = 9.5 * 86400           # istoricul HA (recorder) tine implicit 10 zile
CHUNK_S = 2 * 86400
SAMPLE_S = 30
KEEP_DAYS = 400
MIN_SUPPLY_W = 50.0               # sub atat nu e curent in casa: minutul nu se numara
BAT_MIN_KWH = 0.5                 # fara asta, o baterie aproape goala ar face din g un numar aiurea
COVER_MIN = 0.8                   # cat din minutele unei incarcari trebuie sa avem ca sa o calculam


def advance(g, soc, cap, rows, charge_sign=-1):
    """rows: [(t, pv, grid, batt, soc|None)] puteri in W (medii pe minut, sortate); battery_power e negativ cand incarca daca charge_sign = -1.
    Intoarce ([(t, phi|None, phi_baterie|None, g)], g, soc)."""
    out = []
    for t, pv, grid, batt, s in rows:
        ch = (batt or 0.0) * (-1.0 if charge_sign < 0 else 1.0)              # + = bateria se incarca
        p_in, p_out = max(0.0, ch), max(0.0, -ch)
        p_g, p_pv = max(0.0, grid or 0.0), max(0.0, pv or 0.0)
        supply = p_pv + p_g + p_out
        if supply < MIN_SUPPLY_W:
            out.append((t, None, None, g))
        else:
            phi_b = p_out * g / supply
            phi = p_g / supply + phi_b
            if p_in > 0:                                                    # bateria primeste din bara: se amesteca fractia
                ein = p_in * MIN / 3.6e6
                prev = max(BAT_MIN_KWH, (soc if soc is not None else 50.0) / 100.0 * cap)
                g = min(1.0, max(0.0, (g * prev + phi * ein) / (prev + ein)))
            out.append((t, phi, phi_b, g))
        if s is not None:
            soc = s
    return out, g, soc


def resample(series, t0, n):
    """Medii pe minut (n minute de la t0) dintr-o serie (t, valoare) tinuta constanta pana la urmatoarea schimbare; None unde nu stim nimic."""
    out = [None] * n
    if not series:
        return out
    i, cur = 0, None
    while i < len(series) and series[i][0] <= t0:
        cur = series[i][1]
        i += 1
    for m in range(n):
        a = t0 + m * MIN
        b = a + MIN
        acc = cov = 0.0
        tc, v = a, cur
        while i < len(series) and series[i][0] < b:
            tp, vp = series[i]
            if v is not None:
                acc += v * (tp - tc)
                cov += tp - tc
            tc, v = tp, vp
            i += 1
        if v is not None:
            acc += v * (b - tc)
            cov += b - tc
        cur = v
        out[m] = acc / cov if cov > 0 else None
    return out


def weighted_share(rows, power, expected):
    """rows: [(t, phi, phi_baterie)] ale unei incarcari; power: [(t, kW)] sau None; expected = cate minute are incarcarea. Intoarce {phi, phi_batt, minutes} sau None
    (acoperire sub COVER_MIN / nicio putere)."""
    if not rows or len(rows) < COVER_MIN * max(1, expected):
        return None
    times = [p[0] for p in power] if power else []
    sw = sp = sb = 0.0
    n = 0
    for t, phi, phib in rows:
        if phi is None:
            continue
        w = 1.0
        if power:
            i = bisect.bisect_right(times, t + MIN / 2) - 1
            w = max(0.0, power[i][1]) if i >= 0 else 0.0
        if w <= 0:
            continue
        sw += w
        sp += w * phi
        sb += w * (phib or 0.0)
        n += 1
    if sw <= 0:
        return None
    return dict(phi=min(1.0, sp / sw), phi_batt=min(1.0, sb / sw), minutes=n)


def init(S):
    lock = threading.Lock()
    S.OWN.migrate('energysrc', ['create table src_min (t integer primary key, pv real, grid real, batt real, soc real, phi real, phib real, g real)'])
    st = dict(g=0.0, soc=None, t=0, cap=None, cap_t=0.0)
    last = S.OWN.one('select t, g, soc from src_min order by t desc limit 1')
    if last:
        st.update(g=last['g'] or 0.0, soc=last['soc'], t=last['t'])

    def ents():
        grid, pre = S.HA.get('grid') or '', ''
        if grid.endswith('grid_import_power'):
            pre = grid[:-len('grid_import_power')]
        e = dict(grid=grid, pv=S.HA.get('pv') or (pre + 'pv_power' if pre else ''), batt=S.cget('ha_batt_power', 'HA_BATT_POWER', '') or (pre + 'battery_power' if pre else ''),
                 soc=S.cget('ha_batt_soc', 'HA_BATT_SOC', '') or (pre + 'battery' if pre else ''))
        cap = str(S.cget('ha_batt_kwh', 'HA_BATT_KWH', '') or '')
        e['cap'] = cap or (pre + 'battery_capacity' if pre else '')
        return e

    def active():
        e = ents()
        return bool(S.ha_ok() and e['grid'] and e['pv'] and e['batt'] and e['soc'])

    def sign():
        return 1 if str(S.cget('ha_batt_sign', 'HA_BATT_SIGN', '-')).strip() == '+' else -1

    def num(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return None

    def capacity(force=False):
        """kWh utili ai bateriei casei: valoare fixa din setare sau senzorul de capacitate (citit rar)."""
        if st['cap'] and not force and time.time() - st['cap_t'] < 600:
            return st['cap']
        raw = ents()['cap']
        v = num(raw)
        if v is None and raw:
            s = S.ha_state(raw)
            v = num(s.get('state')) if s else None
        if v and v > 0:
            st['cap'], st['cap_t'] = v, time.time()
        return st['cap'] or 30.0

    def store(rows):
        """Ruleaza modelul pe minutele noi (in ordine) si le salveaza."""
        rows = [r for r in rows if r[0] > st['t']]
        if not rows:
            return 0
        with lock:
            out, st['g'], st['soc'] = advance(st['g'], st['soc'], capacity(), [(t, pv, gr, b, s) for t, pv, gr, b, s in rows], sign())
            by_t = {r[0]: r for r in rows}
            recs = [(t, by_t[t][1], by_t[t][2], by_t[t][3], by_t[t][4], phi, phib, g) for t, phi, phib, g in out]
            with S.OWN.tx() as c:
                c.executemany('insert or replace into src_min(t, pv, grid, batt, soc, phi, phib, g) values(?,?,?,?,?,?,?,?)', recs)
            st['t'] = rows[-1][0]
        return len(rows)

    def backfill(t_from, t_to):
        """Umple minutele [t_from, t_to) din istoricul HA, in bucati. Intoarce cate minute a adaugat."""
        e = ents()
        t_from = int(t_from // MIN + 1) * MIN
        t_to = int(t_to // MIN) * MIN
        total = 0
        cur = t_from
        while cur < t_to:
            end = min(t_to, cur + CHUNK_S)
            a, b = dt.datetime.fromtimestamp(cur - MIN, dt.timezone.utc).replace(tzinfo=None), dt.datetime.fromtimestamp(end, dt.timezone.utc).replace(tzinfo=None)
            ser = {k: S.ha_history(e[k], a, b) for k in ('pv', 'grid', 'batt', 'soc')}
            if not (ser['grid'] or ser['batt'] or ser['pv']):
                cur = end
                continue
            n = int((end - cur) // MIN)
            cols = {k: resample(v, cur, n) for k, v in ser.items()}
            rows = []
            for i in range(n):
                pv, gr, ba = cols['pv'][i], cols['grid'][i], cols['batt'][i]
                if pv is None and gr is None and ba is None:
                    continue
                rows.append((cur + i * MIN, pv, gr, ba, cols['soc'][i]))
            total += store(rows)
            cur = end
        return total

    def ensure():
        """Completeaza de la ultimul minut salvat pana acum (la pornire: din istoricul HA, cel mult ~10 zile)."""
        now = time.time()
        start = max(now - HA_KEEP_S, st['t'])
        if now - start < 3 * MIN:
            return 0
        n = backfill(start, now - MIN)
        if n and hasattr(S, 'RC_CACHE'):
            S.RC_CACHE.clear()                                          # costurile reale se recalculeaza cu originea energiei
        return n

    def prune():
        S.OWN.run('delete from src_min where t < ?', (time.time() - KEEP_DAYS * 86400,))

    def loop():
        time.sleep(45)
        bucket, cur_min, last_ens, last_prune = {}, 0, 0.0, 0.0
        while True:
            try:
                if active():
                    if time.time() - last_ens > 3600:
                        last_ens = time.time()
                        ensure()
                    e = ents()
                    now = time.time()
                    m = int(now // MIN) * MIN
                    if cur_min and m != cur_min and bucket:                  # s-a incheiat un minut: media esantioanelor lui
                        avg = lambda k: (sum(bucket[k]) / len(bucket[k])) if bucket.get(k) else None
                        store([(cur_min, avg('pv'), avg('grid'), avg('batt'), avg('soc'))])
                        bucket = {}
                    cur_min = m
                    for k in ('pv', 'grid', 'batt', 'soc'):
                        s = S.ha_state(e[k])
                        v = num(s.get('state')) if s else None
                        if v is not None:
                            bucket.setdefault(k, []).append(v)
                    if now - last_prune > 86400:
                        last_prune = now
                        prune()
            except Exception as ex:  # noqa
                S.log('origine energie:', str(ex)[:100], flush=True)
            time.sleep(SAMPLE_S)

    class EnergySrc:
        def share(self, t0, t1, power=None):
            """Fractia din energia luata de masina in [t0, t1] (UNIX) care a venit din retea (direct sau prin bateria incarcata din retea); power = [(t, kW)] ca sa
            se pondereze cu puterea masinii. None daca nu avem minutele."""
            a = int(t0 // MIN) * MIN
            rows = S.OWN.rows('select t, phi, phib from src_min where t >= ? and t < ? order by t', (a, t1))
            out = weighted_share([(r['t'], r['phi'], r['phib']) for r in rows], power, max(1, int((t1 - t0) // MIN)))
            if out:
                out['g_end'] = (S.OWN.one('select g from src_min where t < ? order by t desc limit 1', (t1,)) or {}).get('g')
            return out

        def for_charge(self, cp_id, t0, t1):
            """Ca `share`, ponderat cu puterea de la incarcator a incarcarii TeslaMate `cp_id`."""
            try:
                pw = [(dt.datetime.fromisoformat(str(r['date'])).replace(tzinfo=dt.timezone.utc).timestamp(), float(r['kw'] or 0)) for r in S.q(
                    'select date, charger_power kw from charges where charging_process_id=%s order by date', (cp_id,))]
            except Exception:  # noqa
                pw = None
            return self.share(t0, t1, pw or None)

        def fill(self):
            """Completeaza minutele lipsa din istoricul HA (la pornire si din ora in ora); intoarce cate minute a adaugat."""
            return ensure() if active() else 0

        def status(self):
            first = S.OWN.one('select min(t) a, max(t) b, count(*) n from src_min') or {}
            cur = S.OWN.one('select t, phi, phib, g, soc from src_min order by t desc limit 1')
            return dict(active=active(), minutes=first.get('n') or 0, from_=first.get('a'), to=first.get('b'), battery_grid_pct=None if not cur else round((cur['g'] or 0) * 100),
                        soc=None if not cur else cur['soc'], now_grid_pct=None if not cur or cur['phi'] is None else round(cur['phi'] * 100), entities=ents() if active() else None)

    S.ENERGYSRC = EnergySrc()

    @S.route('GET', '/api/energysrc')
    def status_route(h, a):
        return S.ENERGYSRC.status()

    if hasattr(S, 'BG_TASKS'):
        S.BG_TASKS.append(loop)

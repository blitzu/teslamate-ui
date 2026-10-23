"""Statistici de incarcare (ca dashboard-ul "Charging Stats" din TeslaMate): kWh AC vs DC, viteza medie/maxima pe procente de baterie (pe tip de incarcare),
nivelul bateriei la care incepi si opresti incarcarea, kWh pe luna. Se calculeaza din datele TeslaMate, pe perioada aleasa."""
import datetime as dt

STEP = 10                                   # latimea unui interval de baterie (%)


def bucket(v, step=STEP):
    return min(100 - step, max(0, int(v) // step * step))


def summarize(rows):
    """rows: incarcari terminate cu dc, charge_energy_added/used, duration_min, power_max, start_soc/end_soc, start_date. Intoarce totaluri AC/DC, histograme si kWh pe luna."""
    kinds = {k: dict(n=0, kwh=0.0, used=0.0, min=0.0, power_max=0.0, maxsum=0.0) for k in ('ac', 'dc')}
    start_h = {k: [0] * (100 // STEP) for k in kinds}
    end_h = {k: [0] * (100 // STEP) for k in kinds}
    months = {}
    for r in rows:
        k = 'dc' if r.get('dc') else 'ac'
        x = kinds[k]
        add = float(r.get('charge_energy_added') or 0)
        x['n'] += 1
        x['kwh'] += add
        x['used'] += float(r.get('charge_energy_used') or 0) or add
        x['min'] += float(r.get('duration_min') or 0)
        pm = float(r.get('power_max') or 0)
        x['power_max'] = max(x['power_max'], pm)
        x['maxsum'] += pm
        if r.get('start_soc') is not None:
            start_h[k][bucket(r['start_soc']) // STEP] += 1
        if r.get('end_soc') is not None:
            end_h[k][min(100 // STEP - 1, max(0, (int(r['end_soc']) - 1) // STEP))] += 1       # 100% intra in intervalul 90-100
        m = str(r['start_date'])[:7]
        mm = months.setdefault(m, dict(month=m, ac=0.0, dc=0.0))
        mm[k] += add
    out = {}
    for k, x in kinds.items():
        out[k] = dict(n=x['n'], kwh=round(x['kwh'], 1), used=round(x['used'], 1), hours=round(x['min'] / 60, 1), avg_kwh=round(x['kwh'] / x['n'], 1) if x['n'] else None,
                      avg_kw=round(x['kwh'] / (x['min'] / 60), 1) if x['min'] > 0 else None, power_max=round(x['power_max']) if x['n'] else None,
                      avg_peak=round(x['maxsum'] / x['n']) if x['n'] else None, efficiency=round(x['kwh'] / x['used'] * 100) if x['used'] else None)
    tot = out['ac']['kwh'] + out['dc']['kwh']
    return dict(kinds=out, dc_share=round(out['dc']['kwh'] / tot * 100) if tot else None,
                start_hist={k: [dict(from_=i * STEP, n=n) for i, n in enumerate(v)] for k, v in start_h.items()},
                end_hist={k: [dict(from_=i * STEP, n=n) for i, n in enumerate(v)] for k, v in end_h.items()},
                months=[dict(month=m['month'], ac=round(m['ac'], 1), dc=round(m['dc'], 1)) for m in sorted(months.values(), key=lambda m: m['month'])][-24:])


def init(S):
    @S.route('GET', '/api/chstats')
    def stats(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        if hc is False:
            return dict(empty=True)
        car = int(a.get('car', 1))
        lo, hi, _ = S.list_filters(a, 'charge')
        rows = S._charges_rows(car, 5000, 0, None, lo, hi)
        out = summarize(rows)
        # viteza pe procente de baterie: medie si maxim din esantioanele de putere, separat AC / DC (dupa tipul sesiunii)
        q = [f"select case when s.dc then 'dc' else 'ac' end as k, (least(ch.battery_level, 99) / {STEP}) * {STEP} as b, avg(ch.charger_power) as avg_kw, max(ch.charger_power) as max_kw, count(*) as n",
             "from charges ch join charging_processes cp on cp.id = ch.charging_process_id",
             "join (select charging_process_id as id, bool_or(fast_charger_present) as dc from charges group by charging_process_id) s on s.id = cp.id",
             "where cp.car_id = %s and cp.end_date is not null and ch.battery_level is not null and ch.charger_power is not null and ch.charger_power > 1"]
        par = [car]
        if lo:
            q.append('and cp.start_date >= %s')
            par.append(lo)
        if hi:
            q.append('and cp.start_date < %s')
            par.append(hi)
        q.append('group by 1, 2 order by 1, 2')
        by = {'ac': [], 'dc': []}
        for r in S.q(' '.join(q), tuple(par)):
            by[r['k']].append(dict(from_=int(r['b']), avg=round(float(r['avg_kw']), 1), max=round(float(r['max_kw']), 1), n=r['n']))
        out['power_by_soc'] = by
        out['period'] = dict(from_=lo.isoformat() if lo else None, to=hi.isoformat() if hi else None)
        return out

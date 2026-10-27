"""Statistici de incarcare (ca dashboard-ul "Charging Stats" din TeslaMate): kWh AC vs DC, viteza medie/maxima pe procente de baterie (pe tip de incarcare),
nivelul bateriei la care incepi si opresti incarcarea, kWh pe luna. Se calculeaza din datele TeslaMate, pe perioada aleasa."""
import datetime as dt

STEP = 10                                   # latimea unui interval de baterie (%)


def bucket(v, step=STEP):
    return min(100 - step, max(0, int(v) // step * step))


def month_of(start_date, tz):
    """Luna (YYYY-MM) in ora locala; start_date vine din TeslaMate in UTC."""
    s = str(start_date)
    if tz is None:
        return s[:7]
    try:
        return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).astimezone(tz).strftime('%Y-%m')
    except ValueError:
        return s[:7]


def summarize(rows, tz=None):
    """rows: incarcari terminate cu dc, charge_energy_added/used, duration_min, power_max, start_soc/end_soc, start_date. Intoarce totaluri AC/DC, histograme si kWh pe luna."""
    kinds = {k: dict(n=0, kwh=0.0, used=0.0, min=0.0, power_max=0.0, maxsum=0.0, eff_add=0.0, eff_used=0.0) for k in ('ac', 'dc')}
    start_h = {k: [0] * (100 // STEP) for k in kinds}
    end_h = {k: [0] * (100 // STEP) for k in kinds}
    months = {}
    for r in rows:
        k = 'dc' if r.get('dc') else 'ac'
        x = kinds[k]
        add = float(r.get('charge_energy_added') or 0)
        x['n'] += 1
        x['kwh'] += add
        used = float(r.get('charge_energy_used') or 0)
        x['used'] += used or add
        if used > 0:
            x['eff_add'] += add                                           # eficienta se calculeaza doar din sesiunile care raporteaza energia consumata
            x['eff_used'] += used
        x['min'] += float(r.get('duration_min') or 0)
        pm = float(r.get('power_max') or 0)
        x['power_max'] = max(x['power_max'], pm)
        x['maxsum'] += pm
        if r.get('start_soc') is not None:
            start_h[k][bucket(r['start_soc']) // STEP] += 1
        if r.get('end_soc') is not None:
            end_h[k][bucket(r['end_soc']) // STEP] += 1                                       # aceeasi regula ca la start: 80% intra in 80-90, 100% in 90-100
        m = month_of(r['start_date'], tz)
        mm = months.setdefault(m, dict(month=m, ac=0.0, dc=0.0))
        mm[k] += add
    out = {}
    for k, x in kinds.items():
        out[k] = dict(n=x['n'], kwh=round(x['kwh'], 1), used=round(x['used'], 1), hours=round(x['min'] / 60, 1), avg_kwh=round(x['kwh'] / x['n'], 1) if x['n'] else None,
                      avg_kw=round(x['kwh'] / (x['min'] / 60), 1) if x['min'] > 0 else None, power_max=round(x['power_max']) if x['n'] else None,
                      avg_peak=round(x['maxsum'] / x['n']) if x['n'] else None, efficiency=round(x['eff_add'] / x['eff_used'] * 100) if x['eff_used'] else None)
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
        lo, hi, ids = S.list_filters(a, 'charge')
        rows = S._charges_rows(car, 5000, 0, None, lo, hi, ids)
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(S.LOCAL_TZ)
        except Exception:  # noqa
            tz = None
        out = summarize(rows, tz)
        # viteza pe procente de baterie: medie si maxim din esantioanele de putere, separat AC / DC (dupa tipul sesiunii)
        sel = ['cp.car_id = %s', 'cp.end_date is not null']                  # tipul (AC/DC) se calculeaza doar pentru sesiunile din perioada, nu pentru toata tabela charges
        par = [car]
        if lo:
            sel.append('cp.start_date >= %s')
            par.append(lo)
        if hi:
            sel.append('cp.start_date < %s')
            par.append(hi)
        if ids is not None:
            sel.append('cp.id = any(%s)')
            par.append(list(ids))
        q = [f"with cps as (select cp.id, coalesce((select bool_or(c2.fast_charger_present) from charges c2 where c2.charging_process_id = cp.id), false) as dc from charging_processes cp where {' and '.join(sel)})",
             f"select case when cps.dc then 'dc' else 'ac' end as k, (least(ch.battery_level, 99) / {STEP}) * {STEP} as b, avg(ch.charger_power) as avg_kw, max(ch.charger_power) as max_kw, count(*) as n",
             "from charges ch join cps on cps.id = ch.charging_process_id",
             "where ch.battery_level is not null and ch.charger_power is not null and ch.charger_power > 1",
             'group by 1, 2 order by 1, 2']
        by = {'ac': [], 'dc': []}
        for r in S.q(' '.join(q), tuple(par)):
            by[r['k']].append(dict(from_=int(r['b']), avg=round(float(r['avg_kw']), 1), max=round(float(r['max_kw']), 1), n=r['n']))
        out['power_by_soc'] = by
        out['period'] = dict(from_=lo.isoformat() if lo else None, to=hi.isoformat() if hi else None)
        return out

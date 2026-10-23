"""Software: istoricul versiunilor instalate (tabelul `updates` din TeslaMate), durata instalarii, consumul mediu inainte/dupa si notele de versiune
de la Tesla (doar daca masina e treaza; nu o trezim niciodata)."""
import datetime as dt
import time


def wh_km(rows):
    km = sum(r.get('distance') or 0 for r in rows if r.get('kwh') is not None)
    kwh = sum(r['kwh'] for r in rows if r.get('kwh') is not None)
    return round(kwh * 1000 / km) if km > 20 else None


def init(S):
    def consumption(car, a, b):
        rows = S.q("""select d.distance, (d.start_ideal_range_km - d.end_ideal_range_km) * c.efficiency as kwh, d.outside_temp_avg t
                      from drives d join cars c on c.id = d.car_id where d.car_id=%s and d.end_date is not null and d.start_date >= %s and d.start_date < %s""", (car, a, b))
        temps = [r['t'] for r in rows if r['t'] is not None]
        return dict(wh_km=wh_km(rows), km=round(sum(r['distance'] or 0 for r in rows)), temp=round(sum(temps) / len(temps), 1) if temps else None)

    def release_notes(car):
        """Notele versiunii curente, citite o data pe saptamana (si la schimbarea versiunii) si numai cat masina e treaza."""
        live = S.LIVE.get(car, {})
        ver = live.get('version')
        cached = S.OWN.kv_get('release_notes', {})
        fresh = cached.get('version') == ver and time.time() - cached.get('ts', 0) < 7 * 86400
        if fresh or live.get('state') not in ('online', 'charging', 'driving'):
            return cached
        try:
            vin = S.vin_for(car)
            code, r = S.vehicle_call(vin, 'release_notes', method='GET')
            notes = ((r.get('response') or {}).get('release_notes') or []) if code == 200 else []
            text = '\n\n'.join('%s\n%s' % (n.get('title') or '', n.get('description') or '') for n in notes).strip()
            cached = dict(version=ver, ts=time.time(), text=text[:4000], ok=code == 200)
            S.OWN.kv_set('release_notes', cached)
        except Exception as e:  # noqa
            S.log('note versiune: %s' % e)
        return cached

    @S.route('GET', '/api/software')
    def software(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        car = int(a.get('car', 1))
        live = S.LIVE.get(car, {})
        if hc is False:
            now = dt.datetime.utcnow()
            return dict(current='2026.14.3', update_available=None, notes=dict(text='Demo: note de versiune.'), updates=[
                dict(version='2026.14.3', start=(now - dt.timedelta(days=12)).isoformat(), end=(now - dt.timedelta(days=12, hours=-1)).isoformat(), minutes=58,
                     before=dict(wh_km=148, km=900, temp=6.1), after=dict(wh_km=143, km=640, temp=4.8)),
                dict(version='2026.8.9', start=(now - dt.timedelta(days=51)).isoformat(), end=(now - dt.timedelta(days=51, hours=-1)).isoformat(), minutes=44,
                     before=dict(wh_km=139, km=1100, temp=11.2), after=dict(wh_km=148, km=900, temp=6.1))])
        rows = S.q('select version, start_date, end_date from updates where car_id=%s order by start_date desc limit 30', (car,))
        now = dt.datetime.utcnow()
        out = []
        for r in rows:
            a0 = dt.datetime.fromisoformat(r['start_date'])
            b0 = dt.datetime.fromisoformat(r['end_date']) if r['end_date'] else None
            before = consumption(car, (a0 - dt.timedelta(days=30)).isoformat(), a0.isoformat())
            after = consumption(car, (b0 or a0).isoformat(), ((b0 or a0) + dt.timedelta(days=30)).isoformat()) if b0 else None
            out.append(dict(version=r['version'], start=r['start_date'], end=r['end_date'], minutes=round((b0 - a0).total_seconds() / 60) if b0 else None, before=before, after=after))
        return dict(current=live.get('version') or (out[0]['version'] if out else None), update_available=live.get('update_version') if live.get('update_available') else None,
                    notes=release_notes(car), updates=out)

"""Tag-uri pentru curse si incarcari (ex. "Vacanta Grecia", "Serviciu") si vederea de ansamblu pe harta (traseu + incarcari + opriri) pentru o calatorie,
un interval de date, cateva curse alese sau tot ce are un tag. Tag-urile se tin in baza proprie a aplicatiei, nu in TeslaMate."""
import datetime as dt
import re

KINDS = ('drive', 'charge')
NAME = re.compile(r'[^\w \-.+/]', re.U)
MAX_DRIVES = 300
MAX_POINTS = 6000
STOP_MIN = 5                                # pauze mai scurte de 5 min nu se arata


def clean_name(s):
    n = NAME.sub('', str(s or '')).strip()[:30]
    return n


def build(drives, charges, tagged_charge_ids=(), gap_min=STOP_MIN):
    """drives: curse (cu start/end, coordonate), sortate cronologic; charges: incarcari din interval. Intoarce (incarcari incluse, opriri, rezumat).
    O incarcare intra daca are tag-ul cerut sau cade intre prima plecare si ultima sosire (+/- 30 min). Oprirea = pauza dintre doua curse consecutive care nu e o incarcare."""
    P = lambda x: dt.datetime.fromisoformat(str(x)) if x else None
    if not drives:
        return [], [], dict(drives=0, km=0, kwh=0, drive_min=0, charges=0, charged_kwh=0, cost=0, stops=0, start=None, end=None)
    t0, t1 = P(drives[0]['start_date']), P(drives[-1]['end_date'])
    pad = dt.timedelta(minutes=30)
    keep = [c for c in charges if c['id'] in tagged_charge_ids or (t0 - pad <= P(c['start_date']) <= t1 + pad)]
    keep.sort(key=lambda c: c['start_date'])
    stops = []
    for a, b in zip(drives, drives[1:]):
        ea, sb = P(a['end_date']), P(b['start_date'])
        gap = (sb - ea).total_seconds() / 60
        if gap < gap_min:
            continue
        if any(ea - dt.timedelta(minutes=2) <= P(c['start_date']) <= sb for c in keep):
            continue                                                      # pauza cu incarcare: apare ca incarcare
        if a.get('end_lat') is None:
            continue
        stops.append(dict(lat=a['end_lat'], lon=a['end_lon'], start=a['end_date'], end=b['start_date'], min=round(gap), name=a.get('end_name')))
    km = sum(d.get('distance') or 0 for d in drives)
    cost = sum(c.get('cost_eff') or 0 for c in keep)
    return keep, stops, dict(drives=len(drives), km=round(km, 1), kwh=round(sum(d.get('kwh') or 0 for d in drives), 1), drive_min=round(sum(d.get('duration_min') or 0 for d in drives)),
                             charges=len(keep), charged_kwh=round(sum(c.get('charge_energy_added') or 0 for c in keep), 1), cost=round(cost, 2), stops=len(stops),
                             start=drives[0]['start_date'], end=drives[-1]['end_date'])


def thin(points, per):
    step = max(1, -(-len(points) // per))
    out = points[::step]
    if points and out[-1] is not points[-1]:
        out.append(points[-1])
    return out


def init(S):
    S.OWN.migrate('tags', ['create table tags (id integer primary key, name text not null unique collate nocase)',
                           'create table tag_links (kind text not null, ref integer not null, tag_id integer not null, primary key (kind, ref, tag_id))',
                           'create index tag_links_tag on tag_links(tag_id)'])

    class Tags:
        def ids(self, kind, name):
            return [r['ref'] for r in S.OWN.rows('select l.ref from tag_links l join tags t on t.id=l.tag_id where l.kind=? and t.name=?', (kind, clean_name(name)))]

        def attach(self, kind, rows):
            if not rows:
                return rows
            m = {}
            for r in S.OWN.rows('select l.ref, t.name from tag_links l join tags t on t.id=l.tag_id where l.kind=? and l.ref in (%s) order by t.name' % ','.join('?' * len(rows)), (kind,) + tuple(x['id'] for x in rows)):
                m.setdefault(r['ref'], []).append(r['name'])
            for x in rows:
                x['tags'] = m.get(x['id'], [])
            return rows

    S.TAGS = Tags()

    @S.route('GET', '/api/tags')
    def listing(h, a):
        return dict(tags=S.OWN.rows('select t.name, count(l.ref) n from tags t left join tag_links l on l.tag_id=t.id group by t.id order by t.name collate nocase'))

    @S.route('POST', '/api/tags/set', pin=True, role='user')
    def set_tags(h, b):
        kind = b.get('kind')
        if kind not in KINDS:
            raise ValueError('kind: drive | charge')
        try:
            ids = [int(i) for i in (b.get('ids') or [])][:500]
        except (TypeError, ValueError):
            raise ValueError('ids invalide')
        if not ids:
            raise ValueError('Nimic selectat.')
        add = [n for n in (clean_name(x) for x in (b.get('add') or [])) if n][:5]
        rem = [n for n in (clean_name(x) for x in (b.get('remove') or [])) if n][:5]
        if add and S.OWN.one('select count(*) n from tags')['n'] + len(add) > 80:
            raise ValueError('Prea multe tag-uri (max 80).')
        with S.OWN.tx() as c:
            for n in add:
                c.execute('insert into tags(name) values(?) on conflict(name) do nothing', (n,))
                tid = c.execute('select id from tags where name=?', (n,)).fetchone()[0]
                c.executemany('insert into tag_links(kind, ref, tag_id) values(?,?,?) on conflict do nothing', [(kind, i, tid) for i in ids])
            for n in rem:
                row = c.execute('select id from tags where name=?', (n,)).fetchone()
                if row:
                    c.executemany('delete from tag_links where kind=? and ref=? and tag_id=?', [(kind, i, row[0]) for i in ids])
            c.execute('delete from tags where id not in (select tag_id from tag_links)')                    # tag-urile fara nicio legatura dispar
        return dict(ok=True)

    @S.route('GET', '/api/journey')
    def journey(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        if hc is False:
            return dict(drives=[], charges=[], stops=[], summary=build([], [])[2], note='Nu există curse reale în demo.')
        car = int(a.get('car', 1))
        trip_id = a.get('trip')
        tag = clean_name(a.get('tag'))
        tagged_ch = set()
        truncated = False
        if trip_id:                                        # calatoria care contine cursa: curse vecine cu pauza < TRIP_GAP (acelasi lant ca la reluare)
            did = int(trip_id)
            rows = S.q("""select id, start_date, end_date from drives where car_id=%s and end_date is not null
                and start_date between (select start_date - interval '3 days' from drives where id=%s) and (select end_date + interval '3 days' from drives where id=%s)
                order by start_date""", (car, did, did))
            idx = next((i for i, r in enumerate(rows) if r['id'] == did), None)
            if idx is None:
                raise S.NotFound()
            lo = hi = idx
            while lo > 0 and S._dtp(rows[lo]['start_date']) - S._dtp(rows[lo - 1]['end_date']) < S.TRIP_GAP:
                lo -= 1
            while hi < len(rows) - 1 and S._dtp(rows[hi + 1]['start_date']) - S._dtp(rows[hi]['end_date']) < S.TRIP_GAP:
                hi += 1
            ds = S.drives_by_ids(car, [r['id'] for r in rows[lo:hi + 1]])
        elif a.get('ids'):
            try:
                want = [int(i) for i in str(a['ids']).split(',') if i][:MAX_DRIVES]
            except ValueError:
                raise ValueError('ids invalide')
            ds = S.drives_by_ids(car, want)
        else:
            lo_d, hi_d, ids = S.list_filters(a, 'drive')
            ds = S.drives(car, MAX_DRIVES + 1, 0, lo_d, hi_d, ids)
            if len(ds) > MAX_DRIVES:
                truncated, ds = True, ds[:MAX_DRIVES]
            ds.sort(key=lambda d: d['start_date'])
            if tag:
                tagged_ch = set(S.TAGS.ids('charge', tag))
        ds.sort(key=lambda d: d['start_date'])
        if not ds and not tagged_ch:
            return dict(drives=[], charges=[], stops=[], summary=build([], [])[2], truncated=False)
        starts = [d['start_date'] for d in ds]
        t0 = S._dtp(min(starts)) - dt.timedelta(minutes=45) if ds else None
        t1 = S._dtp(max(d['end_date'] for d in ds)) + dt.timedelta(minutes=45) if ds else None
        chs = S.decorate(S._charges_rows(car, 600, 0, None, t0, t1)) if ds else []
        if tagged_ch:
            have = {c['id'] for c in chs}
            extra = [c for c in S.decorate(S._charges_rows(car, 600, 0, None, None, None, list(tagged_ch))) if c['id'] not in have]
            chs += extra
        keep, stops, summ = build(ds, chs, tagged_ch)
        per = max(40, MAX_POINTS // max(1, len(ds)))
        out = []
        for d in ds:
            pts = S.q('select latitude, longitude, speed from positions where drive_id=%s and latitude is not null order by date', (d['id'],))
            out.append(dict(id=d['id'], start=d['start_date'], end=d['end_date'], km=d['distance'], kwh=d['kwh'], from_=d['start_name'], to=d['end_name'],
                            pts=[[round(p['latitude'], 5), round(p['longitude'], 5), p['speed']] for p in thin(pts, per)]))
        return dict(drives=out, charges=[dict(id=c['id'], lat=c['lat'], lon=c['lon'], name=c['name'], start=c['start_date'], end=c['end_date'], kwh=c['charge_energy_added'], cost=c.get('cost_eff'), dc=c['dc'])
                                         for c in keep if c.get('lat') is not None], stops=stops, summary=summ, truncated=truncated)

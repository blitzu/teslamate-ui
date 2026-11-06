"""Credit cumparat la un furnizor (pachet): platesti X si primesti credit mai mare in bani ("1000 lei pentru 2000 lei credit" la iHunt) sau in kilometri de autonomie
("100 lei pentru 1000 km" la Tesla Supercharger). Cat timp furnizorul unei incarcari are un pachet, costul ei real se calculeaza singur din pret de lista:
  - bani:  cost real = cost la tarif de lista x (platit / credit)          (2000 credit pentru 1000 lei = 50% din tariful afisat)
  - km:    cost real = km de autonomie adaugati x (platit / km cumparati)   (1000 km pentru 100 lei = 0,10 lei/km)
Un cost scris de tine de mana ramane neatins (e suma reala); un cost venit din tariful ales al unei statii e pret de lista, deci i se aplica creditul.
Nu se scrie nimic in TeslaMate; pachetele stau in baza proprie a aplicatiei."""
import re
import time

MAX_PACKS = 60


def clean(s, n=40):
    return re.sub(r'[<>"\r\n]', '', str(s or '')).strip()[:n]


def num(x, lo, hi, what):
    try:
        v = float(str(x).replace(',', '.'))
    except (TypeError, ValueError):
        raise ValueError(what + ' invalid')
    if not (lo < v <= hi):
        raise ValueError(what + ' invalid')
    return round(v, 4)


def parse(b):
    """Pachetul din cerere, validat: furnizor, tip ('money' | 'km'), suma platita, creditul primit (bani sau km), de la ce data se aplica (optional)."""
    prov = clean(b.get('provider'))
    if not prov:
        raise ValueError('Scrie furnizorul.')
    kind = 'km' if str(b.get('kind')) == 'km' else 'money'
    paid = num(b.get('paid'), 0, 1e7, 'Suma plătită')
    amount = num(b.get('amount'), 0, 1e7, 'Creditul primit' if kind == 'money' else 'Kilometrii')
    since = str(b.get('since') or '').strip()[:10]
    if since and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', since):
        raise ValueError('Data invalidă.')
    return dict(provider=prov, kind=kind, paid=paid, amount=amount, since=since, note=clean(b.get('note'), 60))


def rate(p):
    """bani: cat platesti pentru 1 leu de credit (0,5 = jumatate din pret); km: lei pe kilometru de autonomie."""
    return p['paid'] / p['amount']


def pick(packs, provider, day):
    """Pachetul care se aplica unei incarcari: al furnizorului ei, valabil la data ei; daca sunt mai multe, cel mai recent (dupa data de la care se aplica)."""
    prov = str(provider or '').strip().casefold()
    ok = [p for p in packs if p['provider'].casefold() == prov and (not p.get('since') or p['since'] <= str(day)[:10])]
    return max(ok, key=lambda p: (p.get('since') or '', p['id'])) if ok else None


def adjust(p, list_cost=None, km=None):
    """Costul real dupa credit (sau None daca lipseste ce trebuie): bani => din costul de lista, km => din kilometrii adaugati."""
    if p['kind'] == 'km':
        return round(km * rate(p), 2) if km and km > 0 else None
    return round(list_cost * rate(p), 2) if list_cost is not None else None


def range_km(r):
    r0, r1 = r.get('start_rated_range_km'), r.get('end_rated_range_km')
    return float(r1) - float(r0) if r0 is not None and r1 is not None else None


def info_row(packs, r):
    """Pachetul care se aplica unei incarcari, chiar daca ea are cost scris de mana: pentru "pretul real" afisat langa tarifele statiilor. Pentru km, si echivalentul pe kWh."""
    p = pick(packs, r.get('provider'), r.get('start_date') or '')
    if not p:
        return None
    out = dict(pack=p['id'], kind=p['kind'], rate=round(rate(p), 4))
    kwh, km = r.get('charge_energy_used') or r.get('charge_energy_added'), range_km(r)
    if p['kind'] == 'km' and kwh and km and km > 0:
        out['per_kwh'] = round(rate(p) * km / float(kwh), 3)
    return out


def adjust_row(packs, r, e):
    """Pentru o incarcare (r = randul ei dupa furnizor si cost_eff, e = datele salvate in aplicatie): dict cu costul real si detaliile, sau None cand nu se aplica."""
    p = pick(packs, r.get('provider'), r.get('start_date') or '')
    if not p:
        return None
    kwh = r.get('charge_energy_used') or r.get('charge_energy_added')
    st = e.get('station') or {}
    tar, sel = st.get('tariffs') or [], int(st.get('sel', -1) if st.get('sel') is not None else -1)
    t = tar[sel] if 0 <= sel < len(tar) else None
    manual = e.get('cost')
    if manual is not None:
        if not (t and kwh and abs(float(manual) - round(float(t['price']) * float(kwh), 2)) <= 0.011):
            return None                                                    # suma scrisa de tine = suma reala: nu o schimbam
        base = float(manual)                                                # costul vine din tariful statiei: e pret de lista
    else:
        base = r.get('cost_eff')
    km = range_km(r)
    cost = adjust(p, base, km)
    if cost is None:
        return None
    return dict(pack=p['id'], kind=p['kind'], rate=round(rate(p), 4), list=round(base, 2) if base is not None else None, km=round(km, 1) if km else None, cost=cost)


def init(S):
    S.OWN.migrate('credits', ['create table credit_packs (id integer primary key, provider text not null, kind text not null, paid real not null, amount real not null, since text, note text, ts real)'])
    cache = {'t': 0, 'rows': []}

    def rows():
        if time.time() - cache['t'] > 30:
            cache['rows'], cache['t'] = S.OWN.rows('select id, provider, kind, paid, amount, since, note from credit_packs'), time.time()
        return cache['rows']

    class Credits:
        def adjust(self, r, e):
            return adjust_row(rows(), r, e)

        def info(self, r):
            return info_row(rows(), r)

    S.CREDITS = Credits()

    def usage(car, demo):
        """Cat s-a folosit din fiecare pachet (din incarcarile care i se potrivesc) si cat a ramas din credit."""
        data = S.decorate([dict(c) for c in S.DEMO['charges']] if demo else S._charges_rows(car, 5000, 0))
        use = {}
        for r in data:
            c = r.get('credit')
            if not c:
                continue
            u = use.setdefault(c['pack'], dict(n=0, kwh=0.0, used=0.0, real=0.0, list=0.0))
            u['n'] += 1
            u['kwh'] += r.get('charge_energy_used') or r.get('charge_energy_added') or 0
            u['real'] += c['cost']
            u['list'] += c['list'] or 0
            u['used'] += (c['km'] or 0) if c['kind'] == 'km' else (c['list'] or 0)
        return {k: dict(n=u['n'], kwh=round(u['kwh'], 1), used=round(u['used'], 1), real=round(u['real'], 2), saved=round(u['list'] - u['real'], 2) if u['list'] else None) for k, u in use.items()}

    @S.route('GET', '/api/credits')
    def listing(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        car = int(a.get('car', 1))
        packs = S.OWN.rows('select id, provider, kind, paid, amount, since, note from credit_packs order by provider collate nocase, since, id')
        use = usage(car, hc is False) if packs else {}
        for p in packs:
            p['rate'] = round(rate(p), 4)
            p['usage'] = use.get(p['id']) or dict(n=0, kwh=0, used=0, real=0, saved=None)
        return dict(packs=packs, providers=S.provider_list(car, hc is False))

    @S.route('POST', '/api/credits/save', pin=True, role='user')
    def save(h, b):
        p = parse(b)
        if b.get('id'):
            S.OWN.run('update credit_packs set provider=?, kind=?, paid=?, amount=?, since=?, note=?, ts=? where id=?', (p['provider'], p['kind'], p['paid'], p['amount'], p['since'], p['note'], time.time(), int(b['id'])))
        else:
            if S.OWN.one('select count(*) n from credit_packs')['n'] >= MAX_PACKS:
                raise ValueError('Maxim %d pachete.' % MAX_PACKS)
            S.OWN.run('insert into credit_packs(provider, kind, paid, amount, since, note, ts) values(?,?,?,?,?,?,?)', (p['provider'], p['kind'], p['paid'], p['amount'], p['since'], p['note'], time.time()))
        cache['t'] = 0

    @S.route('POST', '/api/credits/delete', pin=True, role='user')
    def delete(h, b):
        S.OWN.run('delete from credit_packs where id=?', (int(b.get('id', 0)),))
        cache['t'] = 0

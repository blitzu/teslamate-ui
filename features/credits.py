"""Credit cumparat la un furnizor (pachet): platesti X si primesti credit mai mare in bani ("1000 lei pentru 2000 lei credit" la iHunt) sau in kilometri de autonomie
("100 lei pentru 1000 km" la Tesla Supercharger). Cat timp furnizorul unei incarcari are un pachet, costul ei real se calculeaza singur din pret de lista:
  - bani:  cost real = cost la tarif de lista x (platit / credit)          (2000 credit pentru 1000 lei = 50% din tariful afisat)
  - km:    cost real = km de autonomie adaugati x (platit / km cumparati)   (1000 km pentru 100 lei = 0,10 lei/km)
Un cost scris de tine de mana ramane neatins (e suma reala); un cost venit din tariful ales al unei statii e pret de lista, deci i se aplica creditul.
Nu se scrie nimic in TeslaMate; pachetele stau in baza proprie a aplicatiei."""
import datetime as dt
import re
import threading
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
    kind = {'km': 'km', 'voucher': 'voucher'}.get(str(b.get('kind')), 'money')
    paid = 0.0 if kind == 'voucher' else num(b.get('paid'), 0, 1e7, 'Suma plătită')
    amount = num(b.get('amount'), 0, 1e7, {'money': 'Creditul primit', 'km': 'Kilometrii', 'voucher': 'Valoarea voucherului'}[kind])
    since = str(b.get('since') or '').strip()[:10]
    if since and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', since):
        raise ValueError('Data invalidă.')
    if kind == 'voucher' and not since:
        since = dt.date.today().isoformat()                                  # un voucher se aplica de la data primirii, nu incarcarilor de dinainte
    fee = 0.0 if kind == 'voucher' or str(b.get('fee') or '').strip() == '' else num(b.get('fee'), -1, 1000, 'Taxa')
    if fee < 0:
        raise ValueError('Taxa invalidă')
    return dict(provider=prov, kind=kind, paid=paid, amount=amount, since=since, note=clean(b.get('note'), 60), fee=fee,
                fee_in_credit=0 if str(b.get('fee_in_credit', '1')).lower() in ('0', 'false', 'no') else 1)


def rate(p):
    """bani: cat platesti pentru 1 leu de credit (0,5 = jumatate din pret); km: lei pe kilometru de autonomie."""
    return p['paid'] / p['amount']


def pick(packs, provider, day):
    """Pachetul care se aplica unei incarcari: al furnizorului ei, valabil la data ei; daca sunt mai multe, cel mai recent (dupa data de la care se aplica)."""
    prov = str(provider or '').strip().casefold()
    ok = [p for p in packs if p['kind'] != 'voucher' and p['provider'].casefold() == prov and (not p.get('since') or p['since'] <= str(day)[:10])]
    return max(ok, key=lambda p: (p.get('since') or '', p['id'])) if ok else None


def adjust(p, list_cost=None, km=None, voucher=0.0):
    """Costul real dupa credit (sau None daca lipseste ce trebuie), ca (cost, de_la_credit): bani => din costul de lista, km => din kilometrii adaugati.
    Taxa de conectare a pachetului (pe sesiune) se adauga la fiecare incarcare: la creditul in bani se plateste din credit (se aduna la pretul de lista) sau separat, in bani;
    la creditul in km se plateste mereu separat. de_la_credit = cat din pretul de lista a trecut prin credit. Voucherele (bani gratis) se scad primele din ce trece prin credit."""
    fee = p.get('fee') or 0
    if p['kind'] == 'km':
        return (round(km * rate(p) + fee, 2), km) if km and km > 0 else None
    if list_cost is None:
        return None
    fic = p.get('fee_in_credit', 1)
    through = list_cost + (fee if fic else 0)
    return round(max(0.0, through - voucher) * rate(p) + (0 if fic else fee), 2), round(through, 2)


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


CASH = dict(id=0, kind='money', paid=1.0, amount=1.0, fee=0, fee_in_credit=1)       # fara pachet cumparat: banii se platesc la tariful de lista (pentru vouchere)


def basis(r, e):
    """(se_aplica, cost_de_lista): costul de pe care pleaca creditul. Un cost scris de tine (alt decat kWh x tariful statiei alese) e suma reala si nu se atinge (False)."""
    kwh = r.get('charge_energy_used') or r.get('charge_energy_added')
    st = e.get('station') or {}
    tar, sel = st.get('tariffs') or [], int(st.get('sel', -1) if st.get('sel') is not None else -1)
    t = tar[sel] if 0 <= sel < len(tar) else None
    manual = e.get('cost')
    if manual is None:
        return True, r.get('cost_eff')
    if t and kwh and abs(float(manual) - round(float(t['price']) * float(kwh), 2)) <= 0.011:
        return True, float(manual)                                           # costul vine din tariful statiei: e pret de lista
    return False, None


def allocate(packs, items):
    """Voucherele (bani gratis) se scad primele din incarcari, de la cel mai vechi la cel mai nou, in ordinea cronologica a incarcarilor.
    items = [{id, provider, start, base}] doar pentru incarcarile la care se aplica creditul. Intoarce ({id_incarcare: cat acopera voucherele}, {id_voucher: {n, used}})."""
    vouchers = sorted([p for p in packs if p['kind'] == 'voucher'], key=lambda p: (p.get('since') or '', p['id']))
    left = {v['id']: float(v['amount']) for v in vouchers}
    per, per_v = {}, {v['id']: dict(n=0, used=0.0) for v in vouchers}
    if not vouchers:
        return per, per_v
    for it in sorted(items, key=lambda x: (str(x['start']), x['id'])):
        if it.get('base') is None:
            continue
        p = pick(packs, it['provider'], it['start'])
        if p and p['kind'] == 'km':
            continue                                                       # voucherele sunt in bani, nu in km
        need = float(it['base']) + ((p.get('fee') or 0) if p and p.get('fee_in_credit', 1) else 0)
        prov, day = str(it['provider'] or '').strip().casefold(), str(it['start'])[:10]
        for v in vouchers:
            if need <= 0.004:
                break
            if v['provider'].casefold() != prov or left[v['id']] <= 0.004 or (v.get('since') and v['since'] > day):
                continue
            take = min(left[v['id']], need)
            left[v['id']] -= take
            need -= take
            per[it['id']] = per.get(it['id'], 0.0) + take
            per_v[v['id']]['n'] += 1
            per_v[v['id']]['used'] += take
    return per, per_v


def adjust_row(packs, r, e, voucher=0.0):
    """Pentru o incarcare (r = randul ei dupa furnizor si cost_eff, e = datele salvate in aplicatie, voucher = cat din pret acopera voucherele): dict cu costul real si detaliile, sau None cand nu se aplica."""
    p = pick(packs, r.get('provider'), r.get('start_date') or '')
    if not p and not voucher:
        return None
    p = p or dict(CASH, provider=r.get('provider'))
    if p['kind'] == 'km':
        voucher = 0.0
    ok, base = basis(r, e)
    if not ok:
        return None
    km = range_km(r)
    res = adjust(p, base, km, voucher)
    if res is None:
        return None
    cost, via = res
    return dict(pack=p['id'], kind=p['kind'], rate=round(rate(p), 4), list=round(via, 2) if p['kind'] == 'money' else None, base=round(base, 2) if base is not None else None,
                fee=p.get('fee') or 0, fee_in_credit=bool(p.get('fee_in_credit', 1)), voucher=round(voucher, 2), km=round(km, 1) if km else None, cost=cost)


def init(S):
    S.OWN.migrate('credits', ['create table credit_packs (id integer primary key, provider text not null, kind text not null, paid real not null, amount real not null, since text, note text, ts real)',
                              'alter table credit_packs add column fee real not null default 0', 'alter table credit_packs add column fee_in_credit integer not null default 1'])
    cache = {'t': 0, 'rows': []}

    def rows():
        if time.time() - cache['t'] > 30:
            cache['rows'], cache['t'] = S.OWN.rows('select id, provider, kind, paid, amount, since, note, fee, fee_in_credit from credit_packs'), time.time()
        return cache['rows']

    tl = threading.local()
    led = {'t': 0, 'v': ({}, {})}

    def ledger():
        """Cat din fiecare incarcare acopera voucherele (calculat pe toate incarcarile, o data la 30 s; fara vouchere nu se calculeaza nimic)."""
        if time.time() - led['t'] < 30:
            return led['v']
        packs = rows()
        if not any(p['kind'] == 'voucher' for p in packs):
            led['t'], led['v'] = time.time(), ({}, {})
            return led['v']
        items = []
        tl.busy = True                                                      # in timpul calculului baza (cost_eff) e cea dinainte de credit
        try:
            meta = S.meta_load()
            for r in Credits.source():
                ok, base = basis(r, meta.get(str(r['id'])) or {})
                if ok and base is not None:
                    items.append(dict(id=r['id'], provider=r.get('provider'), start=r.get('start_date') or '', base=base))
        except Exception as e:  # noqa
            S.log('credit vouchere:', str(e)[:100], flush=True)
        finally:
            tl.busy = False
        led['t'], led['v'] = time.time(), allocate(packs, items)
        return led['v']

    class Credits:
        @staticmethod
        def source():
            """Toate incarcarile (toate masinile), decorate fara credit; inlocuibila in teste."""
            out = []
            for c in S.q('select id from cars order by id'):
                out += S.decorate(S._charges_rows(c['id'], 5000, 0))
            return out

        def adjust(self, r, e):
            if getattr(tl, 'busy', False):
                return None
            return adjust_row(rows(), r, e, ledger()[0].get(r['id'], 0.0))

        def ledger(self):
            return ledger()

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
            u['list'] += (c['base'] or 0) + (c['fee'] or 0) - (c['voucher'] or 0)               # pretul de lista echivalent (cu taxa), fara partea platita din voucher
            u['used'] += (c['km'] or 0) if c['kind'] == 'km' else (c['list'] or 0) - (c['voucher'] or 0)
        return {k: dict(n=u['n'], kwh=round(u['kwh'], 1), used=round(u['used'], 1), real=round(u['real'], 2), saved=round(u['list'] - u['real'], 2) if u['list'] else None) for k, u in use.items()}

    @S.route('GET', '/api/credits')
    def listing(h, a):
        hc = S.has_cars()
        if hc is None:
            raise S.DBDown()
        car = int(a.get('car', 1))
        packs = S.OWN.rows('select id, provider, kind, paid, amount, since, note, fee, fee_in_credit from credit_packs order by provider collate nocase, since, id')
        use = usage(car, hc is False) if packs else {}
        per_v = S.CREDITS.ledger()[1] if any(p['kind'] == 'voucher' for p in packs) else {}
        for p in packs:
            if p['kind'] == 'voucher':
                u = per_v.get(p['id']) or dict(n=0, used=0)
                p['rate'] = 0
                p['usage'] = dict(n=u['n'], kwh=0, used=round(u['used'], 2), real=0, saved=round(u['used'], 2))
                continue
            p['rate'] = round(rate(p), 4)
            p['usage'] = use.get(p['id']) or dict(n=0, kwh=0, used=0, real=0, saved=None)
        return dict(packs=packs, providers=S.provider_list(car, hc is False))

    @S.route('POST', '/api/credits/save', pin=True, role='user')
    def save(h, b):
        p = parse(b)
        if b.get('id'):
            S.OWN.run('update credit_packs set provider=?, kind=?, paid=?, amount=?, since=?, note=?, fee=?, fee_in_credit=?, ts=? where id=?', (p['provider'], p['kind'], p['paid'], p['amount'], p['since'], p['note'], p['fee'], p['fee_in_credit'], time.time(), int(b['id'])))
        else:
            if S.OWN.one('select count(*) n from credit_packs')['n'] >= MAX_PACKS:
                raise ValueError('Maxim %d pachete.' % MAX_PACKS)
            S.OWN.run('insert into credit_packs(provider, kind, paid, amount, since, note, fee, fee_in_credit, ts) values(?,?,?,?,?,?,?,?,?)', (p['provider'], p['kind'], p['paid'], p['amount'], p['since'], p['note'], p['fee'], p['fee_in_credit'], time.time()))
        cache['t'] = led['t'] = 0

    @S.route('POST', '/api/credits/delete', pin=True, role='user')
    def delete(h, b):
        S.OWN.run('delete from credit_packs where id=?', (int(b.get('id', 0)),))
        cache['t'] = led['t'] = 0

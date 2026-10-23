"""Notificari push native (Web Push, RFC 8030/8291/8292), fara Home Assistant: merg pe Android, desktop si pe iPhone (aplicatia adaugata pe ecranul principal, iOS 16.4+).
Cheile VAPID se genereaza o data si raman in baza proprie. Abonamentele se accepta doar de la serviciile push cunoscute (nu poti face serverul sa apeleze adrese arbitrare)."""
import base64
import json
import os
import re
import struct
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

HOSTS = re.compile(r'^(fcm\.googleapis\.com|updates\.push\.services\.mozilla\.com|[\w.-]+\.push\.apple\.com|web\.push\.apple\.com|[\w.-]+\.notify\.windows\.com|push\.services\.mozilla\.com)$')
DEFAULT_KINDS = dict(alert=True, maint=True, report=True, app_update=True, low_batt=True, update=True, charge_done=True, plugged=True, door=True, rule=True, handoff=True, test=True)


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def b64d(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


def valid_endpoint(url):
    u = urlparse(str(url))
    return u.scheme == 'https' and bool(u.hostname) and bool(HOSTS.match(u.hostname)) and not u.username and len(str(url)) < 1000


def encrypt(payload, p256dh, auth, as_priv=None, salt=None):
    """aes128gcm (RFC 8291). Intoarce corpul cererii. as_priv/salt se dau doar in teste."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    ua_pub = b64d(p256dh) if isinstance(p256dh, str) else p256dh
    auth = b64d(auth) if isinstance(auth, str) else auth
    as_priv = as_priv or ec.generate_private_key(ec.SECP256R1())
    as_pub = as_priv.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    secret = as_priv.exchange(ec.ECDH(), ua_key)
    prk = HKDF(hashes.SHA256(), 32, auth, b'WebPush: info\x00' + ua_pub + as_pub).derive(secret)
    salt = salt or os.urandom(16)
    cek = HKDF(hashes.SHA256(), 16, salt, b'Content-Encoding: aes128gcm\x00').derive(prk)
    nonce = HKDF(hashes.SHA256(), 12, salt, b'Content-Encoding: nonce\x00').derive(prk)
    body = AESGCM(cek).encrypt(nonce, payload + b'\x02', None)                 # un singur record, ultimul (delimitator 0x02)
    return salt + struct.pack('>IB', 4096, len(as_pub)) + as_pub + body


def init(S):
    S.OWN.migrate('push', ['create table push_subs (id integer primary key, endpoint text not null unique, p256dh text not null, auth text not null, role text, ua text, created real, last_ok real, fails integer default 0)'])
    S.KIND_ROUTE.setdefault('test', '#/settings')

    def vapid():
        v = S.OWN.kv_get('push_vapid')
        if v:
            return v
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        k = ec.generate_private_key(ec.SECP256R1())
        v = dict(priv=k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode(),
                 pub=b64u(k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)))
        S.OWN.kv_set('push_vapid', v)
        return v

    def kinds():
        k = dict(DEFAULT_KINDS)
        k.update({a: bool(b) for a, b in (S.OWN.kv_get('push_kinds', {}) or {}).items() if a in k})
        return k

    def post(sub, payload, ttl=3600, urgency='normal'):
        import jwt
        v = vapid()
        u = urlparse(sub['endpoint'])
        claims = dict(aud='%s://%s' % (u.scheme, u.netloc), exp=int(time.time()) + 12 * 3600, sub=S.APPURL if str(S.APPURL).startswith('https://') else 'mailto:noreply@example.com')
        tok = jwt.encode(claims, v['priv'], algorithm='ES256')
        req = urllib.request.Request(sub['endpoint'], data=encrypt(json.dumps(payload).encode(), sub['p256dh'], sub['auth']), method='POST',
                                     headers={'Content-Encoding': 'aes128gcm', 'Content-Type': 'application/octet-stream', 'TTL': str(ttl), 'Urgency': urgency,
                                              'Authorization': 'vapid t=%s, k=%s' % (tok, v['pub'])})
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    ADMIN_ONLY = ('app_update',)                         # tipuri care au sens doar pentru administrator (Setarile nu se pot deschide de altcineva)

    def deliver(payload, urgency='normal', only=None, role=None):
        where, args = [], []
        if only:
            where.append('id=?')
            args.append(only)
        if role:
            where.append('role=?')
            args.append(role)
        subs = S.OWN.rows('select * from push_subs' + (' where ' + ' and '.join(where) if where else ''), tuple(args))
        out = dict(sent=0, gone=0, failed=0)
        for s in subs:
            try:
                code = post(s, payload, urgency=urgency)
            except Exception as e:  # noqa
                S.log('push: %s' % type(e).__name__)
                code = 0
            if 200 <= code < 300:
                S.OWN.run('update push_subs set last_ok=?, fails=0 where id=?', (time.time(), s['id']))
                out['sent'] += 1
            elif code in (404, 410):                                           # abonament expirat/revocat: il scot
                S.OWN.run('delete from push_subs where id=?', (s['id'],))
                out['gone'] += 1
            else:
                out['failed'] += 1
                S.OWN.run('update push_subs set fails=fails+1 where id=?', (s['id'],))
        S.OWN.run('delete from push_subs where fails >= 20')
        return out

    def sink(kind, title, msg, data):
        if not kinds().get(kind) or not S.OWN.one('select 1 x from push_subs limit 1'):
            return
        deliver(dict(title=title, body=msg, kind=kind, tag='tesla_' + kind, path=S.KIND_ROUTE.get(kind, '#/car')), urgency='high' if kind in ('alert', 'rule') else 'normal', role='admin' if kind in ADMIN_ONLY else None)

    S.NOTIFY_SINKS.append(sink)
    S.PUSH_DELIVER = deliver

    @S.route('GET', '/api/push/status', role='user')
    def status(h, a):
        n = S.OWN.one('select count(*) n from push_subs')['n']
        mine = bool(a.get('endpoint')) and bool(S.OWN.one('select 1 x from push_subs where endpoint=?', (a['endpoint'],)))
        return dict(key=vapid()['pub'], devices=n, mine=mine, kinds=kinds())

    @S.route('POST', '/api/push/subscribe', role='user')
    def subscribe(h, b):
        k = b.get('keys') or {}
        ep = b.get('endpoint')
        if not valid_endpoint(ep) or not isinstance(k.get('p256dh'), str) or not isinstance(k.get('auth'), str):
            raise ValueError('Abonament invalid (serviciul push nu e recunoscut).')
        try:
            if len(b64d(k['p256dh'])) != 65 or len(b64d(k['auth'])) < 8:
                raise ValueError
        except Exception:  # noqa
            raise ValueError('Chei de abonament invalide.')
        n = S.OWN.one('select count(*) n from push_subs')['n']
        if n >= 30 and not S.OWN.one('select 1 x from push_subs where endpoint=?', (ep,)):
            raise ValueError('Prea multe dispozitive (max 30). Scoate unele din Setări.')
        S.OWN.run('insert into push_subs(endpoint, p256dh, auth, role, ua, created) values(?,?,?,?,?,?) on conflict(endpoint) do update set p256dh=excluded.p256dh, auth=excluded.auth, role=excluded.role, ua=excluded.ua, fails=0',
                  (ep, k['p256dh'], k['auth'], getattr(h, 'role', None), str(h.headers.get('User-Agent', ''))[:120], time.time()))

    @S.route('POST', '/api/push/unsubscribe', role='user')
    def unsubscribe(h, b):
        S.OWN.run('delete from push_subs where endpoint=?', (str(b.get('endpoint', '')),))

    @S.route('POST', '/api/push/kinds', pin=True, role='admin')
    def set_kinds(h, b):
        S.OWN.kv_set('push_kinds', {k: bool(b.get(k)) for k in DEFAULT_KINDS})
        return dict(ok=True, kinds=kinds())

    @S.route('POST', '/api/push/test', role='user')
    def test(h, b):
        r = deliver(dict(title='🔔 Test notificare', body='Notificările push funcționează pe acest dispozitiv.', kind='test', tag='tesla_test', path='#/settings'))
        return dict(ok=r['sent'] > 0, reason=None if r['sent'] else 'Niciun dispozitiv abonat sau serviciul push nu a răspuns.', **r)

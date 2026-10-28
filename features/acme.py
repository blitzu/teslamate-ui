"""Client ACME (RFC 8555) minimal pentru Let's Encrypt, cu doua tipuri de validare:
  * dns-01: nu are nevoie de niciun port deschis; cine apeleaza da provision(valoare) / cleanup() care pun si sterg inregistrarea TXT `_acme-challenge.<domeniu>` (ex. prin DuckDNS);
  * tls-alpn-01 (RFC 8737): nu are nevoie de acces la DNS, doar de portul 443 al domeniului; provision(digest) primeste cei 32 de octeti pe care serverul trebuie sa-i puna intr-un
    certificat de validare (vezi alpn_cert) si sa-l serveasca pe conexiunile TLS cu ALPN `acme-tls/1`.
Foloseste doar `cryptography` (deja in imagine) si urllib. Cheia contului si cheia certificatului sunt EC P-256."""
import base64
import hashlib
import json
import ssl
import time
import urllib.error
import urllib.request

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.x509.oid import NameOID

PROD = 'https://acme-v02.api.letsencrypt.org/directory'
STAGING = 'https://acme-staging-v02.api.letsencrypt.org/directory'


class AcmeError(Exception):
    pass


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()


def new_key():
    return ec.generate_private_key(ec.SECP256R1())


def key_pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())


def load_key(pem):
    return serialization.load_pem_private_key(pem, password=None)


def make_csr(key, domain):
    csr = (x509.CertificateSigningRequestBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False).sign(key, hashes.SHA256()))
    return csr.public_bytes(serialization.Encoding.DER)


ACME_IDENTIFIER_OID = x509.ObjectIdentifier('1.3.6.1.5.5.7.1.31')


def alpn_cert(domain, digest):
    """Certificatul de validare TLS-ALPN-01 (RFC 8737): autosemnat, SAN = domeniul, extensie critica id-pe-acmeIdentifier cu sha256(keyAuthorization). Intoarce (cert_pem, cheie_pem)."""
    import datetime as dt
    key = new_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, domain)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]), critical=False)
            .add_extension(x509.UnrecognizedExtension(ACME_IDENTIFIER_OID, b'\x04\x20' + digest), critical=True).sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM), key_pem(key)


def cert_info(pem):
    """(not_after_epoch, emitent, domenii) din primul certificat dintr-un lant PEM."""
    c = x509.load_pem_x509_certificate(pem if isinstance(pem, bytes) else pem.encode())
    try:
        names = c.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        names = []
    try:
        issuer = c.issuer.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value
    except IndexError:
        issuer = c.issuer.rfc4514_string()
    return c.not_valid_after_utc.timestamp(), issuer, list(names)


def default_http(ctx=None, timeout=30, ua='teslamate-ui'):
    """http(method, url, body, headers) -> (status, headers, body)."""
    def http(method, url, body=None, headers=None):
        h = {'User-Agent': ua}
        h.update(headers or {})
        req = urllib.request.Request(url, data=body, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()
    return http


class Client:
    def __init__(self, directory_url, account_key=None, http=None, log=lambda *a: None, sleep=time.sleep):
        self.url = directory_url
        self.key = account_key or new_key()
        self.http = http or default_http()
        self.log = log
        self.sleep = sleep
        self.dir = None
        self.nonce = None
        self.kid = None

    # ---- JWS
    def jwk(self):
        n = self.key.public_key().public_numbers()
        return {'crv': 'P-256', 'kty': 'EC', 'x': b64(n.x.to_bytes(32, 'big')), 'y': b64(n.y.to_bytes(32, 'big'))}

    def thumbprint(self):
        return b64(hashlib.sha256(json.dumps(self.jwk(), sort_keys=True, separators=(',', ':')).encode()).digest())

    def _jws(self, url, payload):
        protected = {'alg': 'ES256', 'nonce': self.nonce, 'url': url}
        protected.update({'kid': self.kid} if self.kid else {'jwk': self.jwk()})
        p64 = b64(json.dumps(protected, separators=(',', ':')).encode())
        d64 = '' if payload is None else b64(json.dumps(payload, separators=(',', ':')).encode())
        r, s = decode_dss_signature(self.key.sign(('%s.%s' % (p64, d64)).encode(), ec.ECDSA(hashes.SHA256())))
        return json.dumps({'protected': p64, 'payload': d64, 'signature': b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}).encode()

    def _directory(self):
        if not self.dir:
            st, _, body = self.http('GET', self.url)
            if st != 200:
                raise AcmeError('directorul ACME a raspuns %s' % st)
            self.dir = json.loads(body)
        return self.dir

    def _fresh_nonce(self):
        st, h, _ = self.http('HEAD', self._directory()['newNonce'])
        n = {k.lower(): v for k, v in h.items()}.get('replay-nonce')
        if not n:
            raise AcmeError('serverul ACME nu a dat un nonce')
        self.nonce = n

    def post(self, url, payload, raw=False, accept=None):
        """POST semnat (payload None = POST-as-GET). Reia o data la badNonce. Intoarce (status, headers, corp JSON sau bytes)."""
        for attempt in range(3):
            if not self.nonce:
                self._fresh_nonce()
            headers = {'Content-Type': 'application/jose+json'}
            if accept:
                headers['Accept'] = accept
            st, h, body = self.http('POST', url, self._jws(url, payload), headers)
            h = {k.lower(): v for k, v in h.items()}
            self.nonce = h.get('replay-nonce')
            if st >= 400:
                try:
                    err = json.loads(body)
                except ValueError:
                    err = {}
                if err.get('type', '').endswith(':badNonce') and attempt < 2:
                    continue
                raise AcmeError('%s: %s' % (err.get('type', 'http %s' % st).split(':')[-1], err.get('detail', body[:200].decode('utf-8', 'replace'))))
            return st, h, (body if raw else (json.loads(body) if body else {}))
        raise AcmeError('nonce respins de mai multe ori')

    # ---- flux
    def register(self, email=None):
        payload = {'termsOfServiceAgreed': True}
        if email:
            payload['contact'] = ['mailto:' + email]
        self.kid = None
        st, h, _ = self.post(self._directory()['newAccount'], payload)
        self.kid = h['location']
        return self.kid

    def _poll(self, url, done, bad, what, tries=40, delay=3):
        for _ in range(tries):
            _, _, obj = self.post(url, None)
            if obj.get('status') in done:
                return obj
            if obj.get('status') in bad:
                err = (obj.get('error') or {}).get('detail') or next((((c.get('error') or {}).get('detail')) for c in obj.get('challenges', []) if c.get('error')), '') or obj.get('status')
                raise AcmeError('%s: %s' % (what, err))
            self.sleep(delay)
        raise AcmeError('%s: timp depasit' % what)

    def obtain(self, domain, provision, cleanup, cert_key=None, propagate=15, method='dns-01'):
        """Emite un certificat pentru `domain`. Intoarce (fullchain_pem, cheie_pem).
        dns-01: provision(txt_str) / cleanup() pun si sterg TXT-ul _acme-challenge. tls-alpn-01: provision(digest_32_octeti) pregateste raspunsul pe portul 443, cleanup() il scoate."""
        if not self.kid:
            self.log('Contul ACME: se inregistreaza')
            self.register()
        cert_key = cert_key or new_key()
        self.log('Comanda pentru %s' % domain)
        st, h, order = self.post(self._directory()['newOrder'], {'identifiers': [{'type': 'dns', 'value': domain}]})
        order_url = h['location']
        try:
            for authz_url in order['authorizations']:
                _, _, authz = self.post(authz_url, None)
                if authz.get('status') == 'valid':
                    continue
                ch = next((c for c in authz['challenges'] if c['type'] == method), None)
                if not ch:
                    raise AcmeError('serverul nu ofera validare %s' % method.upper())
                digest = hashlib.sha256(('%s.%s' % (ch['token'], self.thumbprint())).encode()).digest()
                if method == 'dns-01':
                    self.log('TXT _acme-challenge.%s se pune la DNS' % domain)
                    provision(b64(digest))
                else:
                    self.log('Se pregateste raspunsul de validare TLS-ALPN pe portul 443')
                    provision(digest)
                self.sleep(propagate)
                self.log('Let\'s Encrypt verifica %s' % ('DNS' if method == 'dns-01' else 'portul 443'))
                self.post(ch['url'], {})
                self._poll(authz_url, ('valid',), ('invalid', 'deactivated', 'expired', 'revoked'), 'validare')
                self.log('Validare reusita')
        finally:
            try:
                cleanup()
            except Exception as e:  # noqa
                self.log('Curatarea validarii a esuat: %s' % e)
        self.log('Se trimite cererea de certificat')
        self.post(order['finalize'], {'csr': b64(make_csr(cert_key, domain))})
        done = self._poll(order_url, ('valid',), ('invalid',), 'emitere', tries=40, delay=2)
        _, _, chain = self.post(done['certificate'], None, raw=True, accept='application/pem-certificate-chain')
        self.log('Certificat primit')
        return chain.decode(), key_pem(cert_key).decode()

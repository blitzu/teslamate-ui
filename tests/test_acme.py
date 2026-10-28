import base64
import datetime as dt
import hashlib
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.x509.oid import NameOID

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from features import acme as A                           # noqa: E402


def unb64(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


class FakeAcme:
    """Server ACME minimal: verifica semnaturile JWS, nonce-urile, valoarea TXT si CSR-ul, apoi emite un certificat dintr-o CA de test."""

    def __init__(self, bad_nonce_first=False, fail_validation=False, alpn=False):
        self.alpn = alpn
        self.bad_nonce_first = bad_nonce_first
        self.fail_validation = fail_validation
        self.nonces, self.counter = set(), 0
        self.jwk = None
        self.txt_expected = None
        self.validated = False
        self.finalized_domain = None
        self.errors = []
        self.ca_key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'Fake CA')])
        now = dt.datetime.now(dt.timezone.utc)
        self.ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(self.ca_key.public_key()).serial_number(1)
                   .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=3650)).sign(self.ca_key, hashes.SHA256()))
        self.cert_pem = None
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *a):
                pass

            def send(self, code, obj=None, headers=None, raw=None):
                body = raw if raw is not None else (json.dumps(obj).encode() if obj is not None else b'')
                self.send_response(code)
                fake.counter += 1
                n = 'n%d' % fake.counter
                fake.nonces.add(n)
                self.send_header('Replay-Nonce', n)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(body)

            def do_GET(self):
                b = fake.base
                self.send(200, {'newNonce': b + '/nonce', 'newAccount': b + '/acct', 'newOrder': b + '/order'})

            def do_HEAD(self):
                self.send(200)

            def do_POST(self):
                try:
                    return self.post()
                except Exception as e:  # noqa
                    fake.errors.append(repr(e))
                    self.send(500, {'type': 'x', 'detail': repr(e)})

            def post(self):
                b = fake.base
                msg = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                prot = json.loads(unb64(msg['protected']))
                if fake.bad_nonce_first:
                    fake.bad_nonce_first = False
                    return self.send(400, {'type': 'urn:ietf:params:acme:error:badNonce', 'detail': 'otro'})
                assert prot['nonce'] in fake.nonces, 'nonce necunoscut'
                fake.nonces.discard(prot['nonce'])
                assert prot['url'] == b + self.path, 'url gresit in JWS'
                jwk = prot.get('jwk') or fake.jwk
                assert jwk and (('kid' in prot) != ('jwk' in prot)), 'jwk/kid'
                pub = ec.EllipticCurvePublicNumbers(int.from_bytes(unb64(jwk['x']), 'big'), int.from_bytes(unb64(jwk['y']), 'big'), ec.SECP256R1()).public_key()
                sig = unb64(msg['signature'])
                pub.verify(encode_dss_signature(int.from_bytes(sig[:32], 'big'), int.from_bytes(sig[32:], 'big')), ('%s.%s' % (msg['protected'], msg['payload'])).encode(), ec.ECDSA(hashes.SHA256()))
                payload = json.loads(unb64(msg['payload'])) if msg['payload'] else None
                if self.path == '/acct':
                    fake.jwk = jwk
                    assert payload['termsOfServiceAgreed'] is True
                    return self.send(201, {'status': 'valid'}, {'Location': b + '/acct/1'})
                assert prot.get('kid') == b + '/acct/1', 'cerere fara kid'
                if self.path == '/order':
                    fake.domain = payload['identifiers'][0]['value']
                    return self.send(201, {'status': 'pending', 'authorizations': [b + '/authz'], 'finalize': b + '/finalize'}, {'Location': b + '/order/1'})
                if self.path == '/authz':
                    status = 'valid' if fake.validated else 'pending'
                    kind = 'tls-alpn-01' if fake.alpn else 'dns-01'
                    return self.send(200, {'status': status, 'challenges': [{'type': 'http-01', 'url': b + '/c0', 'token': 'zzz'}, {'type': kind, 'url': b + '/chall', 'token': 'tok123', 'status': status}]})
                if self.path == '/chall':
                    tp = A.b64(hashlib.sha256(json.dumps(fake.jwk, sort_keys=True, separators=(',', ':')).encode()).digest())
                    fake.digest_expected = hashlib.sha256(('tok123.' + tp).encode()).digest()
                    fake.txt_expected = A.b64(fake.digest_expected)
                    fake.validated = (fake.txt_set == (fake.digest_expected if fake.alpn else fake.txt_expected)) and not fake.fail_validation
                    return self.send(200, {'status': 'processing'})
                if self.path == '/finalize':
                    csr = x509.load_der_x509_csr(unb64(payload['csr']))
                    assert csr.is_signature_valid
                    san = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
                    fake.finalized_domain = san[0]
                    now = dt.datetime.now(dt.timezone.utc)
                    cert = (x509.CertificateBuilder().subject_name(csr.subject).issuer_name(fake.ca.subject).public_key(csr.public_key()).serial_number(2)
                            .not_valid_before(now - dt.timedelta(minutes=1)).not_valid_after(now + dt.timedelta(days=90))
                            .add_extension(x509.SubjectAlternativeName([x509.DNSName(san[0])]), critical=False).sign(fake.ca_key, hashes.SHA256()))
                    fake.cert_pem = cert.public_bytes(serialization.Encoding.PEM) + fake.ca.public_bytes(serialization.Encoding.PEM)
                    return self.send(200, {'status': 'processing'})
                if self.path == '/order/1':
                    return self.send(200, {'status': 'valid', 'certificate': b + '/cert'})
                if self.path == '/cert':
                    return self.send(200, headers={'Content-Type': 'application/pem-certificate-chain'}, raw=fake.cert_pem)
                self.send(404, {'type': 'x', 'detail': 'nu exista'})

        self.txt_set = None
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.base = 'http://127.0.0.1:%d' % self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


class AcmeClientTests(unittest.TestCase):
    def run_flow(self, fake, domain='masina.duckdns.org'):
        log, txts = [], []

        def set_txt(v):
            fake.txt_set = v
            txts.append(('set', v))

        c = A.Client(fake.base + '/dir', http=A.default_http(), log=log.append, sleep=lambda s: None)
        return c, log, txts, set_txt, (lambda: txts.append(('clear', None)))

    def test_full_dns01_flow_issues_a_valid_certificate(self):
        fake = FakeAcme()
        try:
            c, log, txts, set_txt, clear = self.run_flow(fake)
            chain, key = c.obtain('masina.duckdns.org', set_txt, clear, propagate=0)
            self.assertEqual(fake.errors, [])
            self.assertEqual(fake.finalized_domain, 'masina.duckdns.org')                    # CSR cu domeniul cerut
            self.assertEqual([t[0] for t in txts], ['set', 'clear'])                         # TXT pus, apoi sters
            self.assertEqual(txts[0][1], fake.txt_expected)                                  # valoarea TXT = sha256(token.amprenta) cum cere RFC 8555
            not_after, issuer, names = A.cert_info(chain)
            self.assertEqual((issuer, names), ('Fake CA', ['masina.duckdns.org']))
            self.assertGreater(not_after, dt.datetime.now(dt.timezone.utc).timestamp() + 80 * 86400)
            cert = x509.load_pem_x509_certificate(chain.encode())
            priv = A.load_key(key.encode())
            self.assertEqual(cert.public_key().public_numbers(), priv.public_key().public_numbers())      # cheia privata se potriveste certificatului
            self.assertTrue(any('Certificat primit' in x for x in log))
        finally:
            fake.stop()

    def test_bad_nonce_is_retried(self):
        fake = FakeAcme(bad_nonce_first=True)
        try:
            c, log, txts, set_txt, clear = self.run_flow(fake)
            chain, _ = c.obtain('a.duckdns.org', set_txt, clear, propagate=0)
            self.assertIn('BEGIN CERTIFICATE', chain)
            self.assertEqual(fake.errors, [])
        finally:
            fake.stop()

    def test_failed_validation_raises_and_still_clears_the_txt_record(self):
        fake = FakeAcme(fail_validation=True)
        try:
            c, log, txts, set_txt, clear = self.run_flow(fake)
            c.sleep = lambda s: None

            def fast_poll(url, done, bad, what, tries=40, delay=3):
                raise A.AcmeError('%s: TXT gresit' % what)
            c._poll = fast_poll
            with self.assertRaises(A.AcmeError):
                c.obtain('a.duckdns.org', set_txt, clear, propagate=0)
            self.assertEqual(txts[-1][0], 'clear')                                           # nu ramane TXT in DNS dupa o eroare
        finally:
            fake.stop()

    def test_tls_alpn_flow_hands_the_32_byte_digest_to_the_server(self):
        fake = FakeAcme(alpn=True)
        try:
            c, log, txts, set_txt, clear = self.run_flow(fake)
            chain, _ = c.obtain('casa.go.ro', set_txt, clear, propagate=0, method='tls-alpn-01')
            self.assertEqual(fake.errors, [])
            self.assertEqual(txts[0], ('set', fake.digest_expected))                         # octeti bruti (nu TXT): sha256(token.amprenta)
            self.assertEqual(len(txts[0][1]), 32)
            self.assertEqual(txts[-1][0], 'clear')
            self.assertEqual(fake.finalized_domain, 'casa.go.ro')
            self.assertIn('BEGIN CERTIFICATE', chain)
        finally:
            fake.stop()

    def test_missing_challenge_type_is_reported(self):
        fake = FakeAcme()                                                                    # ofera doar dns-01
        try:
            c, log, txts, set_txt, clear = self.run_flow(fake)
            with self.assertRaises(A.AcmeError) as cm:
                c.obtain('casa.go.ro', set_txt, clear, propagate=0, method='tls-alpn-01')
            self.assertIn('TLS-ALPN-01', str(cm.exception))
        finally:
            fake.stop()

    def test_validation_certificate_has_the_critical_acme_identifier_extension(self):
        digest = hashlib.sha256(b'x').digest()
        pem, key = A.alpn_cert('casa.go.ro', digest)
        cert = x509.load_pem_x509_certificate(pem)
        ext = cert.extensions.get_extension_for_oid(A.ACME_IDENTIFIER_OID)
        self.assertTrue(ext.critical)
        self.assertEqual(ext.value.value, b'\x04\x20' + digest)                           # OCTET STRING de 32 de octeti (RFC 8737)
        self.assertEqual(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName), ['casa.go.ro'])
        self.assertEqual(cert.public_key().public_numbers(), A.load_key(key).public_key().public_numbers())

    def test_key_helpers_roundtrip(self):
        k = A.new_key()
        self.assertEqual(A.load_key(A.key_pem(k)).public_key().public_numbers(), k.public_key().public_numbers())
        self.assertTrue(A.make_csr(k, 'x.duckdns.org').startswith(b'\x30'))


if __name__ == '__main__':
    unittest.main()

import datetime as dt
import http.client
import os
import socket
import ssl
import sys
import tempfile
import threading
import types
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='tesla-ui-tls-'))
os.environ.setdefault('DEMO_ONLY', '')
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as S  # noqa: E402
from isolation import Isolated  # noqa: E402

HOST = 'masina.duckdns.org'
CRLF = bytes([13, 10])


def self_signed(d):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(7).not_valid_before(now - dt.timedelta(days=1))
            .not_valid_after(now + dt.timedelta(days=30)).add_extension(x509.SubjectAlternativeName([x509.DNSName(HOST)]), critical=False).sign(key, hashes.SHA256()))
    cf, kf = os.path.join(d, 'c.pem'), os.path.join(d, 'k.pem')
    open(cf, 'wb').write(cert.public_bytes(serialization.Encoding.PEM))
    open(kf, 'wb').write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return cf, kf


class TlsServerTests(Isolated):
    def setUp(self):
        d = tempfile.mkdtemp()
        cf, kf = self_signed(d)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cf, kf)
        self.cafile = cf
        S.DEMO_ONLY = False                                                                  # (alte teste importa serverul in modul demo)
        S.INET = types.SimpleNamespace(fqdn=lambda: HOST)
        S.AUTH['pw'] = 'a-long-test-password'
        S.APPURL = ''
        self.srv = S.TlsServer(('127.0.0.1', 0), S.HS, types.SimpleNamespace(ctx=ctx))
        self.port = self.srv.server_port
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def req(self, method='GET', path='/api/health', headers=None, body=None):
        cctx = ssl.create_default_context(cafile=self.cafile)
        conn = http.client.HTTPSConnection('127.0.0.1', self.port, context=cctx, timeout=10, source_address=None)
        conn.sock = cctx.wrap_socket(socket.create_connection(('127.0.0.1', self.port), timeout=10), server_hostname=HOST)       # SNI + validare contra certificatului
        h = {'Host': HOST}
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        data = r.read()
        out = (r.status, dict(r.getheaders()), data)
        conn.close()
        return out

    def test_serves_the_app_over_tls_with_hsts(self):
        st, h, body = self.req()
        self.assertIn(st, (200, 503))                                                        # 503 = fara baza de date in test; important: raspunde aplicatia, prin TLS
        self.assertIn(b'"ok"', body)
        self.assertIn('max-age', h['Strict-Transport-Security'])

    def test_any_external_port_works_because_the_host_header_may_carry_it(self):
        st, _, body = self.req(headers={'Host': HOST + ':8443'})                             # https://masina.duckdns.org:8443 (portul extern ales de utilizator)
        self.assertIn(st, (200, 503))                                                        # nu 421
        st, _, _ = self.req('POST', '/api/logout_all', headers={'Host': HOST + ':8443', 'Origin': 'https://' + HOST + ':8443', 'Content-Type': 'application/json'}, body=b'{}')
        self.assertNotEqual(st, 421)                                                         # Origin cu port == Host cu port
        st, _, _ = self.req(headers={'Host': 'evil.example.com:8443'})
        self.assertEqual(st, 421)                                                            # portul nu deschide alte nume

    def test_unknown_host_is_refused(self):
        st, _, body = self.req(headers={'Host': 'evil.example.com'})
        self.assertEqual(st, 421)
        self.assertIn(b'evil.example.com', body)

    def test_no_trust_in_proxy_headers_and_everything_needs_the_password(self):
        # un client care pretinde ca vine prin Cloudflare / din LAN nu primeste nimic
        st, _, _ = self.req(path='/api/state', headers={'X-Forwarded-For': '192.168.1.5', 'Cf-Connecting-Ip': '192.168.1.5', 'Cf-Ray': 'x'})
        self.assertEqual(st, 401)
        S.AUTH['pw'] = ''
        st, _, _ = self.req(path='/api/state', headers={'X-Forwarded-For': '192.168.1.5'})
        self.assertIn(st, (401, 403))                                                        # fara parola configurata: totul inchis pe internet

    def test_cross_origin_posts_are_refused(self):
        st, _, _ = self.req('POST', '/api/logout_all', headers={'Origin': 'https://evil.example.com', 'Content-Type': 'application/json'}, body=b'{}')
        self.assertIn(st, (400, 403))

    def test_public_routes_still_answer(self):
        st, _, _ = self.req(path='/.well-known/appspecific/com.tesla.3p.public-key.pem')
        self.assertIn(st, (200, 404))                                                        # 404 daca nu exista cheia in acest mediu; important: nu 421/401
        st, _, _ = self.req(path='/auth/callback')
        self.assertEqual(st, 400)                                                            # fara cod de autorizare

    def test_plain_http_to_the_tls_port_and_garbage_do_not_break_the_server(self):
        s = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        s.sendall(b'GET / HTTP/1.1\r\nHost: x\r\n\r\n')
        s.settimeout(5)
        try:
            s.recv(100)
        except OSError:
            pass
        s.close()
        s = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        s.sendall(b'\x16\x03\x01garbage')
        s.close()
        self.assertIn(self.req()[0], (200, 503))                                             # serverul tot raspunde

    def test_connection_limit_refuses_the_excess(self):
        self.srv.sem = threading.BoundedSemaphore(1)
        hold = socket.create_connection(('127.0.0.1', self.port), timeout=5)                 # tine ocupat singurul loc (handshake neterminat)
        try:
            import time
            time.sleep(0.3)
            extra = socket.create_connection(('127.0.0.1', self.port), timeout=5)
            extra.settimeout(3)
            try:
                data = extra.recv(10)
            except OSError:
                data = b''
            self.assertEqual(data, b'')                                                      # conexiunea in plus e inchisa fara raspuns
            extra.close()
        finally:
            hold.close()


class AlpnChallengeTests(Isolated):
    def setUp(self):
        import hashlib
        from features import acme as A
        self.A = A
        self.digest = hashlib.sha256(b'cheie').digest()
        d = tempfile.mkdtemp()
        cert, key = A.alpn_cert(HOST, self.digest)
        cf, kf = os.path.join(d, 'c.pem'), os.path.join(d, 'k.pem')
        open(cf, 'wb').write(cert)
        open(kf, 'wb').write(key)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cf, kf)
        ctx.set_alpn_protocols(['acme-tls/1'])
        S.DEMO_ONLY = False
        S.INET = types.SimpleNamespace(fqdn=lambda: HOST)
        self.holder = types.SimpleNamespace(ctx=ctx, challenge_only=True)
        self.srv = S.TlsServer(('127.0.0.1', 0), S.HS, self.holder)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_letsencrypt_style_handshake_gets_the_validation_certificate(self):
        cctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        cctx.check_hostname = False
        cctx.verify_mode = ssl.CERT_NONE
        cctx.set_alpn_protocols(['acme-tls/1'])
        with socket.create_connection(('127.0.0.1', self.srv.server_port), timeout=5) as raw:
            with cctx.wrap_socket(raw, server_hostname=HOST) as tls:
                self.assertEqual(tls.selected_alpn_protocol(), 'acme-tls/1')                 # serverul a negociat protocolul de validare
                cert = x509.load_der_x509_certificate(tls.getpeercert(binary_form=True))
        ext = cert.extensions.get_extension_for_oid(self.A.ACME_IDENTIFIER_OID)
        self.assertEqual(ext.value.value, b'\x04\x20' + self.digest)
        self.assertTrue(ext.critical)

    def test_nothing_of_the_app_is_served_while_the_challenge_is_active(self):
        cctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        cctx.check_hostname = False
        cctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection(('127.0.0.1', self.srv.server_port), timeout=5) as raw:
            with cctx.wrap_socket(raw, server_hostname=HOST) as tls:
                tls.settimeout(3)
                tls.sendall(b'GET /api/health HTTP/1.0' + CRLF + b'Host: ' + HOST.encode() + CRLF + CRLF)
                try:
                    data = tls.recv(100)
                except (OSError, ssl.SSLError):
                    data = b''
        self.assertEqual(data, b'')                                                          # cererile obisnuite nu primesc nimic cat timp e activa validarea


class PublicPortSwitchTests(Isolated):
    def test_public_port_switches_between_http_and_https_on_restart(self):
        import time
        d = tempfile.mkdtemp()
        cf, kf = self_signed(d)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cf, kf)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        old_env = os.environ.get('PUBLIC_PORT')
        os.environ['PUBLIC_PORT'] = str(port)
        S.DEMO_ONLY = False
        S.INET = types.SimpleNamespace(fqdn=lambda: HOST)
        S.INET_TLS = None
        threading.Thread(target=S.serve_public, daemon=True).start()
        try:
            def wait_mode(mode):
                end = time.time() + 10
                while S.PUBLIC.get('mode') != mode and time.time() < end:
                    time.sleep(0.05)
                time.sleep(0.4)                                                              # lasa listenerul sa porneasca
                self.assertEqual(S.PUBLIC.get('mode'), mode)

            def get(tls):
                if tls:
                    cctx = ssl.create_default_context(cafile=cf)
                    raw = cctx.wrap_socket(socket.create_connection(('127.0.0.1', port), timeout=5), server_hostname=HOST)
                else:
                    raw = socket.create_connection(('127.0.0.1', port), timeout=5)
                raw.sendall(b'GET /nimic HTTP/1.0' + CRLF + b'Host: ' + HOST.encode() + CRLF + CRLF)
                raw.settimeout(5)
                data = b''
                try:
                    while len(data) < 15:
                        c = raw.recv(100)
                        if not c:
                            break
                        data += c
                except OSError:
                    pass
                raw.close()
                return data
            wait_mode('http')
            self.assertTrue(get(False).startswith(b'HTTP/1.0 404'))                           # HTTP simplu: ruta publica inexistenta
            S.INET_TLS = types.SimpleNamespace(ctx=ctx)
            S.public_restart()
            wait_mode('tls')
            self.assertTrue(get(True).startswith(b'HTTP/1.0'))                                # acum cere TLS si raspunde aplicatia
            S.INET_TLS = None
            S.public_restart()
            wait_mode('http')
            self.assertTrue(get(False).startswith(b'HTTP/1.0 404'))                           # inapoi pe HTTP
        finally:
            if old_env is None:
                os.environ.pop('PUBLIC_PORT', None)
            else:
                os.environ['PUBLIC_PORT'] = old_env
            S.PUBLIC['stop'] = True                                                          # opreste bucla serve_public (nu mai reporneste serverul)
            srv = S.PUBLIC.get('srv')
            if srv:
                srv.shutdown()
            time.sleep(0.5)


if __name__ == '__main__':
    unittest.main()

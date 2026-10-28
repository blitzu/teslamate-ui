import json
import os
import stat
import sys
import tempfile
import time
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import acme as A                           # noqa: E402
from features import inet as I                           # noqa: E402
from test_acme import FakeAcme                           # noqa: E402

TOKEN = '12345678-aaaa-bbbb-cccc-1234567890ab'


class InetTests(unittest.TestCase):
    def setUp(self):
        self.orig = (A.PROD, A.STAGING, I.WAITS, I.OWN_WAITS)
        I.WAITS = (0, 0, 0)
        I.OWN_WAITS = (0, 0)
        self.cfg = {'inet_on': '1', 'duck_domain': 'masina', 'duck_token': TOKEN}
        self.duck_calls, self.restarts, self.logs = [], [], []
        self.duck_reply = 'OK\n203.0.113.7\n\nUPDATED'
        self.fake = FakeAcme()
        A.PROD = A.STAGING = self.fake.base + '/dir'

        def get_text(url, timeout=20):
            self.duck_calls.append(url)
            if 'txt=' in url and 'clear=true' not in url:
                self.fake.txt_set = [p.split('=')[1] for p in url.split('?')[1].split('&') if p.startswith('txt=')][0]
            return self.duck_reply
        self.S = types.SimpleNamespace(DATA_DIR=tempfile.mkdtemp(), APP_VERSION='9', AUTH={'pw': 'x' * 12}, cget=lambda k, env='', d='': self.cfg.get(k, d), _get_text=get_text,
                                       log=lambda *a, **k: self.logs.append(a), INET_TLS=None, PUBLIC={'mode': 'http'}, INET_LOOPS=False,
                                       route=lambda m, p, **k: (lambda fn: fn), public_restart=lambda: self.restarts.append(1))
        I.init(self.S)
        self.inet = self.S.INET

    def tearDown(self):
        A.PROD, A.STAGING, I.WAITS, I.OWN_WAITS = self.orig
        self.fake.stop()

    def wait(self, secs=20):
        end = time.time() + secs
        while self.inet.issuing and time.time() < end:
            time.sleep(0.05)
        self.assertFalse(self.inet.issuing, 'emiterea nu s-a terminat')

    def own_mode(self):
        self.cfg.update(inet_mode='own', inet_domain='casa.go.ro')
        self.cfg.pop('duck_token')
        self.fake.alpn = True

        def restart():
            self.restarts.append(1)
            self.S.PUBLIC['mode'] = 'tls' if self.S.INET_TLS is not None else 'http'
        self.S.public_restart = restart

    def test_own_domain_is_validated_and_needs_no_token(self):
        self.own_mode()
        self.assertEqual((self.inet.mode(), self.inet.fqdn(), self.inet.blockers()), ('own', 'casa.go.ro', []))
        for raw, want in (('https://Casa.GO.ro:8443/x', 'casa.go.ro'), ('casa', ''), ('192.168.1.5', ''), ('*.go.ro', ''), ('../x.ro', ''), ('exemplu.ro.', 'exemplu.ro'), ('a_b.go.ro', '')):
            self.cfg['inet_domain'] = raw
            self.assertEqual(self.inet.own_domain(), want, raw)

    def test_own_domain_certificate_via_tls_alpn_without_touching_duckdns(self):
        self.own_mode()
        seen = {}
        orig = self.inet._challenge_on

        def spy(domain, digest):
            orig(domain, digest)
            self.fake.txt_set = digest                                                       # ce ar vedea Let's Encrypt in certificatul de validare
            seen.update(only=self.inet.holder.challenge_only, mode=self.S.PUBLIC['mode'], tls=self.S.INET_TLS is not None, domain=domain, digest=digest)
        self.inet._challenge_on = spy
        self.assertTrue(self.inet.issue())
        self.wait()
        self.assertEqual(self.inet.error, '')
        self.assertEqual(self.duck_calls, [])                                                # niciun apel DuckDNS in modul "domeniu propriu"
        self.assertEqual((seen['only'], seen['mode'], seen['tls'], seen['domain'], len(seen['digest'])), (True, 'tls', True, 'casa.go.ro', 32))   # portul public in HTTPS doar pentru validare
        self.assertEqual(self.fake.finalized_domain, 'casa.go.ro')
        self.assertFalse(self.inet.holder.challenge_only)                                    # dupa validare: certificatul real, nu cel de validare
        self.assertTrue(self.inet.cert_ok())
        self.assertIsNotNone(self.inet.holder.ctx)
        self.assertEqual(self.S.PUBLIC['mode'], 'tls')
        self.assertEqual(self.inet.cert()['domain'], 'casa.go.ro')
        self.assertTrue(self.inet.status()['listening'])
        self.inet.holder.challenge_only = True                                               # cat serveste doar certificatul de validare, HTTPS-ul aplicatiei nu e "activ"
        self.assertFalse(self.inet.status()['listening'])
        self.inet.holder.challenge_only = False
        self.assertEqual(self.inet.status()['mode'], 'own')

    def test_failed_validation_in_own_mode_gives_a_port_hint_and_goes_back_to_http(self):
        self.own_mode()
        self.fake.fail_validation = True
        orig_poll = A.Client._poll

        def poll(client, url, done, bad, what, tries=40, delay=3):
            raise A.AcmeError('%s: Timeout during connect (likely firewall problem)' % what)
        A.Client._poll = poll
        try:
            self.inet.issue()
            self.wait()
        finally:
            A.Client._poll = orig_poll
        self.assertTrue(self.inet.error)
        self.assertTrue(any('443' in x and 'router' in x for x in self.inet.lines))          # indiciu: redirectionarea portului 443
        self.assertIsNone(self.S.INET_TLS)
        self.assertEqual(self.S.PUBLIC['mode'], 'http')                                      # fara certificat, portul public revine pe HTTP
        self.assertFalse(self.inet.holder.challenge_only)

    def test_domain_is_normalised_and_conditions_are_reported(self):
        self.cfg['duck_domain'] = 'https://MaSina.duckdns.org/'
        self.assertEqual((self.inet.sub(), self.inet.fqdn()), ('masina', 'masina.duckdns.org'))
        self.cfg['duck_domain'] = '../etc'
        self.assertEqual(self.inet.fqdn(), '')
        self.cfg['duck_domain'] = 'masina'
        self.assertEqual(self.inet.blockers(), [])
        self.S.AUTH['pw'] = ''
        self.assertIn('parola', self.inet.blockers()[0])
        self.assertFalse(self.inet.enabled())                                                # fara parola nu se expune nimic
        with self.assertRaises(ValueError):
            self.inet.issue()

    def test_certificate_is_issued_stored_privately_and_https_starts(self):
        self.assertTrue(self.inet.issue())
        self.assertFalse(self.inet.issue())                                                  # deja ruleaza (sau abia terminat): nu pornim doua
        self.wait()
        self.assertEqual(self.inet.error, '')
        self.assertEqual(self.fake.finalized_domain, 'masina.duckdns.org')
        d = os.path.join(self.S.DATA_DIR, 'tls')
        for n in ('fullchain.pem', 'cert.key', 'meta.json', 'account-prod.key'):
            self.assertTrue(os.path.isfile(os.path.join(d, n)), n)
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, 'cert.key')).st_mode), 0o600)         # cheia privata: doar proprietarul
        self.assertTrue(self.inet.cert_ok())
        self.assertIsNotNone(self.S.INET_TLS)                                                # contextul TLS e pus
        self.assertEqual(self.restarts, [1])                                                 # portul public a trecut pe HTTPS
        txt = [u for u in self.duck_calls if 'txt=' in u]
        self.assertTrue(any('clear=true' in u for u in txt))                                 # TXT-ul s-a sters dupa validare
        self.assertTrue(any(('txt=' + self.fake.txt_expected) in u for u in txt))            # cu valoarea ceruta de ACME

    def test_the_token_never_leaks_into_status_or_log(self):
        self.duck_reply = 'KO'
        self.inet.issue()
        self.wait()
        st = self.inet.status()
        self.assertTrue(st['error'])
        self.assertNotIn(TOKEN, json.dumps(st))
        self.assertNotIn(TOKEN, json.dumps(self.logs, default=str))
        self.assertIsNone(self.S.INET_TLS)                                                   # fara certificat ramane HTTP

    def test_apply_starts_the_issuance_when_there_is_no_certificate_and_switches_modes(self):
        self.inet.apply()
        self.assertTrue(self.inet.issuing or self.inet.cert_ok())
        self.wait()
        self.assertEqual(self.S.PUBLIC['mode'], 'http')                                      # (restart-ul e simulat: modul real il schimba serve_public)
        self.S.PUBLIC['mode'] = 'tls'
        self.restarts.clear()
        self.cfg['inet_on'] = '0'                                                            # utilizatorul opreste optiunea
        self.inet.apply()
        self.assertIsNone(self.S.INET_TLS)
        self.assertEqual(self.restarts, [1])                                                 # portul public revine pe HTTP

    def test_renewal_only_when_missing_or_close_to_expiry_and_not_too_often(self):
        self.assertTrue(self.inet.renew_check())                                             # nu exista certificat
        self.wait()
        self.inet.last_attempt = 0
        self.assertFalse(self.inet.renew_check())                                            # valabil ~90 zile: nimic de facut
        real = self.inet.cert
        self.inet.cert = lambda: dict(real(), days_left=10)
        self.inet.last_attempt = time.time()
        self.assertFalse(self.inet.renew_check())                                            # tocmai am incercat: nu mai des de 12 h
        self.inet.last_attempt = 0
        self.assertTrue(self.inet.renew_check())                                             # sub 30 de zile: reinnoieste
        self.wait()

    def test_status_reports_progress_for_the_interface(self):
        st = self.inet.status()
        self.assertEqual((st['domain'], st['password_set'], st['token_set'], st['cert']), ('masina.duckdns.org', True, True, None))
        self.assertEqual(st['port'], 4101)
        self.inet.issue()
        self.wait()
        st = self.inet.status()
        self.assertTrue(st['cert_ok'])
        self.assertGreater(st['cert']['days_left'], 80)
        self.assertTrue(any('Gata' in x for x in st['log']))


if __name__ == '__main__':
    unittest.main()

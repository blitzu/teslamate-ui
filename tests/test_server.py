"""Teste fara dependente externe: python -m unittest discover -s tests

Acopera logica pura (cost/furnizor, pretul combustibilului, comparatia cu masina termica, reguli, fisiere JSON atomice) si comportamentul HTTP
al serverului pornit fara baza de date (autentificare, limitarea PIN-ului, 503 la DB cazut, limite de corp).
"""
import http.client
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='tesla-ui-test-')
os.environ['DATA_DIR'] = TMP
os.environ['DEMO_ONLY'] = '1'
sys.path.insert(0, ROOT)
import server as S  # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from isolation import Isolated  # noqa: E402

CRLF = chr(13) + chr(10)


class Pure(Isolated):
    def setUp(self):
        S.FUELFILE = os.path.join(TMP, 'fuel.json')
        S.METAFILE = os.path.join(TMP, 'meta.json')
        S.CURRENCY = 'lei'
        S.CFG.clear()
        S.CFG.update(fuel_type='euro95', fuel_country='Romania', ice_l100='7')

    def test_jsave_jload_bak_and_corrupt(self):
        f = os.path.join(TMP, 'a.json')
        S.jsave(f, {'a': 1})
        S.jsave(f, {'a': 2})
        self.assertEqual(S.jload(f, None), {'a': 2})
        self.assertEqual(S.jload(f + '.bak', None), {'a': 1})
        with open(f, 'w') as fh:
            fh.write('{"a": 3')
        self.assertEqual(S.jload(f, None), {'a': 1})                  # fisier corupt -> copia .bak
        self.assertEqual(S.jload(os.path.join(TMP, 'lipsa.json'), 'D'), 'D')

    def test_meta_and_decorate(self):
        self.assertEqual(S.meta_update(5, dict(cost='12,5', provider='Ionity')), {'cost': 12.5, 'provider': 'Ionity'})
        self.assertEqual(S.meta_update(5, dict(cost='')), {'provider': 'Ionity'})
        with self.assertRaises(ValueError):
            S.meta_update(5, dict(cost='abc'))
        S.meta_update(2, dict(cost=9))
        rows = S.decorate([dict(id=1, name='Supercharger Pitesti', cost=3.0), dict(id=2, name='Acasa', cost=1.0, cost_real=0.5)])
        self.assertEqual((rows[0]['provider'], rows[0]['cost_eff']), ('Tesla Supercharger', 3.0))
        self.assertEqual((rows[1]['cost_eff'], rows[1]['cost_manual']), (9.0, 9.0))

    def test_parse_llms(self):
        txt = 'Last updated: 2026-10-19\nFuel        EUR/Liter\nEuro 95     €1.895      €7.17\nDiesel      €2.044      €7.74\n'
        self.assertEqual(S.parse_llms(txt), (1.895, 2.044, '2026-10-19'))
        with self.assertRaises(ValueError):
            S.parse_llms('altceva')

    def test_fuel_book_filters_currency_and_country(self):
        S.jsave(S.FUELFILE, {'days': {
            '2026-10-01': dict(euro95=1.8, diesel=2.0, rate=5.0, cur='RON', country='Romania'),
            '2026-10-10': dict(euro95=1.9, diesel=2.1, rate=1.0, cur='EUR', country='Romania'),
            '2026-10-12': dict(euro95=1.9, diesel=2.1, rate=5.0, cur='RON', country='Germany'),
            '2026-10-15': dict(euro95=2.0, diesel=2.2, rate=5.0, cur='RON', country='Romania')}})
        book = S.fuel_book()
        self.assertEqual([d for d, _ in book], ['2026-10-01', '2026-10-15'])
        self.assertEqual(S.fuel_lookup(book, '2026-09-30'), (9.0, 'early'))
        self.assertEqual(S.fuel_lookup(book, '2026-10-10'), (9.0, 'carry'))
        self.assertEqual(S.fuel_lookup(book, '2026-10-15'), (10.0, 'exact'))
        self.assertEqual(S.fuel_lookup([], '2026-10-15', 7.5), (7.5, 'manual'))

    def test_ice_calc(self):
        book = [('2026-10-01', 10.0)]
        by_day = [dict(day='2026-09-30', km=100.0), dict(day='2026-10-01', km=100.0), dict(day='2026-10-02', km=100.0)]
        ic = S.ice_calc(by_day, 50.0, 100.0, 200.0, l100=7.0, book=book, manual=0)
        self.assertEqual(ic['liters'], 21.0)
        self.assertEqual(ic['cost'], 210.0)
        self.assertEqual(ic['ev_cost'], 25.0)                                    # 50 kWh x (100 / 200 kWh)
        self.assertEqual(ic['est_days'], 2)                                      # 09-30 = early, 10-02 = carry
        self.assertFalse(S.ice_calc(by_day, 1, 1, 1, l100=0, book=book, manual=0)['enabled'])

    def test_rules_fire_after_mqtt_noise_and_skip_first_value(self):
        calls = []
        S.rule_exec = lambda car, r, cmd, *a: calls.append((r['id'], cmd))
        S.rules_load = lambda: [dict(id='g1', enabled=True, type='arrive_gate', geofence='Acasa'), dict(id='p1', enabled=True, type='plug_limit', limit=80)]
        S.LAST_SENT.clear()
        S.rules_check(1, 'latitude', 44.0, 44.1)
        S.rules_check(1, 'geofence', None, 'Acasa', True)
        S.rules_check(1, 'plugged_in', False, True)
        self.assertEqual(calls, [('g1', 'homelink'), ('p1', 'charge_limit')])
        calls.clear()
        S.LAST_SENT.clear()
        S.rules_check(1, 'geofence', None, 'Acasa', False)                        # prima valoare dupa repornire
        self.assertEqual(calls, [])

    def test_roles_and_sessions(self):
        S.CFG.update(roles='Wife@Example.com:Family, guest@x.ro:EDITOR')
        S.apply_config()
        self.assertEqual(S.ROLES, {'wife@example.com': 'family', 'guest@x.ro': 'viewer'})
        S.AUTH['pw'] = 'parola-1-parola-1'
        cookie = S.sess_make()
        self.assertTrue(S.sess_ok(cookie))
        S.AUTH['pw'] = 'parola-2-parola-2'
        self.assertFalse(S.sess_ok(cookie))                                       # schimbarea parolei invalideaza sesiunile
        S.AUTH['pw'] = ''

    def test_session_revocation_and_peer(self):
        import types
        S.AUTH['pw'] = 'parola-1-parola-1'
        a, b = S.sess_make(), S.sess_make()
        self.assertNotEqual(a, b)                                                 # nonce: valori diferite chiar in aceeasi secunda
        self.assertFalse(S.sess_ok(a.rsplit('.', 1)[0] + '.' + '0' * 64))
        old = S.SESS['epoch']
        try:
            S.SESS['epoch'] = int(time.time()) + 5                                # "deconectare de pe toate dispozitivele"
            self.assertFalse(S.sess_ok(a))
            S.SESS['epoch'] = 0
            self.assertTrue(S.sess_ok(a))
        finally:
            S.SESS['epoch'] = old
            S.AUTH['pw'] = ''
        peer = lambda ip: S.H.private_peer(types.SimpleNamespace(client_address=(ip, 1)))
        for ip in ('192.168.1.5', '10.0.0.1', '172.18.0.1', '127.0.0.1', '::1', '::ffff:192.168.1.9', 'fe80::1'):
            self.assertTrue(peer(ip), ip)
        for ip in ('8.8.8.8', '2a00:1450::1', '::ffff:8.8.8.8', 'nu-e-ip'):
            self.assertFalse(peer(ip), ip)

    def test_compositor_url_highland_and_juniper(self):
        old = os.environ.get('TESLA_RENDERS')
        os.environ['TESLA_RENDERS'] = '1'
        self.addCleanup(lambda: os.environ.pop('TESLA_RENDERS', None) if old is None else os.environ.__setitem__('TESLA_RENDERS', old))
        u = S.compositor_url(dict(model='3', color='PearlWhite'))
        self.assertIn('options=$MT367,$PPSW,$W38C,$IBB8', u)
        self.assertIn('view=STUD_FRONT34&model=m3', u)
        self.assertIn('crop=1200,700,370,230', u)
        self.assertIn('$PR01', S.compositor_url(dict(model='3', color='RedMulticoat')))
        self.assertIn('$PBSB', S.compositor_url(dict(model='Y', color='SolidBlack')))
        self.assertIn('view=FRONT34&model=my', S.compositor_url(dict(model='y', color='PearlWhite')))
        self.assertIn('$PN01', S.compositor_url(dict(model='3', color='MidnightSilver')))        # culoare fara cod valid: cea mai apropiata
        self.assertIsNone(S.compositor_url(dict(model='S', color='PearlWhite')))
        os.environ['TESLA_RENDERS'] = '0'
        self.assertIsNone(S.compositor_url(dict(model='3', color='PearlWhite')))                  # oprit: nicio cerere catre Tesla

    def test_run_command_norepeat(self):
        calls = []
        S._run_command = lambda car, name, arg=None: (calls.append(name) or dict(ok=True))
        S.CMD_LAST.clear()
        self.assertTrue(S.run_command(1, 'homelink')['ok'])
        self.assertEqual(S.run_command(1, 'homelink')['code'], 429)
        self.assertEqual(calls, ['homelink'])

    def test_ble_plan_clamps(self):
        S.HA.update(prefix='tesla_ble')
        self.assertEqual(S.ble_plan('set_temps', {'driver': 99})[2]['temperature'], 28.0)
        self.assertEqual(S.ble_plan('cop_temp', {'level': 77})[2]['option'], 'High')


class Versioning(Isolated):
    def setUp(self):
        S.UPDFILE = os.path.join(TMP, 'update.json')
        S.APP_VERSION = '1.0.0'
        S.UPD.update(latest='', url='', notes='', published='', checked=0, error='', notified='')
        S.CFG.clear()
        self.sent = []
        S.notify = lambda kind, title, msg, data=None, log=True: self.sent.append((kind, title))

    def test_ver_tuple_and_newer(self):
        self.assertEqual(S.ver_tuple('v1.2.3')[:3], (1, 2, 3))
        self.assertEqual(S.ver_tuple('1.10')[:3], (1, 10, 0))
        self.assertLess(S.ver_tuple('1.6.0-rc1'), S.ver_tuple('1.6.0'))                # un release candidate nu e la fel cu versiunea finala
        self.assertEqual(S.ver_tuple('1.6.0-private'), S.ver_tuple('1.6.0'))
        self.assertGreater(S.ver_tuple('1.10.0'), S.ver_tuple('1.9.9'))
        S.UPD['latest'] = '1.0.1'
        self.assertTrue(S.update_newer())
        S.UPD['latest'] = '1.0.0'
        self.assertFalse(S.update_newer())

    def test_update_check_notifies_once_per_version(self):
        S._get_text = lambda url, timeout=20: json.dumps(dict(tag_name='v1.2.0', html_url='https://github.com/x/y/releases/tag/v1.2.0', body='note', published_at='2026-10-23T00:00:00Z'))
        r = S.update_check()
        self.assertTrue(r['ok'] and r['newer'])
        self.assertEqual(len(self.sent), 1)
        S.update_check()
        self.assertEqual(len(self.sent), 1)                                   # aceeasi versiune: nu se mai notifica
        S._get_text = lambda url, timeout=20: json.dumps(dict(tag_name='v1.3.0', body=''))
        S.update_check()
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(S.jload(S.UPDFILE, {})['notified'], '1.3.0')          # supravietuieste repornirii

    def test_update_check_error_is_recorded(self):
        def boom(url, timeout=20):
            raise OSError('fara retea')
        S._get_text = boom
        self.assertFalse(S.update_check()['ok'])
        self.assertIn('fara retea', S.UPD['error'])

    def test_private_build_does_not_check(self):
        S.APP_VERSION = '1.0.0-private'
        self.assertFalse(S.update_enabled())
        S.APP_VERSION = '1.0.0'
        S.CFG['update_check'] = '0'
        self.assertFalse(S.update_enabled())

    def test_apply_needs_webhook_and_token_rule(self):
        self.assertFalse(S.update_apply()['ok'])
        calls = []
        S.http = lambda url, data=None, headers=None, **k: (calls.append((url, headers)) or (200, {}))
        S.CFG.update(update_webhook='http://watchtower:8080/v1/update', update_token='tok')
        self.assertTrue(S.update_apply()['ok'])
        self.assertEqual(calls[0][1], {'Authorization': 'Bearer tok'})
        S.CFGFILE = os.path.join(TMP, 'cfg2.json')
        ok, err = S.cfg_update({'update_webhook': 'http://evil.example/x'})
        self.assertFalse(ok)
        self.assertIn('tokenul', err)


def start(env_extra):
    env = dict(os.environ, PORT='4177', PUBLIC_PORT='4176', DATABASE_HOST='127.0.0.1', DATABASE_PASS='x', DATA_DIR=tempfile.mkdtemp(prefix='tesla-ui-srv-'), **env_extra)
    env.pop('DEMO_ONLY', None)
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, 'server.py')], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for _ in range(60):
        try:
            socket.create_connection(('127.0.0.1', 4177), 0.3).close()
            return p
        except OSError:
            time.sleep(0.25)
    p.kill()
    raise RuntimeError('serverul nu porneste')


def req(method, path, body=None, headers=None):
    c = http.client.HTTPConnection('127.0.0.1', 4177, timeout=30)
    h = dict(headers or {})
    if body is not None and not isinstance(body, bytes):
        body = json.dumps(body).encode()
        h['Content-Type'] = 'application/json'
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    return r.status, r.read(), dict(r.getheaders())


def raw_status(lines):
    s = socket.create_connection(('127.0.0.1', 4177), 5)
    s.sendall((CRLF.join(lines) + CRLF + CRLF).encode())
    time.sleep(0.6)
    out = s.recv(300)
    s.close()
    return out.split(CRLF.encode())[0]


class HttpOpen(Isolated):
    """Fara parola, fara baza de date."""
    @classmethod
    def setUpClass(cls):
        cls.p = start({})

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()
        cls.p.wait()

    def test_lan_open_without_password_internet_closed(self):
        st, d, _ = req('GET', '/api/state')
        self.assertEqual(st, 200)
        self.assertTrue(json.loads(d)['lan_open'])
        self.assertEqual(req('GET', '/api/state', headers={'X-Forwarded-For': '1.2.3.4'})[0], 401)

    def test_update_buttons_work_before_a_pin_is_set(self):
        st, d, _ = req('POST', '/api/update/check', body=b'{}', headers={'Content-Type': 'application/json'})
        self.assertEqual(st, 200)                                                           # inainte: 403 "PIN gresit sau neconfigurat" pe o instalare noua
        st, d, _ = req('POST', '/api/update/apply', body=b'{}', headers={'Content-Type': 'application/json'})
        self.assertEqual(st, 200)
        self.assertIn('updater', json.loads(d)['reason'])                                   # nu exista updater in test: mesajul vine de la updater, nu de la PIN
        self.assertEqual(req('POST', '/api/rules', body=b'{}', headers={'Content-Type': 'application/json'})[0], 403)      # restul comenzilor cer in continuare PIN

    def test_db_down_is_503_not_demo(self):
        self.assertEqual(req('GET', '/api/drives')[0], 503)
        self.assertEqual(req('GET', '/api/charge_row/5')[0], 503)
        self.assertEqual(req('GET', '/api/rules')[0], 200)

    def test_health_reports_db(self):
        st, d, _ = req('GET', '/api/health')
        self.assertEqual(st, 503)
        self.assertFalse(json.loads(d)['db'])

    def test_body_limits_and_content_type(self):
        self.assertIn(b' 400 ', raw_status(['POST /api/notify/test HTTP/1.0', 'Content-Type: application/json', 'Content-Length: -1']))
        self.assertIn(b' 400 ', raw_status(['POST /api/notify/test HTTP/1.0', 'Content-Type: application/json', 'Content-Length: 2097152']))
        self.assertEqual(req('POST', '/api/notify/test', body=b'{}', headers={'Content-Type': 'text/plain'})[0], 415)

    def test_host_and_origin_checks(self):
        self.assertEqual(req('GET', '/api/health', headers={'Host': 'evil.example.com'})[0], 421)                  # DNS rebinding
        st, d, _ = req('GET', '/api/health', headers={'Host': 'masina.exemplu.ro'})
        self.assertEqual(st, 421)
        reason = json.loads(d)['reason']
        self.assertIn('masina.exemplu.ro', reason)                                                            # mesajul spune ce adresa a fost refuzata
        self.assertIn('Adrese permise', reason)
        self.assertEqual(req('GET', '/api/health', headers={'Host': '192.168.1.5:4100'})[0], 503)                  # IP: acceptat (503 = fara DB in test)
        self.assertEqual(req('GET', '/api/health', headers={'Host': 'casa'})[0], 503)                              # nume simplu: acceptat
        self.assertNotEqual(req('GET', '/api/health', headers={'Host': 'masina.exemplu.ro', 'Cf-Ray': 'x'})[0], 421)   # prin Cloudflare nu se verifica
        st, _, _ = req('POST', '/api/notify/test', body={}, headers={'Origin': 'http://evil.example.com'})
        self.assertEqual(st, 403)

    def test_version_endpoint(self):
        st, d, _ = req('GET', '/api/version')
        self.assertEqual(st, 200)
        self.assertIn('version', json.loads(d))

    def test_security_headers(self):
        st, _, h = req('GET', '/')
        self.assertEqual(st, 200)
        self.assertIn("script-src 'self'", h.get('Content-Security-Policy', ''))
        self.assertEqual(h.get('X-Content-Type-Options'), 'nosniff')


class HttpWithPassword(Isolated):
    PW = 'parola-de-test-123'

    @classmethod
    def setUpClass(cls):
        cls.p = start(dict(APP_PASSWORD=cls.PW, APP_PIN='abc123'))

    @classmethod
    def tearDownClass(cls):
        cls.p.kill()
        cls.p.wait()

    def test_login_pin_throttle_and_cookie(self):
        self.assertEqual(req('GET', '/api/state')[0], 401)                        # cu parola setata, si LAN-ul cere login
        st, _, h = req('POST', '/login', body=('password=' + self.PW).encode(), headers={'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(st, 303)
        cookie = h.get('Set-Cookie', '').split(';')[0]
        self.assertEqual(req('GET', '/api/state', headers={'Cookie': cookie})[0], 200)
        codes = [req('POST', '/api/cmd/flash', body={'car': 1}, headers={'Cookie': cookie, 'X-Pin': 'gresit%d' % i})[0] for i in range(7)]
        self.assertEqual(codes, [403] * 5 + [429, 429])
        self.assertEqual(req('POST', '/api/cmd/flash', body={'car': 1}, headers={'Cookie': cookie, 'X-Pin': 'abc123'})[0], 429)
        bad = [req('POST', '/login', body=b'password=x', headers={'Content-Type': 'application/x-www-form-urlencoded'})[0] for _ in range(7)]
        self.assertEqual(bad[0], 401)
        self.assertIn(429, bad)


if __name__ == '__main__':
    unittest.main()

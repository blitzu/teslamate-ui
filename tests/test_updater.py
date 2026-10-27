"""Teste pentru updater/updater.py (autentificare, servicii permise, o singura rulare, limitare, HTTP)."""
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'updater'))
import updater as U  # noqa: E402

TOKEN = 'x' * 20


class UpdaterTests(unittest.TestCase):
    def test_services_are_sanitised(self):
        self.assertEqual(U.services('ui proxy'), ['ui', 'proxy'])
        self.assertEqual(U.services('ui `x` $(y) --x ../etc UI proxy-2 /'), ['ui', 'proxy-2'])          # doar nume simple, litere mici
        self.assertEqual(U.services(''), ['ui', 'proxy'])

    def test_authorization(self):
        self.assertTrue(U.authorized('Bearer ' + TOKEN, TOKEN))
        self.assertFalse(U.authorized('Bearer ' + TOKEN + 'x', TOKEN))
        self.assertFalse(U.authorized('Basic ' + TOKEN, TOKEN))
        self.assertFalse(U.authorized(None, TOKEN))
        self.assertFalse(U.authorized('Bearer short', 'short'))                                         # tokenul trebuie sa aiba minim 16 caractere

    def test_token_is_generated_once_and_reused(self):
        import tempfile
        path = os.path.join(tempfile.mkdtemp(), 'updater.token')
        os.environ.pop('UPDATER_TOKEN', None)
        t1 = U.load_token(path, uid=os.getuid() if hasattr(os, 'getuid') else 0)
        self.assertGreaterEqual(len(t1), 16)
        self.assertEqual(U.load_token(path), t1)                                                        # la repornire se refoloseste
        self.assertEqual(open(path).read().strip(), t1)
        os.environ['UPDATER_TOKEN'] = 'z' * 20
        try:
            self.assertEqual(U.load_token(path), 'z' * 20)                                              # variabila de mediu are prioritate
        finally:
            os.environ.pop('UPDATER_TOKEN')

    def test_project_is_discovered_from_compose_labels(self):
        info = [dict(Config=dict(Image='ghcr.io/x/y-updater:latest', Labels={'com.docker.compose.project': 'teslamate-ui', 'com.docker.compose.project.working_dir': '/srv/teslamate-ui',
                                                                              'com.docker.compose.project.config_files': '/srv/teslamate-ui/docker-compose.yml,/srv/teslamate-ui/extra.yml'}))]
        self.assertEqual(U.self_info(info), ('/srv/teslamate-ui', 'teslamate-ui', ['/srv/teslamate-ui/docker-compose.yml', '/srv/teslamate-ui/extra.yml'], 'ghcr.io/x/y-updater:latest'))
        with self.assertRaises(RuntimeError):
            U.self_info([dict(Config=dict(Labels={}))])                                                 # nu ruleaza sub compose

    def test_runs_pull_then_up_and_reports(self):
        calls = []
        up = U.Updater(TOKEN, ['ui', 'proxy'], runner=lambda a: (calls.append(a) or (0, 'ok ' + a[0])))
        self.assertEqual(up.start()[0], 202)
        for _ in range(50):
            if not up.status()['running']:
                break
            time.sleep(0.05)
        st = up.status()
        self.assertEqual((st['success'], calls), (True, [['pull', 'ui', 'proxy'], ['up', '-d', '--no-build', 'ui', 'proxy']]))
        self.assertIn('docker compose pull ui proxy', st['log'])
        self.assertEqual(up.start()[0], 429)                                                            # prea repede dupa o rulare

    def _run(self, up):
        up.start()
        for _ in range(100):
            if not up.status()['running']:
                break
            time.sleep(0.05)
        return up.status()

    def test_self_update_is_the_last_step(self):
        import tempfile
        sf = os.path.join(tempfile.mkdtemp(), 'state.json')
        calls = []
        up = U.Updater(TOKEN, ['ui', 'proxy'], runner=lambda a: (calls.append(a) or (0, 'ok')), selfsvc='updater', state_file=sf)
        st = self._run(up)
        self.assertEqual(calls, [['pull', 'ui', 'proxy'], ['up', '-d', '--no-build', 'ui', 'proxy'], ['pull', 'updater'], ['up', '-d', '--no-build', '--no-deps', 'updater']])
        self.assertTrue(st['success'])
        self.assertEqual(json.load(open(sf))['success'], True)                                          # starea ramane pe disc

    def test_self_update_failure_keeps_app_success(self):
        calls = []
        up = U.Updater(TOKEN, ['ui'], runner=lambda a: (calls.append(a) or ((1, 'nu merge') if a[:2] == ['pull', 'updater'] else (0, 'ok'))), selfsvc='updater')
        st = self._run(up)
        self.assertTrue(st['success'])                                                                  # aplicatia s-a actualizat; doar imaginea updater-ului a esuat
        self.assertIn('actualizarea imaginii updater-ului a esuat', st['log'])
        self.assertEqual(calls[-1], ['pull', 'updater'])                                                # nu se mai recreeaza daca imaginea n-a putut fi trasa

    def test_self_service_not_duplicated_and_none_without_label(self):
        calls = []
        up = U.Updater(TOKEN, ['ui', 'updater'], runner=lambda a: (calls.append(a) or (0, 'ok')), selfsvc='updater')
        self._run(up)
        self.assertEqual(len(calls), 2)                                                                 # daca e deja in UPDATER_SERVICES, nu se adauga un pas separat
        self.assertEqual(U.self_service([dict(Config=dict(Labels={'com.docker.compose.service': 'updater'}))]), 'updater')
        self.assertIsNone(U.self_service([dict(Config=dict(Labels={}))]))
        self.assertIsNone(U.self_service([dict(Config=dict(Labels={'com.docker.compose.service': 'x; rm -rf /'}))]))

    def test_state_survives_restart_during_self_step(self):
        import tempfile
        sf = os.path.join(tempfile.mkdtemp(), 'state.json')
        json.dump(dict(running=True, started=1, finished=0, success=None, log='$ pull', self_step=True), open(sf, 'w'))
        up = U.Updater(TOKEN, ['ui'], runner=lambda a: (0, ''), state_file=sf)
        st = up.status()
        self.assertEqual((st['running'], st['success']), (False, True))
        self.assertIn('imaginea noua', st['log'])
        json.dump(dict(running=True, started=1, finished=0, success=None, log='$ pull'), open(sf, 'w'))     # oprit din alt motiv
        st = U.Updater(TOKEN, ['ui'], runner=lambda a: (0, ''), state_file=sf).status()
        self.assertEqual((st['running'], st['success']), (False, None))
        open(sf, 'w').write('nu e json')
        self.assertFalse(U.Updater(TOKEN, ['ui'], runner=lambda a: (0, ''), state_file=sf).status()['running'])   # fisier stricat: ignorat

    def test_failure_stops_before_up(self):
        calls = []
        up = U.Updater(TOKEN, ['ui'], runner=lambda a: (calls.append(a[0]) or (1, 'nu merge')))
        up.start()
        for _ in range(50):
            if not up.status()['running']:
                break
            time.sleep(0.05)
        self.assertEqual((up.status()['success'], calls), (False, ['pull']))

    def test_only_one_run_at_a_time(self):
        gate = threading.Event()
        up = U.Updater(TOKEN, ['ui'], runner=lambda a: (gate.wait(2) and (0, '')) or (0, ''))
        self.assertEqual(up.start()[0], 202)
        self.assertEqual(up.start(time.time() + 100)[0], 409)
        gate.set()

    def test_http_endpoints(self):
        up = U.Updater(TOKEN, ['ui'], runner=lambda a: (0, 'ok'))
        srv = ThreadingHTTPServer(('127.0.0.1', 0), U.make_handler(up))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = 'http://127.0.0.1:%d' % srv.server_address[1]

        def call(path, method='GET', tok=None):
            req = urllib.request.Request(base + path, method=method, data=b'' if method == 'POST' else None, headers={'Authorization': 'Bearer ' + tok} if tok else {})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, r.read().decode()
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode()
        try:
            self.assertEqual(call('/health'), (200, 'ok'))
            self.assertEqual(call('/update', 'POST')[0], 401)                                           # fara token
            self.assertEqual(call('/update', 'POST', 'gresit' * 5)[0], 401)
            self.assertEqual(call('/status')[0], 401)
            self.assertEqual(call('/altceva', 'POST', TOKEN)[0], 404)
            code, body = call('/update', 'POST', TOKEN)
            self.assertEqual((code, json.loads(body)['ok']), (202, True))
            time.sleep(0.3)
            code, body = call('/status', 'GET', TOKEN)
            self.assertEqual((code, json.loads(body)['ok'], json.loads(body)['success']), (200, True, True))
        finally:
            srv.shutdown()


if __name__ == '__main__':
    unittest.main()

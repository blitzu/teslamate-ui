#!/usr/bin/env python3
"""Updater minimal pentru aplicatie: la un POST autentificat trage imaginile noi ale serviciilor aplicatiei si le reporneste cu `docker compose`.
Nu are alta functie: nu atinge alte containere, nu expune niciun port pe gazda (aplicatia il apeleaza prin reteaua Docker), cere un token de minim 16 caractere.

  POST /update   (Authorization: Bearer <token>)  porneste actualizarea in fundal; 202 daca a pornit, 409 daca ruleaza deja, 429 daca s-a rulat acum cateva secunde
  GET  /status   (Authorization: Bearer <token>)  starea ultimei rulari (si coada jurnalului)
  GET  /health   fara autentificare, doar "ok"

Variabile: UPDATER_TOKEN (obligatoriu), PROJECT_DIR (folderul proiectului compose, montat la ACEEASI cale ca pe gazda), UPDATER_SERVICES (implicit "ui proxy"),
UPDATER_AUTO_HOURS (0 = doar la cerere; altfel actualizeaza singur la acest interval, minim 1 h), UPDATER_PORT (implicit 8080)."""
import hmac
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MIN_GAP = 30                         # secunde intre doua rulari
CMD_TIMEOUT = 900                    # o descarcare lenta poate dura minute


def services(raw):
    """Doar nume simple de servicii compose (fara optiuni sau cai)."""
    return [s for s in str(raw or 'ui proxy').split() if re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,39}', s)]


def authorized(header, token):
    h = str(header or '')
    return len(token) >= 16 and h.startswith('Bearer ') and hmac.compare_digest(h[7:].strip().encode(), token.encode())


class Updater:
    def __init__(self, token, svcs, project_dir, runner=None):
        self.token, self.svcs, self.dir = token, svcs, project_dir
        self.runner = runner or self.docker
        self.lock = threading.Lock()
        self.state = dict(running=False, started=0, finished=0, success=None, log='')

    def docker(self, args):
        r = subprocess.run(['docker', 'compose'] + args, cwd=self.dir, capture_output=True, text=True, timeout=CMD_TIMEOUT)
        return r.returncode, (r.stdout + r.stderr)

    def work(self):
        log, ok = [], True
        try:
            for args in (['pull'] + self.svcs, ['up', '-d', '--no-build'] + self.svcs):       # fara --remove-orphans: nu se atinge nimic din afara serviciilor date
                code, out = self.runner(args)
                log.append('$ docker compose %s\n%s' % (' '.join(args), out.strip()))
                if code != 0:
                    ok = False
                    break
        except Exception as e:  # noqa
            ok = False
            log.append('eroare: %s' % e)
        with self.lock:
            self.state.update(running=False, finished=time.time(), success=ok, log='\n'.join(log)[-4000:])

    def start(self, now=None):
        """(cod HTTP, mesaj). Porneste o rulare in fundal daca se poate."""
        now = now or time.time()
        with self.lock:
            if self.state['running']:
                return 409, 'o actualizare ruleaza deja'
            if now - self.state['finished'] < MIN_GAP:
                return 429, 'prea devreme, asteapta cateva secunde'
            self.state.update(running=True, started=now, success=None)
        threading.Thread(target=self.work, daemon=True).start()
        return 202, 'pornit'

    def status(self):
        with self.lock:
            return dict(self.state)


def make_handler(up):
    class H(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.0'

        def log_message(self, *a):
            pass

        def send(self, code, obj=None, text=None):
            b = (text if text is not None else json.dumps(obj)).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'text/plain; charset=utf-8' if text is not None else 'application/json')
            self.send_header('Content-Length', str(len(b)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if self.path == '/health':
                return self.send(200, text='ok')
            if self.path == '/status':
                if not authorized(self.headers.get('Authorization'), up.token):
                    return self.send(401, dict(ok=False, reason='token'))
                return self.send(200, dict(ok=True, **up.status()))
            return self.send(404, dict(ok=False))

        def do_POST(self):
            if self.path != '/update':
                return self.send(404, dict(ok=False))
            if not authorized(self.headers.get('Authorization'), up.token):
                return self.send(401, dict(ok=False, reason='token'))
            code, msg = up.start()
            return self.send(code, dict(ok=code == 202, reason=msg))
    return H


def main():
    token = os.environ.get('UPDATER_TOKEN', '')
    if len(token) < 16:
        sys.exit('UPDATER_TOKEN lipseste sau are sub 16 caractere (setează-l in .env).')
    pdir = os.environ.get('PROJECT_DIR', '/project')
    if not os.path.isfile(os.path.join(pdir, 'docker-compose.yml')) and not os.path.isfile(os.path.join(pdir, 'compose.yaml')):
        sys.exit('PROJECT_DIR=%s nu contine docker-compose.yml: monteaza folderul proiectului la aceeasi cale ca pe gazda.' % pdir)
    svcs = services(os.environ.get('UPDATER_SERVICES'))
    if not svcs:
        sys.exit('UPDATER_SERVICES gol sau invalid.')
    up = Updater(token, svcs, pdir)
    try:
        hours = float(os.environ.get('UPDATER_AUTO_HOURS', '0') or 0)
    except ValueError:
        hours = 0
    if hours > 0:
        hours = max(1.0, hours)

        def loop():
            time.sleep(600)
            while True:
                up.start()
                time.sleep(hours * 3600)
        threading.Thread(target=loop, daemon=True).start()
    print('updater pornit: servicii=%s auto=%sh' % (' '.join(svcs), hours or 'off'), flush=True)
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('UPDATER_PORT', '8080'))), make_handler(up)).serve_forever()


if __name__ == '__main__':
    main()

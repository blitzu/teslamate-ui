#!/usr/bin/env python3
"""Updater inclus in stack, fara configurare: la un POST autentificat trage imaginile noi ale serviciilor aplicatiei si le reporneste cu `docker compose`.
Nu are alta functie: nu atinge alte containere, nu expune niciun port pe gazda (aplicatia il apeleaza prin reteaua Docker).

Fara setari manuale:
  * folderul proiectului si numele proiectului le afla singur, din etichetele pe care compose le pune pe propriul container;
  * comenzile compose le ruleaza intr-un container ajutator (aceeasi imagine, cu folderul proiectului montat la aceeasi cale ca pe gazda);
  * tokenul si-l genereaza la prima pornire in /data/updater.token, de unde il citeste aplicatia (acelasi folder ./data).

  POST /update   (Authorization: Bearer <token>)  porneste actualizarea in fundal; 202 daca a pornit, 409 daca ruleaza deja, 429 daca s-a rulat acum cateva secunde
  GET  /status   (Authorization: Bearer <token>)  starea ultimei rulari (si coada jurnalului)
  GET  /health   fara autentificare, doar "ok"

Setari optionale (variabile): UPDATER_SERVICES (implicit "ui proxy"), UPDATER_AUTO_HOURS (0 = doar la cerere; altfel actualizeaza singur la acest interval, minim 1 h),
UPDATER_TOKEN (in loc de fisier), APP_UID (proprietarul fisierului de token, implicit 10001), UPDATER_PORT (implicit 8080)."""
import hmac
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MIN_GAP = 30                         # secunde intre doua rulari
CMD_TIMEOUT = 900                    # o descarcare lenta poate dura minute
TOKEN_FILE = os.environ.get('UPDATER_TOKEN_FILE', '/data/updater.token')


def services(raw):
    """Doar nume simple de servicii compose (fara optiuni sau cai)."""
    return [s for s in str(raw or 'ui proxy').split() if re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,39}', s)]


def authorized(header, token):
    h = str(header or '')
    return len(token) >= 16 and h.startswith('Bearer ') and hmac.compare_digest(h[7:].strip().encode(), token.encode())


def load_token(path=TOKEN_FILE, uid=None):
    """Tokenul din UPDATER_TOKEN sau din fisier; daca nu exista, il genereaza (mod 600, al utilizatorului aplicatiei, ca sa-l poata citi aplicatia)."""
    t = os.environ.get('UPDATER_TOKEN', '').strip()
    if len(t) >= 16:
        return t
    try:
        with open(path) as f:
            t = f.read().strip()
        if len(t) >= 16:
            return t
    except OSError:
        pass
    t = secrets.token_urlsafe(24)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(t + '\n')
    try:
        u = int(uid if uid is not None else os.environ.get('APP_UID', '10001'))
        os.chown(path, u, u)
    except (OSError, ValueError, AttributeError):
        os.chmod(path, 0o644)                                        # fara drept de chown: citibil de aplicatie, in folderul ei de date
    return t


def self_info(inspect_json):
    """(folder proiect, nume proiect, fisiere compose, imagine) din rezultatul `docker inspect` al propriului container."""
    d = inspect_json[0] if isinstance(inspect_json, list) else inspect_json
    lab = (d.get('Config') or {}).get('Labels') or {}
    wd = lab.get('com.docker.compose.project.working_dir')
    if not wd:
        raise RuntimeError('containerul nu a fost pornit cu docker compose (lipsesc etichetele compose)')
    files = [f for f in str(lab.get('com.docker.compose.project.config_files') or '').split(',') if f]
    return wd, lab.get('com.docker.compose.project') or os.path.basename(wd.rstrip('/')), files, (d.get('Config') or {}).get('Image') or d.get('Image')


class Updater:
    def __init__(self, token, svcs, runner=None):
        self.token, self.svcs = token, svcs
        self.runner = runner or self.docker
        self.lock = threading.Lock()
        self.state = dict(running=False, started=0, finished=0, success=None, log='')

    def docker(self, args):
        """Ruleaza `docker compose <args>` pentru proiectul in care ruleaza acest container, intr-un container ajutator."""
        me = subprocess.run(['docker', 'inspect', socket.gethostname()], capture_output=True, text=True, timeout=30)
        if me.returncode != 0:
            return me.returncode, me.stderr
        wd, project, files, image = self_info(json.loads(me.stdout))
        name = 'tessie-updater-run-%d' % int(time.time())
        cmd = ['docker', 'run', '--rm', '--name', name, '--entrypoint', 'docker', '--cap-drop', 'ALL', '--cap-add', 'DAC_READ_SEARCH', '--security-opt', 'no-new-privileges:true',
               '-v', '/var/run/docker.sock:/var/run/docker.sock', '-v', '%s:%s' % (wd, wd), '-w', wd, image, 'compose', '-p', project, '--project-directory', wd]
        for f in files:
            cmd += ['-f', f]
        try:
            r = subprocess.run(cmd + args, capture_output=True, text=True, timeout=CMD_TIMEOUT)
        except subprocess.TimeoutExpired:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True, timeout=30)           # containerul ajutator nu trebuie sa ramana in urma si sa se suprapuna cu urmatoarea rulare
            raise
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
        timeout = 30                                              # o conexiune care nu trimite nimic nu blocheaza handler-ul (pids_limit mic)

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
    svcs = services(os.environ.get('UPDATER_SERVICES'))
    if not svcs:
        sys.exit('UPDATER_SERVICES gol sau invalid.')
    try:
        token = load_token()
    except OSError as e:
        sys.exit('Nu pot crea tokenul in %s (%s). Monteaza folderul ./data la /data.' % (TOKEN_FILE, e))
    try:                                                                                       # esueaza devreme, cu un mesaj clar, daca nu ruleaza sub compose
        me = subprocess.run(['docker', 'inspect', socket.gethostname()], capture_output=True, text=True, timeout=30)
        wd, project, _, image = self_info(json.loads(me.stdout))
    except Exception as e:  # noqa
        sys.exit('Nu pot afla proiectul compose: %s. Ai montat /var/run/docker.sock?' % e)
    up = Updater(token, svcs)
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
    print('updater pornit: proiect=%s folder=%s servicii=%s auto=%sh' % (project, wd, ' '.join(svcs), hours or 'off'), flush=True)
    ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('UPDATER_PORT', '8080'))), make_handler(up)).serve_forever()


if __name__ == '__main__':
    main()

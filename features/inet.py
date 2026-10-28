"""Acces direct din internet, fara Cloudflare: HTTPS cu certificat Let's Encrypt, totul din Setari -> Securitate (fara .env, fara terminal). Doua moduri:
  * "duckdns": un subdomeniu DuckDNS; aplicatia ii tine IP-ul la zi (la 5 minute) si obtine certificatul prin validare DNS-01 (TXT prin DuckDNS): fara port 80, fara nimic deschis pentru validare;
  * "own": domeniul tau (go.ro de la Digi, No-IP, domeniu propriu...) al carui IP il actualizeaza deja ISP-ul / routerul; nu foloseste DNS-ul, ci validarea TLS-ALPN-01: Let's Encrypt se
    conecteaza la portul 443 al domeniului si aplicatia raspunde cu un certificat de validare (pentru cateva secunde, portul public trece in HTTPS doar pentru asta).
In ambele moduri:
  * serveste aplicatia prin HTTPS pe portul public (PUBLIC_PORT, implicit 4101 - cel pe care il ai deja publicat); tu redirectionezi portul 443 al routerului catre el.
Nu se porneste fara parola aplicatiei. Cheile (cont, certificat) sunt in /data/tls, cu drepturi doar pentru aplicatie. Tokenul DuckDNS nu apare in jurnal sau in raspunsuri."""
import collections
import json
import os
import re
import socket
import ssl
import threading
import time
import types
import urllib.parse

from . import acme

RENEW_DAYS = 30
ATTEMPT_GAP = 12 * 3600          # dupa o incercare esuata, cel mai devreme peste 12 h (limite Let's Encrypt)
DNS_EVERY = 300
WAITS = (15, 45, 90)             # secunde de asteptare pentru propagarea TXT, pe incercari
OWN_WAITS = (2, 10)              # TLS-ALPN: fara DNS de propagat; doar doua incercari (fiecare validare esuata conteaza la limitele Let's Encrypt)


def truthy(v):
    return str(v).strip().lower() in ('1', 'true', 'yes', 'on')


def init(S):
    base = os.path.join(S.DATA_DIR, 'tls')

    def P(name):
        return os.path.join(base, name)

    class Inet:
        def __init__(self):
            self.holder = types.SimpleNamespace(ctx=None, saved=None, challenge_only=False)
            self.lines = collections.deque(maxlen=80)
            self.issuing = False
            self.error = ''
            self.last_attempt = 0.0
            self.ip, self.ip_at, self.dns_msg = '', 0.0, ''
            self.resolved, self.resolved_at = '', 0.0
            self.pub, self.pub_at = '', 0.0
            self.lock = threading.RLock()
            try:
                os.makedirs(base, mode=0o700, exist_ok=True)
            except OSError:
                pass

        # ---- configuratie (din Setari; env ca rezerva)
        def mode(self):
            return 'own' if str(S.cget('inet_mode', 'INET_MODE', 'duckdns')).strip().lower() == 'own' else 'duckdns'

        def own_domain(self):
            raw = re.sub(r'^https?://', '', str(S.cget('inet_domain', 'INET_DOMAIN', '')).strip().lower()).split('/')[0].split(':')[0].strip('.')
            ok = len(raw) <= 253 and re.fullmatch(r'([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{1,62}', raw) and not re.fullmatch(r'[0-9.]+', raw)
            return raw if ok else ''

        def sub(self):
            raw = re.sub(r'^https?://', '', str(S.cget('duck_domain', 'DUCK_DOMAIN', '')).strip().lower()).strip('/')
            raw = raw[:-len('.duckdns.org')] if raw.endswith('.duckdns.org') else raw
            return raw if re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', raw) else ''

        def fqdn(self):
            if self.mode() == 'own':
                return self.own_domain()
            s = self.sub()
            return s + '.duckdns.org' if s else ''

        def token(self):
            return str(S.cget('duck_token', 'DUCK_TOKEN', '')).strip()

        def staging(self):
            return truthy(S.cget('inet_staging', 'INET_STAGING', '0'))

        def on(self):
            return truthy(S.cget('inet_on', 'INET_ON', '0'))

        def blockers(self):
            out = []
            if not S.AUTH.get('pw'):
                out.append('Setează întâi parola aplicației (Securitate → Acces din internet și roluri): fără ea aplicația nu se expune pe internet.')
            if self.mode() == 'own':
                if not self.own_domain():
                    out.append('Scrie domeniul tău complet (ex. casa.go.ro).')
            else:
                if not self.sub():
                    out.append('Scrie subdomeniul DuckDNS.')
                if not self.token():
                    out.append('Scrie tokenul DuckDNS.')
            return out

        def enabled(self):
            return self.on() and not self.blockers()

        def say(self, msg):
            self.lines.append('%s  %s' % (time.strftime('%H:%M:%S'), msg))

        # ---- DuckDNS
        def duck(self, **extra):
            """Apel DuckDNS; intoarce liniile raspunsului. Mesajele de eroare nu contin niciodata URL-ul (are tokenul)."""
            q = dict(domains=self.sub(), token=self.token(), verbose='true')
            q.update(extra)
            try:
                txt = S._get_text('https://www.duckdns.org/update?' + urllib.parse.urlencode(q), 20).strip()
            except Exception as e:  # noqa
                raise RuntimeError('DuckDNS nu răspunde (%s)' % type(e).__name__)
            lines = [x.strip() for x in txt.splitlines()]
            if not lines or lines[0] != 'OK':
                raise RuntimeError('DuckDNS a refuzat cererea: verifică subdomeniul și tokenul')
            return lines

        def update_ip(self):
            if self.mode() == 'own':
                return ''
            lines = self.duck(ip='')
            self.ip, self.ip_at = (lines[1] if len(lines) > 1 else ''), time.time()
            self.dns_msg = lines[-1] if len(lines) > 2 else 'OK'
            return self.ip

        # ---- certificat
        def cert(self):
            try:
                with open(P('meta.json'), encoding='utf-8') as f:
                    meta = json.load(f)
                with open(P('fullchain.pem'), encoding='utf-8') as f:
                    pem = f.read()
                not_after, issuer, names = acme.cert_info(pem)
            except (OSError, ValueError, KeyError, TypeError):
                return None
            return dict(domain=meta.get('domain', ''), staging=bool(meta.get('staging')), not_after=int(not_after), days_left=int((not_after - time.time()) // 86400), issuer=issuer, names=names)

        def cert_ok(self):
            c = self.cert()
            return bool(c and c['days_left'] >= 0 and self.fqdn() and self.fqdn() in c['names'])

        def load_ctx(self):
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(P('fullchain.pem'), P('cert.key'))
            self.holder.ctx = ctx

        def _challenge_ctx(self, domain, digest):
            """Context TLS cu certificatul de validare TLS-ALPN-01 (ALPN acme-tls/1)."""
            import shutil
            import tempfile
            cert, key = acme.alpn_cert(domain, digest)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            d = tempfile.mkdtemp(dir=base)
            try:
                with open(os.path.join(d, 'c.pem'), 'wb') as f:
                    f.write(cert)
                with open(os.path.join(d, 'k.pem'), 'wb') as f:
                    f.write(key)
                ctx.load_cert_chain(os.path.join(d, 'c.pem'), os.path.join(d, 'k.pem'))
            finally:
                shutil.rmtree(d, ignore_errors=True)
            ctx.set_alpn_protocols(['acme-tls/1'])
            return ctx

        def _challenge_on(self, domain, digest):
            """Pregateste raspunsul: portul public trece in HTTPS cu certificatul de validare (doar el, pana se termina validarea)."""
            ctx = self._challenge_ctx(domain, digest)
            with self.lock:
                self.holder.saved, self.holder.ctx, self.holder.challenge_only = self.holder.ctx, ctx, True
                S.INET_TLS = self.holder
                if getattr(S, 'PUBLIC', {}).get('mode') != 'tls':
                    S.public_restart()
            end = time.time() + 15
            while time.time() < end and getattr(S, 'PUBLIC', {}).get('mode') != 'tls':
                time.sleep(0.2)
            time.sleep(1.0)                                                       # listenerul HTTPS tocmai a pornit

        def _challenge_off(self):
            with self.lock:
                self.holder.ctx, self.holder.saved, self.holder.challenge_only = self.holder.saved, None, False

        def _write(self, name, data, mode=0o600):
            tmp = P(name) + '.tmp'
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(data)
            os.replace(tmp, P(name))

        def issue(self):
            """Porneste emiterea in fundal. False daca ruleaza deja; ValueError daca lipsesc conditiile."""
            why = self.blockers()
            if why:
                raise ValueError(why[0])
            with self.lock:
                if self.issuing:
                    return False
                self.issuing, self.error = True, ''
                self.lines.clear()
            threading.Thread(target=self._run, daemon=True).start()
            return True

        def _run(self):
            try:
                self.last_attempt = time.time()
                fq, stag, own = self.fqdn(), self.staging(), self.mode() == 'own'
                self.say("Let's Encrypt%s pentru %s (%s)" % (' (STAGING, certificat de test)' if stag else '', fq, 'validare TLS-ALPN pe portul 443' if own else 'validare DNS prin DuckDNS'))
                if not own:
                    try:
                        self.say('DuckDNS: IP %s' % self.update_ip())
                    except RuntimeError as e:
                        self.say(str(e))
                kf = P('account-%s.key' % ('staging' if stag else 'prod'))
                key = None
                if os.path.isfile(kf):
                    with open(kf, 'rb') as f:
                        key = acme.load_key(f.read())
                client = acme.Client(acme.STAGING if stag else acme.PROD, key, http=acme.default_http(ua='teslamate-ui/%s' % S.APP_VERSION), log=self.say)
                if key is None:
                    self._write(os.path.basename(kf), acme.key_pem(client.key).decode())
                email = str(S.cget('inet_email', 'INET_EMAIL', '')).strip()
                last = None
                waits = OWN_WAITS if own else WAITS
                for i, wait in enumerate(waits):
                    try:
                        if not client.kid:
                            client.register(email or None)
                        if own:
                            chain, ckey = client.obtain(fq, lambda dg: self._challenge_on(fq, dg), self._challenge_off, propagate=wait, method='tls-alpn-01')
                        else:
                            chain, ckey = client.obtain(fq, lambda v: self.duck(txt=v), lambda: self.duck(txt='', clear='true'), propagate=wait)
                        last = None
                        break
                    except acme.AcmeError as e:
                        last = e
                        self.say('Eroare: %s' % e)
                        if own and re.search(r'(?i)connect|timeout|refused|unreachable', str(e)):
                            self.say('Let\'s Encrypt nu a ajuns la portul 443 al domeniului: verifică în router redirecționarea extern 443 → portul public al aplicației și că %s arată către IP-ul tău public (nu CGNAT).' % fq)
                        if 'rateLimited' in str(e) or i == len(waits) - 1:
                            break
                        self.say('Reîncerc')
                if last:
                    raise last
                self._write('fullchain.pem', chain, 0o644)
                self._write('cert.key', ckey, 0o600)
                self._write('meta.json', json.dumps(dict(domain=fq, staging=stag, issued=int(time.time()))), 0o644)
                self.load_ctx()
                c = self.cert()
                self.say('Gata: certificat valabil %d zile' % c['days_left'])
            except Exception as e:  # noqa
                self.error = str(e)[:300]
                self.say('Nu s-a putut obține certificatul: %s' % self.error)
            finally:
                self.issuing = False
                self.apply(auto_issue=False)

        # ---- pornire / oprire a listenerului HTTPS
        def apply(self, auto_issue=True):
            """Aduce serverul in starea ceruta de setari: HTTPS pe portul public daca e activat si exista un certificat bun, altfel HTTP; porneste emiterea daca lipseste certificatul."""
            with self.lock:
                want = self.enabled()
                if want and self.cert_ok():
                    if self.holder.ctx is None:
                        try:
                            self.load_ctx()
                        except (OSError, ssl.SSLError) as e:
                            self.error = 'certificat ilizibil: %s' % str(e)[:100]
                    S.INET_TLS = self.holder if self.holder.ctx is not None else None
                else:
                    S.INET_TLS = None
                tls = S.INET_TLS is not None
                if tls != (getattr(S, 'PUBLIC', {}).get('mode') == 'tls'):
                    S.public_restart()
                    self.say('Portul public trece pe %s' % ('HTTPS' if tls else 'HTTP'))
            if want:
                if self.mode() == 'duckdns':
                    threading.Thread(target=self._ip_quiet, daemon=True).start()
                if auto_issue and not self.cert_ok() and not self.issuing and time.time() - self.last_attempt > 3600:
                    try:
                        self.issue()
                    except ValueError:
                        pass

        def _ip_quiet(self):
            if self.mode() != 'duckdns':
                return
            try:
                self.update_ip()
            except RuntimeError as e:
                self.dns_msg = str(e)

        def _resolve_bg(self):
            try:
                self.resolved = socket.gethostbyname(self.fqdn())
            except OSError:
                self.resolved = ''
            self.resolved_at = time.time()

        def _pub_bg(self):
            try:
                v = S._get_text('https://api.ipify.org', 10).strip()
                if re.fullmatch(r'[0-9.]{7,15}', v):
                    self.pub = v
            except Exception:  # noqa
                pass

        def public_ip(self):
            """IP-ul public vazut din exterior (doar in modul "own", ca sa poti compara cu ce arata DNS-ul); cerere anonima la ipify.org, cel mult la 10 minute."""
            if time.time() - self.pub_at > 600:
                self.pub_at = time.time()
                threading.Thread(target=self._pub_bg, daemon=True).start()
            return self.pub

        def status(self):
            fq = self.fqdn()
            if fq and time.time() - self.resolved_at > 60:
                self.resolved_at = time.time()
                threading.Thread(target=self._resolve_bg, daemon=True).start()
            c = self.cert()
            return dict(mode=self.mode(), public_ip=self.public_ip() if self.mode() == 'own' else '', on=self.on(), enabled=self.enabled(), blockers=self.blockers(), domain=fq, staging=self.staging(), password_set=bool(S.AUTH.get('pw')), token_set=bool(self.token()),
                        ip=self.ip, ip_at=int(self.ip_at), dns_msg=self.dns_msg, resolved=self.resolved, cert=c, cert_ok=self.cert_ok(), issuing=self.issuing, error=self.error,
                        log=list(self.lines), listening=getattr(S, 'PUBLIC', {}).get('mode') == 'tls' and not self.holder.challenge_only, port=int(os.environ.get('PUBLIC_PORT', '4101')))

        # ---- fundal
        def dns_loop(self):
            time.sleep(45)
            while True:
                if self.enabled() and self.mode() == 'duckdns':
                    self._ip_quiet()
                time.sleep(DNS_EVERY)

        def renew_check(self):
            """Reinnoieste certificatul cand lipseste sau mai are sub 30 de zile (cel mult o incercare la 12 h). True daca a pornit o emitere."""
            if not self.enabled() or self.issuing or time.time() - self.last_attempt <= ATTEMPT_GAP:
                return False
            c = self.cert()
            if self.cert_ok() and c['days_left'] >= RENEW_DAYS:
                return False
            self.say('Reînnoire automată')
            return self.issue()

        def renew_loop(self):
            time.sleep(120)
            while True:
                try:
                    self.renew_check()
                except Exception as e:  # noqa
                    S.log('inet reinnoire:', str(e)[:100], flush=True)
                time.sleep(6 * 3600)

    inet = Inet()
    S.INET = inet
    if inet.enabled() and inet.cert_ok():                  # prima pornire dupa repornire: portul public porneste direct in HTTPS
        try:
            inet.load_ctx()
            S.INET_TLS = inet.holder
        except (OSError, ssl.SSLError) as e:
            S.log('inet: certificatul nu se poate incarca: %s' % str(e)[:100], flush=True)

    @S.route('GET', '/api/inet/status', role='admin')
    def status(h, a):
        return inet.status()

    @S.route('POST', '/api/inet/issue', pin=True, role='admin')
    def issue(h, b):
        try:
            return dict(ok=True, started=inet.issue())
        except ValueError as e:
            return dict(ok=False, reason=str(e))

    @S.route('POST', '/api/inet/ip', pin=True, role='admin')
    def ip(h, b):
        if inet.blockers():
            return dict(ok=False, reason=inet.blockers()[0])
        try:
            return dict(ok=True, ip=inet.update_ip())
        except RuntimeError as e:
            return dict(ok=False, reason=str(e))

    if getattr(S, 'INET_LOOPS', True):
        threading.Thread(target=inet.dns_loop, daemon=True).start()
        threading.Thread(target=inet.renew_loop, daemon=True).start()

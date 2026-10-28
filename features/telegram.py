"""Trimitere de notificari pe Telegram (bot propriu). Tokenul si chat-ul se seteaza din Setari (secret in config.json). Alegi ce tipuri de mesaje merg pe Telegram."""
import json

DEFAULT_KINDS = dict(alert=True, maint=True, report=True, app_update=True, low_batt=False, update=False, charge_done=False, charge_cost=False, plugged=False, door=False, rule=False, handoff=True, test=True)


def init(S):
    def creds():
        return str(S.cget('telegram_token', 'TELEGRAM_TOKEN', '')), str(S.cget('telegram_chat', 'TELEGRAM_CHAT', ''))

    def kinds():
        k = dict(DEFAULT_KINDS)
        k.update({a: bool(b) for a, b in (S.OWN.kv_get('telegram_kinds', {}) or {}).items() if a in k})
        return k

    def send(text, force=False):
        tok, chat = creds()
        if not (tok and chat):
            return dict(ok=False, reason='Telegram nu e configurat (token + chat în Setări).')
        try:
            c, r = S.http('https://api.telegram.org/bot%s/sendMessage' % tok, dict(chat_id=chat, text=text[:4000], disable_web_page_preview=True), timeout=15)
        except Exception as e:  # noqa
            S.log('telegram: %s' % str(e).replace(tok, '***'))
            return dict(ok=False, reason='Nu pot ajunge la Telegram.')
        if c != 200:
            return dict(ok=False, reason='Telegram a răspuns %s: %s' % (c, str((r or {}).get('description', ''))[:120]))
        return dict(ok=True)

    def sink(kind, title, msg, data):
        if kinds().get(kind) and all(creds()):
            r = send('%s\n%s' % (title, msg))
            if not r['ok']:
                S.log('telegram (%s): %s' % (kind, r['reason']))

    S.NOTIFY_SINKS.append(sink)
    S.TELEGRAM_SEND = send

    @S.route('GET', '/api/telegram/status', role='admin')
    def status(h, a):
        tok, chat = creds()
        return dict(configured=bool(tok and chat), kinds=kinds())

    @S.route('POST', '/api/telegram/kinds', pin=True, role='admin')
    def set_kinds(h, b):
        S.OWN.kv_set('telegram_kinds', {k: bool(b.get(k)) for k in DEFAULT_KINDS})
        return dict(ok=True, kinds=kinds())

    @S.route('POST', '/api/telegram/test', pin=True, role='admin')
    def test(h, b):
        return send('🔔 Test Telegram\nNotificările din aplicația Tesla ajung aici.')

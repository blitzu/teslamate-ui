"""Module optionale ale aplicatiei. Fiecare modul din MODULES are o functie `init(S)` (S = modulul server) si isi inregistreaza singur rutele HTTP
(`S.route(...)`), sarcinile de fundal (`S.BG_TASKS`), hook-urile MQTT (`S.MQTT_HOOKS`), receptorii de notificari (`S.NOTIFY_SINKS`) si tabelele (`S.OWN.migrate`)."""
import importlib

MODULES = ['events', 'backup', 'alerts', 'sleepguard', 'service', 'trips', 'software', 'telegram', 'reports', 'pzu', 'push', 'share', 'handoff', 'zones', 'tags', 'places']          # modulele noi se adauga aici, in ordinea initializarii


def load(S):
    from .store import Store
    S.OWN = Store(S.DATA_DIR + '/app.db')
    loaded = []
    for name in MODULES:
        try:
            importlib.import_module('features.' + name).init(S)
            loaded.append(name)
        except Exception as e:  # noqa
            S.log('modul %s nu a pornit: %s' % (name, e))
    return loaded

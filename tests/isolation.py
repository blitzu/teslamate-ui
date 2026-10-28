"""Baza pentru teste: ce schimba un test in modulul `server` (functii inlocuite, dictionarele de configurare) se readuce la loc dupa fiecare test,
ca rezultatul sa nu depinda de ordinea in care ruleaza testele."""
import unittest

ATTRS = ('notify', 'http', 'q', 'run_command', '_run_command', '_get_text', 'CURRENCY', 'APP_VERSION', 'FUELFILE', 'METAFILE', 'UPDFILE', 'CFGFILE',
         'UPD_TOKEN_FILE', 'NHOOK', 'rule_exec', 'rules_load', 'LOCAL_TZ', '_charges_rows', 'cget', 'LA_CLEAR_GAP', 'ha_state', 'live_apply', 'vin_for', 'notify_clear', 'charge_cost_prompt')
DICTS = ('CFG', 'HA', 'UPD', 'LA', 'AUTH', 'LIVE', 'SESS', 'BLE_SEEN', 'TEL_WINDOWS', 'TEL_VIN_CAR')


def take(S):
    return ({k: getattr(S, k) for k in ATTRS if hasattr(S, k)}, {k: dict(getattr(S, k)) for k in DICTS if isinstance(getattr(S, k, None), dict)})


def restore(S, snap):
    attrs, dicts = snap
    for k, v in attrs.items():
        setattr(S, k, v)
    for k, v in dicts.items():
        d = getattr(S, k)
        d.clear()
        d.update(v)


class Isolated(unittest.TestCase):
    def run(self, result=None):
        import server as S
        snap = take(S)
        try:
            return super().run(result)
        finally:
            restore(S, snap)

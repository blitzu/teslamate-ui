#!/usr/bin/env python3
"""Forwards decoded Tesla Fleet Telemetry records to the app's Profiler (and optionally SentryMode changes to a webhook).

Run it on the host that runs the official `tesla/fleet-telemetry` container (with "json_log_enable": true and the logger enabled for "V" records).
Environment:
  APP_INGEST_URL     e.g. http://192.168.1.50:4100/api/profiler/ingest
  APP_INGEST_TOKEN   same value as INGEST_TOKEN in the app's .env.profiler
  FT_CONTAINER       fleet-telemetry container name (default: fleet-telemetry)
  SENTRY_WEBHOOK_URL optional: POST {"state": "...", "created_at": ...} on SentryMode changes (e.g. a Home Assistant webhook)
"""
import json, os, subprocess, threading, time, urllib.request

INGEST_URL = os.environ['APP_INGEST_URL']
TOKEN = os.environ['APP_INGEST_TOKEN']
CONTAINER = os.environ.get('FT_CONTAINER', 'fleet-telemetry')
SENTRY_URL = os.environ.get('SENTRY_WEBHOOK_URL', '')
BATCH, LOCK, last = [], threading.Lock(), None


def log(*a):
    print(time.strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)


def flusher():
    while True:
        time.sleep(0.5)
        with LOCK:
            recs, BATCH[:] = list(BATCH), []
        if recs:
            try:
                req = urllib.request.Request(INGEST_URL, json.dumps({'records': recs}).encode(), {'Content-Type': 'application/json', 'X-Ingest-Token': TOKEN})
                urllib.request.urlopen(req, timeout=5).read()
            except Exception as e:
                log('ingest error', repr(e)[:100])


def sentry(state, created):
    try:
        req = urllib.request.Request(SENTRY_URL, json.dumps({'state': state, 'created_at': created}).encode(), {'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception as e:
        log('sentry webhook error', repr(e)[:100])


def run():
    global last
    p = subprocess.Popen(['docker', 'logs', '-f', '--since', '10s', CONTAINER], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in p.stdout:
        if not line.startswith('{'):
            continue
        try:
            j = json.loads(line)
        except ValueError:
            continue
        d = j.get('data')
        tx = (j.get('metadata') or {}).get('txtype')
        if tx == 'connectivity' and isinstance(d, dict):
            with LOCK:
                BATCH.append({'conn': {'Status': d.get('Status'), 'NetworkInterface': d.get('NetworkInterface')}})
            continue
        if tx != 'V' or not isinstance(d, dict):
            continue
        with LOCK:
            BATCH.append({'data': d})
            del BATCH[:-500]
        sm = d.get('SentryMode')
        if SENTRY_URL and isinstance(sm, dict):
            st = str(sm.get('sentryModeState', '')).replace('SentryModeState', '') or 'Unknown'
            if st != last:
                last = st
                sentry(st, d.get('CreatedAt'))
    p.wait()


threading.Thread(target=flusher, daemon=True).start()
while True:
    try:
        run()
    except Exception as e:
        log('forwarder error', repr(e)[:150])
    time.sleep(5)

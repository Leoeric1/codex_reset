#!/usr/bin/env bash
set -euo pipefail
docker exec -i codex-reset-monitor python - <<'PY'
import json, urllib.request, urllib.error
for path in ['/live', '/api/status', '/api/events/latest', '/api/events?limit=1', '/health']:
    try:
        with urllib.request.urlopen('http://127.0.0.1:8080'+path, timeout=5) as r:
            data=json.load(r)
            print(path, r.status)
            if path == '/api/status':
                print(json.dumps({k:data[k] for k in ['status','source','checked_at','last_sync','total','consecutive_failures']},ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(path, e.code, e.read().decode())
        raise SystemExit(1)
PY

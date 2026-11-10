#!/usr/bin/env bash
# Run in regular SSH: bash scripts/phase0_acceptance.sh [compose-project]
# No Compose interpolation, credentials, migration execution, or container lifecycle changes.
set -euo pipefail
cd -- "$(dirname -- "$0")/.."
python3 - "${1:-axtor-dev}" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

root = Path.cwd().resolve()
project = sys.argv[1]
source = root / 'src/axtor/main.py'
original = source.read_bytes()
backup = None
changed = False


def run(*args):
    return subprocess.check_output(args, text=True).strip()


def check(condition, message):
    if not condition:
        raise RuntimeError(message)
    print('PASS:', message, flush=True)


def container(service):
    ids = run('docker', 'ps', '-q', '--filter', f'label=com.docker.compose.project={project}',
              '--filter', f'label=com.docker.compose.service={service}').splitlines()
    check(len(ids) == 1, f'exactly one running {project}/{service} container')
    obj = json.loads(run('docker', 'inspect', ids[0]))[0]
    labels = obj['Config']['Labels']
    check(Path(labels.get('com.docker.compose.project.working_dir', '')).resolve() == root,
          f'{service} belongs to this working directory')
    check(obj['State'].get('Health', {}).get('Status') == 'healthy', f'{service} is healthy')
    return ids[0], obj


def api_json(path):
    with urllib.request.urlopen('http://127.0.0.1:8013' + path, timeout=4) as response:
        assert response.status == 200
        return json.load(response)


def wait_title(title):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        try:
            if api_json('/openapi.json')['info']['title'] == title:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError('Timed out waiting for OpenAPI title: ' + title)


def interrupted(signum, frame):
    raise RuntimeError(f'Interrupted by signal {signum}')


for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
    signal.signal(sig, interrupted)

try:
    print(run('id'))
    print(run('git', 'status', '--short'))
    api, ai = container('api')
    db, di = container('db')
    mounts = [m for m in ai['Mounts'] if m['Destination'] == '/app/src']
    check(len(mounts) == 1 and mounts[0]['Type'] == 'bind'
          and Path(mounts[0]['Source']).resolve() == root / 'src'
          and mounts[0]['RW'] is False, 'live /app/src bind is correct and read-only')
    check(not any(di['HostConfig'].get('PortBindings', {}).values())
          and not any(di['NetworkSettings'].get('Ports', {}).values()),
          'PostgreSQL has no published host ports')
    volumes = [m for m in di['Mounts'] if m['Destination'] == '/var/lib/postgresql/data']
    check(len(volumes) == 1 and volumes[0]['Type'] == 'volume'
          and volumes[0]['Name'] == project + '_postgres_data', 'intended development volume')
    print('Volume:', volumes[0]['Name'])
    command = ai['Config'].get('Cmd') or []
    check('uvicorn' in command and '--reload' in command
          and '--reload-dir' in command and '/app/src' in command,
          'live command uses native Uvicorn source reload')
    # Dump schema only; never dump rows, passwords, or connection URLs.
    def schema():
        return run('docker', 'exec', db, 'pg_dump', '-U', 'axtor', '-d', 'axtor',
                   '--schema-only', '--no-owner', '--no-privileges')
    def normalized_schema():
        # PostgreSQL 17 emits randomized psql restriction tokens on each dump.
        return '\n'.join(line for line in schema().splitlines()
                         if not line.startswith(('\\restrict ', '\\unrestrict ')))
    before = normalized_schema()
    current = run('docker', 'exec', api, 'alembic', 'current')
    print('Alembic current:', current or '(unversioned database)')
    print('Alembic heads:', run('docker', 'exec', api, 'alembic', 'heads'))
    print('Alembic history:', run('docker', 'exec', api, 'alembic', 'history'))
    # Unversioned is allowed: startup must not silently apply the empty baseline.
    check(not current or current == '0001 (head)', 'current revision is base or expected 0001')
    for path in ('/health', '/ready', '/openapi.json'):
        api_json(path)
        print('PASS: initial HTTP 200', path)
    check(original.count(b'title="Axtor",') == 1, 'reload edit target is unambiguous')
    # Exclusive backup beside source; survives an uncatchable SIGKILL or host outage.
    candidate = source.with_name('.main.py.phase0-backup')
    with candidate.open('xb') as stream:
        stream.write(original)
    backup = candidate
    changed = True
    source.write_bytes(original.replace(b'title="Axtor",', b'title="Axtor Phase0 reload probe",'))
    wait_title('Axtor Phase0 reload probe')
    print('PASS: container served temporary title after native reload')
    source.write_bytes(original)
    os.utime(source, None)
    changed = False
    wait_title('Axtor')
    check(source.read_bytes() == original, 'source restored byte-for-byte')
    for path in ('/health', '/ready', '/openapi.json'):
        api_json(path)
        print('PASS: restored HTTP 200', path)
    check(normalized_schema() == before, 'database schema unchanged across reload')
    check(run('docker', 'exec', api, 'alembic', 'current') == current,
          'database migration revision unchanged across reload')
    print('Source SHA256:', hashlib.sha256(original).hexdigest())
    print('PASS: Phase 0 live acceptance complete; no migrations executed')
finally:
    # Ignore additional termination signals while restoring. SIGKILL cannot be trapped.
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)
    if changed:
        source.write_bytes(original)
        os.utime(source, None)
        print('Cleanup: restored original source', flush=True)
    if backup is not None and backup.exists() and source.read_bytes() == original:
        backup.unlink()
PY

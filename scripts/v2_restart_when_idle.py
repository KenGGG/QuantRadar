"""Load an application update after all tasks finish; never stop a running task."""
import json
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:7242/api/v2'

def runs():
    with urllib.request.urlopen(BASE + '/runs?limit=1000', timeout=10) as response:
        return json.load(response)

if __name__ == '__main__':
    # Wait for the existing API's queue to drain. The updated UI submits only
    # prepared tasks while the old API is still serving this running task.
    while any(r['status'] in {'RUNNING', 'QUEUED'} for r in runs()):
        time.sleep(5)
    # Recheck immediately before invoking the identity-checked stop script.
    if any(r['status'] in {'RUNNING', 'QUEUED'} for r in runs()):
        raise SystemExit('A task appeared; API left running')
    python = str(ROOT / '.venv-v2/Scripts/python.exe')
    subprocess.run([python, '-B', str(ROOT / 'scripts/v2_stop.py')], cwd=ROOT, check=True)
    directory = ROOT / 'var/quantradar2'
    with (directory / 'mandatory-api.stdout.log').open('ab') as out, (directory / 'mandatory-api.stderr.log').open('ab') as err:
        process = subprocess.Popen([python, '-B', str(ROOT / 'scripts/v2_api.py')], cwd=ROOT,
                                   stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(30):
        try:
            runs()
            break
        except (OSError, ValueError):
            if process.poll() is not None:
                raise SystemExit('Updated API failed to start; see mandatory-api.stderr.log')
            time.sleep(1)
    else:
        raise SystemExit('Updated API readiness timed out')
    with urllib.request.urlopen('http://127.0.0.1:7242/openapi.json', timeout=10) as response:
        schema = json.load(response)
    if schema['components']['schemas']['RunInput']['properties']['data_mode']['default'] != 'prepared':
        raise SystemExit('API did not load the mandatory preparation update')
    (directory / 'mandatory-deployment.json').write_text(json.dumps({'loaded': True, 'timestamp': time.time()}), encoding='utf-8')

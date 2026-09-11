"""Move the existing Web process to main, preserving its private environment."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

parser = argparse.ArgumentParser()
parser.add_argument('--pid', type=int, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
runs = json.load(urllib.request.urlopen('http://127.0.0.1:7231/api/backtest/runs'))['runs']
if any(r['status'] in ('RUNNING', 'PENDING') for r in runs):
    raise RuntimeError('active application backtest; defer service switch')
cmdline = Path(f'/proc/{args.pid}/cmdline').read_bytes()
if b'uvicorn' not in cmdline or b'7231' not in cmdline:
    raise RuntimeError('unexpected process identity')
env = dict(item.decode().split('=', 1) for item in Path(f'/proc/{args.pid}/environ').read_bytes().split(b'\0') if b'=' in item)
env.update(PYTHONPATH=str(root / 'backend'), QUANTRADAR_APP_ROOT=str(root))
os.kill(args.pid, signal.SIGTERM)
for _ in range(40):
    if not Path(f'/proc/{args.pid}').exists():
        break
    time.sleep(.25)
with Path('/tmp/quantradar-main-web.log').open('a') as log:
    process = subprocess.Popen([str(root / '.venv/bin/uvicorn'), 'quantradar.api.app:app', '--app-dir', str(root / 'backend'), '--host', '127.0.0.1', '--port', '7231'], cwd=root, env=env, stdout=log, stderr=log, start_new_session=True)
print(process.pid)

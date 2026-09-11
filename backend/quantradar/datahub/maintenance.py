"""Short exclusive maintenance window; base tables remain read-only to strategies."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import subprocess
import socket
import time
import urllib.request


@contextmanager
def base_lease(exclusive=False):
    path = Path('/tmp') / f'quantradar-base-{os.getuid()}.lock'
    with path.open('a+') as handle:
        try:
            fcntl.flock(handle.fileno(), (fcntl.LOCK_EX | fcntl.LOCK_NB) if exclusive else fcntl.LOCK_SH)
        except BlockingIOError as exc:
            raise RuntimeError('基础数据正被回测使用，请稍后更新') from exc
        yield


def trusted_cli_sync(branch):
    if branch != 'master':
        raise RuntimeError('未配置该基础分支的维护同步')
    unit = 'quantradar-investment-data-dolt.service'
    repo = Path('/data/investment_data')
    config = subprocess.run(['systemctl', '--user', 'cat', unit], capture_output=True, text=True, check=True).stdout
    if 'WorkingDirectory=/data/investment_data' not in config or '--readonly' not in config or '-P 3307' not in config:
        raise RuntimeError('基础服务配置不符合已核验的只读部署')
    with base_lease(exclusive=True):
        runs = json.load(urllib.request.urlopen('http://127.0.0.1:7231/api/backtest/runs', timeout=10))['runs']
        if any(r['status'] in ('RUNNING', 'PENDING') for r in runs):
            raise RuntimeError('存在运行中或排队的回测，暂缓维护同步')
        subprocess.run(['systemctl', '--user', 'stop', unit], check=True, timeout=30)
        try:
            status = subprocess.run(['dolt', 'sql', '-r', 'json', '-q', 'SELECT * FROM dolt_status'], cwd=repo, text=True, capture_output=True, check=True, timeout=30)
            if json.loads(status.stdout).get('rows'):
                raise RuntimeError('基础工作区有未提交内容，不执行同步')
            result = subprocess.run(['dolt', 'pull', '--ff-only', 'origin', branch], cwd=repo, text=True, capture_output=True, timeout=600)
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout)[-2000:])
            return {'method': 'trusted_cli_ff_only', 'output': result.stdout[-2000:]}
        finally:
            subprocess.run(['systemctl', '--user', 'start', unit], check=True, timeout=30)
            deadline = time.monotonic() + 15
            while True:
                try:
                    with socket.create_connection(('127.0.0.1', 3307), timeout=1):
                        break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('基础只读服务已启动，但数据库端口尚未恢复')
                    time.sleep(.25)

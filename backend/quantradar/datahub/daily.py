"""Single-process daily update coordinator, with durable per-stage outcomes."""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pymysql

from .store import UpdateJournal, _atomic_json
from .quality import validate_candidate
from .mvp import ShardRunner, AkshareValuationFetcher
from .governor import RequestGovernor


def process_identity(pid):
    try:
        fields = Path(f'/proc/{int(pid)}/stat').read_text().rsplit(')', 1)[1].split()
        return None if fields[0] == 'Z' else fields[19]
    except (OSError, ValueError, IndexError, TypeError):
        return None


def plan_symbols(units, lifecycle, target, *, mode='sync', start=None, summaries=None):
    """One source check per target; full-history transport includes recent revisions."""
    if mode in ('audit', 'publish'):
        return []
    selected = []
    for symbol, unit in units.items():
        if unit.get('status') not in ('COMPLETE', 'PENDING'):
            continue
        life = lifecycle.get(symbol, {})
        if life.get('list_date', '') > target or (life.get('delist_date') and life['delist_date'] < (start or target)):
            continue
        if mode == 'backfill':
            gap = (summaries or {}).get(symbol, {}).get('missing_internal_days', 0)
            needs = unit.get('first_date', '9999') > start or unit.get('last_date', '') < target or gap > 0
            checked = unit.get('last_checked_target') == target and unit.get('requested_start') == start
        else:
            # Recheck once on a new target even if MAX(date) already reached it:
            # sources can revise recent values without appending a date.
            needs = True
            checked = unit.get('last_checked_target') == target
        if needs and not checked:
            selected.append(symbol)
    return selected


class DailyUpdate:
    def __init__(self, service):
        self.service = service
        self.root = Path(service.config.supplemental_repo)
        self.path = self.root / 'daily-update.json'

    def status(self):
        data = json.loads(self.path.read_text()) if self.path.exists() else {'status': 'IDLE', 'stages': {}}
        if data.get('status') == 'RUNNING' and (not data.get('identity') or process_identity(data.get('pid')) != data.get('identity')):
            data = {**data, 'status': 'INTERRUPTED'}
        return data

    def start(self, mode='update-all', start=None, end=None):
        if mode not in ('update-all', 'sync', 'backfill', 'audit', 'publish', 'base-sync'):
            raise ValueError('unsupported update mode')
        if mode == 'backfill' and (not start or not end):
            raise ValueError('backfill requires start and end')
        if mode != 'backfill' and start:
            raise ValueError('start 只适用于历史 backfill')
        if start and end and start > end:
            raise ValueError('start must not exceed end')
        for value in (start, end):
            if value:
                datetime.strptime(value, '%Y-%m-%d')
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / 'daily-launch.lock').open('a+') as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            previous = self.status()
            if previous['status'] == 'RUNNING' or self.service.job_status()['worker_alive']:
                return {'status': 'ALREADY_RUNNING', 'job': previous}
            if previous.get('job_id'):
                _atomic_json(self.root / 'updates' / (previous['job_id'] + '.json'), previous)
            job_id = 'update_' + uuid.uuid4().hex
            args = [sys.executable, '-m', 'quantradar.datahub.cli', 'run-update', '--job-id', job_id, '--mode', mode]
            if start:
                args += ['--start', start]
            if end:
                args += ['--end', end]
            with (self.root / 'daily-update.log').open('a') as log:
                process = subprocess.Popen(args, cwd=str(Path(__file__).parents[3]), env={**os.environ, 'PYTHONPATH': str(Path(__file__).parents[3] / 'backend')}, stdout=log, stderr=log, start_new_session=True)
            state = {'job_id': job_id, 'mode': mode, 'pid': process.pid, 'identity': process_identity(process.pid), 'status': 'RUNNING', 'stages': {}, 'started_at': datetime.now().astimezone().isoformat()}
            state['requested_range'] = {'start': start, 'end': end}
            _atomic_json(self.path, state)
            return state

    def _base_connection(self, commit=None):
        c = self.service.config
        return pymysql.connect(host=c.base_host, port=c.base_port, user=c.user, password=c.password,
                               database=c.base_database + ('/' + commit if commit else ''), cursorclass=pymysql.cursors.DictCursor,
                               connect_timeout=c.connect_timeout, read_timeout=max(c.read_timeout, 300))

    def base_sync(self):
        with self._base_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT DOLT_HASHOF('HEAD') AS commit_hash, ACTIVE_BRANCH() AS branch, DOLT_VERSION() AS version")
            before = cur.fetchone()
            cur.execute('SELECT * FROM dolt_status')
            if cur.fetchall():
                return {**before, 'status': 'SOURCE_BLOCKED', 'reason': '基础库存在未提交改动'}
            cur.execute('SELECT * FROM dolt_remotes')
            remotes = cur.fetchall()
            trusted = 'https://doltremoteapi.dolthub.com/chenditc/investment_data'
            if not any(r['name'] == 'origin' and r['url'].rstrip('/') == trusted for r in remotes):
                return {**before, 'status': 'SOURCE_BLOCKED', 'reason': '基础库 remote 未获准'}
            try:
                cur.execute("CALL DOLT_PULL('--ff-only', 'origin', %s)", (before['branch'],))
                pull = cur.fetchall()
            except pymysql.Error as exc:
                if 'read only' not in str(exc).lower():
                    return {**before, 'status': 'SOURCE_BLOCKED', 'reason': str(exc)}
                try:
                    from .maintenance import trusted_cli_sync
                    pull = trusted_cli_sync(before['branch'])
                except Exception as blocked:
                    return {**before, 'status': 'SOURCE_BLOCKED', 'reason': str(blocked)}
        # A new session observes the actual post-pull HEAD.
        after = self.service._base_commit()
        return {**before, 'before_commit': before['commit_hash'], 'commit_hash': after, 'pull': pull,
                'status': 'NO_CHANGE' if after == before['commit_hash'] else 'UPDATED'}

    def base_coverage(self, commit):
        result = {}
        with self._base_connection(commit) as conn, conn.cursor() as cur:
            for name, table, day, symbol in [('行情', 'final_a_stock_eod_price', 'tradedate', 'symbol'), ('ST / 停牌', 'bao_a_stock_eod_info', 'tradedate', 'code'), ('股票基础信息', 'ts_a_stock_list', 'list_date', 'ts_code')]:
                # Contract columns are verified on the deployed version; no user SQL.
                cur.execute(f'SHOW COLUMNS FROM {table}')
                columns = {r['Field'] for r in cur.fetchall()}
                if symbol not in columns:
                    symbol = 'symbol'
                scope = f" WHERE {symbol} REGEXP '^(SH(60|68)[0-9]{{4}}|SZ(00|30)[0-9]{{4}})$'" if table != 'ts_a_stock_list' else " WHERE ts_code REGEXP '^((60|68)[0-9]{4}\\\\.SH|(00|30)[0-9]{4}\\\\.SZ)$'"
                cur.execute(f'SELECT MIN({day}) AS first_date, MAX({day}) AS latest_date, COUNT(DISTINCT {symbol}) AS stocks, COUNT(*) AS row_count FROM {table}' + scope)
                result[name] = {k: str(v) if hasattr(v, 'isoformat') else v for k, v in cur.fetchone().items()}
                result[name]['base_commit'] = commit
                result[name]['checked_at'] = datetime.now().astimezone().isoformat()
            cur.execute('SELECT date, is_open FROM ts_trade_day_calendar WHERE exchange=%s ORDER BY date', ('SSE',))
            from ..providers.investment_data.provider import _is_open
            calendar = [str(r['date'])[:10] for r in cur.fetchall() if _is_open(r['is_open'])]
        return result, calendar

    def run(self, job_id, mode='update-all', start=None, end=None):
        # The launch lock also ensures the parent's initial state is written first.
        with (self.root / 'daily-launch.lock').open('a+') as launch:
            fcntl.flock(launch.fileno(), fcntl.LOCK_EX)
            state = self.status()
            if state.get('job_id') != job_id:
                raise RuntimeError('update reservation mismatch')
        def record(name, value):
            state['stages'][name] = value
            state['heartbeat'] = datetime.now().astimezone().isoformat()
            _atomic_json(self.path, state)
            if name in ('base', 'valuation', 'industry', 'lifecycle'):
                path = self.root / 'watermarks.json'
                marks = json.loads(path.read_text()) if path.exists() else {}
                mark = marks.setdefault(name, {})
                mark.update(target_as_of=state.get('target_as_of'), last_attempt_at=state['heartbeat'],
                            status=value['status'], job_id=job_id)
                if value['status'] == 'UPDATED':
                    mark['last_success_at'] = state['heartbeat']
                _atomic_json(path, marks)
        try:
            with self.service._updater_lock():
                record('base', {'status': 'RUNNING'})
                base = self.base_sync() if mode in ('update-all', 'base-sync') else {'status': 'NO_CHANGE', 'commit_hash': self.service._base_commit()}
                record('base', base)
                commit = base['commit_hash']
                record('coverage', {'status': 'RUNNING'})
                coverage, calendar = self.base_coverage(commit)
                _atomic_json(self.root / 'base-coverage.json', {'base_commit': commit, 'datasets': coverage})
                record('coverage', {'status': 'UPDATED', 'datasets': coverage})
                if mode == 'base-sync':
                    from .publication import publish_base_only
                    for name in ('valuation', 'industry', 'lifecycle'):
                        record(name, {'status': 'NO_CHANGE', 'reason': '仅同步基础库；补充数据保留原版本'})
                    record('check', {'status': 'PARTIAL', 'reason': '固定基础版本的 schema 和覆盖已核对；补充数据未重检'})
                    record('publish', publish_base_only(self.service, commit, '基础维护同步，补充版本保留'))
                    state['status'] = 'PARTIAL' if base['status'] == 'SOURCE_BLOCKED' else base['status']
                    return state
                now = datetime.now(ZoneInfo('Asia/Shanghai'))
                cutoff = end or (now.date() if now.hour >= 18 else now.date() - timedelta(days=1)).isoformat()
                target = max(d for d in calendar if d <= cutoff)
                state['target_as_of'] = target
                journal = UpdateJournal(Path(self.service.config.journal_root) / 'valuation_daily-mvp.json')
                lifecycle = {r['symbol']: r for r in self.service._base_lifecycle(base_commit=commit)}
                journal.ensure_pending([s for s, r in lifecycle.items() if r['list_date'] <= target and not r.get('delist_date')], reason='fixed base lifecycle')
                # Deterministic SDK parse failures remain isolated until adapter evidence changes.
                prior_check = self.root / 'candidate-check.json'
                summaries = json.loads(prior_check.read_text()).get('shards', {}) if prior_check.exists() else {}
                selected = plan_symbols(journal.data['units'], lifecycle, target, mode=mode, start=start, summaries=summaries)
                record('valuation', {'status': 'RUNNING' if selected else 'NO_CHANGE', 'selected': len(selected), 'target_as_of': target, 'transport': 'per-symbol full history'})
                if selected:
                    governor = RequestGovernor(self.root / 'governance', 'eastmoney')
                    with governor.operation_lock():
                        journal.begin_job(total_shards=len(journal.data['units']), resume=True)
                        runner = ShardRunner(self.root / 'staging' / 'valuation_daily-mvp', journal, AkshareValuationFetcher(governor), self.service.raw)
                        result = runner.run(selected, resume=False, target_as_of=target, requested_start=start)
                    record('valuation', {'status': 'PARTIAL' if result['failed'] else 'UPDATED', **result})
                    if runner.stop_requested:
                        state['status'] = 'PARTIAL'
                        record('publish', {'status': 'NO_CHANGE', 'reason': '任务已暂停，保留候选与原发布版本'})
                        return state
                record('industry', {'status': 'SOURCE_BLOCKED', 'reason': '无已验收的行业增量更新入口；保留原发布日期'})
                record('lifecycle', {'status': 'NO_CHANGE', 'base_commit': commit, 'reason': '使用本次固定基础版本；不推断上市或退市日期'})
                record('check', {'status': 'RUNNING'})
                candidate = validate_candidate(self.root / 'staging' / 'valuation_daily-mvp', journal.data['units'], base_commit=commit, raw_store=self.service.raw, calendar=calendar)
                _atomic_json(self.root / 'candidate-check.json', candidate)
                record('check', {'status': 'PARTIAL' if candidate['isolated'] else candidate['quality'], 'candidate_id': candidate['candidate_id'], 'accepted': len(candidate['accepted']), 'isolated': len(candidate['isolated']), 'not_checked': candidate['rules_not_checked']})
                if mode == 'audit':
                    record('publish', {'status': 'NO_CHANGE', 'reason': '仅检查候选数据'})
                elif candidate['quality'] != 'PASS':
                    from .publication import publish_base_only
                    record('publish', publish_base_only(self.service, commit, '没有通过质量检查的补充数据'))
                else:
                    from .publication import publish_candidate
                    record('publish', {'status': 'RUNNING'})
                    try:
                        record('publish', publish_candidate(self.service, candidate, progress=lambda table, rows: record('publish', {'status': 'RUNNING', 'reason': f'{table} 已写入 {rows:,} 行（尚未切换版本）'})))
                    except Exception as exc:
                        from .publication import publish_base_only
                        record('publish', publish_base_only(self.service, commit, f'补充版本未发布：{exc}'))
            state['status'] = 'PARTIAL'
        except Exception as exc:
            state['status'] = 'FAILED'
            state['error'] = str(exc)
        finally:
            state['finished_at'] = datetime.now().astimezone().isoformat()
            _atomic_json(self.path, state)
            _atomic_json(self.root / 'updates' / (job_id + '.json'), state)
        return state

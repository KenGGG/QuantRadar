"""Publish only validated shards on an isolated Dolt branch, then switch manifest."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from .dolt import SupplementalStore
from .quality import POLICY

PUBLICATION_POLICY = 'canonical-valuation-base-lifecycle-units-v3'


def checked_rows(root, candidate, symbols=None):
    for symbol in candidate['accepted'] if symbols is None else symbols:
        path = root / 'valuation_daily' / f'{symbol}.jsonl'
        # Validate exact bytes again before yielding; an old report cannot approve new bytes.
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != candidate['shards'][symbol]['input_hash']:
            raise ValueError(f'candidate input changed: {symbol}')
        for line in content.splitlines():
            yield json.loads(line)


def publish_candidate(service, candidate, progress=None):
    if candidate['policy'] != POLICY or candidate['quality'] != 'PASS' or not candidate['accepted']:
        raise ValueError('candidate quality failed')
    try:
        old = service.releases.current()
    except FileNotFoundError:
        old = None
    identity = hashlib.sha256(json.dumps({s: candidate['shards'][s]['economic_hash'] for s in candidate['accepted']}, sort_keys=True).encode()).hexdigest()
    same_values = bool(old and old.get('metadata', {}).get('quality') == 'PASS' and old.get('metadata', {}).get('economic_hash') == identity)
    if same_values and old['base_commit'] == candidate['base_commit'] and old.get('metadata', {}).get('isolated') == candidate['isolated'] and old.get('metadata', {}).get('publication_policy') == PUBLICATION_POLICY:
        return {'status': 'NO_CHANGE', 'release_id': old['release_id']}
    industries = service._existing_industries() if old and old.get('supplemental_commit') else []
    lifecycle = service._base_lifecycle(base_commit=candidate['base_commit'])
    previous = {}
    for row in sorted(industries, key=lambda r: (r['symbol'], str(r['effective_from']))):
        start = str(row['effective_from'])[:10]
        end = str(row['effective_to'])[:10] if row.get('effective_to') else None
        date.fromisoformat(start)
        if end:
            date.fromisoformat(end)
        if not row.get('source', '').startswith('swsresearch') or (end and end < start):
            raise ValueError('industry source/interval validation failed')
        if row['symbol'] in previous and (previous[row['symbol']] is None or previous[row['symbol']] >= start):
            raise ValueError('overlapping industry intervals')
        previous[row['symbol']] = end
    for row in lifecycle:
        date.fromisoformat(row['list_date'])
        if not row.get('source', '').startswith('investment_data:') or (row.get('delist_date') and row['delist_date'] < row['list_date']):
            raise ValueError('lifecycle source/interval validation failed')
    conn = service._connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM dolt_status')
            if cursor.fetchall():
                raise ValueError('补充库主分支存在未提交内容，保留原状')
            # Each candidate owns a separate branch; the serving branch is never reset.
            branch = 'candidate_' + candidate['candidate_id'][1:17] + '_p2'
            cursor.execute('SELECT name FROM dolt_branches WHERE name=%s', (branch,))
            if cursor.fetchone():
                cursor.execute('CALL DOLT_CHECKOUT(%s)', (branch,))
            else:
                if old and old.get('metadata', {}).get('quality') == 'PASS':
                    cursor.execute("CALL DOLT_CHECKOUT('-b', %s, %s)", (branch, old['supplemental_commit']))
                else:
                    cursor.execute("CALL DOLT_CHECKOUT('-b', %s)", (branch,))
        writer = SupplementalStore(conn, progress=progress)
        writer.ensure_schema()
        writer.prepare_canonical_valuation()
        with conn.cursor() as cursor:
            # Frozen legacy records remain in their immutable historical release.
            cursor.execute("DELETE FROM qr_security_lifecycle WHERE source NOT LIKE 'investment_data:%'")
        root = Path(service.config.supplemental_repo) / 'staging' / 'valuation_daily-mvp'
        previous_hashes = old.get('metadata', {}).get('shard_hashes', {}) if old else {}
        changed = [] if same_values else [s for s in candidate['accepted'] if previous_hashes.get(s) != candidate['shards'][s]['economic_hash']]
        writer.upsert_valuations(checked_rows(root, candidate, changed))
        # Retaining industry is explicitly not a source refresh.
        if industries:
            writer.upsert_industries(industries)
        writer.upsert_lifecycles(lifecycle)
        commit = writer.commit('datahub: checked candidate ' + candidate['candidate_id'])
    finally:
        conn.close()
    datasets = {}
    with service._connection(service.config.supplemental_database + '/' + commit) as frozen, frozen.cursor() as cur:
        for name, table, field in [('valuation_daily', 'qr_valuation_daily', 'trade_date'), ('sw_industry_history', 'qr_sw_industry_history', 'effective_from'), ('security_lifecycle', 'qr_security_lifecycle', 'list_date')]:
            cur.execute(f'SELECT COUNT(*) AS row_count, COUNT(DISTINCT symbol) AS stocks, MIN({field}) AS first_date, MAX({field}) AS latest_date FROM {table}')
            metrics = {k: str(v) if hasattr(v, 'isoformat') else v for k, v in cur.fetchone().items()}
            cur.execute(f'SELECT DISTINCT source FROM {table}')
            datasets[name] = {**metrics, 'source': [r['source'] for r in cur.fetchall()], 'pit_status': 'PARTIAL', 'quality_status': 'PARTIAL', 'refresh_status': 'RETAINED' if name == 'sw_industry_history' else 'UPDATED', 'published_through': metrics.get('latest_date') if name != 'security_lifecycle' else None}
        # Verify actual committed per-symbol coverage, not staging metadata alone.
        cur.execute('SELECT symbol, COUNT(*) AS n, MIN(trade_date) AS first_date, MAX(trade_date) AS latest_date FROM qr_valuation_daily GROUP BY symbol')
        actual = {r['symbol']: r for r in cur.fetchall()}
        for symbol in candidate['accepted']:
            expected = candidate['shards'][symbol]
            row = actual.get(symbol)
            if not row or row['n'] < expected['rows'] or str(row['first_date']) > expected['first_date'] or str(row['latest_date']) < expected['latest_date']:
                raise ValueError(f'fixed-commit verification failed: {symbol}')
        cur.execute("SELECT COUNT(*) AS invalid FROM qr_valuation_daily WHERE source <> 'eastmoney:RPT_VALUEANALYSIS_DET' OR adapter_version IS NULL")
        if cur.fetchone()['invalid']:
            raise ValueError('disallowed valuation source in candidate commit')
    manifest = service.releases.publish(base_commit=candidate['base_commit'], supplemental_commit=commit, datasets=datasets,
        source_adapters={'valuation': 'akshare-1.18.94', 'quality_policy': POLICY},
        metadata={'candidate_id': candidate['candidate_id'], 'economic_hash': identity, 'isolated': candidate['isolated'],
                  'publication_policy': PUBLICATION_POLICY,
                  'price_units': 'joinquant-shares-yuan-v2',
                  'shard_hashes': {s: candidate['shards'][s]['economic_hash'] for s in candidate['accepted']},
                  'validated_through': {s: candidate['shards'][s]['latest_date'] if candidate['shards'][s].get('calendar_status') == 'PASS' else None for s in candidate['accepted']},
                  'rules_not_checked': candidate['rules_not_checked'], 'quality': 'PASS', 'coverage': 'PARTIAL', 'pit': 'PARTIAL'})
    return {'status': 'PARTIAL' if candidate['isolated'] else 'UPDATED', 'release_id': manifest['release_id'], 'base_commit': manifest['base_commit'], 'supplemental_commit': commit}


def publish_base_only(service, base_commit, reason):
    """Base availability must not depend on missing/frozen supplemental records."""
    try:
        old = service.releases.current()
    except FileNotFoundError:
        old = None
    if old and old['base_commit'] == base_commit:
        return {'status': 'NO_CHANGE', 'release_id': old['release_id'], 'reason': reason}
    eligible = old and old.get('metadata', {}).get('quality') == 'PASS'
    manifest = service.releases.publish(base_commit=base_commit,
        supplemental_commit=old['supplemental_commit'] if eligible else None,
        datasets=old['datasets'] if eligible else {}, source_adapters=old['source_adapters'] if eligible else {},
        metadata={**(old.get('metadata', {}) if eligible else {}), 'supplemental_refresh': 'RETAINED' if eligible else 'UNAVAILABLE'})
    return {'status': 'PARTIAL', 'release_id': manifest['release_id'], 'reason': reason}

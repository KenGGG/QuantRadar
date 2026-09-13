"""Publish only validated shards on an isolated Dolt branch, then switch manifest."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path

from .dolt import SupplementalStore
from .market_cap import validate_market_cap_candidate
from .quality import POLICY, valuation_contracts

PUBLICATION_POLICY = 'canonical-valuation-base-lifecycle-units-v3'


def validate_trade_status_patch(rows: list[dict]) -> dict:
    """Validate a narrow status candidate before any Dolt branch is touched."""
    seen, errors = set(), []
    for row in rows:
        key = (row.get("trade_date"), row.get("symbol"))
        try:
            date.fromisoformat(str(key[0])[:10])
        except ValueError:
            errors.append("invalid trade_date")
        if not isinstance(key[1], str) or len(key[1]) != 9 or not key[1][:6].isdigit() or not key[1].endswith((".SH", ".SZ")):
            errors.append("invalid symbol")
        if key in seen:
            errors.append("duplicate key")
        seen.add(key)
        if row.get("tradestatus") not in (0, 1) or row.get("is_st") not in (0, 1):
            errors.append("invalid status")
        if len(str(row.get("raw_sha256") or "")) != 64 or not row.get("source") or not row.get("adapter_version") or row.get("source_contract_id") != "baostock-daily-v2":
            errors.append("missing provenance")
    return {"status": "PASS" if rows and not errors else "FAIL", "rows": len(rows), "errors": sorted(set(errors))}


def validate_price_patch(rows: list[dict]) -> dict:
    """Validate complete, raw-unit daily prices before any supplement write."""
    seen, errors = set(), []
    for row in rows:
        key = (str(row.get("trade_date"))[:10], row.get("symbol"))
        try:
            date.fromisoformat(key[0])
        except ValueError:
            errors.append("invalid trade_date")
        if not isinstance(key[1], str) or len(key[1]) != 9 or not key[1][:6].isdigit() or not key[1].endswith((".SH", ".SZ")):
            errors.append("invalid symbol")
        if key in seen:
            errors.append("duplicate key")
        seen.add(key)
        for field in ("open", "high", "low", "close", "volume", "amount"):
            try:
                value = float(row.get(field))
                if not math.isfinite(value) or value < 0:
                    raise ValueError
            except (TypeError, ValueError):
                errors.append("invalid " + field)
        try:
            if float(row["low"]) > min(float(row["open"]), float(row["close"])) or float(row["high"]) < max(float(row["open"]), float(row["close"])):
                errors.append("invalid ohlc bounds")
        except (TypeError, ValueError):
            pass
        if len(str(row.get("raw_sha256") or "")) != 64 or row.get("source") != "baostock" or not row.get("adapter_version") or row.get("source_contract_id") != "baostock-daily-v2" or row.get("unit_contract_version") != "baostock-shares-yuan":
            errors.append("missing provenance")
    return {"status": "PASS" if rows and not errors else "FAIL", "rows": len(rows), "errors": sorted(set(errors))}


def validate_trade_status_base_gap(rows: list[dict], base_keys: set[tuple[str, str]]) -> dict:
    """Reject a candidate that would replace a base status observation.

    Supplemental records are deliberately additive.  Runtime reads also favour
    the base table, but that is a safety net rather than publication approval:
    allowing an overlapping row into a release would make provenance and later
    audits ambiguous.
    """
    overlapping = sorted(
        (str(row["trade_date"])[:10], str(row["symbol"]))
        for row in rows
        if (str(row["trade_date"])[:10], str(row["symbol"])) in base_keys
    )
    return {
        "status": "PASS" if not overlapping else "FAIL",
        "base_overlap_count": len(overlapping),
        "base_overlaps": overlapping,
    }


def status_patch_delta(rows: list[dict], existing: dict[tuple[str, str], dict]) -> dict:
    """Split an idempotent retry from a conflicting rewrite attempt."""
    # A full-range source receipt and a one-day receipt legitimately have
    # different byte hashes for the same observation.  Keep the first raw
    # receipt immutable; only a change to the state or source contract is a
    # publication conflict.
    comparable = ("tradestatus", "is_st", "turn", "source", "adapter_version", "source_contract_id", "available_date", "pit_status")

    def value(row: dict, field: str):
        if field != "source_contract_id":
            return row.get(field)
        # Releases published before the explicit column still carry BaoStock
        # provenance.  Treat that immutable source label as its only approved
        # historical contract, so an idempotent retry remains retryable.
        return row.get(field) or ("baostock-daily-v2" if row.get("source") == "baostock" else None)

    new, conflicts = [], []
    for row in rows:
        key = (str(row["trade_date"])[:10], str(row["symbol"]))
        prior = existing.get(key)
        if prior is None:
            new.append(row)
        elif any(value(prior, field) != value(row, field) for field in comparable):
            conflicts.append(key)
    return {"new_rows": new, "conflicts": sorted(conflicts)}


def price_patch_delta(rows: list[dict], existing: dict[tuple[str, str], dict]) -> dict:
    comparable = ("open", "high", "low", "close", "volume", "amount", "preclose", "source", "adapter_version", "source_contract_id", "unit_contract_version", "available_date", "pit_status")
    new, conflicts = [], []
    for row in rows:
        key = (str(row["trade_date"])[:10], str(row["symbol"]))
        prior = existing.get(key)
        if prior is None:
            new.append(row)
        elif any(prior.get(field) != row.get(field) for field in comparable):
            conflicts.append(key)
    return {"new_rows": new, "conflicts": sorted(conflicts)}


def market_cap_patch_delta(rows: list[dict], existing: dict[tuple[str, str], dict]) -> dict:
    """Market-cap history is append-only within a supplemental lineage."""
    new, conflicts = [], []
    comparable = ('total_market_cap_cny', 'raw_sha256', 'qualification')
    for row in rows:
        key = (str(row['trade_date'])[:10], str(row['symbol']))
        prior = existing.get(key)
        if prior is None:
            new.append(row)
        elif any(prior.get(field) != row.get(field) for field in comparable):
            conflicts.append(key)
    return {'new_rows': new, 'conflicts': sorted(conflicts)}


def _market_cap_stage_rows(stage_path: Path):
    """Re-read a JSONL candidate; each record must pass the publication gate."""
    with stage_path.open(encoding='utf-8') as handle:
        for line_number, line in enumerate(handle, 1):
            row = json.loads(line)
            check = validate_market_cap_candidate([row])
            if check['status'] != 'PASS':
                raise ValueError(f'market-cap candidate row {line_number} failed: {check["errors"]}')
            yield row


def publish_market_cap_stage(service, stage_path: Path) -> dict:
    """Publish hash-verified staged total market cap on an isolated Dolt branch."""
    stage_path = Path(stage_path)
    digest = hashlib.sha256()
    rows = 0
    first = latest = None
    for row in _market_cap_stage_rows(stage_path):
        digest.update((json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode())
        rows += 1
        day = str(row['trade_date'])[:10]
        first = day if first is None or day < first else first
        latest = day if latest is None or day > latest else latest
    if not rows:
        raise ValueError('market-cap candidate is empty')
    old = service.releases.current()
    identity = digest.hexdigest()[:16]
    conn = service._connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT * FROM dolt_status')
            if cursor.fetchall():
                raise ValueError('supplemental repository has uncommitted changes')
            branch = 'candidate_market_cap_' + identity
            cursor.execute('SELECT name FROM dolt_branches WHERE name=%s', (branch,))
            if cursor.fetchone():
                cursor.execute('CALL DOLT_CHECKOUT(%s)', (branch,))
            else:
                cursor.execute('CALL DOLT_CHECKOUT(\'-b\', %s, %s)', (branch, old['supplemental_commit']))
        writer = SupplementalStore(conn)
        writer.ensure_schema()
        writer.upsert_market_caps(_market_cap_stage_rows(stage_path))
        commit = writer.commit('datahub: checked total market cap candidate ' + identity)
    finally:
        conn.close()
    with service._connection(service.config.supplemental_database + '/' + commit) as frozen, frozen.cursor() as cur:
        cur.execute('SELECT COUNT(*) AS row_count, COUNT(DISTINCT symbol) AS stocks, MIN(trade_date) AS first_date, MAX(trade_date) AS latest_date FROM qr_market_cap_daily')
        metrics = {k: str(v) if hasattr(v, 'isoformat') else v for k, v in cur.fetchone().items()}
        cur.execute('SELECT COUNT(*) AS invalid FROM qr_market_cap_daily WHERE total_market_cap_cny < 0 OR source <> %s OR qualification <> %s', ('eastmoney:RPT_VALUEANALYSIS_DET', 'CANDIDATE_NOT_PUBLISHED'))
        if cur.fetchone()['invalid']:
            raise ValueError('fixed-commit market-cap verification failed')
    datasets = {**old['datasets'], 'market_cap_daily': {**metrics, 'source': ['eastmoney:RPT_VALUEANALYSIS_DET'],
        'pit_status': 'PARTIAL', 'quality_status': 'PARTIAL', 'qualification': 'CANDIDATE_NOT_PUBLISHED',
        'field': 'total_market_cap_cny', 'forbidden_substitute': 'float_market_cap', 'refresh_status': 'PUBLISHED'}}
    manifest = service.releases.publish(base_commit=old['base_commit'], supplemental_commit=commit, datasets=datasets,
        source_adapters={**old['source_adapters'], 'market_cap_daily': 'eastmoney-archive-v1'},
        metadata={**old.get('metadata', {}), 'market_cap_candidate': {'rows': rows, 'stage_sha256': digest.hexdigest(),
            'selection': 'archived_total_market_cap_only', 'qualification': 'CANDIDATE_NOT_PUBLISHED'}})
    return {'status': 'PARTIAL', 'release_id': manifest['release_id'], 'supplemental_commit': commit,
            'rows': rows, 'validation': {'status': 'PASS', 'stage_sha256': digest.hexdigest(), 'first_date': first, 'latest_date': latest}}


def publish_trade_status_patch(service, rows: list[dict]) -> dict:
    """Publish a validated, additive status patch on an isolated Dolt branch."""
    check = validate_trade_status_patch(rows)
    if check["status"] != "PASS":
        raise ValueError("trade status candidate failed: " + ", ".join(check["errors"]))
    old = service.releases.current()
    base_gap = validate_trade_status_base_gap(
        rows, service.base_trade_status_keys(rows, base_commit=old["base_commit"])
    )
    if base_gap["status"] != "PASS":
        raise ValueError(
            "trade status candidate overlaps immutable base observations: "
            + ", ".join(f"{day}/{symbol}" for day, symbol in base_gap["base_overlaps"])
        )
    prior = service.supplemental_trade_status_rows(rows, supplemental_commit=old.get("supplemental_commit"))
    delta = status_patch_delta(rows, prior)
    if delta["conflicts"]:
        raise ValueError(
            "trade status candidate conflicts with published supplemental observations: "
            + ", ".join(f"{day}/{symbol}" for day, symbol in delta["conflicts"])
        )
    if not delta["new_rows"]:
        return {"status": "NO_CHANGE", "release_id": old["release_id"], "rows": 0, "validation": {**check, "base_gap": base_gap}}
    rows = delta["new_rows"]
    conn = service._connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM dolt_status")
            if cursor.fetchall():
                raise ValueError("supplemental repository has uncommitted changes")
            identity = hashlib.sha256(json.dumps(sorted((r["trade_date"], r["symbol"], r["raw_sha256"]) for r in rows)).encode()).hexdigest()[:16]
            branch = "candidate_status_" + identity
            cursor.execute("SELECT name FROM dolt_branches WHERE name=%s", (branch,))
            if cursor.fetchone():
                cursor.execute("CALL DOLT_CHECKOUT(%s)", (branch,))
            else:
                cursor.execute("CALL DOLT_CHECKOUT('-b', %s, %s)", (branch, old["supplemental_commit"]))
        writer = SupplementalStore(conn)
        writer.ensure_schema()
        writer.upsert_trade_status(rows)
        commit = writer.commit("datahub: checked trade status patch " + identity)
    finally:
        conn.close()
    with service._connection(service.config.supplemental_database + "/" + commit) as frozen, frozen.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS row_count, COUNT(DISTINCT symbol) AS stocks, MIN(trade_date) AS first_date, MAX(trade_date) AS latest_date FROM qr_trade_status_daily")
        metrics = {k: str(v) if hasattr(v, "isoformat") else v for k, v in cur.fetchone().items()}
        cur.execute("SELECT COUNT(*) AS invalid FROM qr_trade_status_daily WHERE tradestatus NOT IN (0,1) OR is_st NOT IN (0,1)")
        if cur.fetchone()["invalid"]:
            raise ValueError("fixed-commit status verification failed")
    datasets = {**old["datasets"], "trade_status_daily": {**metrics, "source": ["baostock"], "pit_status": "PARTIAL", "quality_status": "PARTIAL", "refresh_status": "UPDATED", "published_through": metrics["latest_date"]}}
    manifest = service.releases.publish(base_commit=old["base_commit"], supplemental_commit=commit, datasets=datasets,
        source_adapters={**old["source_adapters"], "trade_status": "baostock-daily-v2"},
        metadata={**old.get("metadata", {}), "trade_status_patch": {"rows": len(rows), "candidate": identity, "selection": "fill_base_missing_only"}})
    return {"status": "PARTIAL", "release_id": manifest["release_id"], "supplemental_commit": commit, "rows": len(rows), "validation": {**check, "base_gap": base_gap}}


def publish_price_patch(service, rows: list[dict]) -> dict:
    """Publish an additive raw-price patch; adjusted price remains unavailable."""
    check = validate_price_patch(rows)
    if check["status"] != "PASS":
        raise ValueError("price candidate failed: " + ", ".join(check["errors"]))
    old = service.releases.current()
    base_gap = validate_trade_status_base_gap(rows, service.base_price_keys(rows, base_commit=old["base_commit"]))
    if base_gap["status"] != "PASS":
        raise ValueError("price candidate overlaps immutable base observations: " + ", ".join(f"{day}/{symbol}" for day, symbol in base_gap["base_overlaps"]))
    prior = service.supplemental_price_rows(rows, supplemental_commit=old.get("supplemental_commit"))
    delta = price_patch_delta(rows, prior)
    if delta["conflicts"]:
        raise ValueError("price candidate conflicts with published supplemental observations: " + ", ".join(f"{day}/{symbol}" for day, symbol in delta["conflicts"]))
    if not delta["new_rows"]:
        return {"status": "NO_CHANGE", "release_id": old["release_id"], "rows": 0, "validation": {**check, "base_gap": base_gap}}
    rows = delta["new_rows"]
    conn = service._connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM dolt_status")
            if cursor.fetchall():
                raise ValueError("supplemental repository has uncommitted changes")
            identity = hashlib.sha256(json.dumps(sorted((r["trade_date"], r["symbol"], r["raw_sha256"]) for r in rows)).encode()).hexdigest()[:16]
            branch = "candidate_price_" + identity
            cursor.execute("SELECT name FROM dolt_branches WHERE name=%s", (branch,))
            if cursor.fetchone(): cursor.execute("CALL DOLT_CHECKOUT(%s)", (branch,))
            else: cursor.execute("CALL DOLT_CHECKOUT('-b', %s, %s)", (branch, old["supplemental_commit"]))
        writer = SupplementalStore(conn)
        writer.ensure_schema()
        writer.upsert_prices(rows)
        commit = writer.commit("datahub: checked raw price patch " + identity)
    finally:
        conn.close()
    with service._connection(service.config.supplemental_database + "/" + commit) as frozen, frozen.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS row_count, COUNT(DISTINCT symbol) AS stocks, MIN(trade_date) AS first_date, MAX(trade_date) AS latest_date FROM qr_a_stock_eod_price")
        metrics = {k: str(v) if hasattr(v, "isoformat") else v for k, v in cur.fetchone().items()}
        cur.execute("SELECT COUNT(*) AS invalid FROM qr_a_stock_eod_price WHERE open < 0 OR high < 0 OR low < 0 OR close < 0 OR volume < 0 OR amount < 0 OR low > LEAST(open, close) OR high < GREATEST(open, close)")
        if cur.fetchone()["invalid"]:
            raise ValueError("fixed-commit price verification failed")
    datasets = {**old["datasets"], "a_stock_eod_price": {**metrics, "source": ["baostock"], "pit_status": "PARTIAL", "quality_status": "PARTIAL", "refresh_status": "UPDATED", "published_through": metrics["latest_date"], "adjustment_factor": "UNAVAILABLE"}}
    manifest = service.releases.publish(base_commit=old["base_commit"], supplemental_commit=commit, datasets=datasets,
        source_adapters={**old["source_adapters"], "a_stock_eod_price": "baostock-daily-v2"},
        metadata={**old.get("metadata", {}), "price_patch": {"rows": len(rows), "candidate": identity, "selection": "fill_base_missing_only", "adjustment_factor": "UNAVAILABLE"}})
    return {"status": "PARTIAL", "release_id": manifest["release_id"], "supplemental_commit": commit, "rows": len(rows), "validation": {**check, "base_gap": base_gap}}


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
        allowed_sources = {'eastmoney:RPT_VALUEANALYSIS_DET', 'baostock'}
        cur.execute("SELECT COUNT(*) AS invalid FROM qr_valuation_daily WHERE source NOT IN (%s, %s) OR adapter_version IS NULL", tuple(sorted(allowed_sources)))
        if cur.fetchone()['invalid']:
            raise ValueError('disallowed valuation source in candidate commit')
        contracts = {contract for summary in candidate['shards'].values() for contract in summary.get('source_contract_ids', [])}
        if not contracts <= set(valuation_contracts()):
            raise ValueError('candidate references an unapproved valuation contract')
    manifest = service.releases.publish(base_commit=candidate['base_commit'], supplemental_commit=commit, datasets=datasets,
        source_adapters={'valuation': sorted({contract for summary in candidate['shards'].values() for contract in summary.get('source_contract_ids', [])}), 'quality_policy': POLICY},
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

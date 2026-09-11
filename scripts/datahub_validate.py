"""Explicit offline candidate check; saves evidence, never publishes."""
import json
from pathlib import Path
from quantradar.config import load_datahub_config
from quantradar.datahub.service import DataHubService
from quantradar.datahub.quality import validate_candidate
from quantradar.datahub.store import RawStore, _atomic_json

config = load_datahub_config()
service = DataHubService(config)
journal = json.loads((Path(config.journal_root) / 'valuation_daily-mvp.json').read_text())
base = service._base_commit()
report = validate_candidate(Path(config.supplemental_repo) / 'staging' / 'valuation_daily-mvp', journal['units'], base_commit=base, raw_store=RawStore(config.raw_root))
destination = Path('docs/acceptance/datahub-remediation-2026-09-11/candidate-report.json')
_atomic_json(destination, report)
print(json.dumps({k: v for k, v in report.items() if k not in ('shards', 'accepted', 'isolated')}, ensure_ascii=False))
print('accepted', len(report['accepted']), 'isolated', len(report['isolated']))

"""Workflow regressions; browser acceptance separately uses real PostgreSQL/Dolt."""
import hashlib
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_web_report_data_preserves_native_values_and_csv(tmp_path, monkeypatch):
    import importlib
    api = importlib.import_module("quantradar.api.app")
    monkeypatch.setattr(api, "_run_dir_of", lambda _: str(tmp_path))
    for name in ("report.html", "standard_report.html"):
        (tmp_path / name).write_text("<html>native</html>")
    (tmp_path / "metrics.json").write_text(json.dumps({"metrics": {"策略收益": 1.72, "盈亏比": float("inf")}, "meta": {"benchmark": "000300.XSHG"}}))
    (tmp_path / "daily_records.csv").write_text('date,returns_pct\n2023-01-03,-0.07679999999999909\n', encoding="utf-8-sig")
    (tmp_path / "trades.csv").write_text('时间,标的,备注\n2023-01-03,600519.XSHG,"带逗号,的文本"\n', encoding="utf-8-sig")
    client = TestClient(api.app)
    response = client.get("/api/backtest/runs/native/report-data")
    assert response.status_code == 200
    data = response.json()
    assert data["metrics"] == {"策略收益": 1.72, "盈亏比": "Infinity"}
    assert data["daily"]["rows"][0]["returns_pct"] == "-0.07679999999999909"
    assert data["trades"]["rows"][0]["备注"] == "带逗号,的文本"
    assert data["positions"]["available"] is False
    (tmp_path / "report.html").unlink()
    assert client.get("/api/backtest/runs/native/report-data").status_code == 409


def test_save_reopen_strategy_versions(monkeypatch):
    from quantradar import storage
    from quantradar.api.app import app
    engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
    storage.Base.metadata.create_all(engine)
    monkeypatch.setattr(storage, 'get_session', sessionmaker(bind=engine))
    client = TestClient(app)
    first = client.post('/api/strategies', json={'name': '买入持有', 'source': 'first'})
    assert first.status_code == 200
    second = client.post('/api/strategies', json={'name': '买入持有', 'source': 'second'}).json()
    original = client.get(f"/api/strategies/{first.json()['id']}").json()
    assert original['source'] == 'first'
    assert original['strategy_hash'] == hashlib.sha256(b'first').hexdigest()
    assert second['id'] != original['id']
    assert len(client.get('/api/strategies').json()['strategies']) == 2
    assert client.post('/api/strategies', json={'name': '', 'source': ''}).status_code == 400


def test_recovery_uses_immutable_run_source(monkeypatch):
    from quantradar.worker import _payload_from_record
    monkeypatch.setattr('quantradar.worker.get_strategy', lambda _: None)
    result = _payload_from_record({'strategy_id': 1, 'config': {'has_code': True, 'strategy_source': 'original source'}})
    assert result['code'] == 'original source'


def test_native_report_initial_cash_and_units():
    import pandas as pd
    from bullet_trade.reporting import _build_summary_rows, _format_metric_value
    rows = _build_summary_rows(pd.DataFrame({'total_value': [499616, 508615]}),
                               {'initial_total_value': 500000, 'start_date': '2023-01-03', 'end_date': '2023-03-31'}, {})
    assert next(r['value'] for r in rows if r['label'] == '初始资金') == '500,000.00'
    assert _format_metric_value('最大回撤持续天数', 49) == '49'
    assert _format_metric_value('收益回撤比', 2.12) == '2.12'


def test_report_gate_rejects_missing_files(tmp_path):
    import pytest
    from quantradar.backtest_run import require_report_artifacts
    with pytest.raises(ValueError, match='report.html'):
        require_report_artifacts(str(tmp_path))


def test_engine_price_mode_survives_strategy_reset():
    import pytest
    from bullet_trade.core.engine import BacktestEngine
    from bullet_trade.core.settings import get_settings
    class Inspected(Exception):
        pass
    def initialize(context):
        assert get_settings().options["use_real_price"] is True
        raise Inspected()
    engine = BacktestEngine(initialize=initialize, start_date="2023-01-03", end_date="2023-01-04", use_real_price=True)
    with pytest.raises(Inspected):
        engine.run()


def test_invalid_page_parameters_are_rejected():
    from quantradar.api.app import app
    client = TestClient(app)
    base = {'start_date': '2023-01-03', 'end_date': '2023-03-31'}
    for override in ({'frequency': 'minute'}, {'fq': 'post'}, {'initial_cash': -1}, {'code': ''}, {'end_date': '2022-01-01'}, {'amount': 0.5}):
        assert client.post('/api/backtest/async', json={**base, **override}).status_code == 400


def test_infinite_native_metrics_remain_json_serializable():
    import json
    import numpy as np
    from quantradar.snapshot import _to_native
    metrics = _to_native({'盈亏比': float('inf'), 'negative': np.float64('-inf'), 'missing': float('nan')})
    assert metrics == {'盈亏比': 'Infinity', 'negative': '-Infinity', 'missing': None}
    json.dumps(metrics, allow_nan=False)


def test_missing_benchmark_cannot_produce_success_report(tmp_path, monkeypatch):
    import pandas as pd
    import pytest
    from quantradar.backtest_run import run_unified_backtest
    monkeypatch.setattr('quantradar.bootstrap.bootstrap_investment_data', lambda **kw: None)
    monkeypatch.setattr('bullet_trade.core.engine.create_backtest', lambda **kw: {
        'daily_records': pd.DataFrame({'total_value': [500000]}),
        'meta': {'benchmark': '000001.XSHG'},
    })
    # If this reaches report generation, missing benchmark was silently accepted.
    monkeypatch.setattr('bullet_trade.core.analysis.generate_report', lambda *a, **kw: pytest.fail('missing benchmark accepted'))
    with pytest.raises(ValueError, match='基准.*缺少'):
        run_unified_backtest('missing_benchmark', {'benchmark': '000001.XSHG'}, runs_dir=str(tmp_path))

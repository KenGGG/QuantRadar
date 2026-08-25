from datetime import date

from fastapi.testclient import TestClient


def test_research_dates_returns_collected_dates(monkeypatch, tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    store.upsert_report({"source":"qyj", "source_report_id":"A" * 32, "title":"标题", "publish_date":date(2026,8,24), "content_type":"pdf", "source_payload":{}})
    from quantradar.api import app as api_module
    monkeypatch.setattr(api_module, "_research_store", lambda: store)

    response = TestClient(api_module.app).get("/api/research/dates")

    assert response.status_code == 200
    assert response.json() == {"dates": ["2026-08-24"]}


def test_research_reports_returns_channel_reports_in_platform_order(monkeypatch, tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    first = store.upsert_report({"source":"qyj", "source_report_id":"A" * 32, "title":"策略报告", "institution":"机构甲", "publish_date":date(2026,8,24), "content_type":"pdf", "source_payload":{}})
    second = store.upsert_report({"source":"qyj", "source_report_id":"B" * 32, "title":"非 PDF 报告", "institution":"机构乙", "publish_date":date(2026,8,24), "content_type":"web", "source_payload":{}})
    store.record_snapshot(second.id, date(2026,8,24), "STRATEGY", 2, "b" * 64)
    store.record_snapshot(first.id, date(2026,8,24), "STRATEGY", 1, "a" * 64)
    from quantradar.api import app as api_module
    monkeypatch.setattr(api_module, "_research_store", lambda: store)

    response = TestClient(api_module.app).get("/api/research/reports?date=2026-08-24&channel=STRATEGY")

    assert response.status_code == 200
    assert response.json() == {"reports": [
        {"id": first.id, "title": "策略报告", "institution": "机构甲", "publish_date": "2026-08-24", "content_type": "pdf", "channel": "STRATEGY", "platform_order": 1, "status": "PENDING"},
        {"id": second.id, "title": "非 PDF 报告", "institution": "机构乙", "publish_date": "2026-08-24", "content_type": "web", "channel": "STRATEGY", "platform_order": 2, "status": "UNSUPPORTED"},
    ]}


def test_research_status_returns_channel_counts(monkeypatch, tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source":"qyj", "source_report_id":"C" * 32, "title":"标题", "publish_date":date(2026,8,24), "content_type":"pdf", "source_payload":{}})
    store.record_snapshot(report.id, date(2026,8,24), "HOT", 1, "c" * 64)
    from quantradar.api import app as api_module
    monkeypatch.setattr(api_module, "_research_store", lambda: store)

    response = TestClient(api_module.app).get("/api/research/status?date=2026-08-24")

    assert response.status_code == 200
    assert response.json() == {"date": "2026-08-24", "channels": {"HOT": 1, "STRATEGY": 0, "FINANCIAL_ENGINEERING": 0}}

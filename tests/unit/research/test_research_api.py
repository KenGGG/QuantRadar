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

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
        {"id": first.id, "title": "策略报告", "institution": "机构甲", "publish_date": "2026-08-24", "content_type": "pdf", "channel": "STRATEGY", "platform_order": 1, "status": "PENDING", "pdf_status": "PENDING", "mineru_status": "PENDING", "agnes_status": "PENDING", "research_value": None, "reproducibility": None},
        {"id": second.id, "title": "非 PDF 报告", "institution": "机构乙", "publish_date": "2026-08-24", "content_type": "web", "channel": "STRATEGY", "platform_order": 2, "status": "UNSUPPORTED", "pdf_status": "PENDING", "mineru_status": "PENDING", "agnes_status": "PENDING", "research_value": None, "reproducibility": None},
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


def test_research_visibility_endpoints_are_read_only_and_traceable(monkeypatch, tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.models import ResearchArtifact, ResearchDailyDigest, ResearchOutbox
    from quantradar.research.storage import ResearchStore

    runtime = tmp_path / "data"; runtime.mkdir()
    pdf = runtime / "report.pdf"; pdf.write_bytes(b"%PDF-1.4 test")
    markdown = runtime / "report.md"; markdown.write_text("# Test report\n\nChunk evidence", encoding="utf-8")
    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", runtime, tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({
        "source": "qyj", "source_report_id": "D" * 32, "title": "真实报告", "institution": "机构甲",
        "authors": ["作者甲"], "publish_date": date(2026, 8, 24), "category": "策略",
        "industry": "金融", "security": ["000001.XSHE"], "content_type": "pdf", "source_payload": {},
    })
    store.record_snapshot(report.id, date(2026, 8, 24), "HOT", 1, "d" * 64)
    with store._session() as session:
        session.add(ResearchArtifact(
            report_id=report.id, pdf_path=str(pdf), pdf_sha256="p" * 64, pdf_pages=3, platform_pages=3,
            page_count_match=True, markdown_path=str(markdown), markdown_sha256="m" * 64,
            parser="mineru", parser_version="1.0", parse_quality={"score": "HIGH"},
        ))
        session.add(ResearchDailyDigest(
            target_date=date(2026, 8, 24), content_md="# Digest", content_json={}, digest_hash="g" * 64,
            completeness="COMPLETE",
        ))
        session.add(ResearchOutbox(
            notification_key="daily:2026-08-24", target_date=date(2026, 8, 24), digest_hash="g" * 64,
            status="SENT", attempt=1, payload_hash="o" * 64,
        ))
        session.commit()
    store.save_analysis(report.id, "m" * 64, "profile-v1", "agnes", {
        "summary": "结构化摘要", "research_type": "STRATEGY", "core_method": "回归",
        "key_variables": ["x"], "main_conclusion": "结论", "applicable_market": "A股",
        "possible_quantradar_use": "因子", "risks_and_limitations": "样本有限",
        "research_value": "HIGH", "reproducibility": "MEDIUM",
    })
    from quantradar.research.llm.chunking import SourceChunk
    store.save_analysis_chunks(report.id, "m" * 64, [SourceChunk("chunk-1", 0, 0, 31, "c" * 64, "Chunk evidence")])
    stage = store.begin_stage(report.id, "ANALYZE", "i" * 64)
    store.finish_stage(stage.id, "SUCCESS", output_hash="o" * 64)
    from quantradar.api import app as api_module
    monkeypatch.setattr(api_module, "_research_store", lambda: store)
    client = TestClient(api_module.app)

    overview = client.get("/api/research/overview?date=2026-08-24")
    detail = client.get(f"/api/research/reports/{report.id}")
    pdf_response = client.get(f"/api/research/reports/{report.id}/pdf")
    markdown_response = client.get(f"/api/research/reports/{report.id}/markdown")
    digest = client.get("/api/research/digests/2026-08-24")
    operations = client.get("/api/research/operations?date=2026-08-24")
    observation = client.get("/api/research/observation")

    assert overview.status_code == 200
    assert overview.json()["metadata_count"] == 1
    assert overview.json()["channels"]["HOT"]["count"] == 1
    assert detail.status_code == 200
    assert detail.json()["analysis"]["summary"] == "结构化摘要"
    assert detail.json()["evidence"][0]["chunk_id"] == "chunk-1"
    assert "pdf_path" not in detail.text and str(runtime) not in detail.text
    assert pdf_response.status_code == 200 and pdf_response.content.startswith(b"%PDF")
    assert markdown_response.status_code == 200 and "Chunk evidence" in markdown_response.text
    assert digest.json()["outbox"]["status"] == "SENT"
    assert operations.json()["runs"][0]["status"] == "SUCCESS"
    assert observation.json() == {"engineering_pass": True, "live_pass": False, "real_operating_days": 0, "required_operating_days": 7}


def test_research_artifact_endpoint_rejects_unregistered_path(monkeypatch, tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.models import ResearchArtifact
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source":"qyj", "source_report_id":"E" * 32, "title":"标题", "publish_date":date(2026,8,24), "content_type":"pdf", "source_payload":{}})
    with store._session() as session:
        session.add(ResearchArtifact(report_id=report.id, pdf_path="/etc/passwd"))
        session.commit()
    from quantradar.api import app as api_module
    monkeypatch.setattr(api_module, "_research_store", lambda: store)

    response = TestClient(api_module.app).get(f"/api/research/reports/{report.id}/pdf")

    assert response.status_code == 404

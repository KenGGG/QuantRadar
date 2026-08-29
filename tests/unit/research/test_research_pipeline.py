from datetime import date


def _setup_report(store, tmp_path, source_id: str):
    report = store.upsert_report({"source": "qyj", "source_report_id": source_id, "title": source_id, "publish_date": date(2026, 8, 24), "content_type": "pdf", "source_payload": {}})
    store.record_snapshot(report.id, date(2026, 8, 24), "HOT", report.id, source_id)
    return report


def test_research_pipeline_rerun_skips_successful_prepare_and_analyze_stages(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.pipeline import run_pipeline
    from quantradar.research.storage import ResearchStore
    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema(); report = _setup_report(store, tmp_path, "A" * 32); calls = {"collect": 0, "prepare": 0, "analyze": 0}
    class Collector:
        def __init__(self, *_args): pass
        def collect(self, _date): calls["collect"] += 1; return {}
    def prepare(_store, _settings, item):
        calls["prepare"] += 1; path = tmp_path / f"{item.id}.md"; path.write_text("正文", encoding="utf-8"); return _store.save_markdown_artifact(item.id, path, "a" * 64, parser="mineru", parser_version="3.4.4", parse_quality={"status": "PARSE_OK"})
    def analyze(_store, _id, _markdown, *_args): calls["analyze"] += 1
    first = run_pipeline(settings, date(2026, 8, 24), store=store, collector_cls=Collector, prepare_fn=prepare, analyze_fn=analyze)
    second = run_pipeline(settings, date(2026, 8, 24), store=store, collector_cls=Collector, prepare_fn=prepare, analyze_fn=analyze)
    assert first.prepared == first.analyzed == 1 and second.prepared == second.analyzed == 0
    assert calls == {"collect": 2, "prepare": 1, "analyze": 1} and report.id > 0


def test_research_pipeline_continues_after_one_report_prepare_failure(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.pipeline import run_pipeline
    from quantradar.research.storage import ResearchStore
    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema(); first = _setup_report(store, tmp_path, "A" * 32); second = _setup_report(store, tmp_path, "B" * 32); analyzed = []
    class Collector:
        def __init__(self, *_args): pass
        def collect(self, _date): return {}
    def prepare(_store, _settings, item):
        if item.id == first.id: raise RuntimeError("MinerU temporary error")
        path = tmp_path / f"{item.id}.md"; path.write_text("正文", encoding="utf-8"); return _store.save_markdown_artifact(item.id, path, "b" * 64, parser="mineru", parser_version="3.4.4", parse_quality={"status": "PARSE_OK"})
    def analyze(_store, report_id, _markdown, *_args): analyzed.append(report_id)
    result = run_pipeline(settings, date(2026, 8, 24), store=store, collector_cls=Collector, prepare_fn=prepare, analyze_fn=analyze)
    assert result.prepare_failed == 1 and result.analyzed == 1 and analyzed == [second.id]

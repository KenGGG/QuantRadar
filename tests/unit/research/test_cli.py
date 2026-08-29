from datetime import date


def test_health_reports_shared_mineru_version(tmp_path, capsys) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.cli import run

    class FakeMineru:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def health(self) -> dict:
            return {"version": "3.4.4"}

    settings = ResearchSettings("sqlite+pysqlite://", tmp_path / "data", tmp_path / "profile")

    assert run(["health"], settings=settings, mineru_cls=FakeMineru) == 0
    assert '"mineru"' in capsys.readouterr().out


def test_collect_creates_schema_and_collects_requested_date(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.cli import run

    calls: list[date] = []

    class FakeCollector:
        def __init__(self, settings, store) -> None:
            assert settings.data_dir.exists()
            store.create_schema()

        def collect(self, target_date: date) -> dict:
            calls.append(target_date)
            return {"HOT": [1, 2], "STRATEGY": [1], "FINANCIAL_ENGINEERING": []}

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")

    assert run(["collect", "--date", "2026-08-24"], settings=settings, collector_cls=FakeCollector) == 0
    assert calls == [date(2026, 8, 24)]


def test_analyze_requires_a_date_and_returns_structured_empty_result(tmp_path, capsys) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.cli import run

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")

    assert run(["analyze", "--date", "2026-08-24"], settings=settings) == 0
    assert '"analyzed": 0' in capsys.readouterr().out


def test_analyze_continues_after_one_report_fails(tmp_path, capsys) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.cli import run
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    for source_id in ("A" * 32, "B" * 32):
        report = store.upsert_report({"source": "qyj", "source_report_id": source_id, "title": source_id, "publish_date": date(2026, 8, 24), "content_type": "pdf", "source_payload": {}})
        path = tmp_path / f"{report.id}.md"; path.write_text("正文", encoding="utf-8")
        store.save_markdown_artifact(report.id, path, source_id.lower() * 2, parser="mineru", parser_version="3.4.4", parse_quality={"status": "PARSE_OK"})
    calls: list[int] = []

    def analyze(_store, report_id, _markdown, *_args):
        calls.append(report_id)
        if len(calls) == 1:
            raise RuntimeError("temporary Agnes error")

    assert run(["analyze", "--date", "2026-08-24", "--limit", "2"], settings=settings, analyze_fn=analyze) == 0
    assert len(calls) == 2
    output = capsys.readouterr().out
    assert '"analyzed": 1' in output
    assert '"failed": 1' in output


def test_prepare_processes_collected_pdf_reports_for_date(tmp_path, capsys) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.cli import run
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "A" * 32, "title": "标题", "publish_date": date(2026, 8, 24), "content_type": "pdf", "source_payload": {}})
    store.record_snapshot(report.id, date(2026, 8, 24), "HOT", 1, "hash")
    prepared: list[int] = []

    def prepare(_store, _settings, item) -> None:
        prepared.append(item.id)

    assert run(["prepare", "--date", "2026-08-24", "--limit", "1"], settings=settings, prepare_fn=prepare) == 0
    assert prepared == [report.id]
    assert '"prepared": 1' in capsys.readouterr().out


def test_prepare_continues_after_one_report_fails(tmp_path, capsys) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.cli import run
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    for source_id in ("A" * 32, "B" * 32):
        report = store.upsert_report({"source": "qyj", "source_report_id": source_id, "title": source_id, "publish_date": date(2026, 8, 24), "content_type": "pdf", "source_payload": {}})
        store.record_snapshot(report.id, date(2026, 8, 24), "HOT", report.id, source_id)
    calls: list[int] = []

    def prepare(_store, _settings, item) -> None:
        calls.append(item.id)
        if len(calls) == 1:
            raise RuntimeError("temporary MinerU error")

    assert run(["prepare", "--date", "2026-08-24", "--limit", "2"], settings=settings, prepare_fn=prepare) == 0
    assert len(calls) == 2
    output = capsys.readouterr().out
    assert '"prepared": 1' in output
    assert '"failed": 1' in output


def test_pipeline_invokes_the_resumable_runner(tmp_path, capsys) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.cli import run

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile")
    calls = []

    def pipeline(runtime, target_date, *, limit):
        calls.append((runtime, target_date, limit))
        return type("Result", (), {"target_date": target_date.isoformat(), "collected": 3, "prepared": 2, "prepare_failed": 0, "analyzed": 2, "analyze_failed": 0})()

    assert run(["pipeline", "--date", "2026-08-24", "--limit", "7"], settings=settings, pipeline_fn=pipeline) == 0
    assert calls[0][1:] == (date(2026, 8, 24), 7)
    assert '"analyzed": 2' in capsys.readouterr().out


def test_deliver_invokes_the_idempotent_delivery_runner(tmp_path, capsys) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.cli import run

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'research.db'}", tmp_path / "data", tmp_path / "profile", feishu_webhook_url="https://feishu.example/webhook")
    calls = []

    def deliver(store, runtime, target_date):
        calls.append((store, runtime, target_date))
        return type("Result", (), {"digest_hash": "abc", "sent": True, "outbox_status": "SENT"})()

    assert run(["deliver", "--date", "2026-08-24"], settings=settings, delivery_fn=deliver) == 0
    assert calls[0][2] == date(2026, 8, 24)
    assert '"sent": true' in capsys.readouterr().out

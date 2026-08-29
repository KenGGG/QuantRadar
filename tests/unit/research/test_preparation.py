from datetime import date


def test_prepare_report_publishes_mineru_markdown(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "A" * 32, "title": "报告", "publish_date": date(2026, 8, 24), "content_type": "pdf", "source_payload": {"attach": [{"fileUrl": "https://example.test/a.pdf"}]}})

    class Downloader:
        def download(self, *_args):
            path = tmp_path / "input.pdf"; path.write_bytes(b"%PDF-1.4")
            return type("Result", (), {"status": "SUCCESS", "path": path})()

    class Mineru:
        def parse_pdf(self, _path):
            return "# 已解析\n这是一段足够长的真实风格解析正文，用于通过最低质量阈值。", "3.4.4"

    artifact = prepare_report(store, settings, report, downloader=Downloader(), mineru=Mineru())

    assert artifact.markdown_path.endswith(".md")
    assert artifact.parser == "mineru"
    assert artifact.parser_version == "3.4.4"
    assert artifact.parse_quality["status"] == "PARSE_OK"


def test_prepare_report_reuses_an_existing_markdown_artifact(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "B" * 32, "title": "报告", "publish_date": date(2026, 8, 24), "content_type": "pdf", "source_payload": {"attach": [{"fileUrl": "https://example.test/b.pdf"}]}})

    class Downloader:
        calls = 0
        def download(self, *_args):
            self.calls += 1
            path = tmp_path / "input.pdf"; path.write_bytes(b"%PDF-1.4")
            return type("Result", (), {"status": "SUCCESS", "path": path})()

    class Mineru:
        calls = 0
        def parse_pdf(self, _path):
            self.calls += 1
            return "# 已解析\n这是一段足够长的解析正文，用于通过最低质量阈值。", "3.4.4"

    downloader, mineru = Downloader(), Mineru()
    first = prepare_report(store, settings, report, downloader=downloader, mineru=mineru)
    second = prepare_report(store, settings, report, downloader=downloader, mineru=mineru)

    assert second.report_id == first.report_id
    assert downloader.calls == mineru.calls == 1

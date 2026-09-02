from datetime import date
from pathlib import Path


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


def test_prepare_report_converts_embedded_html_to_canonical_markdown(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "C" * 32, "title": "HTML 报告", "publish_date": date(2026, 8, 24), "content_type": "html", "source_payload": {"abstract": "<article><h1>HTML 报告</h1><p>这是一段足够长的嵌入正文，用于验证可审计的 Canonical Markdown。</p></article>"}})
    store.record_snapshot(report.id, date(2026, 8, 24), "HOT", 1, "snapshot")

    artifact = prepare_report(store, settings, report)
    markdown = (tmp_path / "data" / "source_md" / str(report.id) / f"{artifact.markdown_sha256}.md").read_text(encoding="utf-8")

    assert artifact.parser == "qyj-html"
    assert "source_kind: html" in markdown
    assert "HTML 报告" in markdown
    assert "嵌入正文" in markdown


def test_prepare_report_reuses_canonical_html_when_source_is_unchanged(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "D" * 32, "title": "HTML", "publish_date": date(2026, 8, 24), "content_type": "html", "source_payload": {"abstract": "<p>一段足够长的稳定正文，用于验证同源内容不会重复处理。</p>"}})
    first = prepare_report(store, settings, report)
    second = prepare_report(store, settings, report)

    assert second.markdown_sha256 == first.markdown_sha256


def test_prepare_report_rebuilds_html_when_embedded_source_changes(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "E" * 32, "title": "HTML", "publish_date": date(2026, 8, 24), "content_type": "html", "source_payload": {"abstract": "<p>第一版正文足够长，用于验证变更后需要生成新的 Canonical Markdown。</p>"}})
    first = prepare_report(store, settings, report)
    report = store.upsert_report({**report.source_payload, "source": "qyj", "source_report_id": report.source_report_id, "title": report.title, "publish_date": report.publish_date, "content_type": "html", "source_payload": {"abstract": "<p>第二版正文已经变更，必须产生不同的 Canonical Markdown 哈希。</p>"}})

    second = prepare_report(store, settings, report)

    assert second.markdown_sha256 != first.markdown_sha256


def test_prepare_report_uses_url_markdown_for_weixin_source(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore
    from quantradar.research.url_markdown import UrlMarkdownResult

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "F" * 32, "title": "微信报告", "publish_date": date(2026, 8, 24), "content_type": "html", "source_payload": {"articleUrl": "https://mp.weixin.qq.com/s/example"}})

    class Adapter:
        def extract(self, url):
            assert url == "https://mp.weixin.qq.com/s/example"
            return UrlMarkdownResult("# 微信标题\n\n一段足够长的微信正文，用于验证统一正文提取和审计。", "url-md-weixin", "0.3")

    artifact = prepare_report(store, settings, report, url_markdown=Adapter())
    text = Path(artifact.markdown_path).read_text(encoding="utf-8")

    assert artifact.parser == "url-md-weixin"
    assert "source_kind: weixin" in text


def test_prepare_report_uses_authenticated_qyj_page_for_weixin_icon(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "W" * 32, "title": "企业预警通微信报告", "publish_date": date(2026, 8, 24), "content_type": "non_pdf", "source_payload": {"icon": "wx", "pcContentLink": "/information/researchReport?id=example"}})

    class Adapter:
        def extract(self, url):
            assert url == "https://www.qyyjt.cn/information/researchReport?id=example"
            return type("Result", (), {"markdown": "# 微信标题\n\n这是一段从已登录企业预警通详情页读取的足够长正文，用于验证微信图标报告可进入统一审计流程。", "extractor": "qyj-authenticated-html", "extractor_version": "playwright"})()

    artifact = prepare_report(store, settings, report, qyj_html=Adapter())

    assert artifact.parser == "qyj-authenticated-html"
    assert "source_kind: weixin" in Path(artifact.markdown_path).read_text(encoding="utf-8")


def test_prepare_report_records_and_merges_multiple_real_sources(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "G" * 32, "title": "混合报告", "publish_date": date(2026, 8, 24), "content_type": "pdf", "source_payload": {"attach": [{"fileUrl": "https://files.example/mixed.pdf"}], "abstract": "<p>嵌入 HTML 的独立正文，应作为第二来源保存。</p>"}})

    class Downloader:
        def download(self, *_args):
            path = tmp_path / "mixed.pdf"; path.write_bytes(b"%PDF")
            return type("Result", (), {"status": "SUCCESS", "path": path})()
    class Mineru:
        def parse_pdf(self, _path):
            return "# PDF 正文\n\n这是 PDF 的独立正文。", "3.4.4"

    artifact = prepare_report(store, settings, report, downloader=Downloader(), mineru=Mineru())

    assert [row.source_kind for row in store.list_artifact_sources(report.id)] == ["PDF", "HTML_EMBEDDED"]
    markdown = Path(artifact.markdown_path).read_text(encoding="utf-8")
    assert "# Source 1 — PDF" in markdown and "# Source 2 — HTML_EMBEDDED" in markdown


def test_prepare_report_uses_embedded_html_when_pdf_source_is_unavailable(tmp_path) -> None:
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "I" * 32, "title": "HTML 回退报告", "publish_date": date(2026, 8, 24), "content_type": "pdf", "source_payload": {"attach": [{"fileUrl": "https://files.example/unavailable.pdf"}], "abstract": "<p>可用的嵌入正文足够长，应在不可下载 PDF 来源不可用时继续完成准备。</p>"}})

    class Downloader:
        def download(self, *_args):
            return type("Result", (), {"status": "FAILED", "path": None, "error_code": "UNSUPPORTED_CONTENT"})()

    artifact = prepare_report(store, settings, report, downloader=Downloader())

    assert artifact.parser == "qyj-html"
    assert "可用的嵌入正文" in Path(artifact.markdown_path).read_text(encoding="utf-8")


def test_prepare_report_rejects_login_page_markdown(tmp_path) -> None:
    import pytest
    from quantradar.research.config import ResearchSettings
    from quantradar.research.preparation import prepare_report
    from quantradar.research.storage import ResearchStore

    settings = ResearchSettings(f"sqlite+pysqlite:///{tmp_path / 'db.sqlite'}", tmp_path / "data", tmp_path / "profile")
    store = ResearchStore(settings); store.create_schema()
    report = store.upsert_report({"source": "qyj", "source_report_id": "H" * 32, "title": "受限网页", "publish_date": date(2026, 8, 24), "content_type": "html", "source_payload": {"abstract": "<p>登录后查看全文 | 首页 | 研报</p>"}})

    with pytest.raises(RuntimeError, match="Markdown quality failed"):
        prepare_report(store, settings, report)

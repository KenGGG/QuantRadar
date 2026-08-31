from __future__ import annotations

import subprocess


def test_url_markdown_adapter_returns_markdown_and_version() -> None:
    from quantradar.research.url_markdown import UrlMarkdownAdapter

    def run(command, **_kwargs):
        assert command[:2] == ["url-md", "md"]
        return subprocess.CompletedProcess(command, 0, stdout="# 标题\n\n正文内容", stderr="")

    result = UrlMarkdownAdapter(run=run).extract("https://mp.weixin.qq.com/s/example")

    assert result.markdown.startswith("# 标题")
    assert result.extractor == "url-md-weixin"


def test_url_markdown_adapter_uses_configured_binary() -> None:
    from quantradar.research.url_markdown import UrlMarkdownAdapter

    def run(command, **_kwargs):
        assert command[:2] == ["/opt/tools/url-md", "md"]
        return subprocess.CompletedProcess(command, 0, stdout="# 标题\n\n正文内容", stderr="")

    UrlMarkdownAdapter(binary="/opt/tools/url-md", run=run).extract("https://example.com/report")


def test_url_markdown_adapter_maps_auth_failure_to_explicit_error() -> None:
    from quantradar.research.url_markdown import UrlMarkdownAdapter, UrlMarkdownError

    def run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="authentication required")

    try:
        UrlMarkdownAdapter(run=run).extract("https://example.com/report")
    except UrlMarkdownError as exc:
        assert exc.code == "AUTH_REQUIRED"
    else:
        raise AssertionError("expected UrlMarkdownError")

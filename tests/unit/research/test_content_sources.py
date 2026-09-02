from __future__ import annotations


def test_detect_content_source_prefers_pdf_and_records_embedded_html() -> None:
    from quantradar.research.content_sources import ContentKind, detect_content_sources

    sources = detect_content_sources({
        "attach": [{"icon": "pdf", "fileUrl": "https://files.example/report.pdf"}],
        "abstract": "<p>可审计的嵌入正文，长度足以通过质量门。</p>",
    })

    assert [source.kind for source in sources] == [ContentKind.PDF, ContentKind.HTML_EMBEDDED]
    assert sources[0].url == "https://files.example/report.pdf"


def test_detect_content_source_classifies_weixin_html_url_and_unknown() -> None:
    from quantradar.research.content_sources import ContentKind, detect_content_sources

    assert detect_content_sources({"articleUrl": "https://mp.weixin.qq.com/s/example"})[0].kind is ContentKind.WEIXIN
    assert detect_content_sources({"articleUrl": "https://example.com/article"})[0].kind is ContentKind.HTML_URL
    assert detect_content_sources({"title": "仅标题"})[0].kind is ContentKind.UNKNOWN


def test_detect_content_source_classifies_qyj_weixin_icon_as_authenticated_weixin() -> None:
    from quantradar.research.content_sources import ContentKind, detect_content_sources

    source = detect_content_sources({"icon": "wx", "pcContentLink": "/information/researchReport?id=example"})[0]

    assert source.kind is ContentKind.WEIXIN
    assert source.url == "https://www.qyyjt.cn/information/researchReport?id=example"


def test_build_inventory_accounts_for_every_snapshot_member() -> None:
    from quantradar.research.content_sources import ContentKind, build_content_inventory

    inventory = build_content_inventory([
        ("HOT", 1, "PDF", {"attach": [{"fileUrl": "https://files.example/a.pdf"}]}),
        ("HOT", 2, "HTML", {"abstract": "<p>正文</p>"}),
        ("STRATEGY", 3, "Unknown", {"title": "仅标题"}),
    ])

    assert inventory["HOT"]["upstream_count"] == 2
    assert inventory["HOT"]["PDF"] == 1
    assert inventory["HOT"]["HTML_EMBEDDED"] == 1
    assert inventory["STRATEGY"]["UNKNOWN"] == 1
    assert inventory["STRATEGY"]["classified_report_count"] == 1

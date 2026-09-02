from datetime import date


def _row(report_id: str, title: str) -> dict:
    return {
        "id": report_id,
        "title": title,
        "publishDate": "08-24",
        "reportType": "行业周报",
        "attach": [{"fileUrl": f"https://example.test/{report_id}.pdf", "filePages": 12}],
    }


def test_normalize_stable_source_report_id() -> None:
    from quantradar.research.collector.qyj import Channel, normalize_report

    normalized = normalize_report(_row("A" * 32, "标题"), Channel.HOT, 1, date(2026, 8, 24))

    assert normalized.report["source"] == "qyj"
    assert normalized.report["source_report_id"] == "A" * 32
    assert normalized.report["content_type"] == "pdf"
    assert normalized.platform_order == 1


def test_search_params_use_a_closed_publish_date_range() -> None:
    from quantradar.research.collector.qyj import Channel, build_search_params

    params = build_search_params(Channel.HOT, date(2026, 8, 28), offset=50, size=20)

    assert params["publishDate"] == "[2026-08-28,2026-08-28]"
    assert params["from"] == "50"
    assert params["size"] == "20"
    assert params["depthOnly"] == "1"


def test_search_params_only_filters_hot_reports_to_depth() -> None:
    from quantradar.research.collector.qyj import Channel, build_search_params

    target_date = date(2026, 8, 28)

    assert build_search_params(Channel.STRATEGY, target_date, 0, 20)["depthOnly"] == "0"
    assert build_search_params(Channel.FINANCIAL_ENGINEERING, target_date, 0, 20)["depthOnly"] == "0"


def test_pagination_uses_size_and_from_without_duplicates() -> None:
    from quantradar.research.collector.qyj import Channel, QyjCollector

    calls: list[int] = []

    def fetch(channel: Channel, target_date: date, offset: int, size: int):
        calls.append(offset)
        rows = [_row("A" * 32, "第一页"), _row("B" * 32, "第二页")] if offset == 0 else [_row("B" * 32, "重复"), _row("C" * 32, "第三页")]
        return {"total": 4, "data": {"list": rows}}

    collector = QyjCollector(fetch_page=fetch, page_size=2)
    result = collector.collect_channel(Channel.HOT, date(2026, 8, 24))

    assert calls == [0, 2]
    assert [row.report["source_report_id"] for row in result] == ["A" * 32, "B" * 32, "C" * 32]
    assert [row.platform_order for row in result] == [1, 2, 4]


def test_auth_failure_stops_collection() -> None:
    from quantradar.research.collector.qyj import AuthState, QyjAuthenticationError, QyjCollector

    collector = QyjCollector(auth_probe=lambda: AuthState.LOGIN_REQUIRED)

    try:
        collector.require_authenticated()
    except QyjAuthenticationError as exc:
        assert exc.code == "LOGIN_REQUIRED"
    else:
        raise AssertionError("collection must stop when login is required")


def test_saved_browser_login_submits_without_reading_credentials() -> None:
    from quantradar.research.collector.qyj import QyjCollector

    events: list[str] = []

    class FakeKeyboard:
        def press(self, key: str) -> None:
            events.append(f"key:{key}")

    class FakeLocator:
        def __init__(self, name: str) -> None:
            self.name = name

        def click(self, **kwargs) -> None:
            events.append(f"click:{self.name}:{kwargs}")

        def is_enabled(self) -> bool:
            return True

    class FakePage:
        keyboard = FakeKeyboard()
        url = "https://www.qyyjt.cn/report/research"

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(selector)

        def wait_for_timeout(self, milliseconds: int) -> None:
            events.append(f"wait:{milliseconds}")

    QyjCollector._submit_saved_browser_login(FakePage())

    assert events == [
        "click:#username:{}",
        "key:ArrowDown",
        "key:Enter",
        "wait:250",
        "click:button[type='submit']:{'no_wait_after': True}",
        "wait:2000",
    ]


def test_saved_browser_login_returns_false_when_autofill_is_unavailable() -> None:
    from quantradar.research.collector.qyj import QyjCollector

    events: list[str] = []

    class FakeKeyboard:
        def press(self, key: str) -> None:
            events.append(f"key:{key}")

    class FakeLocator:
        def __init__(self, name: str) -> None:
            self.name = name

        def click(self, **kwargs) -> None:
            events.append(f"click:{self.name}:{kwargs}")

        def is_enabled(self) -> bool:
            return False

    class FakePage:
        keyboard = FakeKeyboard()
        url = "https://www.qyyjt.cn/user/login"

        def locator(self, selector: str) -> FakeLocator:
            return FakeLocator(selector)

        def wait_for_timeout(self, milliseconds: int) -> None:
            events.append(f"wait:{milliseconds}")

    assert QyjCollector._submit_saved_browser_login(FakePage()) is False
    assert events == ["click:#username:{}", "key:ArrowDown", "key:Enter", "wait:250"]


def test_saved_browser_login_returns_false_when_submission_stays_on_login_page() -> None:
    from quantradar.research.collector.qyj import QyjCollector

    class Keyboard:
        def press(self, _key: str) -> None: pass

    class Locator:
        def click(self, **_kwargs) -> None: pass
        def is_enabled(self) -> bool: return True

    class Page:
        keyboard = Keyboard()
        url = "https://www.qyyjt.cn/user/login"
        def locator(self, _selector: str) -> Locator: return Locator()
        def wait_for_timeout(self, _milliseconds: int) -> None: pass

    assert QyjCollector._submit_saved_browser_login(Page()) is False

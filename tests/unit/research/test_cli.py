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

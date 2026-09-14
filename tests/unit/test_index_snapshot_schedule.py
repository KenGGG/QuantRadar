from datetime import datetime
from zoneinfo import ZoneInfo


def test_index_snapshot_schedule_uses_fixed_calendar_not_weekday():
    from quantradar.datahub.index_snapshots import index_snapshot_due
    assert index_snapshot_due(datetime(2026, 10, 1, 20, 30, tzinfo=ZoneInfo('Asia/Shanghai')), {'2026-09-30'}) is False
    assert index_snapshot_due(datetime(2026, 9, 30, 20, 30, tzinfo=ZoneInfo('Asia/Shanghai')), {'2026-09-30'}) is True


def test_index_snapshot_schedule_waits_until_2030_shanghai():
    from quantradar.datahub.index_snapshots import index_snapshot_due
    assert index_snapshot_due(datetime(2026, 9, 30, 20, 29, tzinfo=ZoneInfo('Asia/Shanghai')), {'2026-09-30'}) is False

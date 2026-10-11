"""Wire-seam regression: the data service defaults omitted count to 250."""
import pandas as pd
from quantradar2.frozen import FrozenProvider


class CalendarWire:
    def __init__(self):
        self.days = pd.bdate_range('2010-01-01', '2025-12-05')
        self.payloads = []

    def request(self, action, payload, **kwargs):
        assert action == 'data.trade_days'
        self.payloads.append(payload)
        days = self.days
        if payload['start'] is not None:
            days = days[days >= pd.Timestamp(payload['start'])]
        if payload['end'] is not None:
            days = days[days <= pd.Timestamp(payload['end'])]
        count = payload['count'] if payload['count'] is not None else 250
        return {'values': [str(d.date()) for d in days[-count:]]}


def test_closed_interval_is_not_truncated_to_default_250():
    wire = CalendarWire()
    provider = FrozenProvider(wire)
    expected = wire.days[wire.days >= '2010-01-01']
    actual = provider.get_trade_days('2010-01-01', '2025-12-05')
    assert actual == list(expected)
    assert wire.payloads[-1]['count'] > 2000


def test_existing_count_and_open_ended_modes_are_preserved():
    for start, end, count in [(None, None, None), (None, '2025-12-05', 22),
                              ('2019-01-01', None, None), ('2019-01-01', '2025-12-05', 10)]:
        wire = CalendarWire()
        FrozenProvider(wire).get_trade_days(start, end, count)
        assert wire.payloads[-1] == {'start': start, 'end': end, 'count': count}


def test_empty_and_date_object_intervals():
    from datetime import date, datetime
    wire = CalendarWire()
    provider = FrozenProvider(wire)
    assert provider.get_trade_days(date(2025, 12, 6), datetime(2025, 12, 7)) == []
    assert wire.payloads[-1]['count'] == 2
    assert provider.get_trade_days('2025-12-07', '2025-12-06') == []


def test_record_replay_uses_explicit_bound_and_checks_identity(tmp_path):
    import pytest
    from quantradar2.frozen import Recorder, Replay, FrozenDataError
    identity = {'adapter_fingerprint': 'new-calendar-adapter'}
    directory = tmp_path / 'frozen'
    recorded = FrozenProvider(Recorder(CalendarWire(), directory, identity)).get_trade_days('2019-01-01', '2025-12-05')
    replay = Replay(directory, identity)
    assert FrozenProvider(replay).get_trade_days('2019-01-01', '2025-12-05') == recorded
    assert len(replay.used) == 1
    with pytest.raises(FrozenDataError, match='identity mismatch'):
        Replay(directory, {'adapter_fingerprint': 'old-calendar-adapter'})


def test_closed_interval_rejects_unordered_calendar():
    import pytest
    class BrokenWire(CalendarWire):
        def request(self, action, payload, **kwargs):
            return {'values': ['2019-01-03', '2019-01-02']}
    with pytest.raises(ValueError, match='calendar'):
        FrozenProvider(BrokenWire()).get_trade_days('2019-01-01', '2019-01-31')

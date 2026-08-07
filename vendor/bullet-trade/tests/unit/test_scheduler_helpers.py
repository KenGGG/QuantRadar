from datetime import datetime, time as T

from bullet_trade.core.scheduler import (
    parse_market_periods_string,
    is_event_expired,
    next_minute_after,
)


def test_parse_market_periods_string():
    periods = parse_market_periods_string("09:30-11:30,13:00-15:00")
    assert periods[0][0] == T(9, 30)
    assert periods[0][1] == T(11, 30)
    assert periods[1][0] == T(13, 0)
    assert periods[1][1] == T(15, 0)


def test_is_event_expired_and_next_minute():
    scheduled = datetime(2025, 1, 1, 9, 40, 0)
    now = datetime(2025, 1, 1, 9, 41, 5)
    assert is_event_expired(scheduled, now, 60) is True
    assert next_minute_after(datetime(2025, 1, 1, 9, 40, 20)) == datetime(2025, 1, 1, 9, 41, 0)


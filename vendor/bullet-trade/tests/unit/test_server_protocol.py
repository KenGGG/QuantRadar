from __future__ import annotations

import json
from datetime import date, datetime

from bullet_trade.server.protocol import HEADER_SIZE, encode_message


def test_encode_message_serializes_date_and_datetime() -> None:
    frame = encode_message(
        {
            "start_date": date(2026, 3, 18),
            "created_at": datetime(2026, 3, 18, 20, 4, 27),
        }
    )
    payload = json.loads(frame[HEADER_SIZE:].decode("utf-8"))
    assert payload["start_date"] == "2026-03-18"
    assert payload["created_at"] == "2026-03-18 20:04:27"

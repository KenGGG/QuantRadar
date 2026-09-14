"""Frozen industry ETF eligibility policy; no name-based inference."""
from __future__ import annotations

POLICY = {
    "financials": {"label": "金融", "definition": "银行与非银金融", "allowed_tracking_indexes": []},
    "consumer": {"label": "消费", "definition": "主要消费", "allowed_tracking_indexes": []},
    "healthcare": {"label": "医药", "definition": "医药卫生", "allowed_tracking_indexes": []},
    "technology": {"label": "科技", "definition": "信息技术", "allowed_tracking_indexes": []},
    "materials": {"label": "周期", "definition": "原材料", "allowed_tracking_indexes": []},
}

def qualify(masters: dict) -> dict:
    result={}
    for key, policy in POLICY.items():
        candidates=[row for row in masters.values() if row.get("tracking_index") in policy["allowed_tracking_indexes"]]
        selected=sorted(candidates,key=lambda r:(str(r.get("listing_date") or "9999-12-31"),r["symbol"]))[0] if candidates else None
        result[key]={**policy,"status":"READY" if selected else "BLOCKED","selected":selected,
                     "reason":None if selected else "没有已冻结且可验证的跟踪指数身份；不会按 ETF 名称猜测行业"}
    return result

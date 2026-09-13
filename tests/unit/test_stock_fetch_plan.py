from quantradar.datahub.stock_fetch_plan import build_stock_bundle_fetch_plan


def test_stock_fetch_plan_merges_duplicate_fields_and_groups_same_ranges():
    sessions = ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
    runs = [
        {"symbol": "000009.SZ", "field": "open", "action": "FETCH", "start_date": sessions[0], "end_date": sessions[1]},
        {"symbol": "000009.SZ", "field": "is_st", "action": "FETCH", "start_date": sessions[0], "end_date": sessions[1]},
        {"symbol": "600004.SH", "field": "close", "action": "FETCH", "start_date": sessions[0], "end_date": sessions[1]},
        {"symbol": "000009.SZ", "field": "market_cap", "action": "FETCH", "start_date": sessions[0], "end_date": sessions[1]},
    ]
    plan = build_stock_bundle_fetch_plan(runs, sessions)
    assert plan["task_count"] == 1 and plan["symbol_count"] == 2
    assert plan["tasks"][0]["symbols"][0]["fields"] == ["is_st", "open"]
    assert plan["session_count"] == 4


def test_stock_fetch_plan_keeps_nonadjacent_ranges_separate():
    sessions = ["2024-01-02", "2024-01-03", "2024-01-04"]
    runs = [
        {"symbol": "000009.SZ", "field": "open", "action": "FETCH", "start_date": sessions[0], "end_date": sessions[0]},
        {"symbol": "000009.SZ", "field": "open", "action": "FETCH", "start_date": sessions[2], "end_date": sessions[2]},
    ]
    assert build_stock_bundle_fetch_plan(runs, sessions)["task_count"] == 2

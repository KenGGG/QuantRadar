import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException
from quantradar.factorlab.correlation import complete_link_clusters, pairwise_summary, pairwise_summary_paths

def test_signed_correlation_and_complete_link():
    dates=pd.date_range('2020-01-01',periods=60); cols=[f's{i}' for i in range(20)]
    base=pd.DataFrame(np.tile(np.arange(20),(60,1)),index=dates,columns=cols)
    pairs=pairwise_summary({1:base,2:-base,3:base*0+1})
    assert pairs[0]['rho']==-1.0
    assert complete_link_clusters([1,2,3],pairs)==[[1,2],[3]]


def test_path_correlation_uses_only_requested_dates(tmp_path):
    dates=pd.date_range('2020-01-01',periods=61); cols=[f's{i}' for i in range(20)]
    left=pd.DataFrame(np.tile(np.arange(20),(61,1)),index=dates,columns=cols)
    right=left.copy(); right.iloc[-1] = -right.iloc[-1]
    a,b=tmp_path/'a.parquet',tmp_path/'b.parquet'; left.to_parquet(a); right.to_parquet(b)
    pairs=pairwise_summary_paths({1:str(a),2:str(b)},dates=[str(x.date()) for x in dates[:-1]])
    assert pairs[0]['rho']==1.0


def test_representative_selection_requires_reasons_and_is_immutable(monkeypatch):
    """The holdout gate is a user decision, never an automatic factor choice."""
    from quantradar.api import app as api
    import quantradar.storage as storage

    config = {"items": [{"alpha_id": 1}, {"alpha_id": 2}]}
    row = {"kind": "factor", "config": config}
    monkeypatch.setattr(storage, "get_experiment", lambda _id: row)
    updated = []
    monkeypatch.setattr(storage, "update_experiment", lambda _id, **kwargs: updated.append(kwargs))

    with pytest.raises(HTTPException, match="每个代表因子") as missing_reason:
        api.factorlab_freeze_representatives("batch", {"alpha_ids": [1], "reasons": {}})
    assert missing_reason.value.status_code == 400
    assert "representative_selection" not in config

    result = api.factorlab_freeze_representatives(
        "batch", {"alpha_ids": [2, 1], "reasons": {"1": "验证段稳定", "2": "覆盖独立信息"}}
    )
    assert result["representative_selection"]["alpha_ids"] == [1, 2]
    assert updated and updated[-1]["config"]["representative_selection"]["reasons"]["1"] == "验证段稳定"

    with pytest.raises(HTTPException, match="已冻结") as repeated:
        api.factorlab_freeze_representatives("batch", {"alpha_ids": [1], "reasons": {"1": "changed"}})
    assert repeated.value.status_code == 409


def test_holdout_route_requires_frozen_representatives(monkeypatch):
    from quantradar.api import app as api
    import quantradar.factorlab.service as service

    monkeypatch.setattr(service, "evaluate_holdout", lambda _id: (_ for _ in ()).throw(ValueError("freeze representative factors before accessing holdout")))
    with pytest.raises(HTTPException, match="freeze representative") as rejected:
        api.factorlab_holdout("batch")
    assert rejected.value.status_code == 400


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ({"status": "RUNNING", "alpha_ids": []}, "NOT_READY"),
        ({"status": "SUCCESS", "alpha_ids": []}, "AWAITING_RESEARCHER_SELECTION"),
        ({"status": "SUCCESS", "alpha_ids": [], "representative_selection": {"alpha_ids": [1]}}, "FROZEN_AWAITING_HOLDOUT_EVALUATION"),
        ({"status": "SUCCESS", "alpha_ids": [], "representative_selection": {"alpha_ids": [1]}, "holdout_access": {"alpha_ids": [1]}}, "HOLDOUT_ACCESSED"),
    ],
)
def test_factorlab_summary_reports_researcher_state(monkeypatch, config, expected):
    from quantradar.api import app as api
    import quantradar.storage as storage

    monkeypatch.setattr(storage, "get_experiment", lambda _id: {"kind": "factor", "config": config, "result_fingerprint": None})
    assert api.factorlab_batch_summary("batch")["researcher_state"] == expected

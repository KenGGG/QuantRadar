from __future__ import annotations

import json

import numpy as np
import pytest

from quantradar.kronos.runtime.inputs import collect_real_input_package
from quantradar.kronos.universe_spec import Universe

pytestmark = [pytest.mark.unit, pytest.mark.requires_dolt]


def test_real_goal1_package_uses_latest_pit_and_complete_qfq_windows(
    live_provider, tmp_path
) -> None:
    manifest = collect_real_input_package(
        live_provider,
        output_dir=tmp_path,
        data_contract_path="reports/kronos/data_audit/data_contract.json",
        universe=Universe.CSI300_PIT,
    )

    arrays = np.load(tmp_path / "runtime_inputs.npz", allow_pickle=False)
    assert manifest["pit_snapshot_date"] == "2022-07-01"
    assert manifest["signal_date"] == "2022-07-01"
    assert manifest["eligible_symbol_count"] >= 50
    assert arrays["values"].shape == (manifest["eligible_symbol_count"], 90, 6)
    assert arrays["y_dates"].shape == (10,)
    assert np.isfinite(arrays["values"]).all()
    assert json.loads((tmp_path / "input_manifest.json").read_text()) == manifest

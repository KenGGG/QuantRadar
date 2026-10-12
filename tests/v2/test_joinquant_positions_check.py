import importlib.util
from pathlib import Path
import zipfile

import pandas as pd
import pytest


spec = importlib.util.spec_from_file_location(
    'positions_check', Path(__file__).parents[2] / 'scripts/v2_joinquant_positions_check.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_ragged_cash_and_position_export(tmp_path):
    rows = [['header'] * 16,
            ['2019-01-02', '', 'Cash', '', '', '', '', '500000'] + [''] * 8,
            ['2019-01-03', 'fund', 'ETF(518880.XSHG)', 'long', '100', '100',
             '2', '200', '0', '2', '-', '0', '0', '100', '0%', '500100', '0%'],
            ['2019-01-03', '', 'Cash', '', '', '', '', '499900'] + [''] * 8]
    archive = tmp_path / 'position.zip'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('position.csv', '\n'.join(','.join(row) for row in rows))
    run = tmp_path / 'run'
    run.mkdir()
    pd.DataFrame({'date': ['2019-01-02', '2019-01-03'],
                  'benchmark_returns_pct': [0, 1]}).to_csv(run / 'daily_records.csv', index=False)
    pd.DataFrame({'date': ['2019-01-03'], 'code': ['518880.XSHG'],
                  'amount': [100], 'price': [2]}).to_csv(run / 'daily_positions.csv', index=False)
    result = module.analyze(archive, run, tmp_path / 'output')
    assert result['days'] == 2
    assert result['final_equity'] == 500100
    assert result['return_pct'] == pytest.approx(.02)
    assert result['price_or_security_difference_rows'] == 0
    rows[2][15] = '500101'
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('position.csv', '\n'.join(','.join(row) for row in rows))
    with pytest.raises(ValueError, match='totals disagree'):
        module.analyze(archive, run, tmp_path / 'bad-output')

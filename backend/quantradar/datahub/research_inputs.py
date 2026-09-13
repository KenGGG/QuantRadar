"""Versioned daily research input derivations; no network and no guessed units."""
from __future__ import annotations

import numpy as np
import pandas as pd

# These are source/reader boundary contracts, not a security-prefix heuristic.
UNIT_CONTRACTS = {
    'base-hands-thousand-yuan': (100.0, 1000.0),
    'joinquant-shares-yuan-v2': (1.0, 1.0),
    'baostock-shares-yuan': (1.0, 1.0),
}


def standard_panel(raw: pd.DataFrame, *, unit_contract: str, adjustment: str) -> pd.DataFrame:
    """Preserve raw execution values; explicitly label fixed-release adjusted research.

    Fixed upstream adjclose is reproducible but its historical availability and
    split/cash decomposition are not established. No adjusted volume is inferred.
    """
    if unit_contract not in UNIT_CONTRACTS:
        raise ValueError(f'unknown unit contract: {unit_contract}')
    if adjustment not in {'raw', 'fixed_hfq'}:
        raise ValueError('adjustment must be raw or fixed_hfq')
    required = {'open', 'high', 'low', 'close', 'volume', 'amount'}
    if missing := required - set(raw.columns):
        raise ValueError(f'missing required fields: {sorted(missing)}')
    result = raw.copy(deep=True)
    for field in required:
        result[field] = pd.to_numeric(result[field], errors='raise')
        if np.isinf(result[field]).any():
            raise ValueError(f'non-finite {field}')
    if (result[['volume', 'amount']] < 0).any().any():
        raise ValueError('negative volume or amount')
    present = result[['open', 'high', 'low', 'close']].notna().all(axis=1)
    invalid = (result['low'] > result[['open', 'close']].min(axis=1)) | (result['high'] < result[['open', 'close']].max(axis=1))
    if (present & invalid).any():
        raise ValueError('invalid OHLC bounds')
    for field in ('open', 'high', 'low', 'close'):
        result['raw_' + field] = result[field]
    volume_scale, amount_scale = UNIT_CONTRACTS[unit_contract]
    result['volume_shares'] = result['volume'] * volume_scale
    result['amount_cny'] = result['amount'] * amount_scale
    result['vwap'] = result['amount_cny'] / result['volume_shares'].where(result['volume_shares'] > 0)
    result['vwap_missing_reason'] = None
    result.loc[result['amount'].isna() | result['volume'].isna(), 'vwap_missing_reason'] = 'MISSING_AMOUNT_OR_VOLUME'
    result.loc[result['volume'].eq(0), 'vwap_missing_reason'] = 'ZERO_VOLUME'
    result['adjustment_factor'] = 1.0
    if adjustment == 'fixed_hfq':
        if 'adjclose' not in raw:
            raise ValueError('missing adjustment factor evidence: adjclose')
        factor = pd.to_numeric(raw['adjclose'], errors='raise') / result['raw_close']
        if (~np.isfinite(factor) | factor.le(0)).any():
            raise ValueError('missing or invalid adjustment factor')
        result['adjustment_factor'] = factor
        for field in ('open', 'high', 'low', 'close', 'vwap'):
            result[field] = result[field] * factor
    result['returns'] = result['close'].pct_change(fill_method=None)
    result.attrs.update(unit_contract=unit_contract, adjustment=adjustment, strict_pit_ready=False,
                        volume_adjustment='none; split factor unavailable',
                        price_availability='end_of_day; execute no earlier than next session',
                        adjustment_anchor='fixed release upstream historical anchor' if adjustment=='fixed_hfq' else 'none')
    return result

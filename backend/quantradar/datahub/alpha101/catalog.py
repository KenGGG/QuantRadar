"""Primary-source mathematical catalogue; computability is not data qualification."""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from .expressions import adaptations, dependencies, parse
from .operators import Interpreter
from ._formulas import FORMULAS

SEMANTICS_VERSION = 'alpha101_research_v1'
# Hash every frozen interpretation along with formula and ADV input basis.
CONVENTIONS = {
    'rank': 'average_ties_ascending_1_to_n_divided_by_n',
    'ts_rank': 'last_value_average_ties_ascending_1_to_n_divided_by_n',
    'arg_extrema': 'oldest_1_newest_n_first_oldest_tie',
    'windows': 'floor_full_window_inclusive_current',
    'variance': 'sample_ddof1_zero_variance_covariance_correlation_nan',
    'missing': 'no_fill_eligible_cross_section_missing_invalidates_row',
    'minmax': 'scalar_second_arg_rolling_panel_second_arg_elementwise',
    'signedpower': 'literal_x_power_a_per_appendix_definition',
    'returns': 'provided_close_to_close_input_requires_two_price_bars',
    'decay_linear': 'oldest_weight1_newest_weight_d_normalized',
    'invalid_arithmetic': 'nonfinite_and_division_by_zero_nan',
    'execution': 'signal_at_t_close_execution_no_earlier_than_t_plus_1',
    'universe': 'explicit_daily_boolean_mask_cross_sections_and_final_output_only',
}


def dependency_matrix(*, adv_basis: str = 'amount') -> list[dict]:
    rows = []
    for alpha_id, formula in enumerate(FORMULAS, 1):
        tree = parse(formula)
        fields, bars = dependencies(tree, adv_basis)
        group = ('industry' if any(f.startswith('indclass.') for f in fields)
                 else 'market_cap' if 'cap' in fields else 'price_volume')
        identity = json.dumps({'formula': formula, 'semantics_version': SEMANTICS_VERSION,
                               'conventions': CONVENTIONS, 'adv_basis': adv_basis}, sort_keys=True)
        rows.append({'alpha_id': alpha_id, 'formula': formula, 'fields': sorted(fields),
                     'group': group, 'lookback_days': bars,
                     'delay_adaptation': 'delay0_to_next_session' if alpha_id in (42, 48, 53, 54) else 'next_session',
                     'formula_hash': hashlib.sha256(identity.encode()).hexdigest(),
                     'formula_status': 'IMPLEMENTED_UNQUALIFIED',
                     'semantic_adaptations': sorted(adaptations(tree)),
                     'semantics_version': SEMANTICS_VERSION, 'adv_basis': adv_basis,
                     'evaluation_status': 'NOT_ASSESSED', 'execution_status': 'NOT_ASSESSED',
                     'strict_pit_status': 'NOT_ASSESSED'})
    return rows


def evaluate(expression: str, panel: dict[str, pd.DataFrame], *, adv_basis: str = 'amount') -> pd.DataFrame:
    """Interpret an expression without I/O. Input frames must share ordered unique axes.

    Input fields use paper names. `volume` is shares, `amount` is currency units,
    `cap` is historical total market cap; OHLC and VWAP share an externally audited
    research adjustment basis. `returns` is supplied, never silently recalculated.
    Optional boolean `universe` defines each day's eligible cross-section. Historical
    raw inputs outside that mask remain available for a new member's rolling warmup.
    """
    tree = parse(expression)
    fields, bars = dependencies(tree, adv_basis)
    missing = fields - panel.keys()
    if missing:
        raise ValueError('missing fields: ' + ', '.join(sorted(missing)))
    if not fields:
        raise ValueError('expression must reference at least one input field')
    template = panel[sorted(fields)[0]]
    if not isinstance(template, pd.DataFrame):
        raise ValueError('inputs must be pandas DataFrames')
    if not template.index.is_unique or not template.columns.is_unique or not template.index.is_monotonic_increasing:
        raise ValueError('input axes must be unique and dates sorted ascending')
    prepared = {}
    for name in sorted(fields):
        value = panel[name]
        if not isinstance(value, pd.DataFrame) or not value.index.equals(template.index) or not value.columns.equals(template.columns):
            raise ValueError(f'panel alignment mismatch: {name}')
        if name.startswith('indclass.'):
            prepared[name] = value.copy()
        else:
            try:
                prepared[name] = value.astype(float).replace([np.inf, -np.inf], np.nan)
            except (TypeError, ValueError) as exc:
                raise ValueError(f'non-numeric field: {name}') from exc
    universe = panel.get('universe')
    if universe is None:
        universe = pd.DataFrame(True, index=template.index, columns=template.columns)
    elif (not isinstance(universe, pd.DataFrame) or not universe.index.equals(template.index)
          or not universe.columns.equals(template.columns) or universe.isna().any().any()
          or not all(pd.api.types.is_bool_dtype(dtype) for dtype in universe.dtypes)):
        raise ValueError('universe must be aligned boolean data without missing values')
    interpreter = Interpreter(prepared, template, adv_basis, universe)
    result = interpreter.frame(interpreter.run(tree)).astype(float).where(universe)
    result.iloc[:max(0, bars - 1)] = np.nan
    result.attrs.update({'semantics_version': SEMANTICS_VERSION, 'adv_basis': adv_basis,
                         'lookback_days': bars, 'qualification': 'NOT_ASSESSED'})
    return result


def compute(alpha_id: int, panel: dict[str, pd.DataFrame], *, adv_basis: str = 'amount') -> pd.DataFrame:
    if isinstance(alpha_id, bool) or not isinstance(alpha_id, int) or not 1 <= alpha_id <= 101:
        raise ValueError('alpha_id must be an integer from 1 through 101')
    result = evaluate(FORMULAS[alpha_id - 1], panel, adv_basis=adv_basis)
    row = dependency_matrix(adv_basis=adv_basis)[alpha_id - 1]
    result.attrs.update({'alpha_id': alpha_id, 'formula_hash': row['formula_hash'],
                         'semantic_adaptations': row['semantic_adaptations'],
                         'delay_adaptation': row['delay_adaptation']})
    return result

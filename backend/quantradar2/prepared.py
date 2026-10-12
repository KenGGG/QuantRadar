"""QMT dataset preparation and strict, network-free daily providers.

Dataset objects are shared by identical data requirements. Each task copies a
verified object into its own directory; running tasks never consult shared cache.
"""
from __future__ import annotations

import ast
from copy import deepcopy
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import re
import time

import pandas as pd

from .frozen import FrozenDataError, canonical, write
from .provider import ResearchQmtProvider

FIELDS = ['open', 'high', 'low', 'close', 'volume', 'money', 'paused']


def requirements(source, explicit=None):
    """Read an explicit literal declaration without executing strategy code."""
    if explicit is not None:
        value = explicit
    else:
        value = None
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'DATA_REQUIREMENTS' for t in node.targets
            ):
                value = ast.literal_eval(node.value)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == 'DATA_REQUIREMENTS':
                value = ast.literal_eval(node.value)
    if not isinstance(value, dict) or set(value) != {'securities', 'warmup_bars'}:
        raise ValueError('Prepared daily runs require DATA_REQUIREMENTS = '
                         "{'securities': [...], 'warmup_bars': 84}, or data_requirements in the request")
    securities = value['securities']
    if not isinstance(securities, list) or not securities or len(securities) > 100:
        raise ValueError('Declare 1 to 100 securities')
    if any(not isinstance(s, str) or not re.fullmatch(r'\d{6}\.(XSHG|XSHE)', s) for s in securities):
        raise ValueError('Invalid declared security')
    bars = value['warmup_bars']
    if type(bars) is not int or not 60 <= bars <= 5000:
        raise ValueError('warmup_bars must be an integer between 60 and 5000')
    return {'securities': sorted(set(securities)), 'warmup_bars': bars}


def day(value):
    return pd.Timestamp(value).normalize()


def dates(frame):
    return pd.DatetimeIndex(pd.to_datetime(frame.index)).normalize()


def encode_frame(frame):
    index = dates(frame)
    if not index.is_unique or not index.is_monotonic_increasing:
        raise FrozenDataError('Daily data must have a unique increasing datetime index')
    if set(FIELDS) - set(frame.columns):
        raise FrozenDataError('QMT daily data lacks required fields')
    return {'index': [t.isoformat() for t in frame.index] if isinstance(frame.index, pd.DatetimeIndex) else list(frame.index),
            'datetime_index': isinstance(frame.index, pd.DatetimeIndex), 'index_dtype': str(frame.index.dtype), 'columns': list(frame.columns),
            'records': [[None if pd.isna(v) else v.item() if hasattr(v, 'item') else v
                         for v in row] for row in frame.itertuples(index=False, name=None)],
            'dtypes': {c: str(t) for c, t in frame.dtypes.items()}, 'index_name': frame.index.name}


def decode_frame(value):
    index = (pd.DatetimeIndex(value['index'], name=value.get('index_name')) if value['datetime_index']
             else pd.Index(value['index'], dtype=value['index_dtype'], name=value.get('index_name')))
    frame = pd.DataFrame(value['records'], columns=value['columns'],
                         index=index)
    for column, dtype in value['dtypes'].items():
        frame[column] = frame[column].astype(dtype)
    return frame


def load_snapshot(directory, identity=None):
    directory = Path(directory)
    meta = json.loads((directory / 'dataset-manifest.json').read_bytes())
    content = (directory / 'dataset.json').read_bytes()
    if meta.get('version') != 1 or hashlib.sha256(content).hexdigest() != meta['sha256']:
        raise FrozenDataError('Prepared dataset checksum mismatch')
    if identity is not None and meta.get('identity') != identity:
        raise FrozenDataError('Prepared dataset identity mismatch')
    return json.loads(content), meta


def save_snapshot(directory, dataset, identity):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    content = canonical(dataset)
    pending = directory / 'dataset.tmp'; pending.write_bytes(content)
    pending.replace(directory / 'dataset.json')
    meta = {'version': 1, 'sha256': hashlib.sha256(content).hexdigest(), 'identity': identity}
    write(directory / 'dataset-manifest.json', meta)
    return meta


def prepare(provider, request, plan, directory, cache_root, cache_identity, task_identity):
    if request.get('frequency', 'day') != 'day':
        raise ValueError('Prepared data currently supports daily backtests only')
    start, end = day(request['start_date']), day(request['end_date'])
    ref = request['reference_date']
    securities = sorted(set(plan['securities'] + ([request['benchmark']] if request.get('benchmark') else [])))
    cache_spec = dict(cache_identity, plan=plan, securities=securities,
                      start=str(start.date()), end=str(end.date()), reference_date=ref, fields=FIELDS, version=1)
    key = hashlib.sha256(canonical(cache_spec)).hexdigest()
    cache_dir = Path(cache_root) / key
    began = time.perf_counter()
    if (cache_dir / 'dataset-manifest.json').exists() and not request.get('refresh_data', False):
        dataset, _ = load_snapshot(cache_dir, cache_spec)
        save_snapshot(directory, dataset, task_identity)
        print('[DATA] Verified cache reused; entering offline backtest', flush=True)
        return {'cache_hit': True, 'dataset_key': key, 'seconds': time.perf_counter() - began}
    provider = provider() if callable(provider) else provider
    print('[DATA] Preparing QMT calendar, daily bars, historical security metadata and corporate actions', flush=True)
    prior = provider.get_trade_days(end_date=str(start.date()), count=plan['warmup_bars'] + 10)
    if not prior:
        raise FrozenDataError('QMT returned no warmup calendar')
    lower = day(prior[0]) - timedelta(days=10)
    upper = end + timedelta(days=7)  # native suspension checks inspect nearby sessions
    calendar = provider.get_trade_days(str(lower.date()), str(upper.date()))
    if not calendar or len(set(calendar)) != len(calendar) or calendar != sorted(calendar):
        raise FrozenDataError('Invalid prepared trading calendar')
    run_days = [d for d in calendar if start <= day(d) <= end]
    if not run_days:
        raise FrozenDataError('No trading days in requested interval')
    dataset = {'lower': str(lower.date()), 'upper': str(upper.date()),
               'run_start': str(start.date()), 'run_end': str(end.date()), 'reference_date': ref,
               'warmup_bars': plan['warmup_bars'],
               'calendar': [str(day(d).date()) for d in calendar], 'prices': {}, 'info': {}, 'events': {}}
    validation = []
    for security in securities:
        print('[DATA] Daily bars: ' + security, flush=True)
        dataset['prices'][security] = {}
        for variant, fq, anchor in [('raw', 'none', None), ('pre', 'pre', None), ('anchored', 'pre', ref)]:
            frame = provider.get_price(security, start_date=str(lower.date()), end_date=str(upper.date()),
                                       fields=FIELDS, frequency='daily', fq=fq, skip_paused=False,
                                       pre_factor_ref_date=anchor)
            if frame.empty:
                raise FrozenDataError('No daily bars for ' + security)
            encoded = encode_frame(frame)
            dataset['prices'][security][variant] = encoded
            # A full-range QMT request must match window requests before trusting local slicing.
            for query_day in [run_days[0], run_days[len(run_days)//2], run_days[-1]]:
                cutoff = day(query_day) - timedelta(days=1)
                expected = provider.get_price(security, end_date=str(cutoff.date()), count=plan['warmup_bars'],
                                              fields=FIELDS, frequency='daily', fq=fq, skip_paused=False,
                                              pre_factor_ref_date=anchor)
                actual = frame.loc[dates(frame) <= cutoff].tail(plan['warmup_bars'])
                if variant == 'anchored' and day(ref) not in dates(actual):
                    unanchored = decode_frame(dataset['prices'][security]['pre'])
                    actual = unanchored.loc[dates(unanchored) <= cutoff].tail(plan['warmup_bars'])
                try:
                    pd.testing.assert_frame_equal(actual, expected, check_freq=False, check_exact=True,
                                                  check_dtype=not expected.empty)
                except AssertionError as error:
                    raise FrozenDataError('QMT bulk/window semantics differ for ' + security + '/' + variant) from error
                validation.append({'security': security, 'variant': variant, 'date': str(cutoff.date()), 'rows': len(actual)})
        dataset['events'][security] = provider.get_split_dividend(security, str(lower.date()), str(upper.date()))
        dataset['info'][security] = {}
        # Preserve historical-date semantics: do not substitute current security metadata.
        for i, query_day in enumerate(run_days):
            date = str(day(query_day).date())
            dataset['info'][security][date] = provider.get_security_info(security, date=date)
            if (i + 1) % 100 == 0:
                print(f'[DATA] Metadata {security}: {i+1}/{len(run_days)}', flush=True)
    dataset['validation'] = validation
    dataset['acquired_at'] = pd.Timestamp.now(tz='UTC').isoformat()
    # Publication happens only after every download and parity check succeeds.
    save_snapshot(cache_dir, dataset, cache_spec)
    save_snapshot(directory, dataset, task_identity)
    print('[DATA] Snapshot ready; QMT connection will close before backtest', flush=True)
    return {'cache_hit': False, 'dataset_key': key, 'seconds': time.perf_counter()-began,
            'trading_days': len(run_days), 'window_checks': len(validation)}


class OfflineConnection:
    def __init__(self):
        self.errors = []; self.used = set()
    def request(self, action, payload, **kwargs):
        self.fail('Unsupported prepared request: ' + action)
    def fail(self, message):
        self.errors.append(message)
        raise FrozenDataError(message + '; network fallback forbidden')
    def close(self):
        pass


class PreparedProvider(ResearchQmtProvider):
    requires_live_data = False
    def __init__(self, directory, identity):
        self.dataset, self.manifest = load_snapshot(directory, identity)
        self._connection = OfflineConnection(); self.config = {}
        self._tick_callback = None; self._tick_context = None; self._subscription_key = 'prepared'
        self.prices = {s: {k: decode_frame(v) for k, v in variants.items()}
                       for s, variants in self.dataset['prices'].items()}

    def security(self, security):
        normalized = str(security).replace('.SH', '.XSHG').replace('.SZ', '.XSHE')
        if normalized not in self.prices:
            self._connection.fail('Undeclared security: ' + str(security))
        return normalized

    def interval(self, start, end, label):
        lower, upper = day(self.dataset['lower']), day(self.dataset['upper'])
        if any(value is not None and not lower <= day(value) <= upper for value in [start, end]):
            self._connection.fail(label + ' request exceeds prepared interval')
        if start is not None and end is not None and day(start) > day(end):
            self._connection.fail('Invalid ' + label.lower() + ' interval')

    def get_price(self, security, start_date=None, end_date=None, frequency='daily', fields=None,
                  skip_paused=False, fq='pre', count=None, panel=True, fill_paused=True,
                  pre_factor_ref_date=None, prefer_engine=False, force_no_engine=False):
        if not isinstance(security, str) or frequency not in {'daily', 'day', '1d'} or not fill_paused:
            self._connection.fail('Unsupported prepared price shape/frequency/fill policy')
        code = self.security(security)
        if fq not in {'pre', 'none'}:
            self._connection.fail('Undeclared adjustment: ' + str(fq))
        if pre_factor_ref_date is not None and str(day(pre_factor_ref_date).date()) != self.dataset['reference_date']:
            self._connection.fail('Undeclared adjustment reference date')
        variant = 'raw' if fq == 'none' else 'anchored' if pre_factor_ref_date is not None else 'pre'
        frame = self.prices[code][variant]
        wanted = fields or FIELDS
        if wanted == ['open', 'close', 'high_limit', 'low_limit', 'paused']:
            wanted = ['open', 'close', 'paused']  # same native historical-limit fallback as ResearchQmtProvider
        if set(wanted) - set(frame.columns):
            self._connection.fail('Undeclared price fields: ' + str(wanted))
        lower, upper = day(self.dataset['lower']), day(self.dataset['upper'])
        self.interval(start_date, end_date, 'Price')
        result = frame
        if start_date is not None: result = result.loc[dates(result) >= day(start_date)]
        if end_date is not None: result = result.loc[dates(result) <= day(end_date)]
        if skip_paused: result = result.loc[result['volume'] > 0]
        if count is not None:
            if type(count) is not int or count < 1:
                self._connection.fail('Invalid prepared bar count')
            if count > len(result) and count > self.dataset['warmup_bars'] and start_date is None:
                self._connection.fail('Requested history exceeds prepared warmup')
            result = result.tail(count)
        # Native QMT scales OHLC only when the reference bar is present in the
        # requested window. A broad bulk request must not change that behavior.
        if variant == 'anchored' and day(self.dataset['reference_date']) not in dates(result):
            result = self.prices[code]['pre'].loc[result.index]
        self._connection.used.add(('price', code, variant))
        return result.loc[:, wanted].copy()

    def get_trade_days(self, start_date=None, end_date=None, count=None):
        calendar = [day(d) for d in self.dataset['calendar']]
        self.interval(start_date, end_date, 'Calendar')
        if start_date is not None: calendar = [d for d in calendar if d >= day(start_date)]
        if end_date is not None: calendar = [d for d in calendar if d <= day(end_date)]
        if count is not None:
            if type(count) is not int or count < 1: self._connection.fail('Invalid prepared calendar count')
            if count > len(calendar): self._connection.fail('Calendar request exceeds prepared warmup')
            calendar = calendar[-count:]
        return calendar

    def get_security_info(self, security, date=None):
        code = self.security(security)
        key = str(day(date).date()) if date is not None else None
        if key not in self.dataset['info'][code]:
            self._connection.fail('Undeclared security metadata date: ' + str(key))
        return deepcopy(self.dataset['info'][code][key])

    def get_split_dividend(self, security, start_date=None, end_date=None):
        code = self.security(security)
        lower, upper = day(self.dataset['lower']), day(self.dataset['upper'])
        start = day(start_date) if start_date is not None else lower
        end = day(end_date) if end_date is not None else upper
        self.interval(start, end, 'Corporate-action')
        events = deepcopy([e for e in self.dataset['events'][code] if start <= day(e['date']) <= end])
        for event in events:
            if 'security' in event: event['security'] = security
        return events

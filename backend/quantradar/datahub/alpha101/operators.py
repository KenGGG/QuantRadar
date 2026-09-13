"""Frozen numerical conventions for Alpha101 research interpretation v1."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .expressions import Node, ROLLING, window


def clean(value):
    if isinstance(value, pd.DataFrame):
        return value.replace([np.inf, -np.inf], np.nan)
    return value if np.isfinite(value) else np.nan


def _rank_last(values):
    # Average ties, normalized by the complete window length.
    return (np.sum(values < values[-1]) + (np.sum(values == values[-1]) + 1) / 2) / len(values)


def rolling(name, x, n):
    r = x.rolling(n, min_periods=n)
    if name in ('sum', 'ts_min', 'ts_max'):
        return getattr(r, name.removeprefix('ts_'))()
    if name == 'stddev':
        return r.std(ddof=1)
    if name == 'ts_rank':
        return r.apply(_rank_last, raw=True)
    if name in ('ts_argmin', 'ts_argmax'):
        fn = np.argmin if name == 'ts_argmin' else np.argmax
        return r.apply(lambda a: float(fn(a) + 1), raw=True)
    if name == 'product':
        return r.apply(np.prod, raw=True)
    weights = np.arange(1, n + 1, dtype=float)
    return r.apply(lambda a: np.dot(a, weights) / weights.sum(), raw=True)


class Interpreter:
    def __init__(self, panel, template, adv_basis, universe):
        self.panel = panel
        self.template = template
        self.adv_basis = adv_basis
        self.universe = universe
        self.cache = {}

    def frame(self, value):
        if isinstance(value, pd.DataFrame):
            return value
        return pd.DataFrame(value, index=self.template.index, columns=self.template.columns)

    def cross_section(self, x):
        x = self.frame(x).where(self.universe)
        # Missing eligible inputs invalidate the whole cross-section; no implicit pool shrinkage.
        invalid = (x.isna() & self.universe).any(axis=1)
        return x.mask(invalid, axis=0)

    def run(self, node: Node):
        if node in self.cache:
            return self.cache[node]
        with np.errstate(all='ignore'):
            result = self._run(node)
        result = clean(result)
        self.cache[node] = result
        return result

    def _run(self, node):
        if node.kind == 'number':
            return float(node.value)
        if node.kind == 'field':
            name = str(node.value)
            if name.startswith('adv'):
                n = int(name[3:])
                return self.panel[self.adv_basis].rolling(n, min_periods=n).mean()
            return self.panel[name]
        args = [self.run(arg) for arg in node.args]
        name = node.value
        if node.kind == 'unary':
            return args[0] if name == '+' else -args[0]
        if node.kind == 'where':
            condition, yes, no = map(self.frame, args)
            return yes.where(condition != 0, no).where(condition.notna())
        if node.kind == 'binary':
            a, b = map(self.frame, args)
            if name == '+':
                result = a + b
            elif name == '-':
                result = a - b
            elif name == '*':
                result = a * b
            elif name == '/':
                result = a / b.where(b != 0)
            elif name == '^':
                result = a ** b
            elif name == '||':
                result = ((a != 0) | (b != 0)).astype(float)
            elif name == '&&':
                result = ((a != 0) & (b != 0)).astype(float)
            else:
                result = {'<': a.lt, '>': a.gt, '==': a.eq, '<=': a.le, '>=': a.ge}[name](b).astype(float)
            return result.where(a.notna() & b.notna())
        x = self.frame(args[0])
        if name in ROLLING:
            return rolling(name, x, window(node.args[1]))
        if name in ('min', 'max'):
            if node.args[1].kind == 'number':
                return rolling('ts_' + name, x, window(node.args[1]))
            y = self.frame(args[1])
            return (np.minimum(x, y) if name == 'min' else np.maximum(x, y))
        if name in ('delay', 'delta'):
            shifted = x.shift(window(node.args[1], delay=True))
            return shifted if name == 'delay' else x - shifted
        if name in ('correlation', 'covariance'):
            y = self.frame(args[1])
            n = window(node.args[2])
            r = x.rolling(n, min_periods=n)
            # Constant windows can otherwise leak large cancellation artifacts through corr.
            variance_ok = (r.var(ddof=1) > 0) & (y.rolling(n, min_periods=n).var(ddof=1) > 0)
            result = r.corr(y) if name == 'correlation' else r.cov(y, ddof=1)
            if name == 'correlation':
                result = result.clip(-1, 1)
            return result.where(variance_ok)
        if name == 'rank':
            return self.cross_section(x).rank(axis=1, method='average', pct=True)
        if name == 'scale':
            x = self.cross_section(x)
            denominator = x.abs().sum(axis=1, min_count=1)
            scale = args[1] if len(args) == 2 else 1
            return x.div(denominator.where(denominator != 0), axis=0) * scale
        if name == 'indneutralize':
            groups = self.frame(args[1]).where(self.universe)
            x = self.cross_section(x)
            invalid = (groups.isna() & self.universe).any(axis=1)
            result = x.copy()
            for date in x.index:
                if invalid.loc[date]:
                    result.loc[date] = np.nan
                else:
                    result.loc[date] = x.loc[date] - x.loc[date].groupby(groups.loc[date]).transform('mean')
            return result
        if name == 'abs':
            return x.abs()
        if name == 'sign':
            return np.sign(x)
        if name == 'log':
            return np.log(x.where(x > 0))
        if name == 'signedpower':
            # Literal Appendix operator definition x^a (not sign(x)*abs(x)^a).
            y = self.frame(args[1])
            return (x ** y).where(x.notna() & y.notna())
        raise ValueError(f'unsupported operator: {name}')

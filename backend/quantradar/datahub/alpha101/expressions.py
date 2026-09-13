"""Restricted, case-insensitive parser for Appendix A's expression language.

Only numeric literals, named inputs and the listed mathematical operations exist.
No Python evaluation, attribute access, subscripting or executable code is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re

FIELDS = frozenset({'open', 'high', 'low', 'close', 'volume', 'amount', 'vwap',
                    'returns', 'cap', 'indclass.sector', 'indclass.industry',
                    'indclass.subindustry'})
ROLLING = frozenset({'sum', 'product', 'stddev', 'ts_min', 'ts_max', 'ts_rank',
                     'ts_argmin', 'ts_argmax', 'decay_linear'})
ARITIES = {**{name: (2,) for name in ROLLING},
           **{name: (1,) for name in ('abs', 'log', 'sign', 'rank')},
           **{name: (2,) for name in ('delay', 'delta', 'signedpower', 'indneutralize', 'min', 'max')},
           'correlation': (3,), 'covariance': (3,), 'scale': (1, 2)}
TOKEN = re.compile(r'\s*(\d+(?:\.\d*)?|\.\d+|[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?|==|<=|>=|\|\||&&|[+*/^()?,:<>-])')
PRECEDENCE = {'||': 1, '&&': 2, '==': 3, '<': 3, '>': 3, '<=': 3, '>=': 3,
              '+': 4, '-': 4, '*': 5, '/': 5, '^': 7}


@dataclass(frozen=True)
class Node:
    kind: str
    value: str | float
    args: tuple[Node, ...] = ()


def window(node: Node, *, delay: bool = False) -> int:
    if node.kind != 'number' or not math.isfinite(float(node.value)):
        raise ValueError('window must be a constant finite number')
    n = math.floor(float(node.value))
    if n < (0 if delay else 1):
        raise ValueError('window must be positive (delay permits zero)')
    return n


class _Parser:
    def __init__(self, source: str):
        if not source.strip() or len(source) > 20000:
            raise ValueError('empty or oversized expression')
        self.tokens = []
        pos = 0
        source = source.strip()
        while pos < len(source):
            match = TOKEN.match(source, pos)
            if not match:
                raise ValueError(f'invalid expression token at position {pos}')
            self.tokens.append(match[1].lower())
            pos = match.end()
        if len(self.tokens) > 4096:
            raise ValueError('expression token limit exceeded')
        self.tokens.append('EOF')
        self.pos = 0

    def take(self, expected=None):
        token = self.tokens[self.pos]
        if expected is not None and token != expected:
            raise ValueError(f'expected {expected}, found {token}')
        self.pos += 1
        return token

    def expression(self, minimum=0):
        token = self.take()
        if token in ('+', '-'):
            node = Node('unary', token, (self.expression(6),))
        elif token == '(':
            node = self.expression()
            self.take(')')
        elif re.fullmatch(r'\d+(?:\.\d*)?|\.\d+', token):
            node = Node('number', float(token))
        elif token in FIELDS or re.fullmatch(r'adv[1-9]\d*', token):
            node = Node('field', token)
        elif token in ARITIES:
            self.take('(')
            args = [self.expression()]
            while self.tokens[self.pos] == ',':
                self.take(',')
                args.append(self.expression())
            self.take(')')
            if len(args) not in ARITIES[token]:
                raise ValueError(f'invalid arity for {token}')
            if token in ROLLING or token in ('delay', 'delta'):
                window(args[1], delay=token in ('delay', 'delta'))
            if token in ('correlation', 'covariance'):
                window(args[2])
            if token in ('min', 'max') and args[1].kind == 'number':
                window(args[1])
            if token == 'indneutralize' and not (
                args[1].kind == 'field' and str(args[1].value).startswith('indclass.')
            ):
                raise ValueError('indneutralize needs an explicit industry level')
            node = Node('call', token, tuple(args))
        else:
            raise ValueError(f'unknown or unexpected expression token: {token}')
        while (op := self.tokens[self.pos]) in PRECEDENCE and PRECEDENCE[op] >= minimum:
            self.take()
            right = self.expression(PRECEDENCE[op] + (0 if op == '^' else 1))
            node = Node('binary', op, (node, right))
        if minimum == 0 and self.tokens[self.pos] == '?':
            self.take('?')
            yes = self.expression()
            self.take(':')
            node = Node('where', '?', (node, yes, self.expression()))
        return node


@lru_cache(maxsize=512)
def parse(source: str) -> Node:
    try:
        parser = _Parser(source)
        node = parser.expression()
        parser.take('EOF')
        return node
    except (IndexError, RecursionError) as exc:
        raise ValueError('invalid or excessively nested expression') from exc


def dependencies(node: Node, adv_basis='amount') -> tuple[set[str], int]:
    """Primitive named fields and total underlying bars, including returns' lag."""
    if adv_basis not in ('amount', 'volume'):
        raise ValueError('adv_basis must be amount or volume')
    if node.kind == 'number':
        return set(), 0
    if node.kind == 'field':
        name = str(node.value)
        if name.startswith('adv'):
            return {adv_basis}, int(name[3:])
        return {name}, 2 if name == 'returns' else 1
    children = [dependencies(child, adv_basis) for child in node.args]
    fields = set().union(*(item[0] for item in children))
    bars = max(item[1] for item in children)
    if node.kind == 'call':
        if node.value in ROLLING:
            bars = children[0][1] + window(node.args[1]) - 1
        elif node.value in ('delay', 'delta'):
            bars = children[0][1] + window(node.args[1], delay=True)
        elif node.value in ('correlation', 'covariance'):
            bars = max(children[0][1], children[1][1]) + window(node.args[2]) - 1
        elif node.value in ('min', 'max') and node.args[1].kind == 'number':
            bars = children[0][1] + window(node.args[1]) - 1
    return fields, bars


def adaptations(node: Node) -> set[str]:
    notes = set().union(*(adaptations(arg) for arg in node.args))
    if node.kind == 'call' and node.value in ('min', 'max') and node.args[1].kind != 'number':
        notes.add('panel_minmax_elementwise')
    return notes

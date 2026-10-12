"""Conservative data planning from Python syntax; never execute strategy code.

Literal security codes are an overapproximation. Unsupported count expressions
use the provider's maximum supported warmup. The offline provider remains the
authority and rejects requests outside the prepared snapshot.
"""
import ast
import operator
import re

CODE = re.compile(r'\d{6}\.(?:XSHG|XSHE|SH|SZ)$')
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.FloorDiv: operator.floordiv}

def automatic_requirements(source, extras=None, benchmark=None):
    tree = ast.parse(source)
    extras = extras or {}
    unsupported = {'get_all_securities', 'get_index_stocks', 'get_fundamentals'}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            if name in unsupported:
                raise ValueError('当前策略使用 '+name+'；该动态选股/财务数据接口尚未支持本地缓存预准备，系统不会启动在线回测。')
    securities = set()
    def collect(value):
        if isinstance(value, str) and CODE.fullmatch(value):
            securities.add(value.replace('.SH', '.XSHG').replace('.SZ', '.XSHE'))
        elif isinstance(value, dict):
            for key, item in value.items():collect(key);collect(item)
        elif isinstance(value, (list, tuple)):
            for item in value:collect(item)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):collect(node.value)
    collect(extras)
    collect(benchmark)
    definitions = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                definitions.setdefault(ast.unparse(target), []).append(node.value)

    def value(node, visiting=frozenset()):
        key = ast.unparse(node)
        if key in visiting:raise ValueError('cyclic expression')
        visiting = visiting | {key}
        if isinstance(node, ast.Constant):return node.value
        if isinstance(node, (ast.List, ast.Tuple)):return [value(v, visiting) for v in node.elts]
        if isinstance(node, ast.Dict):
            result = {value(k, visiting): value(v, visiting) for k, v in zip(node.keys, node.values)}
            return dict(result, **{k:v for k,v in extras.items() if k in result})
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == 'dict' and not node.args and all(k.arg for k in node.keywords):
                result = {k.arg:value(k.value, visiting) for k in node.keywords}
                return dict(result, **{k:v for k,v in extras.items() if k in result})
            if node.func.id in {'max', 'min'} and not node.keywords:
                values = [value(v, visiting) for v in node.args]
                return (max if node.func.id == 'max' else min)(*values)
        if isinstance(node, ast.Subscript):return value(node.value, visiting)[value(node.slice, visiting)]
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            left, right = value(node.left, visiting), value(node.right, visiting)
            if type(left) is not int or type(right) is not int or abs(left)>100000 or abs(right)>100000:
                raise ValueError('non-bounded integer expression')
            return OPS[type(node.op)](left, right)
        if isinstance(node, (ast.Name, ast.Attribute)) and key in definitions:
            choices = [value(v, visiting) for v in definitions[key]]
            if all(v == choices[0] for v in choices):return choices[0]
        raise ValueError('dynamic expression')

    counts = [60]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):continue
        name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
        if name not in {'attribute_history', 'history', 'get_price', 'get_bars', 'get_trade_days'}:continue
        count = next((k.value for k in node.keywords if k.arg == 'count'), None)
        if count is None and name in {'attribute_history', 'get_bars'} and len(node.args)>1:count=node.args[1]
        if count is None and name == 'history' and node.args:count=node.args[0]
        if count is not None:
            try:
                bars = value(count)
                if type(bars) is not int or bars < 1:raise ValueError('invalid count')
            except (ValueError, TypeError, KeyError, IndexError, ZeroDivisionError):bars=5000
            counts.append(bars)
    if not securities:
        raise ValueError('系统无法自动识别该策略的证券范围；当前动态选股数据接口尚未支持本地预准备。策略源码无需添加缓存声明。')
    if len(securities)>100 or max(counts)>5000:
        raise ValueError('该策略超出当前本地缓存适配范围（100只证券、5000根历史窗口），系统未启动回测。')
    return {'securities':sorted(securities), 'warmup_bars':max(counts)}

def resolve_requirements(source, explicit=None, extras=None, benchmark=None):
    from .prepared import requirements
    tree = ast.parse(source)
    declared = any(
        isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id=='DATA_REQUIREMENTS' for t in n.targets)
        or isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id=='DATA_REQUIREMENTS'
        for n in tree.body)
    if explicit is not None or declared:
        return requirements(source, explicit), 'declared'
    return automatic_requirements(source, extras, benchmark), 'automatic'

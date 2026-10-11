"""Resolve UI automatic data mode without executing or guessing strategy code."""
import ast
import re
from .prepared import requirements

def data_mode(source,mode,frequency,explicit=None,benchmark=None):
    reason=None
    if mode=='auto':
        try:tree=ast.parse(source)
        except SyntaxError as error:raise ValueError(f'策略语法错误：第{error.lineno}行，{error.msg}') from error
        declared=any(isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DATA_REQUIREMENTS' for t in node.targets) or isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name) and node.target.id=='DATA_REQUIREMENTS' for node in tree.body)
        if frequency=='day' and (explicit is not None or declared):
            mode='prepared';reason='已声明固定证券池：先准备数据，再本地回测'
        else:
            mode='record';reason='分钟策略或未声明固定数据需求：按需查询QMT并记录数据用于回放'
    if mode=='prepared':
        if frequency!='day':raise ValueError('预准备模式目前仅支持日频；分钟策略请选择自动模式或记录模式')
        if benchmark and not re.fullmatch(r'\d{6}\.(XSHG|XSHE)',benchmark):raise ValueError('预准备模式的基准代码应使用000300.XSHG等格式')
        try:requirements(source,explicit)
        except (ValueError,TypeError,SyntaxError) as error:
            raise ValueError("预准备模式需要固定数据需求。请在设置中选择自动模式，或填写数据需求，例如 {'securities': ['510300.XSHG'], 'warmup_bars': 84}。证券池须覆盖策略可能查询的全部标的，warmup_bars须覆盖历史窗口（60至5000）。"+f' 原因：{error}') from error
    return mode,reason

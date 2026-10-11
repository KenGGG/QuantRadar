"""Force new backtests through verified local data preparation."""
import ast
import re
from .prepared import requirements

def data_mode(source,mode,frequency,explicit=None,benchmark=None):
    reason=None
    if mode in {'auto','live','record','prepared'}:
        try:ast.parse(source)
        except SyntaxError as error:raise ValueError(f'策略语法错误：第{error.lineno}行，{error.msg}') from error
        mode='prepared';reason='强制数据准备：缓存校验通过后才启动纯本地回测'
    if mode=='prepared':
        if frequency!='day':raise ValueError('所有回测必须先缓存数据。分钟数据预准备尚未支持，不能启动分钟回测，也不会退回在线查询。')
        if benchmark and not re.fullmatch(r'\d{6}\.(XSHG|XSHE)',benchmark):raise ValueError('预准备模式的基准代码应使用000300.XSHG等格式')
        try:requirements(source,explicit)
        except (ValueError,TypeError,SyntaxError) as error:
            raise ValueError("所有回测必须先缓存数据。请在策略设置填写数据需求 JSON，或声明 DATA_REQUIREMENTS，例如 {'securities': ['510300.XSHG'], 'warmup_bars': 84}。证券池须覆盖策略可能查询的全部标的，warmup_bars须覆盖历史窗口（60至5000）。无法确定完整需求时不会启动回测。"+f' 原因：{error}') from error
    return mode,reason

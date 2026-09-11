"""Narrow JoinQuant valuation bridge: explicit universe, pinned local data only."""
from datetime import datetime
import pandas as pd
from sqlalchemy.dialects import mysql
from sqlalchemy.sql import visitors, operators
from sqlalchemy.sql.elements import BinaryExpression, TextClause

FIELDS = {'code': 'code', 'pe_ratio': 'pe_ttm', 'pb_ratio': 'pb_mrq', 'ps_ratio': 'ps_ttm'}


class DataUnavailable(NotImplementedError):
    """BulletTrade propagates this instead of swallowing it as an empty frame."""


def fundamentals(provider, query_object, date=None, statDate=None):
    if statDate is not None:
        raise DataUnavailable('本地估值仅支持 date，不支持财报 statDate')
    reader = getattr(provider, '_supplemental_reader', None)
    scope = getattr(provider, '_release_scope', None)
    if reader is None or scope is None:
        raise DataUnavailable('本次运行未绑定可用的补充数据版本')
    statement = getattr(query_object, 'statement', None)
    if statement is None:
        raise DataUnavailable('仅支持 query(valuation.code, valuation.pe_ratio/pb_ratio/ps_ratio)')
    nodes = list(visitors.iterate(statement))
    if any(getattr(c, 'table', None) is None or getattr(c.table, 'name', '') != 'stock_valuation' for c in statement.selected_columns):
        raise DataUnavailable('当前仅支持直接选择估值字段，不支持 SQL 表达式')
    if any(isinstance(n, TextClause) for n in nodes) or any(t.name != 'stock_valuation' for t in statement.get_final_froms()):
        raise DataUnavailable('本地仅支持估值查询；不支持自定义 SQL、联表或其他财务表')
    columns = [n for n in nodes if getattr(n, 'table', None) is not None and getattr(n.table, 'name', '') == 'stock_valuation']
    names = {n.name for n in columns}
    if not names <= set(FIELDS):
        raise DataUnavailable(f'当前版本不支持字段：{sorted(names - set(FIELDS))}；NCF 与 OCF 不能替换')
    codes = None
    for node in nodes:
        if isinstance(node, BinaryExpression) and getattr(node.left, 'name', None) == 'code':
            value = getattr(node.right, 'value', None)
            if node.operator is operators.in_op and isinstance(value, (list, tuple)):
                codes = set(value) if codes is None else codes & set(value)
            elif node.operator is operators.eq and isinstance(value, str):
                codes = {value} if codes is None else codes & {value}
            else:
                raise DataUnavailable('股票范围只支持 code == 或 code.in_')
    if not codes or any(getattr(n, 'operator', None) is operators.or_ for n in nodes):
        raise DataUnavailable('估值查询请明确 code.in_(股票池)；系统不会用下载成功的股票替换你的股票池')
    from ..providers.investment_data.symbols import to_ts_symbol
    symbols = {to_ts_symbol(code) for code in codes}
    isolated = scope.manifest.get('metadata', {}).get('isolated', {})
    blocked = symbols & isolated.keys()
    if blocked:
        raise DataUnavailable(f'当前版本隔离了这些股票的估值：{sorted(blocked)}')
    if 'pcf_ncf_ttm' in str(scope.manifest.get('datasets', {}).get('valuation_daily', {})) or 'baostock' in str(scope.manifest.get('datasets', {}).get('valuation_daily', {}).get('source', [])):
        raise DataUnavailable('该历史版本使用旧估值口径，仅保留回放，不提供新规范估值字段')
    if date is None:
        raise DataUnavailable('估值查询必须指定历史日期')
    day = str(date)[:10]
    days = provider.get_trade_days(end_date=day, count=1)
    if not days:
        raise DataUnavailable(f'缺少交易日历：{day}')
    day = str(days[-1])[:10]
    marks = ','.join(['%s'] * len(symbols))
    rows = reader._query(f'SELECT symbol, pe_ttm, pb_mrq, ps_ttm, pit_status FROM qr_valuation_daily WHERE trade_date=%s AND symbol IN ({marks})', (day, *sorted(symbols)))
    observed = {r['symbol']: r for r in rows}
    missing = symbols - observed.keys()
    required = {FIELDS[n] for n in names if n != 'code'}
    missing |= {s for s, row in observed.items() if any(row.get(f) is None for f in required)}
    if missing:
        raise DataUnavailable(f'{day} 缺少必需估值记录或字段：{sorted(missing)}')
    if getattr(query_object, 'quantradar_require_pit', False) and any(r.get('pit_status') != 'PASS' for r in rows):
        raise DataUnavailable('当前估值不满足严格 PIT')
    compiled = statement.compile(dialect=mysql.dialect(), compile_kwargs={'render_postcompile': True})
    sql = str(compiled)
    if sql.count('FROM stock_valuation') != 1:
        raise DataUnavailable('该查询结构尚不支持')
    derived = "(SELECT CONCAT(LEFT(symbol,6), CASE RIGHT(symbol,2) WHEN 'SH' THEN '.XSHG' ELSE '.XSHE' END) AS code, pe_ttm AS pe_ratio, pb_mrq AS pb_ratio, ps_ttm AS ps_ratio FROM qr_valuation_daily WHERE trade_date=%s) AS stock_valuation"
    sql = sql.replace('FROM stock_valuation', 'FROM ' + derived)
    values = (day, *(compiled.params[k] for k in compiled.positiontup))
    frame = pd.DataFrame(reader._query(sql, values), columns=[c.name for c in statement.selected_columns])
    frame.attrs.update(release_id=scope.release_id, pit_status='PARTIAL')
    return frame


def industry(provider, securities, date=None):
    from ..providers.investment_data.symbols import to_ts_symbol, to_joinquant_symbol
    reader = getattr(provider, '_supplemental_reader', None)
    if not reader or date is None:
        raise DataUnavailable('行业查询需要固定版本与历史日期')
    symbols = [to_ts_symbol(s) for s in ([securities] if isinstance(securities, str) else securities)]
    result = {}
    for symbol in symbols:
        value = reader.industry_as_of(symbol, str(date)[:10])
        if not value:
            raise DataUnavailable(f'{date} 缺少 {symbol} 的行业记录')
        result[to_joinquant_symbol(symbol)] = {'sw_l1': {'industry_code': value['industry_code'], 'industry_name': None}, 'pit_status': value['pit_status']}
    return result

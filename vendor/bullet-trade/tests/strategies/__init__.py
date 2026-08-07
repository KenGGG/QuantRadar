"""
策略测试包

此目录用于存放策略测试用例。
每个策略文件应该包含标准的聚宽策略函数：
- initialize(context): 初始化函数
- handle_data(context, data): 每个交易bar调用的函数（可选）
- process_initialize(context): 模拟盘/实盘初始化（可选）
- after_trading_end(context): 收盘后调用（可选）

策略文件还可以定义一个 STRATEGY_CONFIG 字典来配置测试参数：
STRATEGY_CONFIG = {
    'start_date': '2023-01-01',
    'end_date': '2023-12-31',
    'capital_base': 100000,
    'frequency': 'daily',
    'benchmark': '000300.XSHG',
    # 可选的验证规则
    'expected': {
        'total_returns': {'min': 0.0},  # 期望总收益率 >= 0
        'max_drawdown': {'max': -0.3},   # 期望最大回撤 <= 30%
    }
}
"""


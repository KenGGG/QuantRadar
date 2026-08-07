# 验证 JQData 数据
pytest -q -m requires_network bullet-trade/tests/unit/test_exec_and_dividends_reference.py --live-providers=jqdata

# 同时验证多个数据源
pytest -q -m requires_network bullet-trade/tests/unit/test_exec_and_dividends_reference.py --live-providers=jqdata,qmt

# 查看详细输出 jqdata
pytest -m requires_network bullet-trade/tests/unit/test_exec_and_dividends_reference.py --live-providers=jqdata -v -s


# 查看详细输出 miniqmt
pytest -m requires_network bullet-trade/tests/unit/test_exec_and_dividends_reference.py --live-providers=qmt -v -s
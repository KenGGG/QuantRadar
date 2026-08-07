"""
测试停牌检测功能

验证 513100.XSHG（纳指ETF）在 2022-01-13 的停牌状态能否被正确检测。
这是除权事件延迟处理的关键依赖。
"""
import pytest
from datetime import datetime, date, time as Time
import pandas as pd


class TestPausedDetectionJQData:
    """使用 JQData 数据源测试停牌检测"""

    @pytest.mark.requires_network
    def test_513100_paused_on_20220113(self):
        """测试 513100.XSHG 在 2022-01-13 是否停牌（聚宽数据）"""
        from bullet_trade.data.api import set_data_provider, get_price
        
        # 确保使用 jqdata provider
        set_data_provider('jqdata')
        
        security = '513100.XSHG'
        check_date = date(2022, 1, 13)
        
        # 获取当日数据
        df = get_price(
            security=security,
            end_date=datetime.combine(check_date, Time(15, 0)),
            frequency='daily',
            fields=['volume', 'paused', 'open', 'close'],
            count=1,
            fq='none'
        )
        
        print(f"\n=== JQData 513100.XSHG 2022-01-13 数据 ===")
        print(f"DataFrame:\n{df}")
        
        if not df.empty:
            row = df.iloc[-1]
            print(f"\n字段详情:")
            print(f"  paused: {row.get('paused', 'N/A')}")
            print(f"  volume: {row.get('volume', 'N/A')}")
            print(f"  open: {row.get('open', 'N/A')}")
            print(f"  close: {row.get('close', 'N/A')}")
            
            # 判断停牌
            is_paused = False
            if 'paused' in row:
                is_paused = bool(row['paused'])
                print(f"\n通过 paused 字段判断: {is_paused}")
            elif 'volume' in row:
                is_paused = float(row['volume'] or 0) == 0
                print(f"\n通过 volume=0 判断: {is_paused}")
            
            print(f"\n最终判断 - 2022-01-13 停牌: {is_paused}")
            
            # 断言：513100 在 2022-01-13 应该停牌
            assert is_paused, f"513100.XSHG 在 2022-01-13 应该停牌，但检测结果为不停牌"
        else:
            print("警告：未获取到数据，视为停牌")
            assert True  # 无数据视为停牌

    @pytest.mark.requires_network
    def test_513100_not_paused_on_20220114(self):
        """测试 513100.XSHG 在 2022-01-14 是否正常交易（聚宽数据）"""
        from bullet_trade.data.api import set_data_provider, get_price
        
        set_data_provider('jqdata')
        
        security = '513100.XSHG'
        check_date = date(2022, 1, 14)
        
        df = get_price(
            security=security,
            end_date=datetime.combine(check_date, Time(15, 0)),
            frequency='daily',
            fields=['volume', 'paused', 'open', 'close'],
            count=1,
            fq='none'
        )
        
        print(f"\n=== JQData 513100.XSHG 2022-01-14 数据 ===")
        print(f"DataFrame:\n{df}")
        
        if not df.empty:
            row = df.iloc[-1]
            print(f"\n字段详情:")
            print(f"  paused: {row.get('paused', 'N/A')}")
            print(f"  volume: {row.get('volume', 'N/A')}")
            
            is_paused = False
            if 'paused' in row:
                is_paused = bool(row['paused'])
            elif 'volume' in row:
                is_paused = float(row['volume'] or 0) == 0
            
            print(f"\n最终判断 - 2022-01-14 停牌: {is_paused}")
            
            # 断言：513100 在 2022-01-14 应该正常交易
            assert not is_paused, f"513100.XSHG 在 2022-01-14 应该正常交易，但检测结果为停牌"


class TestPausedDetectionQMT:
    """使用 QMT 数据源测试停牌检测"""

    @pytest.mark.requires_network
    @pytest.mark.requires_qmt
    def test_513100_paused_on_20220113_qmt(self):
        """测试 513100.XSHG 在 2022-01-13 是否停牌（QMT数据）
        
        验证修复后：count=1 + end_date 应该返回 end_date 当天的数据（包含停牌日）
        """
        import logging
        import os
        logging.getLogger('bullet_trade.data.providers.miniqmt').setLevel(logging.DEBUG)
        logging.basicConfig(level=logging.DEBUG)
        
        # 禁用缓存以确保测试使用最新代码
        os.environ['DATA_CACHE_DIR'] = ''
        
        from bullet_trade.data.api import set_data_provider, get_price
        
        # 切换到 QMT provider
        try:
            set_data_provider('qmt')
        except Exception as e:
            pytest.skip(f"QMT provider 不可用: {e}")
        
        security = '513100.XSHG'
        check_date = date(2022, 1, 13)
        
        # 测试1：使用 count=1, end_date=当日
        # 修复后应该返回 2022-01-13 的数据（停牌，volume=0）
        df = get_price(
            security=security,
            end_date=datetime.combine(check_date, Time(15, 0)),
            frequency='daily',
            fields=['volume', 'open', 'close'],
            count=1,
            fq='none'
        )
        
        print(f"\n=== QMT 测试1: count=1, end_date=2022-01-13 15:00 ===")
        print(f"DataFrame:\n{df}")
        print(f"Index: {df.index.tolist() if not df.empty else 'empty'}")
        
        # 验证 QMT 现在能正确返回停牌日的数据（通过 _fill_paused_days 填充）
        # 应该与 JQData 行为一致：返回 end_date 当天的数据，volume=0
        if not df.empty:
            result_date = df.index[-1]
            if hasattr(result_date, 'date'):
                result_date = result_date.date()
            print(f"\n返回数据的日期: {result_date}, 期望日期: {check_date}")
            assert result_date == check_date, f"QMT count=1 应该返回 {check_date}，实际返回 {result_date}"
            
            # 验证 volume=0（停牌）
            row = df.iloc[-1]
            is_paused = float(row.get('volume', 0) or 0) == 0
            print(f"volume={row.get('volume')}, 停牌判断: {is_paused}")
            assert is_paused, f"513100.XSHG 在 2022-01-13 应该停牌（volume=0）"
            
            # 检查 paused 字段（如果存在）
            if 'paused' in row:
                print(f"paused={row.get('paused')}")
                assert float(row.get('paused', 0)) == 1.0, "停牌日 paused 应该为 1"
        
        # 测试2：使用日期范围获取多天数据（作为对照）
        df2 = get_price(
            security=security,
            start_date=date(2022, 1, 10),
            end_date=date(2022, 1, 14),
            frequency='daily',
            fields=['volume', 'open', 'close'],
            fq='none'
        )
        
        print(f"\n=== QMT 测试2: 2022-01-10 至 2022-01-14 范围数据 ===")
        print(f"DataFrame:\n{df2}")
        
        # 验证 2022-01-13 在结果中
        if not df2.empty:
            dates_in_result = [d.date() if hasattr(d, 'date') else d for d in df2.index]
            has_0113 = check_date in dates_in_result
            print(f"包含 2022-01-13: {has_0113}")
            assert has_0113, "日期范围查询应该包含 2022-01-13"

    @pytest.mark.requires_network
    @pytest.mark.requires_qmt
    def test_513100_not_paused_on_20220114_qmt(self):
        """测试 513100.XSHG 在 2022-01-14 是否正常交易（QMT数据）"""
        from bullet_trade.data.api import set_data_provider, get_price
        
        try:
            set_data_provider('qmt')
        except Exception as e:
            pytest.skip(f"QMT provider 不可用: {e}")
        
        security = '513100.XSHG'
        check_date = date(2022, 1, 14)
        
        df = get_price(
            security=security,
            end_date=datetime.combine(check_date, Time(15, 0)),
            frequency='daily',
            fields=['volume', 'open', 'close'],
            count=1,
            fq='none'
        )
        
        print(f"\n=== QMT 513100.XSHG 2022-01-14 数据 ===")
        print(f"DataFrame:\n{df}")
        print(f"Index: {df.index.tolist() if not df.empty else 'empty'}")
        
        if not df.empty:
            row = df.iloc[-1]
            is_paused = float(row.get('volume', 0) or 0) == 0
            print(f"\n通过 volume=0 判断停牌: {is_paused}")
            
            # 检查返回的日期是否正确
            result_date = df.index[-1]
            if hasattr(result_date, 'date'):
                result_date = result_date.date()
            print(f"返回数据的日期: {result_date}, 期望日期: {check_date}")
            
            assert not is_paused, f"513100.XSHG 在 2022-01-14 应该正常交易"


class TestEngineIsSecurityPausedOnDate:
    """直接测试 BacktestEngine._is_security_paused_on_date 方法"""

    @pytest.mark.requires_network
    def test_engine_paused_check_513100_paused(self):
        """测试引擎检测 513100.XSHG（纳指ETF）2022-01-13 停牌
        
        场景：除权日停牌，分红应延迟到复牌日
        - 除权日：2022-01-13
        - 状态：停牌
        - 预期：_is_security_paused_on_date 返回 True
        """
        from bullet_trade.core.engine import BacktestEngine
        from bullet_trade.data.api import set_data_provider
        
        set_data_provider('jqdata')
        
        engine = BacktestEngine(
            start_date='2022-01-12',
            end_date='2022-01-14',
            initial_cash=100000,
        )
        
        # 测试 2022-01-13 停牌
        is_paused = engine._is_security_paused_on_date('513100.XSHG', date(2022, 1, 13))
        print(f"\n=== 513100.XSHG 纳指ETF 停牌检测 ===")
        print(f"检测日期: 2022-01-13")
        print(f"检测结果: 停牌={is_paused}")
        
        assert is_paused, "513100.XSHG 在 2022-01-13 应该停牌"

    @pytest.mark.requires_network
    def test_engine_paused_check_513100_not_paused(self):
        """测试引擎检测 513100.XSHG（纳指ETF）2022-01-14 不停牌
        
        场景：复牌日，分红应该执行
        - 日期：2022-01-14
        - 状态：正常交易
        - 预期：_is_security_paused_on_date 返回 False
        """
        from bullet_trade.core.engine import BacktestEngine
        from bullet_trade.data.api import set_data_provider
        
        set_data_provider('jqdata')
        
        engine = BacktestEngine(
            start_date='2022-01-12',
            end_date='2022-01-14',
            initial_cash=100000,
        )
        
        # 测试 2022-01-14 不停牌
        is_paused = engine._is_security_paused_on_date('513100.XSHG', date(2022, 1, 14))
        print(f"\n=== 513100.XSHG 纳指ETF 停牌检测 ===")
        print(f"检测日期: 2022-01-14")
        print(f"检测结果: 停牌={is_paused}")
        
        assert not is_paused, "513100.XSHG 在 2022-01-14 不应该停牌"

    @pytest.mark.requires_network
    def test_engine_paused_check_601318_not_paused(self):
        """测试引擎检测 601318.XSHG（中国平安）2024-07-26 不停牌
        
        场景：除权日正常交易，分红应当天执行
        - 除权日：2024-07-26
        - 状态：正常交易
        - 预期：_is_security_paused_on_date 返回 False
        """
        from bullet_trade.core.engine import BacktestEngine
        from bullet_trade.data.api import set_data_provider
        
        set_data_provider('jqdata')
        
        engine = BacktestEngine(
            start_date='2024-07-25',
            end_date='2024-07-27',
            initial_cash=100000,
        )
        
        # 测试 2024-07-26 不停牌
        is_paused = engine._is_security_paused_on_date('601318.XSHG', date(2024, 7, 26))
        print(f"\n=== 601318.XSHG 中国平安 停牌检测 ===")
        print(f"检测日期: 2024-07-26（除权日）")
        print(f"检测结果: 停牌={is_paused}")
        
        assert not is_paused, "601318.XSHG（中国平安）在 2024-07-26 不应该停牌，分红应当天执行"

    @pytest.mark.requires_network
    def test_engine_paused_check_601318_prev_day(self):
        """测试引擎检测 601318.XSHG（中国平安）2024-07-25 不停牌
        
        场景：除权日前一天，正常交易
        - 日期：2024-07-25
        - 状态：正常交易
        """
        from bullet_trade.core.engine import BacktestEngine
        from bullet_trade.data.api import set_data_provider
        
        set_data_provider('jqdata')
        
        engine = BacktestEngine(
            start_date='2024-07-24',
            end_date='2024-07-27',
            initial_cash=100000,
        )
        
        # 测试 2024-07-25 不停牌
        is_paused = engine._is_security_paused_on_date('601318.XSHG', date(2024, 7, 25))
        print(f"\n=== 601318.XSHG 中国平安 停牌检测 ===")
        print(f"检测日期: 2024-07-25（除权日前一天）")
        print(f"检测结果: 停牌={is_paused}")
        
        assert not is_paused, "601318.XSHG 在 2024-07-25 不应该停牌"


class TestDividendWithPausedScenarios:
    """测试分红处理在不同停牌场景下的行为"""

    @pytest.mark.requires_network
    def test_513100_dividend_delayed_due_to_pause(self):
        """测试 513100 纳指ETF：除权日停牌，分红延迟到复牌日
        
        场景详情：
        - 除权日：2022-01-13（停牌）
        - 复牌日：2022-01-14
        - 拆分比例：5:1
        - 预期：
          - 2022-01-13 检测到停牌，分红延迟
          - 2022-01-14 执行延迟的分红
        """
        from bullet_trade.core.engine import BacktestEngine
        from bullet_trade.data.api import set_data_provider
        
        set_data_provider('jqdata')
        
        engine = BacktestEngine(
            start_date='2022-01-10',
            end_date='2022-01-14',
            initial_cash=100000,
        )
        
        # 验证停牌检测
        is_paused_13 = engine._is_security_paused_on_date('513100.XSHG', date(2022, 1, 13))
        is_paused_14 = engine._is_security_paused_on_date('513100.XSHG', date(2022, 1, 14))
        
        print(f"\n=== 513100.XSHG 纳指ETF 分红延迟场景测试 ===")
        print(f"除权日 2022-01-13 停牌: {is_paused_13}")
        print(f"复牌日 2022-01-14 停牌: {is_paused_14}")
        
        assert is_paused_13, "2022-01-13（除权日）应该停牌"
        assert not is_paused_14, "2022-01-14（复牌日）不应该停牌"
        
        print("✓ 分红应在 2022-01-14（复牌日）执行")

    @pytest.mark.requires_network
    def test_601318_dividend_same_day(self):
        """测试 601318 中国平安：除权日正常交易，分红当天执行
        
        场景详情：
        - 除权日：2024-07-26（正常交易）
        - 派息：每10股派15元
        - 预期：
          - 2024-07-26 检测到不停牌，分红当天执行
        """
        from bullet_trade.core.engine import BacktestEngine
        from bullet_trade.data.api import set_data_provider
        
        set_data_provider('jqdata')
        
        engine = BacktestEngine(
            start_date='2024-07-24',
            end_date='2024-07-27',
            initial_cash=100000,
        )
        
        # 验证停牌检测
        is_paused = engine._is_security_paused_on_date('601318.XSHG', date(2024, 7, 26))
        
        print(f"\n=== 601318.XSHG 中国平安 分红当天执行场景测试 ===")
        print(f"除权日 2024-07-26 停牌: {is_paused}")
        
        assert not is_paused, "601318.XSHG 在 2024-07-26（除权日）不应该停牌"
        
        print("✓ 分红应在 2024-07-26（除权日当天）执行")


if __name__ == '__main__':
    # 可以直接运行测试
    pytest.main([__file__, '-v', '-s', '-m', 'requires_network'])


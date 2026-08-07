"""
测试模拟券商

单元测试：测试模拟券商的各项功能
"""

import pytest
from bullet_trade.broker.simulator import SimulatorBroker


@pytest.mark.unit
class TestSimulatorBroker:
    """模拟券商测试"""
    
    def test_init(self):
        """测试初始化"""
        broker = SimulatorBroker(initial_cash=100000)
        
        assert broker.account_id == 'simulator'
        assert broker.account_type == 'stock'
        assert broker.initial_cash == 100000
        assert broker.available_cash == 100000
        assert len(broker.positions) == 0
    
    def test_connect_disconnect(self):
        """测试连接和断开"""
        broker = SimulatorBroker()
        
        assert not broker.is_connected()
        
        assert broker.connect()
        assert broker.is_connected()
        
        assert broker.disconnect()
        assert not broker.is_connected()
    
    @pytest.mark.asyncio
    async def test_buy(self):
        """测试买入"""
        broker = SimulatorBroker(initial_cash=100000)
        broker.set_mock_price('000001.XSHE', 10.0)
        
        # 买入
        order_id = await broker.buy('000001.XSHE', 1000, price=10.0)
        
        assert order_id
        assert '000001.XSHE' in broker.positions
        assert broker.positions['000001.XSHE']['amount'] == 1000
        assert broker.available_cash < 100000  # 扣除了资金
    
    @pytest.mark.asyncio
    async def test_sell(self):
        """测试卖出"""
        broker = SimulatorBroker(initial_cash=100000)
        broker.set_mock_price('000001.XSHE', 10.0)
        
        # 先买入
        await broker.buy('000001.XSHE', 1000, price=10.0)
        cash_after_buy = broker.available_cash
        
        # 再卖出
        await broker.sell('000001.XSHE', 500, price=10.0)
        
        assert broker.positions['000001.XSHE']['amount'] == 500
        assert broker.available_cash > cash_after_buy  # 增加了资金
    
    @pytest.mark.asyncio
    async def test_sell_all(self):
        """测试全部卖出"""
        broker = SimulatorBroker(initial_cash=100000)
        broker.set_mock_price('000001.XSHE', 10.0)
        
        # 买入
        await broker.buy('000001.XSHE', 1000, price=10.0)
        
        # 全部卖出
        await broker.sell('000001.XSHE', 1000, price=10.0)
        
        assert '000001.XSHE' not in broker.positions
    
    @pytest.mark.asyncio
    async def test_insufficient_cash(self):
        """测试资金不足"""
        broker = SimulatorBroker(initial_cash=1000)
        broker.set_mock_price('000001.XSHE', 10.0)
        
        # 尝试买入过多
        with pytest.raises(ValueError, match="可用资金不足"):
            await broker.buy('000001.XSHE', 1000, price=10.0)
    
    @pytest.mark.asyncio
    async def test_insufficient_position(self):
        """测试持仓不足"""
        broker = SimulatorBroker(initial_cash=100000)
        
        # 尝试卖出不存在的持仓
        with pytest.raises(ValueError, match="持仓不足"):
            await broker.sell('000001.XSHE', 100, price=10.0)
    
    @pytest.mark.asyncio
    async def test_get_account_info(self):
        """测试获取账户信息"""
        broker = SimulatorBroker(initial_cash=100000)
        broker.set_mock_price('000001.XSHE', 10.0)
        
        # 买入一些股票
        await broker.buy('000001.XSHE', 1000, price=10.0)
        
        # 获取账户信息
        info = broker.get_account_info()
        
        assert 'total_value' in info
        assert 'available_cash' in info
        assert 'positions' in info
        assert len(info['positions']) == 1
    
    @pytest.mark.asyncio
    async def test_get_positions(self):
        """测试获取持仓"""
        broker = SimulatorBroker(initial_cash=100000)
        broker.set_mock_price('000001.XSHE', 10.0)
        broker.set_mock_price('600000.XSHG', 20.0)
        
        # 买入多个股票
        await broker.buy('000001.XSHE', 1000, price=10.0)
        await broker.buy('600000.XSHG', 500, price=20.0)
        
        # 获取持仓
        positions = broker.get_positions()
        
        assert len(positions) == 2
        assert any(p['security'] == '000001.XSHE' for p in positions)
        assert any(p['security'] == '600000.XSHG' for p in positions)
    
    @pytest.mark.asyncio
    async def test_get_order_status(self):
        """测试获取订单状态"""
        broker = SimulatorBroker(initial_cash=100000)
        broker.set_mock_price('000001.XSHE', 10.0)
        
        # 下单
        order_id = await broker.buy('000001.XSHE', 1000, price=10.0)
        
        # 获取订单状态
        order = await broker.get_order_status(order_id)
        
        assert order['order_id'] == order_id
        assert order['security'] == '000001.XSHE'
        assert order['amount'] == 1000
        assert order['status'] == 'filled'
    
    @pytest.mark.asyncio
    async def test_cancel_order(self):
        """测试撤单"""
        broker = SimulatorBroker(initial_cash=100000)
        broker.set_mock_price('000001.XSHE', 10.0)
        
        # 下单
        order_id = await broker.buy('000001.XSHE', 1000, price=10.0)
        
        # 撤单
        assert await broker.cancel_order(order_id)
        
        # 检查状态
        order = await broker.get_order_status(order_id)
        assert order['status'] == 'cancelled'

"""
事件框架测试

测试 EventLoop, EventBus, Message 等核心组件
"""

import asyncio
import sys
import pytest
from bullet_trade.core.event_loop import EventLoop, UVLOOP_AVAILABLE
from bullet_trade.core.event_bus import EventBus, Event, EventPriority, create_event_class
from bullet_trade.core.message import Message, PriorityQueue, AsyncPriorityQueue
from bullet_trade.core.events import (
    MarketOpenEvent,
    OrderCreatedEvent,
    AccountSyncEvent,
    EveryMinuteEvent,
)


# ============ EventLoop 测试 ============

def test_event_loop_creation():
    """测试事件循环创建"""
    loop = EventLoop(use_uvloop=True)
    
    # 检查是否正确选择了事件循环实现
    if sys.platform != 'win32' and UVLOOP_AVAILABLE:
        assert loop._use_uvloop
        print("✅ 使用 uvloop")
    else:
        assert not loop._use_uvloop
        print("✅ 使用 asyncio")
    
    assert not loop.is_running
    assert not loop.is_closed
    
    loop.close()
    assert loop.is_closed


def test_event_loop_run_until_complete():
    """测试运行协程直到完成"""
    loop = EventLoop()
    
    result = []
    
    async def test_coro():
        result.append("executed")
        return "success"
    
    ret = loop.run_until_complete(test_coro())
    
    assert ret == "success"
    assert result == ["executed"]
    
    loop.close()


def test_event_loop_task_scheduling():
    """测试任务调度"""
    loop = EventLoop()
    
    results = []
    
    async def main():
        # 测试 call_later
        loop.call_later(0.1, lambda: results.append("delayed"))
        
        # 测试 create_task
        async def task_func():
            await asyncio.sleep(0.05)
            results.append("task")
        
        task = loop.create_task(task_func())
        await task
        await asyncio.sleep(0.15)  # 等待 delayed 执行
    
    loop.run_until_complete(main())
    
    assert "task" in results
    assert "delayed" in results
    
    loop.close()


# ============ EventBus 测试 ============

def test_event_bus_subscribe():
    """测试事件订阅"""
    loop = EventLoop()
    bus = EventBus(loop.loop)
    
    called = []
    
    def handler(event):
        called.append(event.data)
    
    bus.subscribe(MarketOpenEvent, handler)
    
    assert bus.has_subscribers(MarketOpenEvent)
    assert bus.get_subscriber_count(MarketOpenEvent) == 1
    
    loop.close()


def test_event_bus_emit():
    """测试事件发布"""
    loop = EventLoop()
    bus = EventBus(loop.loop)
    
    results = []
    
    async def async_handler(event):
        results.append(f"async: {event.time}")
    
    def sync_handler(event):
        results.append(f"sync: {event.time}")
    
    bus.subscribe(MarketOpenEvent, async_handler)
    bus.subscribe(MarketOpenEvent, sync_handler)
    
    async def main():
        await bus.emit(MarketOpenEvent(time="09:30:00"))
    
    loop.run_until_complete(main())
    
    assert len(results) == 2
    assert any("async: 09:30:00" in r for r in results)
    assert any("sync: 09:30:00" in r for r in results)
    
    loop.close()


def test_event_bus_priority():
    """测试事件优先级"""
    loop = EventLoop()
    bus = EventBus(loop.loop)
    
    execution_order = []
    
    async def high_priority_handler(event):
        execution_order.append("high")
    
    async def low_priority_handler(event):
        execution_order.append("low")
    
    # 低优先级先注册
    bus.subscribe(MarketOpenEvent, low_priority_handler, EventPriority.DEFAULT)
    # 高优先级后注册
    bus.subscribe(MarketOpenEvent, high_priority_handler, EventPriority.ORDERS_SYNC)
    
    async def main():
        await bus.emit(MarketOpenEvent(time="09:30:00"))
    
    loop.run_until_complete(main())
    
    # 高优先级应该先执行
    assert execution_order == ["high", "low"]
    
    loop.close()


def test_event_bus_unsubscribe():
    """测试取消订阅"""
    loop = EventLoop()
    bus = EventBus(loop.loop)
    
    def handler(event):
        pass
    
    bus.subscribe(MarketOpenEvent, handler)
    assert bus.has_subscribers(MarketOpenEvent)
    
    bus.unsubscribe(MarketOpenEvent, handler)
    assert not bus.has_subscribers(MarketOpenEvent)
    
    loop.close()


# ============ Message 和 PriorityQueue 测试 ============

def test_message_creation():
    """测试消息创建"""
    msg = Message(
        time=10.0,
        priority=5,
        callback=lambda: print("test"),
        name="test_msg"
    )
    
    assert msg.time == 10.0
    assert msg.priority == -5  # 优先级取负
    assert msg.name == "test_msg"


def test_message_sorting():
    """测试消息排序"""
    msg1 = Message(time=10.0, priority=5, seq_number=1, callback=lambda: None)
    msg2 = Message(time=10.0, priority=3, seq_number=2, callback=lambda: None)
    msg3 = Message(time=9.0, priority=1, seq_number=3, callback=lambda: None)
    
    messages = [msg1, msg2, msg3]
    messages.sort()
    
    # 应该按 time, priority(降序), seq_number 排序
    assert messages[0] == msg3  # 时间最早
    assert messages[1] == msg1  # 时间相同，优先级高
    assert messages[2] == msg2  # 时间相同，优先级低


def test_priority_queue():
    """测试优先级队列"""
    queue = PriorityQueue()
    
    queue.push(Message(time=10.0, priority=1, callback=lambda: "low"))
    queue.push(Message(time=10.0, priority=5, callback=lambda: "high"))
    queue.push(Message(time=9.0, priority=1, callback=lambda: "early"))
    
    assert queue.size() == 3
    
    # 时间最早的先弹出
    msg1 = queue.pop()
    assert msg1.time == 9.0
    
    # 时间相同，优先级高的先弹出
    msg2 = queue.pop()
    assert msg2.time == 10.0
    assert -msg2.priority == 5  # priority 被取负了
    
    msg3 = queue.pop()
    assert msg3.time == 10.0
    assert -msg3.priority == 1
    
    assert queue.empty()


@pytest.mark.asyncio
async def test_async_priority_queue():
    """测试异步优先级队列"""
    queue = AsyncPriorityQueue()
    
    await queue.put(Message(time=10.0, priority=1, callback=lambda: "low"))
    await queue.put(Message(time=10.0, priority=5, callback=lambda: "high"))
    
    assert queue.qsize() == 2
    
    # 优先级高的先弹出
    msg1 = await queue.get()
    assert -msg1.priority == 5
    
    msg2 = await queue.get()
    assert -msg2.priority == 1
    
    assert queue.empty()


# ============ 预定义事件测试 ============

def test_predefined_events():
    """测试预定义事件"""
    # 测试各种事件的创建
    market_open = MarketOpenEvent(time="09:30:00")
    assert market_open.time == "09:30:00"
    assert market_open.priority == EventPriority.EVERY_MINUTE
    
    order_created = OrderCreatedEvent(order_id="123", security="000001.XSHE")
    assert order_created.order_id == "123"
    
    account_sync = AccountSyncEvent(timestamp=12345)
    assert account_sync.priority == EventPriority.ACCOUNT_SYNC


def test_create_event_class():
    """测试动态创建事件类"""
    CustomEvent = create_event_class("CustomEvent", EventPriority.DEFAULT)
    
    event = CustomEvent(key="value")
    assert event.key == "value"
    assert event.priority == EventPriority.DEFAULT


# ============ 集成测试 ============

def test_full_event_flow():
    """测试完整的事件流"""
    loop = EventLoop()
    bus = EventBus(loop.loop)
    
    execution_log = []
    
    # 订阅多个事件
    async def on_market_open(event):
        execution_log.append(f"market_open at {event.time}")
        # 触发订单创建事件
        bus.emit_nowait(OrderCreatedEvent(order_id="001", security="000001.XSHE"))
    
    async def on_order_created(event):
        execution_log.append(f"order_created: {event.order_id}")
    
    async def on_account_sync(event):
        execution_log.append("account_sync")
    
    bus.subscribe(MarketOpenEvent, on_market_open, EventPriority.EVERY_MINUTE)
    bus.subscribe(OrderCreatedEvent, on_order_created, EventPriority.DEFAULT)
    bus.subscribe(AccountSyncEvent, on_account_sync, EventPriority.ACCOUNT_SYNC)
    
    async def main():
        # 发布事件
        await bus.emit(MarketOpenEvent(time="09:30:00"))
        await asyncio.sleep(0.1)  # 等待连锁事件
        await bus.emit(AccountSyncEvent(timestamp=12345))
    
    loop.run_until_complete(main())
    
    # 验证执行顺序
    assert "market_open at 09:30:00" in execution_log
    assert "order_created: 001" in execution_log
    assert "account_sync" in execution_log
    
    # 打印日志
    print("\n执行日志:")
    for log in execution_log:
        print(f"  - {log}")
    
    loop.close()


if __name__ == "__main__":
    # 运行测试
    print("🧪 开始测试事件框架...\n")
    
    test_event_loop_creation()
    print("✅ EventLoop 创建测试通过")
    
    test_event_loop_run_until_complete()
    print("✅ EventLoop 运行协程测试通过")
    
    test_event_loop_task_scheduling()
    print("✅ EventLoop 任务调度测试通过")
    
    test_event_bus_subscribe()
    print("✅ EventBus 订阅测试通过")
    
    test_event_bus_emit()
    print("✅ EventBus 发布测试通过")
    
    test_event_bus_priority()
    print("✅ EventBus 优先级测试通过")
    
    test_event_bus_unsubscribe()
    print("✅ EventBus 取消订阅测试通过")
    
    test_message_creation()
    print("✅ Message 创建测试通过")
    
    test_message_sorting()
    print("✅ Message 排序测试通过")
    
    test_priority_queue()
    print("✅ PriorityQueue 测试通过")
    
    test_predefined_events()
    print("✅ 预定义事件测试通过")
    
    test_create_event_class()
    print("✅ 动态创建事件类测试通过")
    
    test_full_event_flow()
    print("✅ 完整事件流测试通过")
    
    print("\n🎉 所有测试通过！")


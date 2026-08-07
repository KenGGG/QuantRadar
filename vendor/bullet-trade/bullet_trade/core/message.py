"""
消息队列模块

实现优先级消息队列，用于事件调度
"""

import heapq
import asyncio
from typing import Any, Callable, Optional, Tuple
from dataclasses import dataclass, field
import logging


logger = logging.getLogger(__name__)


@dataclass(order=True)
class Message:
    """
    消息对象
    
    用于事件循环的调度，支持优先级和时间排序
    
    Attributes:
        time: 执行时间（时间戳）
        priority: 优先级（值越大越先执行）
        seq_number: 序列号（用于相同时间和优先级的排序）
        callback: 回调函数
        args: 回调参数
        kwargs: 回调关键字参数
    
    排序规则：
        1. 时间早的先执行
        2. 时间相同时，优先级高的先执行
        3. 时间和优先级都相同时，序列号小的先执行
    """
    
    # 用于排序的字段（必须放在前面且都要有默认值或都没有）
    time: float
    
    # 不参与排序的字段（必须放在最后）
    callback: Callable = field(compare=False, default=None)
    priority: int = field(compare=True, default=0)
    seq_number: int = field(compare=True, default=0)
    args: tuple = field(compare=False, default_factory=tuple)
    kwargs: dict = field(compare=False, default_factory=dict)
    name: Optional[str] = field(compare=False, default=None)
    
    def __post_init__(self):
        """初始化后处理"""
        # 优先级取负，使得大值先执行
        self.priority = -self.priority
    
    @property
    def sort_key(self) -> Tuple[float, int, int]:
        """获取排序键"""
        return (self.time, self.priority, self.seq_number)
    
    def __repr__(self):
        """字符串表示"""
        name = self.name or self.callback.__name__ if hasattr(self.callback, '__name__') else str(self.callback)
        return f"Message({name} @ {self.time:.2f}, pri={-self.priority})"


class PriorityQueue:
    """
    优先级队列（基于堆实现）
    
    支持按时间和优先级排序的消息队列
    
    Example:
        >>> queue = PriorityQueue()
        >>> queue.push(Message(time=10.0, priority=5, callback=lambda: print("High")))
        >>> queue.push(Message(time=10.0, priority=1, callback=lambda: print("Low")))
        >>> msg = queue.pop()  # 会先返回优先级高的消息
    """
    
    def __init__(self):
        """初始化队列"""
        self._heap = []
        self._seq_number = 0  # 序列号计数器
    
    def push(self, message: Message):
        """
        将消息加入队列
        
        Args:
            message: 消息对象
        """
        # 分配序列号
        if message.seq_number == 0:
            message.seq_number = self._seq_number
            self._seq_number += 1
        
        heapq.heappush(self._heap, message)
        logger.debug(f"📥 队列加入: {message}")
    
    def pop(self) -> Message:
        """
        从队列中取出最高优先级的消息
        
        Returns:
            消息对象
            
        Raises:
            IndexError: 如果队列为空
        """
        if self.empty():
            raise IndexError("队列为空")
        
        message = heapq.heappop(self._heap)
        logger.debug(f"📤 队列弹出: {message}")
        return message
    
    def peek(self) -> Message:
        """
        查看队列顶部消息（不移除）
        
        Returns:
            消息对象
            
        Raises:
            IndexError: 如果队列为空
        """
        if self.empty():
            raise IndexError("队列为空")
        return self._heap[0]
    
    def empty(self) -> bool:
        """检查队列是否为空"""
        return len(self._heap) == 0
    
    def size(self) -> int:
        """获取队列大小"""
        return len(self._heap)
    
    def clear(self):
        """清空队列"""
        count = len(self._heap)
        self._heap.clear()
        logger.info(f"🗑️  清空队列（共 {count} 条消息）")
    
    def __len__(self):
        """获取队列大小"""
        return len(self._heap)
    
    def __repr__(self):
        """字符串表示"""
        return f"<PriorityQueue(size={len(self._heap)})>"


class AsyncPriorityQueue:
    """
    异步优先级队列
    
    基于 asyncio.Queue 的线程安全优先级队列
    
    Example:
        >>> queue = AsyncPriorityQueue()
        >>> await queue.put(Message(time=10.0, priority=5, callback=func))
        >>> message = await queue.get()
    """
    
    def __init__(self, maxsize: int = 0):
        """
        初始化异步队列
        
        Args:
            maxsize: 队列最大容量（0 表示无限）
        """
        self._queue = asyncio.PriorityQueue(maxsize=maxsize)
        self._seq_number = 0
    
    async def put(self, message: Message):
        """
        将消息加入队列（异步）
        
        Args:
            message: 消息对象
        """
        # 分配序列号
        if message.seq_number == 0:
            message.seq_number = self._seq_number
            self._seq_number += 1
        
        await self._queue.put(message)
        logger.debug(f"📥 队列加入: {message}")
    
    def put_nowait(self, message: Message):
        """
        将消息加入队列（非阻塞）
        
        Args:
            message: 消息对象
            
        Raises:
            asyncio.QueueFull: 如果队列已满
        """
        # 分配序列号
        if message.seq_number == 0:
            message.seq_number = self._seq_number
            self._seq_number += 1
        
        self._queue.put_nowait(message)
        logger.debug(f"📥 队列加入: {message}")
    
    async def get(self) -> Message:
        """
        从队列中取出消息（异步）
        
        Returns:
            消息对象
        """
        message = await self._queue.get()
        logger.debug(f"📤 队列弹出: {message}")
        return message
    
    def get_nowait(self) -> Message:
        """
        从队列中取出消息（非阻塞）
        
        Returns:
            消息对象
            
        Raises:
            asyncio.QueueEmpty: 如果队列为空
        """
        message = self._queue.get_nowait()
        logger.debug(f"📤 队列弹出: {message}")
        return message
    
    def task_done(self):
        """标记任务完成"""
        self._queue.task_done()
    
    async def join(self):
        """等待所有任务完成"""
        await self._queue.join()
    
    def empty(self) -> bool:
        """检查队列是否为空"""
        return self._queue.empty()
    
    def full(self) -> bool:
        """检查队列是否已满"""
        return self._queue.full()
    
    def qsize(self) -> int:
        """获取队列大小（近似值）"""
        return self._queue.qsize()
    
    def __repr__(self):
        """字符串表示"""
        return f"<AsyncPriorityQueue(size={self.qsize()})>"


# ============ 工具函数 ============

def create_message(
    time: float,
    callback: Callable,
    priority: int = 0,
    name: Optional[str] = None,
    *args,
    **kwargs
) -> Message:
    """
    创建消息的便捷函数
    
    Args:
        time: 执行时间
        callback: 回调函数
        priority: 优先级
        name: 消息名称
        *args: 回调参数
        **kwargs: 回调关键字参数
        
    Returns:
        Message 对象
    
    Example:
        >>> msg = create_message(10.0, print, priority=5, "Hello", "World")
    """
    return Message(
        time=time,
        priority=priority,
        callback=callback,
        args=args,
        kwargs=kwargs,
        name=name
    )


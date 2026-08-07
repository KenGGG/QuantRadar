"""
事件循环模块

基于 asyncio 的跨平台事件循环实现
- Windows: 使用 asyncio ProactorEventLoop
- macOS/Linux: 优先使用 uvloop，降级到 asyncio
"""

import asyncio
import sys
import signal
from typing import Optional, Callable, Any, Coroutine
import logging

# 尝试导入 uvloop（仅在支持的平台上）
try:
    if sys.platform != 'win32':
        import uvloop
        UVLOOP_AVAILABLE = True
    else:
        UVLOOP_AVAILABLE = False
except ImportError:
    UVLOOP_AVAILABLE = False


logger = logging.getLogger(__name__)


class EventLoop:
    """
    跨平台事件循环
    
    特性：
    - 自动选择最佳事件循环实现（uvloop/asyncio）
    - 支持信号处理和优雅退出
    - 支持同步和异步任务
    - 线程安全
    
    Example:
        >>> loop = EventLoop(use_uvloop=True)
        >>> async def main():
        ...     print("Hello World")
        >>> loop.run_until_complete(main())
    """
    
    def __init__(self, use_uvloop: bool = True, debug: bool = False):
        """
        初始化事件循环
        
        Args:
            use_uvloop: 是否在支持的平台上使用 uvloop
            debug: 是否开启调试模式
        """
        self._use_uvloop = use_uvloop and UVLOOP_AVAILABLE
        self._debug = debug
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._running = False
        self._stop_requested = False
        self._signal_handlers = {}
        
        self._setup_loop()
    
    def _setup_loop(self):
        """设置事件循环"""
        # 选择事件循环策略
        if self._use_uvloop:
            # macOS/Linux 使用 uvloop（高性能）
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
            logger.info("✅ 使用 uvloop 事件循环（高性能模式）")
        else:
            # Windows 或无 uvloop 时使用标准 asyncio
            if sys.platform == 'win32':
                # Windows 专用：ProactorEventLoop 支持子进程和信号
                asyncio.set_event_loop_policy(
                    asyncio.WindowsProactorEventLoopPolicy()
                )
                logger.info("✅ 使用 asyncio ProactorEventLoop（Windows）")
            else:
                logger.info("✅ 使用 asyncio 标准事件循环")
        
        # 创建事件循环
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        # 设置调试模式
        if self._debug:
            self._loop.set_debug(True)
            logger.info("🐛 事件循环调试模式已开启")
        
        # 设置异常处理
        self._loop.set_exception_handler(self._handle_exception)
    
    def _handle_exception(self, loop, context):
        """处理事件循环异常"""
        exception = context.get('exception')
        message = context.get('message', 'Unhandled exception in event loop')
        
        logger.error(f"❌ 事件循环异常: {message}")
        if exception:
            logger.error(f"   异常详情: {exception}", exc_info=exception)
    
    def run_until_complete(self, coro: Coroutine) -> Any:
        """
        运行协程直到完成
        
        Args:
            coro: 要运行的协程
            
        Returns:
            协程的返回值
        """
        try:
            return self._loop.run_until_complete(coro)
        except KeyboardInterrupt:
            logger.info("⚠️  收到键盘中断信号")
            raise
    
    def run_forever(self):
        """
        永久运行事件循环
        
        会一直运行直到调用 stop() 或收到信号
        """
        if self._running:
            logger.warning("⚠️  事件循环已在运行中")
            return
        
        self._running = True
        self._stop_requested = False
        
        try:
            logger.info("🚀 事件循环启动")
            self._loop.run_forever()
        except KeyboardInterrupt:
            logger.info("⚠️  收到键盘中断信号")
        finally:
            self._cleanup()
            self._running = False
            logger.info("🛑 事件循环已停止")
    
    def stop(self):
        """停止事件循环"""
        if not self._running:
            logger.warning("⚠️  事件循环未在运行")
            return
        
        if self._stop_requested:
            logger.warning("⚠️  已请求停止")
            return
        
        self._stop_requested = True
        logger.info("⏸️  正在停止事件循环...")
        
        # 线程安全地停止循环
        self._loop.call_soon_threadsafe(self._loop.stop)
    
    def _cleanup(self):
        """清理资源"""
        # 取消所有未完成的任务
        try:
            pending = asyncio.all_tasks(self._loop)
        except RuntimeError:
            # Python 3.6 兼容
            pending = asyncio.Task.all_tasks(self._loop)
        
        if pending:
            logger.info(f"⏳ 取消 {len(pending)} 个未完成的任务")
            for task in pending:
                task.cancel()
            
            # 等待所有任务取消完成
            self._loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
    
    def close(self):
        """关闭事件循环"""
        if self._running:
            self.stop()
        
        if self._loop and not self._loop.is_closed():
            self._loop.close()
            logger.info("🔒 事件循环已关闭")
    
    # ============ 任务调度 API ============
    
    def create_task(self, coro: Coroutine, name: Optional[str] = None) -> asyncio.Task:
        """
        创建异步任务
        
        Args:
            coro: 协程
            name: 任务名称（可选）
            
        Returns:
            asyncio.Task 对象
        """
        if sys.version_info >= (3, 8) and name:
            return self._loop.create_task(coro, name=name)
        else:
            return self._loop.create_task(coro)
    
    def call_soon(self, callback: Callable, *args):
        """在下一次事件循环迭代时调用回调"""
        return self._loop.call_soon(callback, *args)
    
    def call_later(self, delay: float, callback: Callable, *args):
        """
        延迟调用回调
        
        Args:
            delay: 延迟时间（秒）
            callback: 回调函数
            *args: 回调参数
        """
        return self._loop.call_later(delay, callback, *args)
    
    def call_at(self, when: float, callback: Callable, *args):
        """
        在指定时间调用回调
        
        Args:
            when: 时间戳（loop.time() 返回的时间）
            callback: 回调函数
            *args: 回调参数
        """
        return self._loop.call_at(when, callback, *args)
    
    def run_in_executor(self, executor, func: Callable, *args):
        """
        在线程池中运行同步函数
        
        Args:
            executor: 执行器（None 表示默认线程池）
            func: 同步函数
            *args: 函数参数
            
        Returns:
            Future 对象
        """
        return self._loop.run_in_executor(executor, func, *args)
    
    # ============ 信号处理 API ============
    
    def add_signal_handler(self, sig: signal.Signals, callback: Callable, *args):
        """
        添加信号处理器
        
        Args:
            sig: 信号（如 signal.SIGINT）
            callback: 回调函数
            *args: 回调参数
            
        Note:
            Windows 下信号支持有限
        """
        if sys.platform == 'win32':
            # Windows 下使用简化的信号处理
            signal.signal(sig, lambda s, f: callback(*args))
            logger.info(f"🔔 已注册信号处理器（Windows）: {sig.name}")
        else:
            # Unix 系统使用事件循环的信号处理
            self._loop.add_signal_handler(sig, callback, *args)
            logger.info(f"🔔 已注册信号处理器: {sig.name}")
        
        self._signal_handlers[sig] = callback
    
    def remove_signal_handler(self, sig: signal.Signals):
        """移除信号处理器"""
        if sig in self._signal_handlers:
            if sys.platform != 'win32':
                self._loop.remove_signal_handler(sig)
            del self._signal_handlers[sig]
            logger.info(f"🔕 已移除信号处理器: {sig.name}")
    
    def setup_graceful_shutdown(self):
        """
        设置优雅退出（捕获 SIGINT 和 SIGTERM）
        
        当收到这些信号时，会调用 stop() 停止事件循环
        """
        def shutdown_handler():
            logger.info("🛑 收到退出信号，正在优雅关闭...")
            self.stop()
        
        try:
            self.add_signal_handler(signal.SIGINT, shutdown_handler)
            self.add_signal_handler(signal.SIGTERM, shutdown_handler)
            logger.info("✅ 优雅退出机制已设置")
        except (ValueError, NotImplementedError) as e:
            # 某些平台可能不支持所有信号
            logger.warning(f"⚠️  信号处理设置失败: {e}")
    
    # ============ 属性 ============
    
    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """获取底层事件循环"""
        return self._loop
    
    @property
    def is_running(self) -> bool:
        """事件循环是否正在运行"""
        return self._running
    
    @property
    def is_closed(self) -> bool:
        """事件循环是否已关闭"""
        return self._loop.is_closed()
    
    @property
    def time(self) -> float:
        """当前事件循环时间"""
        return self._loop.time()
    
    # ============ 上下文管理器 ============
    
    def __enter__(self):
        """进入上下文"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文"""
        self.close()
    
    def __repr__(self):
        """字符串表示"""
        status = "running" if self._running else "stopped"
        impl = "uvloop" if self._use_uvloop else "asyncio"
        return f"<EventLoop({impl}, {status})>"


# ============ 工具函数 ============

def get_event_loop() -> EventLoop:
    """
    获取当前事件循环
    
    如果不存在则创建一个新的
    """
    try:
        loop = asyncio.get_event_loop()
        if isinstance(loop, EventLoop):
            return loop
    except RuntimeError:
        pass
    
    # 创建新的事件循环
    return EventLoop()


def set_event_loop(loop: EventLoop):
    """设置当前事件循环"""
    asyncio.set_event_loop(loop.loop)


async def sleep(delay: float):
    """
    异步睡眠
    
    Args:
        delay: 睡眠时间（秒）
    """
    await asyncio.sleep(delay)


def run_async(coro: Coroutine) -> Any:
    """
    运行异步协程（便捷函数）
    
    Args:
        coro: 要运行的协程
        
    Returns:
        协程的返回值
    """
    loop = get_event_loop()
    return loop.run_until_complete(coro)


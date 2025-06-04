# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2023-09-17

import atexit
import functools
import multiprocessing
import signal
import threading
import time
import typing
from functools import lru_cache

from logger import logger


class TimeoutError(Exception):
    """
    统一的超时异常类

    Attributes:
        func: 超时的函数名
        timeout: 超时时间（秒）
        count: 提交的任务数量
    """

    def __init__(self, func: str = None, timeout: float = None, count: int = None):
        """
        初始化超时异常

        Args:
            func: 超时的函数名
            timeout: 超时时间（秒）
            count: 提交的任务数量
        """
        self.func = func or "unknown"
        self.timeout = timeout
        self.count = count or 0

        # 生成错误消息
        message = f"函数 '{self.func}' 执行超时"
        if self.timeout is not None:
            message += f"，超时时间：{self.timeout} 秒"
        if self.count > 0:
            message += f"，提交的任务数量：{self.count} 个"

        super().__init__(message)

    def to_log_dict(self) -> dict:
        """返回适合记录到日志的字典格式"""
        return {
            "type": "TimeoutError",
            "func": self.func,
            "timeout": self.timeout,
            "count": self.count,
            "message": str(self),
        }

    def __repr__(self) -> str:
        """返回详细的字符串表示，用于调试"""
        return f"TimeoutError(func='{self.func}', timeout={self.timeout}, count={self.count})"


@lru_cache(maxsize=256)
def trim(content: str) -> str:
    if not content or type(content) != str:
        return ""

    return content.strip()


def calc_time(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        cost = time.time() - start
        logger.info(f"函数 '{func.__name__}' 执行完成，耗时 {cost:.2f}s")
        return result

    return wrapper


class GlobalProcessPool:
    """
    全局进程池管理器，确保进程安全和资源正确释放
    进程池只创建一次，避免重复创建和销毁的开销
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return

        self._pool = None
        self._pool_lock = threading.Lock()
        self._pool_size = multiprocessing.cpu_count()
        self._initialized = True

        # 注册清理函数
        atexit.register(self._cleanup)

        # 注册信号处理器（仅在主线程中）
        if threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
            except ValueError:
                # 在某些环境中可能无法设置信号处理器
                logger.warning("无法设置信号处理器，进程清理可能不完整")

    def _signal_handler(self, signum, _frame):
        """信号处理器，确保进程池正确关闭"""
        del _frame

        logger.info(f"接收到信号 {signum}，正在清理进程池...")
        self._cleanup()

    def _cleanup(self):
        """清理进程池资源"""
        with self._pool_lock:
            if self._pool is not None:
                try:
                    logger.info("正在关闭进程池...")
                    self._pool.close()

                    # 等待进程池关闭
                    self._pool.join()
                    logger.info("进程池已成功关闭")
                except Exception as e:
                    logger.error(f"关闭进程池时发生错误: {e}")
                    try:
                        self._pool.terminate()
                        self._pool.join()
                        logger.info("进程池已强制终止")
                    except Exception as e2:
                        logger.error(f"强制终止进程池时发生错误: {e2}")
                finally:
                    self._pool = None

    def get_pool(self):
        """获取进程池实例，只创建一次"""
        with self._pool_lock:
            if self._pool is None:
                self._pool = multiprocessing.Pool(self._pool_size)
                logger.info(f"创建进程池，大小: {self._pool_size}")

        return self._pool

    def execute(self, func: typing.Callable, tasks: list) -> list:
        """执行多进程任务"""
        if not func or not isinstance(func, typing.Callable):
            logger.error("跳过执行，因为函数不可调用")
            return []

        if not tasks or type(tasks) != list:
            logger.error("跳过执行，因为任务列表为空或无效")
            return []

        pool = self.get_pool()
        results = []

        try:
            if isinstance(tasks[0], (list, tuple)):
                results = pool.starmap(func, tasks)
            else:
                results = pool.map(func, tasks)
        except KeyboardInterrupt:
            logger.error("任务被取消，程序将退出")
            self._cleanup()
            raise
        except Exception as e:
            logger.error(f"执行多进程任务时发生错误: {e}")
            raise

        return results


# 全局进程池实例
_global_pool = GlobalProcessPool()


@calc_time
def multi_process_run(func: typing.Callable, tasks: list, timeout: float = None) -> list:
    """
    多进程执行函数，使用全局进程池提高性能，支持超时控制
    智能检测是否在子进程中运行，避免嵌套多进程问题

    Args:
        func: 要执行的函数
        tasks: 任务列表
        timeout: 超时时间（秒），None或<=0表示不设置超时

    Returns:
        执行结果列表

    Raises:
        TimeoutError: 当设置了超时且执行超时时抛出
    """
    if not func or not isinstance(func, typing.Callable):
        logger.error("跳过执行，因为函数不可调用")
        return []

    if not tasks or type(tasks) != list:
        logger.error("跳过执行，因为任务列表为空或无效")
        return []

    funcname = getattr(func, "__name__", repr(func))

    # 检测是否在子进程中运行，避免嵌套多进程
    current = multiprocessing.current_process()
    if current.name != 'MainProcess':
        # 在子进程中，直接串行执行避免嵌套多进程
        logger.debug(f"在子进程 {current.name} 中检测到多进程调用，切换为串行执行: {funcname}")
        results = []
        for task in tasks:
            if isinstance(task, (list, tuple)):
                result = func(*task)
            else:
                result = func(task)
            results.append(result)
        return results

    # 判断是否需要超时控制
    if timeout is None or timeout <= 0:
        # 原有的同步执行方式
        results = _global_pool.execute(func, tasks)
        logger.info(f"[Parallel] 多进程并行执行 [{funcname}] 完成，任务数量: {len(tasks)}")
        return results
    else:
        # 带超时的异步执行方式
        pool = _global_pool.get_pool()

        try:
            # 使用async方法提交任务
            if isinstance(tasks[0], (list, tuple)):
                future = pool.starmap_async(func, tasks)
            else:
                future = pool.map_async(func, tasks)

            # 等待结果，如果超时会抛出multiprocessing.TimeoutError
            results = future.get(timeout=timeout)

            logger.info(f"[Parallel] 多进程并行执行 [{funcname}] 在超时 {timeout}s 内完成，任务数量: {len(tasks)}")
            return results

        except multiprocessing.TimeoutError:
            logger.warning(f"[Parallel] 多进程执行 [{funcname}] 在 {timeout}s 后超时，任务数量: {len(tasks)}")

            # 创建详细的超时异常
            error = TimeoutError(
                func=funcname,
                timeout=timeout,
                count=len(tasks)
            )

            # 记录详细的超时信息到日志
            logger.error(f"超时详细信息: {error.to_log_dict()}")

            raise error

        except KeyboardInterrupt:
            logger.error("任务被取消，程序将退出")
            _global_pool._cleanup()
            raise
        except Exception as e:
            logger.error(f"执行多进程任务时发生错误: {e}")
            raise


def cleanup_process_pool():
    """
    手动清理全局进程池
    在某些情况下可能需要手动调用此函数来确保进程池被正确清理
    """
    _global_pool._cleanup()

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
        logger.info(f"function '{func.__name__}' execute finished, cost {cost:.2f}s")
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

    def _signal_handler(self, signum, frame):
        """信号处理器，确保进程池正确关闭"""
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
            logger.error("skip execute due to func is not callable")
            return []

        if not tasks or type(tasks) != list:
            logger.error("skip execute due to tasks is empty or invalid")
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
def multi_process_run(func: typing.Callable, tasks: list) -> list:
    """
    多进程执行函数，使用全局进程池提高性能

    Args:
        func: 要执行的函数
        tasks: 任务列表
        num: 进程数量（保留参数以兼容现有代码，但不再使用）

    Returns:
        执行结果列表
    """
    # 使用全局进程池执行任务
    results = _global_pool.execute(func, tasks)

    funcname = getattr(func, "__name__", repr(func))
    logger.info(f"[Concurrent] multi-process concurrent execute [{funcname}] finished, count: {len(tasks)}")

    return results


def cleanup_process_pool():
    """
    手动清理全局进程池
    在某些情况下可能需要手动调用此函数来确保进程池被正确清理
    """
    _global_pool._cleanup()

from functools import wraps
from typing import Callable, TypeVar

from app.log.logger import get_retry_logger

T = TypeVar("T")
logger = get_retry_logger()


class RetryHandler:
    """重试处理装饰器"""

    def __init__(self, max_retries: int = 3, key_arg: str = "provider"):
        self.max_retries = max_retries
        self.key_arg = key_arg

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(self.max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    logger.warning(f"API call failed with error: {str(e)}. Attempt {attempt + 1} of {self.max_retries}")

                    # 从函数参数中获取 provider_manager
                    provider_manager = kwargs.get("provider_manager")
                    if provider_manager:
                        old_provider = kwargs.get(self.key_arg)
                        new_provider = await provider_manager.handle_api_failure(old_provider)
                        kwargs[self.key_arg] = new_provider
                        logger.info(f"Switched to new API Provider: {new_provider}")

            logger.error(f"All retry attempts failed, raising final exception: {str(last_exception)}")
            raise last_exception

        return wrapper

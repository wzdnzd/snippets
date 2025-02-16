import asyncio
from itertools import cycle
from typing import Dict

from app.core.config import settings
from app.core.logger import get_provider_manager_logger

logger = get_provider_manager_logger()


class ProviderManager:
    def __init__(self, providers: list):
        self.providers = providers
        self.provider_cycle = cycle(providers)
        self.provider_cycle_lock = asyncio.Lock()
        self.failure_count_lock = asyncio.Lock()
        self.provider_failure_counts: Dict[str, int] = {provider: 0 for provider in providers}
        self.MAX_FAILURES = settings.MAX_FAILURES

    async def get_next_provider(self) -> str:
        async with self.provider_cycle_lock:
            return next(self.provider_cycle)

    async def is_provider_valid(self, provider: str) -> bool:
        async with self.failure_count_lock:
            return self.provider_failure_counts[provider] < self.MAX_FAILURES

    async def reset_failure_counts(self):
        async with self.failure_count_lock:
            for provider in self.provider_failure_counts:
                self.provider_failure_counts[provider] = 0

    async def get_next_working_provider(self) -> str:
        initial_provider = await self.get_next_provider()
        current_provider = initial_provider

        while True:
            if await self.is_provider_valid(current_provider):
                return current_provider

            current_provider = await self.get_next_provider()
            if current_provider == initial_provider:
                return current_provider

    async def handle_api_failure(self, provider: str) -> str:
        """处理API调用失败"""
        async with self.failure_count_lock:
            self.provider_failure_counts[provider] += 1
            if self.provider_failure_counts[provider] >= self.MAX_FAILURES:
                logger.warning(f"API provider {provider} has failed {self.MAX_FAILURES} times")

        return await self.get_next_working_provider()

    def get_fail_count(self, provider: str) -> int:
        return self.provider_failure_counts.get(provider, 0)

    async def get_providers_by_status(self) -> dict:
        valid_providers = {}
        invalid_providers = {}

        async with self.failure_count_lock:
            for provider in self.providers:
                fail_count = self.provider_failure_counts[provider]
                if fail_count < self.MAX_FAILURES:
                    valid_providers[provider] = fail_count
                else:
                    invalid_providers[provider] = fail_count

        return {"valid_providers": valid_providers, "invalid_providers": invalid_providers}


_singleton_instance = None
_singleton_lock = asyncio.Lock()


async def get_provider_manager_instance(providers: list = None) -> ProviderManager:
    """
    获取 ProviderManager 单例实例。

    如果尚未创建实例，将使用提供的 providers 初始化 ProviderManager。
    如果已创建实例，则忽略 providers 参数，返回现有单例。
    """
    global _singleton_instance

    async with _singleton_lock:
        if _singleton_instance is None:
            if providers is None:
                raise ValueError("API providers are required to initialize the ProviderManager")
            _singleton_instance = ProviderManager(providers)
        return _singleton_instance

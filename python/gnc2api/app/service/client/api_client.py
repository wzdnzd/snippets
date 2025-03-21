import json
import re
import httpx
from abc import ABC, abstractmethod

from typing import Any, AsyncGenerator, Dict
from app.core.constants import DEFAULT_TIMEOUT, DEFAULT_X_GOOG_API_CLIENT


class ApiClient(ABC):
    """API客户端基类"""

    @abstractmethod
    async def generate_content(self, url: str, payload: Dict[str, Any], model: str, api_key: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def stream_generate_content(
        self, url: str, payload: Dict[str, Any], model: str, api_key: str
    ) -> AsyncGenerator[str, None]:
        pass


class GeminiApiClient(ApiClient):
    """Gemini API客户端"""

    def __init__(self, client_version: str = DEFAULT_X_GOOG_API_CLIENT, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.client_version = client_version

    def _process_url(self, url: str) -> str:
        if not url or type(url) != str:
            raise Exception(f"base_url must be a string and cannot be empty")

        content = url.strip()
        regex = r"^https?://([\w\-_]+\.[\w\-_]+)+"
        if not re.match(regex, content, flags=re.I):
            raise Exception(f"{url} is not a valid url")

        return content

    def _get_real_model(self, model: str) -> str:
        if model.endswith("-search"):
            model = model[:-7]
        if model.endswith("-image"):
            model = model[:-6]

        return model

    def _get_headers(self, base_url: str, api_key: str) -> dict:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": base_url,
            "Referer": base_url,
            "X-Goog-Api-Client": self.client_version,
            "X-Goog-Api-Key": api_key,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36 Edg/134.0.0.0",
        }

    def generate_content(self, base_url: str, payload: Dict[str, Any], model: str, api_key: str) -> Dict[str, Any]:
        base_url = self._process_url(base_url)
        timeout = httpx.Timeout(self.timeout, read=self.timeout)
        model = self._get_real_model(model)

        with httpx.Client(timeout=timeout) as client:
            url = f"{base_url}/models/{model}:generateContent"
            response = client.post(url, json=payload, headers=self._get_headers(base_url, api_key))
            if response.status_code != 200:
                error_content = response.text
                raise Exception(f"API call failed with status code {response.status_code}, {error_content}")

            content_type = response.headers.get("Content-Type")
            if content_type == "text/event-stream":
                content = response.text.removesuffix("\r\n")
                if content.startswith("data:"):
                    content = content.removeprefix("data:").strip()

                return json.loads(content)
            else:
                return response.json()

    async def stream_generate_content(
        self, base_url: str, payload: Dict[str, Any], model: str, api_key: str
    ) -> AsyncGenerator[str, None]:
        base_url = self._process_url(base_url)
        timeout = httpx.Timeout(self.timeout, read=self.timeout)
        headers = self._get_headers(base_url, api_key)
        model = self._get_real_model(model)

        async with httpx.AsyncClient(timeout=timeout) as client:
            url = f"{base_url}/models/{model}:streamGenerateContent?alt=sse"
            async with client.stream(method="POST", url=url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    error_content = await response.aread()
                    error_msg = error_content.decode("utf-8")
                    raise Exception(f"API call failed with status code {response.status_code}, {error_msg}")
                async for line in response.aiter_lines():
                    yield line

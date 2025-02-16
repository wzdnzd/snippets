# app/services/chat/message_converter.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class MessageConverter(ABC):
    """消息转换器基类"""

    @abstractmethod
    def convert(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pass


def _convert_image(image_url: str) -> Dict[str, Any]:
    if image_url.startswith("data:image"):
        return {"inline_data": {"mime_type": "image/jpeg", "data": image_url.split(",")[1]}}
    return {"image_url": {"url": image_url}}


class OpenAIMessageConverter(MessageConverter):
    """OpenAI消息格式转换器"""

    def convert(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        converted_messages = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            parts = []

            if isinstance(msg["content"], str):
                parts.append({"text": msg["content"]})
            elif isinstance(msg["content"], list):
                for content in msg["content"]:
                    if isinstance(content, str):
                        parts.append({"text": content})
                    elif isinstance(content, dict):
                        if content["type"] == "text":
                            parts.append({"text": content["text"]})
                        elif content["type"] == "image_url":
                            parts.append(_convert_image(content["image_url"]["url"]))

            converted_messages.append({"role": role, "parts": parts})

        return converted_messages

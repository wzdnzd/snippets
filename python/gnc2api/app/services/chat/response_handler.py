# app/services/chat/response_handler.py

import time
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.core.config import settings


class ResponseHandler(ABC):
    """响应处理器基类"""

    @abstractmethod
    def handle_response(self, response: Dict[str, Any], model: str, stream: bool = False) -> Dict[str, Any]:
        pass


class GeminiResponseHandler(ResponseHandler):
    """Gemini响应处理器"""

    def __init__(self):
        self.thinking_first = True
        self.thinking_status = False

    def handle_response(self, response: Dict[str, Any], model: str, stream: bool = False) -> Dict[str, Any]:
        if stream:
            return _handle_gemini_stream_response(response, model, stream)
        return _handle_gemini_normal_response(response, model, stream)


def _handle_openai_stream_response(response: Dict[str, Any], model: str, finish_reason: str) -> Dict[str, Any]:
    text = _extract_text(response, model, stream=True)
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": text} if text else {}, "finish_reason": finish_reason}],
    }


def _handle_openai_normal_response(response: Dict[str, Any], model: str, finish_reason: str) -> Dict[str, Any]:
    text = _extract_text(response, model, stream=False)
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


class OpenAIResponseHandler(ResponseHandler):
    """OpenAI响应处理器"""

    def __init__(self, config):
        self.config = config
        self.thinking_first = True
        self.thinking_status = False

    def handle_response(
        self, response: Dict[str, Any], model: str, stream: bool = False, finish_reason: str = None
    ) -> Optional[Dict[str, Any]]:
        if stream:
            return _handle_openai_stream_response(response, model, finish_reason)
        return _handle_openai_normal_response(response, model, finish_reason)

    def handle_image_chat_response(self, image_str: str, model: str, stream=False, finish_reason="stop"):
        if stream:
            return _handle_openai_stream_image_response(image_str, model, finish_reason)
        return _handle_openai_normal_image_response(image_str, model, finish_reason)


def _handle_openai_stream_image_response(image_str: str, model: str, finish_reason: str) -> Dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {"content": image_str} if image_str else {}, "finish_reason": finish_reason}],
    }


def _handle_openai_normal_image_response(image_str: str, model: str, finish_reason: str) -> Dict[str, Any]:
    return {
        "id": f"chatcmpl-{uuid.uuid4()}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": image_str}, "finish_reason": finish_reason}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _extract_text(response: Dict[str, Any], model: str, stream: bool = False) -> str:
    text = ""
    if stream:
        if response.get("candidates"):
            candidate = response["candidates"][0]
            content = candidate.get("content", {})
            parts = content.get("parts", [])

            if "text" in parts[0]:
                text = parts[0].get("text")
            elif "executableCode" in parts[0]:
                text = _format_code_block(parts[0]["executableCode"])
            elif "codeExecution" in parts[0]:
                text = _format_code_block(parts[0]["codeExecution"])
            elif "executableCodeResult" in parts[0]:
                text = _format_execution_result(parts[0]["executableCodeResult"])
            elif "codeExecutionResult" in parts[0]:
                text = _format_execution_result(parts[0]["codeExecutionResult"])
            else:
                text = ""
            text = _add_search_link_text(model, candidate, text)
    else:
        if response.get("candidates"):
            candidate = response["candidates"][0]
            if "thinking" in model:
                if settings.SHOW_THINKING_PROCESS:
                    if len(candidate["content"]["parts"]) == 2:
                        text = (
                            "> thinking\n\n"
                            + candidate["content"]["parts"][0]["text"]
                            + "\n\n---\n> output\n\n"
                            + candidate["content"]["parts"][1]["text"]
                        )
                    else:
                        text = candidate["content"]["parts"][0]["text"]
                else:
                    if len(candidate["content"]["parts"]) == 2:
                        text = candidate["content"]["parts"][1]["text"]
                    else:
                        text = candidate["content"]["parts"][0]["text"]
            else:
                text = ""
                for part in candidate["content"]["parts"]:
                    text += part["text"]
            text = _add_search_link_text(model, candidate, text)
        else:
            text = "暂无返回"
    return text


def _handle_gemini_stream_response(response: Dict[str, Any], model: str, stream: bool) -> Dict[str, Any]:
    text = _extract_text(response, model, stream=stream)
    content = {"parts": [{"text": text}], "role": "model"}
    response["candidates"][0]["content"] = content
    return response


def _handle_gemini_normal_response(response: Dict[str, Any], model: str, stream: bool) -> Dict[str, Any]:
    text = _extract_text(response, model, stream=stream)
    content = {"parts": [{"text": text}], "role": "model"}
    response["candidates"][0]["content"] = content
    return response


def _format_code_block(code_data: dict) -> str:
    """格式化代码块输出"""
    language = code_data.get("language", "").lower()
    code = code_data.get("code", "").strip()
    return f"""\n\n---\n\n【代码执行】\n```{language}\n{code}\n```\n"""


def _add_search_link_text(model: str, candidate: dict, text: str) -> str:
    if (
        settings.SHOW_SEARCH_LINK
        and model.endswith("-search")
        and "groundingMetadata" in candidate
        and "groundingChunks" in candidate["groundingMetadata"]
    ):
        grounding_chunks = candidate["groundingMetadata"]["groundingChunks"]
        text += "\n\n---\n\n"
        text += "**【引用来源】**\n\n"
        for _, grounding_chunk in enumerate(grounding_chunks, 1):
            if "web" in grounding_chunk:
                text += _create_search_link(grounding_chunk["web"])
        return text
    else:
        return text


def _create_search_link(grounding_chunk: dict) -> str:
    return f'\n- [{grounding_chunk["title"]}]({grounding_chunk["uri"]})'


def _format_execution_result(result_data: dict) -> str:
    """格式化执行结果输出"""
    outcome = result_data.get("outcome", "")
    output = result_data.get("output", "").strip()
    return f"""\n【执行结果】\n> outcome: {outcome}\n\n【输出结果】\n```plaintext\n{output}\n```\n\n---\n\n"""

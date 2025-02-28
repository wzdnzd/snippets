# app/services/chat_service.py

import json
from copy import deepcopy
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

from app.core.config import settings
from app.core.logger import get_openai_logger
from app.schemas.openai_models import ChatRequest
from app.services.chat.api_client import GeminiApiClient
from app.services.chat.message_converter import OpenAIMessageConverter
from app.services.chat.response_handler import OpenAIResponseHandler
from app.services.provider_manager import ProviderManager

logger = get_openai_logger()


def _has_image_parts(contents: List[Dict[str, Any]]) -> bool:
    """判断消息是否包含图片部分"""
    for content in contents:
        if "parts" in content:
            for part in content["parts"]:
                if "image_url" in part or "inline_data" in part:
                    return True
    return False


def _build_tools(request: ChatRequest, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """构建工具"""
    tools = []
    model = request.model

    if (
        settings.TOOLS_CODE_EXECUTION_ENABLED
        and not (model.endswith("-search") or "-thinking" in model)
        and not _has_image_parts(messages)
    ):
        tools.append({"code_execution": {}})
    if model.endswith("-search"):
        tools.append({"googleSearch": {}})

    # 将 request 中的 tools 合并到 tools 中
    if request.tools:
        function_declarations = []
        for tool in request.tools:
            if not tool or not isinstance(tool, dict):
                continue

            if tool.get("type", "") == "function" and tool.get("function"):
                function = deepcopy(tool.get("function"))
                parameters = function.get("parameters", {})
                if parameters.get("type") == "object" and not parameters.get("properties", {}):
                    function.pop("parameters", None)

                function_declarations.append(function)

        if function_declarations:
            tools.append({"functionDeclarations": function_declarations})

    return tools


def _get_safety_settings(model: str) -> List[Dict[str, str]]:
    """获取安全设置"""
    if model == "gemini-2.0-flash-exp":
        return [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "OFF"},
            {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "OFF"},
        ]
    return [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
    ]


def _build_payload(
    request: ChatRequest, messages: List[Dict[str, Any]], instruction: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """构建请求payload"""
    payload = {
        "contents": messages,
        "generationConfig": {
            "temperature": request.temperature,
            "maxOutputTokens": request.max_tokens,
            "stopSequences": request.stop,
            "topP": request.top_p,
            "topK": request.top_k,
        },
        "tools": _build_tools(request, messages),
        "safetySettings": _get_safety_settings(request.model),
    }

    if (
        instruction
        and isinstance(instruction, dict)
        and instruction.get("role") == "system"
        and instruction.get("parts")
    ):
        payload["systemInstruction"] = instruction

    return payload


class OpenAIChatService:
    """聊天服务"""

    def __init__(self, provider_manager: ProviderManager = None):
        self.message_converter = OpenAIMessageConverter()
        self.response_handler = OpenAIResponseHandler(config=None)
        self.api_client = GeminiApiClient(settings.X_GOOG_API_CLIENT)
        self.provider_manager = provider_manager

    async def create_chat_completion(
        self,
        base_url: str,
        request: ChatRequest,
        api_key: str,
    ) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
        """创建聊天完成"""
        # 转换消息格式
        messages, instruction = self.message_converter.convert(request.messages)

        # 构建请求payload
        payload = _build_payload(request, messages, instruction)

        if request.stream:
            return self._handle_stream_completion(base_url, request.model, payload, api_key)
        return self._handle_normal_completion(base_url, request.model, payload, api_key)

    def _handle_normal_completion(
        self, base_url: str, model: str, payload: Dict[str, Any], api_key: str
    ) -> Dict[str, Any]:
        """处理普通聊天完成"""
        response = self.api_client.generate_content(base_url, payload, model, api_key)
        return self.response_handler.handle_response(response, model, stream=False, finish_reason="stop")

    async def _handle_stream_completion(
        self, base_url: str, model: str, payload: Dict[str, Any], api_key: str
    ) -> AsyncGenerator[str, None]:
        """处理流式聊天完成，添加重试逻辑"""
        retries = 0
        max_retries = 3
        while retries < max_retries:
            try:
                async for line in self.api_client.stream_generate_content(base_url, payload, model, api_key):
                    if line.startswith("data:"):
                        chunk = json.loads(line[6:])
                        openai_chunk = self.response_handler.handle_response(
                            chunk, model, stream=True, finish_reason=None
                        )
                        if openai_chunk:
                            yield f"data: {json.dumps(openai_chunk)}\n\n"
                yield f"data: {json.dumps(self.response_handler.handle_response({}, model, stream=True, finish_reason='stop'))}\n\n"
                yield "data: [DONE]\n\n"
                logger.info("Streaming completed successfully")
                break  # 成功后退出循环
            except Exception as e:
                retries += 1
                logger.warning(f"Streaming API call failed with error: {str(e)}. Attempt {retries} of {max_retries}")
                base_url = await self.provider_manager.handle_api_failure(base_url)
                logger.info(f"Switched to new API provider: {base_url}")
                if retries >= max_retries:
                    logger.error(f"Max retries ({max_retries}) reached for streaming. Raising error")
                    yield f"data: {json.dumps({'error': 'Streaming failed after retries'})}\n\n"
                    yield "data: [DONE]\n\n"
                    break

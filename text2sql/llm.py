# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-02-28

import time
import uuid
from dataclasses import dataclass

import requests

from tools.logger import logger
from tools.utils import trim


@dataclass
class ChatResponse(object):
    # 是否成功
    success: bool = True

    # 错误信息
    error: str = ""

    # 消息 id
    id: str = ""

    # 消息内容
    content: str = ""

    # 消息创建时间
    created: int = 0

    # 消息角色
    role: str = "assistant"

    # 使用的模型名称
    model: str = ""


def chat(url: str, messages: list[dict], apikey: str = "", retry: int = 3, **kwargs) -> ChatResponse:
    """聊天"""
    goon, url, error = True, trim(url), ""
    if not url:
        goon, error = False, "URL 不能为空"
    elif not messages:
        goon, error = False, "消息不能为空"

    if not goon:
        logger.error(error)
        return ChatResponse(success=False, error=error)

    headers = {"Content-Type": "application/json"}
    apikey = trim(apikey)
    if apikey:
        headers["Authorization"] = f"Bearer {apikey}"

    payload = {"messages": messages}
    payload.update(kwargs)

    response, retry = None, max(0, retry) + 1
    while retry > 0 and response is None:
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            break
        except Exception as e:
            logger.error(e)

        retry -= 1

    if response is None:
        goon, error = False, "请求失败，已达最大重试次数"
    elif response.status_code != 200:
        goon, error = False, f"请求失败，错误码：{response.status_code}"

    if not goon:
        logger.error(error)
        return ChatResponse(success=False, error=error)

    data = response.json()
    success = data.get("success", False)
    if not success:
        error = f"请求失败，错误信息：{data.get('msg', '未知错误')}"
        logger.error(error)
        return ChatResponse(success=False, error=error)

    result = data.get("result", {})
    model = result.get("model", kwargs.get("model", ""))
    created = result.get("created", int(time.time()))
    message_id = result.get("id", f"chatcmpl-{str(uuid.uuid4())}")

    content, role = "", "assistant"
    choices = result.get("choices", [])
    if isinstance(choices, list) and choices:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        role = message.get("role", "assistant")

    return ChatResponse(id=message_id, content=content, created=created, role=role, model=model)

# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-02-28

import time
from dataclasses import dataclass


@dataclass
class ChatHistory:
    # 对话id
    conversation_id: str

    # 消息id
    message_id: str

    # 问题
    question: str

    # 答案
    answer: str

    # 使用的模型名称
    model: str = ""

    # 提问时间
    created: int = int(time.time())

    # 反馈
    fb_score: int = 0

    # 反馈详细内容
    fb_detail: str = ""

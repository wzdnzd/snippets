# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-02-28

import random
import time
import uuid
from dataclasses import dataclass, field

from flask import Flask, jsonify

POEMS = [
    "白日依山尽，黄河入海流。",
    "欲穷千里目，更上一层楼。",
    "黄河之水天上来，奔流到海不复回。",
    "青青子衿，悠悠我心。",
    "春风得意马蹄疾，一日看尽长安花。",
    "床前明月光，疑是地上霜。",
    "举头望明月，低头思故乡。",
    "两情若是久长时，又岂在朝朝暮暮。",
    "海内存知己，天涯若比邻。",
    "人生得意须尽欢，莫使金樽空对月。",
    "天生我材必有用，千金散尽还复来。",
    "烟笼寒水月笼沙，夜泊秦淮近酒家。",
    "横看成岭侧成峰，远近高低各不同。",
    "不识庐山真面目，只缘身在此山中。",
    "君不见黄河之水天上来，奔流到海不复回。",
    "君不见高堂明镜悲白发，朝如青丝暮成雪。",
    "日照香炉生紫烟，遥看瀑布挂前川。",
    "飞流直下三千尺，疑是银河落九天。",
    "攀援青竹笋，藤绕白云回。",
    "酒逢知己千杯少，话不投机半句多。",
    "青青河边草，郁郁园中柳。",
    "动静皆鸣皆飞，阴阳共短共长。",
    "春风吹又生，可奈何天上人间。",
    "白发三千丈，缘愁似个长。",
    "世人笑我太疯癫，我笑他人看不穿。",
    "不妨吟啸且让他，明日太阳照常升。",
    "花间一壶酒，独酌无相亲。",
    "举杯邀明月，对影成三人。",
    "天生我材必有用，千金散尽还复来。",
    "会当凌绝顶，一览众山小。",
    "OpenAI 估值超过 800 亿美元（IT之家备注：当前约 5768 亿元人民币），是人工智能领域的领军企业之一，其发展方向可能对这项颠覆性技术产生重大影响。2023 年 11 月 17 日，OpenAI 董事会解雇了阿尔特曼，五天后又将其复职。知情人士透露， 38 岁的阿尔特曼最近几周表示调查即将结束，结果可能最快在下个月提交给 OpenAI 董事会。",
]


def generate_random_num(low: int = 1, high: int = 10**6) -> int:
    if low > high:
        low, high = high, low

    return random.randint(low, high)


@dataclass
class ChatMessage(object):
    role: str = "assistant"

    function_call: str = None

    tool_call: str = None

    content: str = ""


@dataclass
class ChatChoice(object):
    finish_reason: str = "stop"

    index: int = 0

    message: ChatMessage = None

    logprobs: float = None


@dataclass
class ChatUsage(object):
    completion_tokens: int = 0

    prompt_tokens: int = 0

    total_tokens: int = 0

    @staticmethod
    def new(completion: int = generate_random_num(5, 10**4), prompt: int = generate_random_num(10, 10**4)):
        completion, prompt = max(0, completion), max(0, prompt)

        return ChatUsage(
            completion_tokens=completion,
            prompt_tokens=prompt,
            total_tokens=completion + prompt,
        )


@dataclass
class ChatCompletion(object):
    created: int = int(time.time())

    usage: ChatUsage = field(default_factory=ChatUsage.new)

    model: str = "Qwen-14B"

    id: str = f"chatcmpl-{str(uuid.uuid4())}"

    choices: list[ChatChoice] = field(default_factory=list)

    system_fingerprint: str = None

    object: str = "chat.completion"


@dataclass
class CommonResult(object):
    success: bool = True

    msg: str = ""

    result: ChatCompletion = None


app = Flask(__name__)

# disable sorting keys in JSON response
app.config["JSON_SORT_KEYS"] = False


@app.route("/v1/chat/completions", methods=["POST"])
def chat():
    content = random.choice(POEMS)
    message = ChatMessage(content=content)
    completion = ChatCompletion(id=f"chatcmpl-{str(uuid.uuid4())}", choices=[ChatChoice(message=message)])
    return jsonify(CommonResult(result=completion))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2023-12-27

import argparse
import json
import logging
import multiprocessing
import os
import ssl
import time
import traceback
import typing
import urllib
import urllib.parse
import urllib.request
from http.client import HTTPMessage, HTTPResponse
from threading import Lock

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DATA_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)), "data")

FILE_LOCK = Lock()

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler()],
)

# 知识库名
KNOWLEDGE_BASE_NAME = ""

# API 地址
API_URL = "http://127.0.0.1:7861/chat/knowledge_base_chat"

# LLM 模型名称
MODEL_NAME = "chatglm3-6b"

# 用的 prompt 模板名称
PROMPT_NAME = "default"

# 限制LLM生成Token数量，默认 None 代表模型最大值
MAX_TOKENS = None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def http_error_302(
        self,
        req: urllib.request.Request,
        fp: typing.IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
    ) -> typing.IO[bytes]:
        return fp


def http_post(
    url: str,
    headers: dict = None,
    params: dict = {},
    retry: int = 3,
    timeout: float = 6,
    allow_redirects: bool = True,
) -> HTTPResponse:
    if params is None or type(params) != dict:
        return None

    timeout, retry = max(timeout, 1), retry - 1
    if not headers:
        headers = {
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        }
    try:
        data = json.dumps(params).encode(encoding="UTF8")
        request = urllib.request.Request(url=url, data=data, headers=headers, method="POST")
        if allow_redirects:
            return urllib.request.urlopen(request, timeout=timeout, context=CTX)

        opener = urllib.request.build_opener(NoRedirect)
        return opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as e:
        if retry < 0 or e.code in [400, 401, 404, 405]:
            return None

        return http_post(
            url=url,
            headers=headers,
            params=params,
            retry=retry,
            allow_redirects=allow_redirects,
        )
    except (TimeoutError, urllib.error.URLError) as e:
        return None
    except Exception:
        if retry < 0:
            return None
        return http_post(
            url=url,
            headers=headers,
            params=params,
            retry=retry,
            allow_redirects=allow_redirects,
        )


def isblank(text: str) -> bool:
    return not text or type(text) != str or not text.strip()


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def parallel_query(func: typing.Callable, params: list) -> list:
    if not func or not params or type(params) != list:
        return []

    cpu_count = multiprocessing.cpu_count()
    num = len(params) if len(params) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    if type(params[0]) == list or type(params[0]) == tuple:
        results = pool.starmap(func, params)
    else:
        results = pool.map(func, params)

    pool.close()
    return results


def write_file(filename: str, lines: str | list, overwrite: bool = True) -> bool:
    if not filename or not lines or type(lines) not in [str, list]:
        logging.error(f"文件路径或保存内容无效, 文件路径: {filename}")
        return False

    try:
        if not isinstance(lines, str):
            lines = "\n".join(lines)

        filepath = os.path.abspath(os.path.dirname(filename))
        os.makedirs(filepath, exist_ok=True)
        mode = "w" if overwrite else "a"

        # waitting for lock
        FILE_LOCK.acquire(30)

        with open(filename, mode, encoding="UTF8") as f:
            f.write(lines + "\n")
            f.flush()

        # release lock
        FILE_LOCK.release()

        return True
    except:
        return False


def to_number(num: str) -> tuple[bool, float]:
    try:
        x = float(num)
        return True, x
    except ValueError:
        return False, 0.0


def load_questions(filepath: str, separator: str = "#=>&") -> list[list[str]]:
    """加载问题集，每行一个主题，问题列表之间由分隔符分隔，返回问题列表"""
    if not filepath or not os.path.exists(filepath) or not os.path.isfile(filepath):
        return []

    questions = []
    with open(filepath, encoding="UTF8") as f:
        for line in f.readlines():
            line = trim(line)
            if not line or line.startswith("#"):
                continue

            texts = line.split(separator)
            questions.append([trim(x) for x in texts if not isblank(x)])

    return questions


def query_one(
    questions: list[str],
    temperature: float,
    history_num: int,
    knowledge: str,
    top_k: int,
    score_threshold: float,
    saved_path: str,
) -> None:
    if not questions:
        logging.error(f"问题集为空，跳过")
        return

    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
    }

    sessions = []

    for question in questions:
        histories = [] if history_num <= 0 else sessions
        if len(histories) > history_num:
            histories = histories[-history_num:]

        # see: https://github.com/chatchat-space/Langchain-Chatchat/blob/4e69033d33d887dc8e0640aa602bd373ffd551eb/server/chat/knowledge_base_chat.py#L20
        params = {
            "query": question,
            "knowledge_base_name": knowledge,
            "top_k": top_k,
            "score_threshold": score_threshold,
            "history": histories,
            "stream": False,
            "model_name": MODEL_NAME,
            "temperature": temperature,
            "prompt_name": PROMPT_NAME,
        }

        if MAX_TOKENS:
            params["max_tokens"] = MAX_TOKENS

        response = http_post(API_URL, params=params, headers=headers, retry=5, timeout=120, allow_redirects=False)
        if not response or response.status != 200:
            logging.error(f"请求失败，问题：{question}")
            continue

        try:
            content = response.read().decode("UTF8")
            if not content:
                logging.warning(f"响应内容为空，问题：{question}")
                continue

            data = json.loads(content)
            answer = data.get("answer", "")
            docs = "参考文献："
            for idx, doc in enumerate(data.get("docs", [])):
                docs += f"[{idx+1}] {doc}；"

            answer = f"{answer} {docs}"
            history = [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
            sessions.append(history)
        except:
            logging.error(f"解析响应失败，问题：{question}，message：\n{traceback.format_exc()}")
            continue

    content = [f'{x.get("role")}：{x.get("content")}' for s in sessions for x in s]
    content.append("\n\n")

    filename = os.path.join(saved_path, f"answers-{temperature}_{history_num}_{top_k}_{score_threshold}.txt")
    success = write_file(filename=filename, lines=content, overwrite=False)
    if not success:
        logging.error(f"保存结果失败，文件路径：{filename}，内容：\n{content}")
        return

    logging.info(f"问题【{questions[0]}】处理完毕，文件路径：{filename}")


def main(args: argparse.Namespace) -> None:
    directory, filename = trim(args.directory), trim(args.file)
    if not directory or not filename:
        logging.error("数据目录或文件名为空")
        return

    filepath = os.path.join(directory, filename)
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        logging.error(f"文件不存在，文件路径：{filepath}")
        return

    knowledge = trim(args.knowledge)
    if not knowledge:
        logging.error("知识库名为空")
        return

    histories, nums = set(), trim(args.nums).split(",") or ["0"]
    for num in nums:
        valid, x = to_number(num)
        if not valid or x < 0:
            logging.error(f"附带历史对话数量不合法，num: {num}")
            return

        histories.add(int(x))

    temperatures, nums = set(), trim(args.temperatures).split(",") or ["0.0"]
    for num in nums:
        valid, x = to_number(num)
        if not valid or x < 0 or x > 1:
            logging.error(f"采样温度不合法，temperature: {num}")
            return

        temperatures.add(x)

    quantity, score = args.quantity, args.score
    if quantity < 1:
        logging.error(f"匹配向量数不合法，quantity: {quantity}")
        return

    if score < 0 or score > 1:
        logging.error(f"知识库匹配相关度阈值不合法，score: {score}")
        return

    # 加载问题集
    questions = load_questions(filepath)
    if not questions:
        logging.warning("问题集为空")
        return

    # 结果文件保存路径
    suffix = time.strftime("%Y%m%d%H%M%S", time.localtime())
    saved_path = os.path.join(DATA_DIR, f"answers-{suffix}")

    # 生成任务列表
    tasks = [
        [question, temperature, history, knowledge, quantity, score, saved_path]
        for question in questions
        for temperature in temperatures
        for history in histories
    ]

    logging.info(f"开始并发提问，问题数量：{len(tasks)}")
    start_time = time.time()

    # 并发执行
    parallel_query(query_one, tasks)

    logging.info(f"测试完毕，结果文件在目录 {directory} 下，总耗时：{time.time()-start_time:.2f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-d",
        "--directory",
        type=str,
        required=False,
        default=DATA_DIR,
        metavar="",
        help="数据文件目录路径",
    )

    parser.add_argument(
        "-f",
        "--file",
        type=str,
        required=True,
        metavar="",
        help="问题集文件名",
    )

    parser.add_argument(
        "-k",
        "--knowledge",
        type=str,
        required=False,
        default=KNOWLEDGE_BASE_NAME,
        metavar="",
        help="知识库名",
    )

    parser.add_argument(
        "-n",
        "--nums",
        type=str,
        required=False,
        default="4",
        metavar="",
        help="最大附带历史对话数量，多个值用逗号分隔",
    )

    parser.add_argument(
        "-q",
        "--quantity",
        type=int,
        required=False,
        default=5,
        metavar="",
        help="匹配向量数",
    )

    parser.add_argument(
        "-s",
        "--score",
        type=float,
        required=False,
        default=0.5,
        metavar="",
        help="知识库匹配相关度阈值，取值范围：0.0 ~ 1.0",
    )

    parser.add_argument(
        "-t",
        "--temperatures",
        type=str,
        required=False,
        default="0.35,0.5,0.75",
        metavar="",
        help="LLM 采样温度，多个值用逗号分隔，取值范围：0.0 ~ 1.0",
    )

    main(parser.parse_args())

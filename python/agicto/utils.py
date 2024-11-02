# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import gzip
import json
import os
import random
import socket
import ssl
import string
import time
import traceback
import typing
import urllib
import urllib.error
import urllib.parse
import urllib.request
from concurrent import futures
from http.client import HTTPMessage, HTTPResponse

from tqdm import tqdm

from logger import logger

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

DEFAULT_HTTP_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
}


def random_chars(length: int, punctuation: bool = False) -> str:
    length = max(length, 1)
    if punctuation:
        chars = "".join(random.sample(string.ascii_letters + string.digits + string.punctuation, length))
    else:
        chars = "".join(random.sample(string.ascii_letters + string.digits, length))

    return chars


def write_file(filename: str, lines: list) -> bool:
    if not filename or not lines:
        logger.error(f"filename or lines is empty, filename: {filename}")
        return False

    try:
        if not isinstance(lines, str):
            lines = "\n".join(lines)

        filepath = os.path.abspath(os.path.dirname(filename))
        os.makedirs(filepath, exist_ok=True)
        with open(filename, "a+", encoding="UTF8") as f:
            f.write(lines)
            f.flush()

        return True
    except:
        return False


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def http_get(
    url: str,
    headers: dict = None,
    params: dict = None,
    retry: int = 3,
    proxy: str = "",
    interval: float = 0,
    timeout: float = 10,
    trace: bool = False,
) -> str:
    if not url:
        logger.error(f"invalid url: {url}")
        return ""

    if retry <= 0:
        logger.debug(f"achieves max retry, url={url}")
        return ""

    headers = DEFAULT_HTTP_HEADERS if not headers else headers

    interval = max(0, interval)
    timeout = max(1, timeout)
    try:
        if params and isinstance(params, dict):
            data = urllib.parse.urlencode(params)
            if "?" in url:
                url += f"&{data}"
            else:
                url += f"?{data}"

        request = urllib.request.Request(url=url, headers=headers)
        if proxy and (proxy.startswith("https://") or proxy.startswith("http://")):
            host, protocal = "", ""
            if proxy.startswith("https://"):
                host, protocal = proxy[8:], "https"
            else:
                host, protocal = proxy[7:], "http"
            request.set_proxy(host=host, type=protocal)

        response = urllib.request.urlopen(request, timeout=timeout, context=CTX)
        content = response.read()
        status_code = response.getcode()
        try:
            content = str(content, encoding="utf8")
        except:
            content = gzip.decompress(content).decode("utf8")
        if status_code != 200:
            if trace:
                logger.error(f"request failed, url: {url}, code: {status_code}, message: {content}")

            return ""

        return content
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, ssl.SSLError)):
            time.sleep(interval)
            return http_get(
                url=url,
                headers=headers,
                params=params,
                retry=retry - 1,
                proxy=proxy,
                interval=interval,
                timeout=timeout,
            )
        else:
            return ""
    except Exception as e:
        if trace:
            logger.error(f"request failed, url: {url}, message: \n{traceback.format_exc()}")

        if isinstance(e, urllib.error.HTTPError):
            try:
                message = str(e.read(), encoding="utf8")
            except:
                message = "unknown error"

            if e.code != 503 or "token" in message:
                return ""

        time.sleep(interval)
        return http_get(
            url=url,
            headers=headers,
            params=params,
            retry=retry - 1,
            proxy=proxy,
            interval=interval,
            timeout=timeout,
        )


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
    if params is None or type(params) != dict or retry <= 0:
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
    except Exception:
        time.sleep(random.random())
        return http_post(
            url=url,
            headers=headers,
            params=params,
            retry=retry,
            allow_redirects=allow_redirects,
        )


def multi_thread_run(
    func: typing.Callable,
    tasks: list,
    num_threads: int = None,
    show_progress: bool = False,
    description: str = "",
) -> list:
    if not func or not tasks or not isinstance(tasks, list):
        return []

    if num_threads is None or num_threads <= 0:
        num_threads = min(len(tasks), (os.cpu_count() or 1) * 2)

    funcname = getattr(func, "__name__", repr(func))

    results, starttime = [None] * len(tasks), time.time()
    with futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        if isinstance(tasks[0], (list, tuple)):
            collections = {executor.submit(func, *param): i for i, param in enumerate(tasks)}
        else:
            collections = {executor.submit(func, param): i for i, param in enumerate(tasks)}

        items = futures.as_completed(collections)
        if show_progress:
            description = trim(description) or "Progress"

            # TODO: use p_tqdm instead of tqdm, see https://github.com/swansonk14/p_tqdm
            items = tqdm(items, total=len(collections), desc=description, leave=True)

        for future in items:
            try:
                result = future.result()
                index = collections[future]
                results[index] = result
            except Exception as e:
                logger.error(f"function {funcname} execution generated an exception: {e}")

    logger.info(
        f"[Concurrent] multi-threaded execute [{funcname}] finished, count: {len(tasks)}, cost: {time.time()-starttime:.2f}s"
    )

    return results


def read_response(response: HTTPResponse, expected: int = 200, deserialize: bool = False, key: str = "") -> typing.Any:
    if not response or not isinstance(response, HTTPResponse):
        return None

    success = expected <= 0 or expected == response.getcode()
    if not success:
        return None

    try:
        text = response.read()
    except:
        text = b""

    try:
        content = text.decode(encoding="UTF8")
    except UnicodeDecodeError:
        content = gzip.decompress(text).decode("UTF8")
    except:
        content = ""

    if not deserialize:
        return content

    if not content:
        return None
    try:
        data = json.loads(content)
        return data if not key else data.get(key, None)
    except:
        return None

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量下载 CLIProxyAPI / CPA Manager Plus 的 auth 认证文件。

目标接口：CPA Management API；CPAMP 也会把 /v0/management/* 代理到 CPA。
  GET  /v0/management/auth-files                 列出认证文件
  GET  /v0/management/auth-files/download?name=  下载单个认证文件

认证：
  Authorization: Bearer <CPA Management Key>

示例：
  # 下载全部，默认；密钥含 ! 时务必用单引号，或改用环境变量 / 密钥文件
  python batch_download_auth_files.py \\
    --base-url http://127.0.0.1:8317 \\
    --key 'YOUR_CPA_MANAGEMENT_KEY'

  # 推荐：环境变量，完全避开 shell 对 ! 的历史扩展
  export CPA_MANAGEMENT_KEY='your!key!with!bangs'
  python batch_download_auth_files.py --base-url http://127.0.0.1:8317

  # 或从文件读取密钥，文件内容一行即可
  python batch_download_auth_files.py --key-file ./cpa.key

  # 只下载指定文件
  python batch_download_auth_files.py --key-file ./cpa.key --names a.json b.json

  # 按 provider 过滤，如 codex / claude / gemini / xai
  python batch_download_auth_files.py --key-file ./cpa.key --provider codex

  # 仅列出，不下载
  python batch_download_auth_files.py --key-file ./cpa.key --list-only

  # 默认增量：本地已有且未过期则跳过；已过期会自动重新下载覆盖
  # 强制全部覆盖用 --refresh
  python batch_download_auth_files.py --key-file ./cpa.key --refresh
"""

from __future__ import annotations

import argparse
import getpass
import datetime
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen


AUTH_FILES_PATH = "/v0/management/auth-files"
AUTH_FILES_DOWNLOAD_PATH = "/v0/management/auth-files/download"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_BODY = 64 * 1024 * 1024  # 64 MiB，与 CPAMP 客户端一致
DEFAULT_OUTPUT_DIR = "./auth_files_backup"
DEFAULT_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.0  # 首次等待秒数，之后指数退避
# 可重试的 HTTP 状态码（瞬时/过载类）；401/403/404 等不重试
RETRYABLE_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

# 全局取消标志：Ctrl+C 后停止新的重试/排队任务
_CANCEL = threading.Event()


class CancelledError(RuntimeError):
    """用户中断（Ctrl+C）导致的取消。"""


def request_cancel() -> None:
    _CANCEL.set()


def reset_cancel() -> None:
    _CANCEL.clear()


def is_cancelled() -> bool:
    return _CANCEL.is_set()


def ensure_not_cancelled() -> None:
    if _CANCEL.is_set():
        raise CancelledError("已取消")


def interruptible_sleep(seconds: float) -> None:
    """可被取消标志打断的 sleep；取消时抛 CancelledError。"""
    if seconds <= 0:
        ensure_not_cancelled()
        return
    end = time.monotonic() + seconds
    while True:
        ensure_not_cancelled()
        remaining = end - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.2, remaining))


def force_exit(code: int) -> None:
    """
    立即退出进程，跳过 ThreadPoolExecutor 在 atexit 里对工作线程的 join。
    否则二次 Ctrl+C 或解释器关停时会出现:
      Exception ignored on threading shutdown ... KeyboardInterrupt
    """
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    os._exit(code)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class AuthFile:
    id: str = ""
    name: str = ""
    auth_index: str = ""
    provider: str = ""
    account_snapshot: str = ""
    account_id: str = ""
    disabled: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def display(self) -> str:
        status = "disabled" if self.disabled else "enabled"
        parts = [
            self.name or "no-name",
            f"provider={self.provider or '-'}",
            f"auth_index={self.auth_index or '-'}",
            f"account={self.account_snapshot or self.account_id or '-'}",
            status,
        ]
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# URL / HTTP 工具
# ---------------------------------------------------------------------------

def normalize_base_url(base_url: str) -> str:
    """规范化 CPA / CPAMP base URL（去掉尾部斜杠与 management.html 路径）。"""
    raw = (base_url or "").strip()
    if not raw:
        raise ValueError("base-url 不能为空")

    if not re.match(r"^https?://", raw, re.I):
        raw = "http://" + raw

    parsed = urlparse(raw)
    path = parsed.path or ""
    # 用户可能误填 http://host:8317/management.html
    for suffix in ("/management.html", "/management", "/"):
        if path.lower().endswith(suffix) and suffix != "/":
            path = path[: -len(suffix)]
            break
    path = path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def build_url(base_url: str, path: str, query: Optional[dict[str, str]] = None) -> str:
    base = normalize_base_url(base_url).rstrip("/") + "/"
    full = urljoin(base, path.lstrip("/"))
    if query:
        # 过滤空值
        q = {k: v for k, v in query.items() if v is not None and v != ""}
        if q:
            full = f"{full}?{urlencode(q, quote_via=quote)}"
    return full


class RetryableError(RuntimeError):
    """瞬时错误，可自动重试。"""


def _http_get_once(
    url: str,
    management_key: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_body: int = DEFAULT_MAX_BODY,
) -> bytes:
    req = Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {management_key}",
            "Accept": "*/*",
            "User-Agent": "cpamp-auth-batch-downloader/1.0",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            data = resp.read(max_body + 1)
            if len(data) > max_body:
                # 响应过大不是瞬时问题，不重试
                raise RuntimeError(f"响应体超过限制 {max_body} bytes: {url}")
            return data
    except HTTPError as e:
        body = b""
        try:
            body = e.read(4096)
        except Exception:
            pass
        detail = body.decode("utf-8", errors="replace").strip()
        if e.code == 401:
            raise RuntimeError(
                "认证失败，HTTP 401。请确认使用的是 CPA Management Key，"
                "不是 CPAMP Admin Key；并检查 base-url 是否指向 CPA 或可代理 management 的 CPAMP。"
                f" body={detail!r}"
            ) from e
        if e.code == 403:
            raise RuntimeError(f"无权限，HTTP 403: {url} body={detail!r}") from e
        if e.code == 404:
            raise FileNotFoundError(f"资源不存在，HTTP 404: {url} body={detail!r}") from e
        msg = f"GET {url} 失败: HTTP {e.code} {detail}"
        if e.code in RETRYABLE_HTTP_STATUS:
            raise RetryableError(msg) from e
        raise RuntimeError(msg) from e
    except TimeoutError as e:
        raise RetryableError(f"请求超时: {url}: {e}") from e
    except URLError as e:
        # 连接拒绝 / DNS / 重置等通常可重试
        reason = getattr(e, "reason", e)
        if isinstance(reason, TimeoutError) or "timed out" in str(e).lower():
            raise RetryableError(f"请求超时: {url}: {e}") from e
        raise RetryableError(f"无法连接 {url}: {e}") from e


def http_get(
    url: str,
    management_key: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_body: int = DEFAULT_MAX_BODY,
    retries: int = DEFAULT_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> bytes:
    """
    GET 请求，带有限次重试。

    重试条件：网络错误、超时、HTTP 408/425/429/5xx。
    不重试：401/403/404、响应体过大、其它 4xx。
    退避：backoff * 2^attempt + 少量抖动。
    若已请求取消（Ctrl+C），立即停止后续重试。
    """
    attempts = max(0, int(retries)) + 1  # retries=3 => 最多 4 次尝试
    last_err: Optional[BaseException] = None

    for attempt in range(attempts):
        ensure_not_cancelled()
        try:
            return _http_get_once(url, management_key, timeout=timeout, max_body=max_body)
        except RetryableError as e:
            last_err = e
            if attempt >= attempts - 1:
                break
            delay = retry_backoff * (2**attempt)
            # 抖动，避免并发请求同时打满
            delay += random.uniform(0, min(0.5, delay * 0.2))
            print(
                f"[retry] 第 {attempt + 1}/{attempts - 1} 次重试，"
                f"{delay:.2f}s 后重试: {e}",
                file=sys.stderr,
            )
            interruptible_sleep(delay)
        except CancelledError:
            raise
        except (RuntimeError, FileNotFoundError):
            raise

    assert last_err is not None
    raise RuntimeError(f"重试 {attempts} 次后仍失败: {last_err}") from last_err


def resolve_management_key(
    key_arg: str = "",
    key_file: str = "",
    prompt_if_missing: bool = True,
) -> str:
    """
    解析 Management Key，优先级：
      1) --key-file
      2) --key（支持 @path 表示从文件读）
      3) 环境变量 CPA_MANAGEMENT_KEY
      4) 交互式输入（隐藏回显，避开 shell 对 ! 的历史扩展）

    Bash/Git Bash 注意：
      - 交互式 bash 里双引号仍会做 history expansion：--key "a!b" 会报 event not found
      - 应使用单引号：--key 'a!b'
      - 或 set +H 关闭历史扩展
      - 最稳妥：环境变量 / --key-file / 交互输入
    """
    if key_file:
        path = Path(key_file).expanduser()
        if not path.is_file():
            raise ValueError(f"密钥文件不存在: {path}")
        text = path.read_text(encoding="utf-8-sig").strip()
        # 只取首行，忽略注释空行
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
        raise ValueError(f"密钥文件为空: {path}")

    raw = (key_arg or "").strip()
    if raw.startswith("@") and len(raw) > 1:
        path = Path(raw[1:]).expanduser()
        if not path.is_file():
            raise ValueError(f"密钥文件不存在: {path}")
        text = path.read_text(encoding="utf-8-sig").strip()
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
        raise ValueError(f"密钥文件为空: {path}")

    if raw:
        return raw

    env_key = os.environ.get("CPA_MANAGEMENT_KEY", "").strip()
    if env_key:
        return env_key

    if prompt_if_missing and sys.stdin.isatty():
        print(
            "未提供密钥。请粘贴 CPA Management Key，输入不会回显；"
            "此方式可避免 bash 对 ! 的历史扩展：",
            file=sys.stderr,
        )
        entered = getpass.getpass("CPA Management Key: ").strip()
        if entered:
            return entered

    raise ValueError(
        "未提供 CPA Management Key。可用方式：\n"
        "  1) 环境变量:  export CPA_MANAGEMENT_KEY='your!key'\n"
        "  2) 密钥文件:  --key-file ./cpa.key\n"
        "  3) 单引号:    --key 'your!key'   # bash 双引号会触发 ! 历史扩展\n"
        "  4) 关闭扩展:  set +H  后再用双引号\n"
        "  5) 交互输入:  不传 --key，按提示粘贴"
    )


# ---------------------------------------------------------------------------
# 解析列表响应（兼容多种 CPA 返回形态）
# ---------------------------------------------------------------------------

def _pick(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return d[k]
    return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "disabled", "inactive"}
    return False


def _normalize_provider(value: Any) -> str:
    s = str(value or "").strip().lower()
    aliases = {
        "x-ai": "xai",
        "grok": "xai",
        "openai": "codex",
        "chatgpt": "codex",
        "google": "gemini",
        "anthropic": "claude",
    }
    return aliases.get(s, s)


def parse_auth_file_item(item: Any) -> Optional[AuthFile]:
    if not isinstance(item, dict):
        return None

    name = _pick(item, "name", "file_name", "fileName", "id")
    if name is None:
        return None
    name = str(name)

    disabled = False
    if "disabled" in item:
        disabled = _as_bool(item.get("disabled"))
    else:
        status = str(_pick(item, "status", "state") or "").strip().lower()
        disabled = status in {"disabled", "inactive"}

    return AuthFile(
        id=str(_pick(item, "id") or ""),
        name=name,
        auth_index=str(_pick(item, "auth_index", "authIndex", "auth-index") or ""),
        provider=_normalize_provider(_pick(item, "provider", "type")),
        account_snapshot=str(
            _pick(item, "account", "email", "display_account", "displayAccount") or ""
        ),
        account_id=str(
            _pick(
                item,
                "account_id",
                "accountId",
                "chatgpt_account_id",
                "project_id",
                "sub",
            )
            or ""
        ),
        disabled=disabled,
        raw=item,
    )


def parse_auth_files_list(body: bytes) -> list[AuthFile]:
    """
    兼容 CPA 可能返回的多种 JSON 形态：
      1) [ {...}, ... ]
      2) { "auth_files"|"authFiles"|"files"|"items"|"data": [ ... ] }
      3) 单个文件对象
    """
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return []

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"解析 auth-files 列表 JSON 失败: {e}; body 前 200 字: {text[:200]!r}") from e

    items: list[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        nested = None
        for key in ("auth_files", "authFiles", "files", "items", "data"):
            if key in data and isinstance(data[key], list):
                nested = data[key]
                break
        if nested is not None:
            items = nested
        elif _pick(data, "name", "file_name", "fileName", "id") is not None:
            items = [data]
        else:
            # 某些实现可能把文件名当 key
            maybe = []
            for k, v in data.items():
                if isinstance(v, dict):
                    obj = dict(v)
                    obj.setdefault("name", k)
                    maybe.append(obj)
                elif v is True or v is None or isinstance(v, str):
                    maybe.append({"name": k})
            items = maybe
    else:
        raise RuntimeError(f"不支持的 auth-files 响应类型: {type(data).__name__}")

    files: list[AuthFile] = []
    seen: set[str] = set()
    for item in items:
        f = parse_auth_file_item(item)
        if not f or not f.name:
            continue
        if f.name in seen:
            continue
        seen.add(f.name)
        files.append(f)
    return files


# ---------------------------------------------------------------------------
# 业务逻辑
# ---------------------------------------------------------------------------

def list_auth_files(
    base_url: str,
    management_key: str,
    name: str = "",
    auth_index: str = "",
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = DEFAULT_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> list[AuthFile]:
    url = build_url(
        base_url,
        AUTH_FILES_PATH,
        {"name": name, "auth_index": auth_index},
    )
    body = http_get(
        url,
        management_key,
        timeout=timeout,
        retries=retries,
        retry_backoff=retry_backoff,
    )
    return parse_auth_files_list(body)


def download_auth_file(
    base_url: str,
    management_key: str,
    file_name: str,
    timeout: float = DEFAULT_TIMEOUT,
    max_body: int = DEFAULT_MAX_BODY,
    retries: int = DEFAULT_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> bytes:
    if not file_name:
        raise FileNotFoundError("文件名为空")
    url = build_url(
        base_url,
        AUTH_FILES_DOWNLOAD_PATH,
        {"name": file_name},
    )
    return http_get(
        url,
        management_key,
        timeout=timeout,
        max_body=max_body,
        retries=retries,
        retry_backoff=retry_backoff,
    )


def safe_filename(name: str) -> str:
    """防止路径穿越，保留常见 auth 文件名。"""
    base = os.path.basename(name.replace("\\", "/").strip())
    base = re.sub(r"[^\w.\-@+=()\[\] ]+", "_", base, flags=re.UNICODE)
    return base or "unnamed.json"


def parse_expired_value(value: Any) -> Optional[datetime.datetime]:
    """把 auth 文件中的 expired 字段解析为带时区的 datetime。"""
    if value is None or value is False:
        return None
    if isinstance(value, bool):
        # True 表示已过期，用极早时间触发刷新
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc) if value else None
    if isinstance(value, (int, float)):
        ts = float(value)
        # 毫秒时间戳
        if ts > 1e12:
            ts /= 1000.0
        try:
            return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if s.lower() in {"true", "yes", "expired"}:
            return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        if s.lower() in {"false", "no", "null", "none"}:
            return None
        # 纯数字字符串
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return parse_expired_value(float(s))
        # ISO8601：2026-07-30T11:35:12Z / 带偏移
        s = s.replace("Z", "+00:00").replace("z", "+00:00")
        try:
            dt = datetime.datetime.fromisoformat(s)
        except ValueError:
            # 尝试去掉多余小数位
            m = re.match(
                r"^(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(\.\d+)?([+-]\d{2}:?\d{2}|)$",
                s,
            )
            if not m:
                return None
            try:
                dt = datetime.datetime.fromisoformat(m.group(1) + (m.group(3) or "+00:00"))
            except ValueError:
                return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    return None


def extract_expired_raw(data: Any) -> Any:
    """从认证 JSON 中提取 expired 原始值（优先顶层 expired）。"""
    if not isinstance(data, dict):
        return None
    for key in ("expired", "expires", "expires_at", "expire", "expiry", "exp"):
        if key in data and data[key] is not None and data[key] != "":
            return data[key]
    for nest in ("token", "tokens", "oauth", "credentials", "metadata", "id_token"):
        nested = data.get(nest)
        if isinstance(nested, dict):
            for key in ("expired", "expires", "expires_at", "expire", "expiry", "exp"):
                if key in nested and nested[key] is not None and nested[key] != "":
                    return nested[key]
    return None


def read_local_expired_at(path: Path) -> Optional[datetime.datetime]:
    """读取本地 auth 文件的过期时间；无法解析则返回 None。"""
    try:
        text = path.read_text(encoding="utf-8-sig")
        data = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return parse_expired_value(extract_expired_raw(data))


def local_file_needs_redownload(path: Path, now: Optional[datetime.datetime] = None) -> tuple[bool, str]:
    """
    判断本地已存在文件是否需要重新下载。

    返回 (need_download, reason)：
      - 文件不存在 -> True, "missing"
      - 有 expired 且 <= now -> True, "expired"
      - 其它（未过期 / 无 expired 字段 / 解析失败）-> False, "fresh"|"no-expiry"|"unreadable"
    """
    if not path.is_file():
        return True, "missing"
    expired_at = read_local_expired_at(path)
    if expired_at is None:
        # 无 expired 或解析失败：按“未过期”处理，保持跳过
        try:
            # 能读 JSON 但没有 expired
            json.loads(path.read_text(encoding="utf-8-sig"))
            return False, "no-expiry"
        except Exception:
            return False, "unreadable"
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    else:
        now = now.astimezone(datetime.timezone.utc)
    if expired_at <= now:
        return True, "expired"
    return False, "fresh"


def filter_files(
    files: list[AuthFile],
    names: Optional[Iterable[str]] = None,
    provider: str = "",
    include_disabled: bool = True,
    only_disabled: bool = False,
) -> list[AuthFile]:
    result = list(files)

    if names:
        wanted = {n.strip() for n in names if n and n.strip()}
        result = [f for f in result if f.name in wanted]

    if provider:
        p = _normalize_provider(provider)
        result = [f for f in result if _normalize_provider(f.provider) == p]

    if only_disabled:
        result = [f for f in result if f.disabled]
    elif not include_disabled:
        result = [f for f in result if not f.disabled]

    return result


def save_bytes(path: Path, data: bytes, overwrite: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    target = path
    if target.exists() and not overwrite:
        stem, suffix = target.stem, target.suffix
        i = 1
        while True:
            candidate = target.with_name(f"{stem}__{i}{suffix}")
            if not candidate.exists():
                target = candidate
                break
            i += 1
    target.write_bytes(data)
    return target


@dataclass
class DownloadResult:
    name: str
    ok: bool
    path: str = ""
    size: int = 0
    error: str = ""
    # error 约定: "" | "skipped" | "cancelled" | "expired" | 其它失败信息
    skipped: bool = False
    # True：覆盖了本地已存在文件（过期自动刷新 或 --refresh）
    updated: bool = False


class DownloadInterrupted(Exception):
    """批量下载被用户中断；携带已收集的部分结果。"""

    def __init__(self, results: list[DownloadResult]):
        super().__init__("download interrupted")
        self.results = results


def _shutdown_pool(
    pool: ThreadPoolExecutor,
    future_map: dict[Future, AuthFile],
    *,
    cancel: bool = False,
) -> None:
    """关闭线程池。

    cancel=True（中断路径）：取消未开始任务并 wait=False，避免 atexit join 卡死。
    cancel=False（正常完成）：等待已提交任务收尾后再关闭。
    """
    if cancel:
        request_cancel()
        for fut in future_map:
            fut.cancel()
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            pool.shutdown(wait=False)
    else:
        pool.shutdown(wait=True)


def local_auth_path(output_dir: Path, file_name: str) -> Path:
    """输出目录下与远端文件名对应的本地路径（经 safe_filename 规范化）。"""
    return output_dir / safe_filename(file_name)


def batch_download(
    base_url: str,
    management_key: str,
    files: list[AuthFile],
    output_dir: Path,
    workers: int = 4,
    timeout: float = DEFAULT_TIMEOUT,
    refresh: bool = False,
    dry_run: bool = False,
    retries: int = DEFAULT_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> list[DownloadResult]:
    """
    批量下载。

    默认（未指定 refresh）：
      - 本地不存在 -> 下载
      - 本地存在且 expired 未过期 / 无 expired -> 跳过
      - 本地存在且 expired <= 当前 UTC 时间 -> 重新下载并覆盖
    refresh=True：强制重新下载并覆盖本地文件。

    Ctrl+C 时：
      - 设置取消标志，中断重试等待
      - 取消尚未开始的 Future
      - 尽快 shutdown 线程池
      - 返回已完成的部分结果（并带上未完成项的 cancelled 记录）
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[DownloadResult] = []
    now_utc = datetime.datetime.now(datetime.timezone.utc)

    def _decision(dest: Path) -> tuple[bool, str]:
        """返回 (should_skip, reason)。reason: skip/missing/expired/refresh。"""
        if refresh:
            return False, "refresh" if dest.is_file() else "missing"
        need, reason = local_file_needs_redownload(dest, now=now_utc)
        if need:
            return False, reason
        return True, reason

    if dry_run:
        for f in files:
            ensure_not_cancelled()
            dest = local_auth_path(output_dir, f.name)
            skip, reason = _decision(dest)
            if skip:
                size = dest.stat().st_size if dest.is_file() else 0
                print(f"[dry-run] 跳过 {reason}: {f.display()} -> {dest}，{size} bytes")
                results.append(
                    DownloadResult(
                        name=f.name,
                        ok=True,
                        path=str(dest),
                        size=size,
                        error="skipped",
                        skipped=True,
                    )
                )
            else:
                is_update = reason in {"expired", "refresh"}
                label = {
                    "refresh": "强制覆盖下载",
                    "expired": "过期后重新下载",
                    "missing": "下载",
                }.get(reason, "下载")
                print(f"[dry-run] 将{label}，原因 {reason}: {f.display()} -> {dest}")
                results.append(
                    DownloadResult(
                        name=f.name,
                        ok=True,
                        path=str(dest),
                        error="" if reason in {"missing", "refresh"} else reason,
                        updated=is_update,
                    )
                )
        return results

    def _one(f: AuthFile) -> DownloadResult:
        if is_cancelled():
            return DownloadResult(name=f.name, ok=False, error="cancelled")
        dest = local_auth_path(output_dir, f.name)
        skip, reason = _decision(dest)
        if skip:
            size = dest.stat().st_size
            return DownloadResult(
                name=f.name,
                ok=True,
                path=str(dest),
                size=size,
                error="skipped",
                skipped=True,
            )
        try:
            data = download_auth_file(
                base_url,
                management_key,
                f.name,
                timeout=timeout,
                retries=retries,
                retry_backoff=retry_backoff,
            )
            if is_cancelled():
                return DownloadResult(name=f.name, ok=False, error="cancelled")
            # 新文件 / refresh / 过期刷新：写到规范文件名并覆盖
            saved = save_bytes(dest, data, overwrite=True)
            is_update = reason in {"expired", "refresh"}
            return DownloadResult(
                name=f.name,
                ok=True,
                path=str(saved),
                size=len(data),
                error="" if reason in {"missing", "refresh"} else reason,
                updated=is_update,
            )
        except CancelledError:
            return DownloadResult(name=f.name, ok=False, error="cancelled")
        except Exception as e:
            return DownloadResult(name=f.name, ok=False, error=str(e))

    workers = max(1, min(workers, len(files) or 1))
    pool = ThreadPoolExecutor(max_workers=workers)
    future_map: dict[Future, AuthFile] = {}
    interrupted = False

    try:
        future_map = {pool.submit(_one, f): f for f in files}
        for fut in as_completed(future_map):
            if is_cancelled():
                # 可能由其它路径设置；仍尽量收集已完成结果
                pass
            try:
                r = fut.result()
            except CancelledError:
                f = future_map[fut]
                r = DownloadResult(name=f.name, ok=False, error="cancelled")
            except Exception as e:
                f = future_map[fut]
                r = DownloadResult(name=f.name, ok=False, error=str(e))
            results.append(r)
            if r.skipped:
                print(f"[skip] {r.name} 已存在且未过期 -> {r.path}，{r.size} bytes")
            elif r.ok and r.error == "expired":
                print(f"[ok] {r.name} 已过期，已重新下载 {r.size} bytes -> {r.path}")
            elif r.ok and r.updated:
                print(f"[ok] {r.name} 已更新 {r.size} bytes -> {r.path}")
            elif r.ok:
                print(f"[ok] {r.name} {r.size} bytes -> {r.path}")
            elif r.error == "cancelled":
                print(f"[cancelled] {r.name}", file=sys.stderr)
            else:
                print(f"[fail] {r.name}: {r.error}", file=sys.stderr)
    except KeyboardInterrupt:
        interrupted = True
        request_cancel()
        print("\n收到中断信号，正在停止未完成任务…", file=sys.stderr)
        # 把尚未完成的标为 cancelled（已完成的保留在 results）
        done_names = {r.name for r in results}
        for fut, f in future_map.items():
            if fut.done() and f.name not in done_names:
                try:
                    if fut.cancelled():
                        results.append(DownloadResult(name=f.name, ok=False, error="cancelled"))
                    else:
                        results.append(fut.result(timeout=0))
                except Exception:
                    results.append(DownloadResult(name=f.name, ok=False, error="cancelled"))
            elif not fut.done() and f.name not in done_names:
                results.append(DownloadResult(name=f.name, ok=False, error="cancelled"))
    finally:
        _shutdown_pool(pool, future_map, cancel=interrupted or is_cancelled())

    # 保持与输入大致相同顺序
    order = {f.name: i for i, f in enumerate(files)}
    # 去重（中断路径可能重复追加）
    dedup: dict[str, DownloadResult] = {}
    for r in results:
        prev = dedup.get(r.name)
        if prev is None or (r.ok and not prev.ok):
            dedup[r.name] = r
    results = sorted(dedup.values(), key=lambda x: order.get(x.name, 10**9))

    if interrupted:
        # 用专用异常把部分结果带给 main，便于写 manifest 后优雅退出
        raise DownloadInterrupted(results)

    return results


def write_manifest(output_dir: Path, files: list[AuthFile], results: list[DownloadResult]) -> Path:
    added = sum(1 for r in results if r.ok and not r.skipped and not r.updated)
    updated = sum(1 for r in results if r.ok and r.updated)
    skipped = sum(1 for r in results if r.skipped)
    fail = sum(1 for r in results if not r.ok and r.error != "cancelled")
    cancelled = sum(1 for r in results if r.error == "cancelled")
    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "count_listed": len(files),
        "count_ok": sum(1 for r in results if r.ok),
        "count_added": added,
        "count_updated": updated,
        "count_skipped": skipped,
        "count_fail": fail,
        "count_cancelled": cancelled,
        "files": [
            {
                "name": f.name,
                "provider": f.provider,
                "auth_index": f.auth_index,
                "account": f.account_snapshot or f.account_id,
                "disabled": f.disabled,
            }
            for f in files
        ],
        "results": [
            {
                "name": r.name,
                "ok": r.ok,
                "skipped": r.skipped,
                "updated": r.updated,
                "path": r.path,
                "size": r.size,
                "error": r.error,
            }
            for r in results
        ],
    }
    path = output_dir / "manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="批量下载 CLIProxyAPI / CPA 的 auth 认证文件，默认下载全部",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--base-url",
        default=os.environ.get("CPA_BASE_URL", "http://127.0.0.1:8317"),
        help="CPA 地址，推荐；或可代理 /v0/management 的 CPAMP 地址。也可用环境变量 CPA_BASE_URL",
    )
    p.add_argument(
        "--key",
        default="",
        help=(
            "CPA Management Key。"
            "Bash/Git Bash 下若密钥含 ! 请用单引号：--key 'a!b'；"
            "双引号会触发历史扩展。也可用 --key @./cpa.key 从文件读取。"
            "更推荐 --key-file 或环境变量 CPA_MANAGEMENT_KEY。"
        ),
    )
    p.add_argument(
        "--key-file",
        default="",
        help="从文件读取 CPA Management Key，取首个非空非注释行。可完全避开 shell 对 ! 的解析问题",
    )
    p.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT_DIR,
        help=f"输出目录，默认 {DEFAULT_OUTPUT_DIR}",
    )
    p.add_argument(
        "--names",
        nargs="*",
        default=None,
        help="只下载指定文件名；省略则下载全部",
    )
    p.add_argument(
        "--provider",
        default="",
        help="按 provider 过滤，如 codex / claude / gemini / vertex / xai",
    )
    p.add_argument(
        "--auth-index",
        default="",
        help="列表接口可选过滤：auth_index",
    )
    p.add_argument(
        "--exclude-disabled",
        action="store_true",
        help="跳过已禁用账号",
    )
    p.add_argument(
        "--only-disabled",
        action="store_true",
        help="只下载已禁用账号",
    )
    p.add_argument(
        "--list-only",
        action="store_true",
        help="只列出认证文件，不下载",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="打印将要下载/跳过的文件，不实际请求 download",
    )
    p.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "强制重新下载并覆盖本地已存在的文件。"
            "默认：本地已有且未过期则跳过；已过期会自动重新下载覆盖"
        ),
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="同 --refresh，兼容旧参数：强制下载并覆盖本地文件",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=4,
        help="并发下载线程数，默认 4",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        help=f"单请求超时秒数，默认 {DEFAULT_TIMEOUT}",
    )
    p.add_argument(
        "--retries",
        type=int,
        default=DEFAULT_RETRIES,
        help=f"失败后额外重试次数，默认 {DEFAULT_RETRIES}；总尝试次数 = retries+1",
    )
    p.add_argument(
        "--retry-backoff",
        type=float,
        default=DEFAULT_RETRY_BACKOFF,
        help=f"重试初始等待秒数，之后指数退避，默认 {DEFAULT_RETRY_BACKOFF}",
    )
    p.add_argument(
        "--no-manifest",
        action="store_true",
        help="不写 manifest.json",
    )
    return p


def main(argv: Optional[list[str]] = None) -> int:
    reset_cancel()
    args = build_parser().parse_args(argv)

    try:
        management_key = resolve_management_key(
            key_arg=args.key,
            key_file=args.key_file,
            prompt_if_missing=True,
        )
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130

    try:
        base = normalize_base_url(args.base_url)
    except ValueError as e:
        print(f"错误: {e}", file=sys.stderr)
        return 2

    print(f"Base URL : {base}")
    print(f"List API : {base}{AUTH_FILES_PATH}")
    print(f"Download : {base}{AUTH_FILES_DOWNLOAD_PATH}?name=<file>")
    print(f"Retries  : {args.retries}，backoff={args.retry_backoff}s")
    print("-" * 60)

    try:
        files = list_auth_files(
            base_url=base,
            management_key=management_key,
            name="",  # 列表阶段先拿全量，再在本地按 --names 过滤
            auth_index=args.auth_index,
            timeout=args.timeout,
            retries=args.retries,
            retry_backoff=args.retry_backoff,
        )
    except KeyboardInterrupt:
        request_cancel()
        print("\n已取消。", file=sys.stderr)
        return 130
    except CancelledError:
        print("\n已取消。", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"列出认证文件失败: {e}", file=sys.stderr)
        return 1

    selected = filter_files(
        files,
        names=args.names,
        provider=args.provider,
        include_disabled=not args.exclude_disabled,
        only_disabled=args.only_disabled,
    )

    print(f"服务端共 {len(files)} 个认证文件，筛选后 {len(selected)} 个")
    for f in selected:
        print(f"  - {f.display()}")

    if args.list_only:
        return 0

    if not selected:
        print("没有需要下载的文件。")
        return 0

    if args.names:
        missing = sorted(set(args.names) - {f.name for f in selected})
        if missing:
            print(f"警告: 以下文件名未在列表中找到: {', '.join(missing)}", file=sys.stderr)

    output_dir = Path(args.output)
    refresh = bool(args.refresh or args.overwrite)
    interrupted = False
    results: list[DownloadResult] = []

    if refresh:
        print("模式: 全量刷新，即强制下载并覆盖本地已存在文件")
    else:
        print(
            "模式: 增量，即本地已存在且未过期则跳过；"
            "已过期则自动重新下载覆盖；需要全量覆盖请加 --refresh"
        )

    try:
        results = batch_download(
            base_url=base,
            management_key=management_key,
            files=selected,
            output_dir=output_dir,
            workers=args.workers,
            timeout=args.timeout,
            refresh=refresh,
            dry_run=args.dry_run,
            retries=args.retries,
            retry_backoff=args.retry_backoff,
        )
    except DownloadInterrupted as e:
        interrupted = True
        results = e.results
    except KeyboardInterrupt:
        interrupted = True
        request_cancel()
        print("\n已取消。", file=sys.stderr)

    # 新增：本地原先不存在；更新：覆盖本地已有（过期刷新 / --refresh）
    added = sum(1 for r in results if r.ok and not r.skipped and not r.updated)
    updated = sum(1 for r in results if r.ok and r.updated)
    skipped = sum(1 for r in results if r.skipped)
    fail = sum(1 for r in results if not r.ok and r.error != "cancelled")
    cancelled = sum(1 for r in results if r.error == "cancelled")
    print("-" * 60)
    if interrupted:
        parts = [
            "下载已中断",
            f"新增：{added} 个",
            f"更新：{updated} 个",
            f"跳过：{skipped} 个",
            f"失败：{fail} 个",
        ]
        if cancelled:
            parts.append(f"取消：{cancelled} 个")
        parts.append(f"服务端总文件数：{len(files)} 个")
        parts.append(f"输出目录：{output_dir.resolve()}")
        print("，".join(parts))
    else:
        print(
            f"下载完成，新增：{added} 个，更新：{updated} 个，跳过：{skipped} 个，"
            f"失败：{fail} 个，服务端总文件数：{len(files)} 个，"
            f"输出目录：{output_dir.resolve()}"
        )

    if not args.no_manifest and not args.dry_run and results:
        try:
            manifest = write_manifest(output_dir, selected, results)
            print(f"清单: {manifest}")
        except Exception as e:
            print(f"写入 manifest 失败: {e}", file=sys.stderr)

    if interrupted:
        # 跳过 ThreadPool atexit join，避免二次 KeyboardInterrupt 刷屏
        force_exit(130)

    return 0 if fail == 0 and not interrupted else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        request_cancel()
        print("\n已取消。", file=sys.stderr)
        force_exit(130)

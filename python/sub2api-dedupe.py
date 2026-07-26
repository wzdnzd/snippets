#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通过 sub2api Admin REST API 检查并清理同名重复账号。

特点：
- 只使用 Python 标准库；
- 使用 x-api-key 管理员鉴权；
- 完整遍历分页，并支持并发读取；
- 默认仅预览，显式传入 --apply 才会删除；
- 删除前列出每个重复组中保留与待删除的账号；
- 对网络异常、限流和常见 5xx 错误执行指数退避与随机抖动重试；
- 使用【信息】【警告】【错误】三级彩色日志，重定向输出时默认自动关闭颜色；
- 支持并发删除，并在删除后重新扫描验证结果。

推荐通过环境变量传递凭据：
    export SUB2API_BASE_URL='https://sub2api.example.com'
    export SUB2API_ADMIN_API_KEY='your-admin-api-key'

预览：
    python3 sub2api_dedupe_accounts.py

确认后执行删除：
    python3 sub2api_dedupe_accounts.py --apply

无人值守执行：
    python3 sub2api_dedupe_accounts.py --apply --yes
"""

from __future__ import annotations

import argparse
import email.utils
import json
import logging
import os
import random
import socket
import ssl
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

RETRYABLE_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}
SUCCESS_API_CODES = {0, "0"}
USER_AGENT = "sub2api-account-deduplicator/1.3"

ANSI_RESET = "\033[0m"
ANSI_COLORS = {
    "INFO": "\033[36m",  # 青色
    "WARNING": "\033[33m",  # 黄色
    "ERROR": "\033[31m",  # 红色
}

LEVEL_LABELS = {
    logging.INFO: "【信息】",
    logging.WARNING: "【警告】",
    logging.ERROR: "【错误】",
    logging.CRITICAL: "【错误】",
}


class ChineseLevelFormatter(logging.Formatter):
    """将输出统一格式化为【信息】【警告】【错误】三种中文等级。"""

    def __init__(self, *, use_color: bool) -> None:
        super().__init__("%(message)s")
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if record.levelno >= logging.ERROR:
            level_name = "ERROR"
            label = LEVEL_LABELS[logging.ERROR]
        elif record.levelno >= logging.WARNING:
            level_name = "WARNING"
            label = LEVEL_LABELS[logging.WARNING]
        else:
            level_name = "INFO"
            label = LEVEL_LABELS[logging.INFO]

        rendered = f"{label}{message}"
        if not self.use_color:
            return rendered
        return f"{ANSI_COLORS[level_name]}{rendered}{ANSI_RESET}"


def configure_logging(level_name: str, color_mode: str) -> logging.Logger:
    logger = logging.getLogger("sub2api-dedupe")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)

    if color_mode == "always":
        use_color = True
    elif color_mode == "never":
        use_color = False
    else:
        use_color = sys.stderr.isatty() and os.environ.get("TERM", "") != "dumb"

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(getattr(logging, level_name.upper()))
    handler.setFormatter(ChineseLevelFormatter(use_color=use_color))
    logger.addHandler(handler)
    return logger


LOGGER = configure_logging("INFO", "auto")


class StartRateLimiter:
    """在多个删除线程之间限制请求启动间隔。"""

    def __init__(self, interval: float) -> None:
        self.interval = max(0.0, interval)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_allowed - now)
            self._next_allowed = max(now, self._next_allowed) + self.interval
        if delay > 0:
            time.sleep(delay)


class Sub2ApiError(RuntimeError):
    """sub2api 请求或响应错误。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: Optional[int] = None,
        api_code: Any = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.api_code = api_code
        self.retryable = retryable


class Sub2ApiClient:
    """仅依赖 urllib 的 sub2api Admin REST API 客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = 30.0,
        retries: int = 4,
        backoff_base: float = 1.0,
        backoff_max: float = 30.0,
        verify_tls: bool = True,
    ) -> None:
        self.accounts_url = build_accounts_url(base_url)
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.ssl_context = ssl.create_default_context()
        if not verify_tls:
            self.ssl_context.check_hostname = False
            self.ssl_context.verify_mode = ssl.CERT_NONE

    def request_json(
        self,
        method: str,
        url: str,
        *,
        allow_delete_not_found: bool = False,
    ) -> Tuple[Any, bool]:
        """
        发送请求并解包 sub2api 的 {code, message, data} 响应。

        返回 (data, already_absent)。already_absent 仅用于 DELETE 404：
        这种情况可能表示前一次删除已成功但响应在网络中丢失，也可能是账号
        被其他管理操作删除，因此可安全视为目标已经不存在。
        """
        attempts = self.retries + 1
        last_error: Optional[BaseException] = None

        for attempt in range(attempts):
            request = Request(
                url,
                method=method,
                headers={
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                    "x-api-key": self.api_key,
                },
            )

            try:
                with urlopen(
                    request,
                    timeout=self.timeout,
                    context=self.ssl_context,
                ) as response:
                    raw = response.read()
                    payload = parse_json_bytes(raw, response.status)
                    return unwrap_api_response(payload, response.status), False

            except HTTPError as exc:
                raw = exc.read()
                payload = try_parse_json_bytes(raw)
                api_code, message = extract_api_error(payload, exc.reason)

                if allow_delete_not_found and exc.code == 404:
                    return None, True

                retryable = exc.code in RETRYABLE_HTTP_STATUSES
                error = Sub2ApiError(
                    format_api_error(
                        method=method,
                        url=url,
                        http_status=exc.code,
                        api_code=api_code,
                        message=message,
                    ),
                    http_status=exc.code,
                    api_code=api_code,
                    retryable=retryable,
                )
                last_error = error

                if retryable and attempt + 1 < attempts:
                    delay = retry_delay(
                        attempt=attempt,
                        base=self.backoff_base,
                        maximum=self.backoff_max,
                        retry_after=exc.headers.get("Retry-After"),
                    )
                    print_retry(attempt + 1, self.retries, delay, error)
                    time.sleep(delay)
                    continue
                raise error from exc

            except (URLError, socket.timeout, TimeoutError, ConnectionError) as exc:
                error = Sub2ApiError(
                    f"{method} {redact_url(url)} 网络请求失败: {exc}",
                    retryable=True,
                )
                last_error = error
                if attempt + 1 < attempts:
                    delay = retry_delay(
                        attempt=attempt,
                        base=self.backoff_base,
                        maximum=self.backoff_max,
                        retry_after=None,
                    )
                    print_retry(attempt + 1, self.retries, delay, error)
                    time.sleep(delay)
                    continue
                raise error from exc

            except json.JSONDecodeError as exc:
                raise Sub2ApiError(f"{method} {redact_url(url)} 返回的不是有效 JSON: {exc}") from exc

        # 理论上不会到达这里；保留明确错误便于静态检查和异常诊断。
        raise Sub2ApiError(f"请求失败: {last_error}")

    def _fetch_accounts_page(
        self,
        *,
        page: int,
        page_size: int,
        filters: Mapping[str, Optional[str]],
    ) -> Dict[str, Any]:
        """读取并校验单个账号分页。"""
        query: Dict[str, str] = {
            "page": str(page),
            "page_size": str(page_size),
            "sort_by": "id",
            "sort_order": "asc",
            "lite": "1",
        }
        for key, value in filters.items():
            if value is not None and value != "":
                query[key] = value

        url = f"{self.accounts_url}?{urlencode(query)}"
        data, _ = self.request_json("GET", url)
        if not isinstance(data, dict):
            raise Sub2ApiError(f"账号列表第 {page} 页响应 data 应为对象，实际为 {type(data).__name__}")
        items = data.get("items")
        if not isinstance(items, list):
            raise Sub2ApiError(f"账号列表第 {page} 页响应缺少 data.items 数组")
        for item in items:
            if not isinstance(item, dict):
                raise Sub2ApiError(f"账号列表第 {page} 页中存在非对象元素")
            if item.get("id") is None:
                raise Sub2ApiError(f"账号列表第 {page} 页中存在缺少 id 的记录")

        LOGGER.info(
            "已读取账号分页：page=%d, items=%d, total=%r, pages=%r",
            page,
            len(items),
            data.get("total"),
            data.get("pages"),
        )
        return data

    def list_all_accounts(
        self,
        *,
        page_size: int,
        filters: Mapping[str, Optional[str]],
        concurrency: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        按 ID 升序完整读取全部账号。

        先同步读取第一页以获得 total/pages，再并发读取其余页面。任意一页
        最终失败、分页元数据变化或唯一账号数与 total 不一致时，整次扫描失败。
        """
        first = self._fetch_accounts_page(page=1, page_size=page_size, filters=filters)
        first_items = first["items"]
        expected_total = to_positive_int(first.get("total"), default=len(first_items))
        expected_pages = to_positive_int(first.get("pages"), default=0)
        if expected_pages == 0:
            expected_pages = max(1, (expected_total + page_size - 1) // page_size)
        if expected_pages > 1_000_000:
            raise Sub2ApiError("分页数量异常，已停止以避免资源耗尽")

        pages: Dict[int, Dict[str, Any]] = {1: first}
        if expected_pages > 1:
            worker_count = min(max(1, concurrency), expected_pages - 1)
            LOGGER.info(
                "共 %d 页，使用 %d 个并发线程读取剩余 %d 页",
                expected_pages,
                worker_count,
                expected_pages - 1,
            )
            executor = ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="sub2api-scan")
            futures: Dict[Future[Dict[str, Any]], int] = {}
            try:
                for page in range(2, expected_pages + 1):
                    future = executor.submit(
                        self._fetch_accounts_page,
                        page=page,
                        page_size=page_size,
                        filters=filters,
                    )
                    futures[future] = page

                for future in as_completed(futures):
                    page = futures[future]
                    try:
                        data = future.result()
                    except BaseException as exc:
                        for pending in futures:
                            if pending is not future:
                                pending.cancel()
                        raise Sub2ApiError(f"并发读取账号第 {page} 页失败，无法建立完整快照：{exc}") from exc
                    pages[page] = data
            finally:
                executor.shutdown(wait=True, cancel_futures=True)

        all_accounts: List[Dict[str, Any]] = []
        seen_ids = set()
        for page in range(1, expected_pages + 1):
            data = pages.get(page)
            if data is None:
                raise Sub2ApiError(f"账号第 {page} 页缺失，扫描结果不完整")

            page_total = to_positive_int(data.get("total"), default=expected_total)
            page_pages = to_positive_int(data.get("pages"), default=expected_pages)
            if page_total != expected_total or page_pages != expected_pages:
                raise Sub2ApiError(
                    "分页扫描期间账号数据发生变化："
                    f"第 1 页 total/pages={expected_total}/{expected_pages}，"
                    f"第 {page} 页为 {page_total}/{page_pages}"
                )

            for item in data["items"]:
                marker = str(item.get("id"))
                if marker in seen_ids:
                    raise Sub2ApiError(f"分页结果重复出现账号 ID={marker}，扫描快照不一致")
                seen_ids.add(marker)
                all_accounts.append(item)

        if len(seen_ids) != expected_total:
            raise Sub2ApiError(
                "账号分页扫描不完整或扫描期间数据发生变化："
                f"接口 total={expected_total}，实际唯一账号数={len(seen_ids)}"
            )

        all_accounts.sort(key=id_sort_key)
        return all_accounts

    def delete_account(self, account_id: Any) -> bool:
        """删除账号；返回 True 表示删除前目标已不存在。"""
        encoded_id = quote(str(account_id), safe="")
        _, already_absent = self.request_json(
            "DELETE",
            f"{self.accounts_url}/{encoded_id}",
            allow_delete_not_found=True,
        )
        return already_absent


def build_accounts_url(base_url: str) -> str:
    """允许传入站点根地址、/api/v1、/api/v1/admin 或完整 accounts 地址。"""
    raw = base_url.strip()
    if not raw:
        raise ValueError("base URL 不能为空")

    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base URL 必须是完整的 http:// 或 https:// 地址")
    if parsed.query or parsed.fragment:
        raise ValueError("base URL 不应包含查询参数或片段")

    path = parsed.path.rstrip("/")
    if path.endswith("/api/v1/admin/accounts"):
        accounts_path = path
    elif path.endswith("/api/v1/admin"):
        accounts_path = f"{path}/accounts"
    elif path.endswith("/api/v1"):
        accounts_path = f"{path}/admin/accounts"
    else:
        accounts_path = f"{path}/api/v1/admin/accounts"

    return urlunsplit((parsed.scheme, parsed.netloc, accounts_path, "", ""))


def parse_json_bytes(raw: bytes, http_status: int) -> Any:
    if not raw:
        raise Sub2ApiError(f"HTTP {http_status} 响应体为空")
    return json.loads(raw.decode("utf-8-sig"))


def try_parse_json_bytes(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def unwrap_api_response(payload: Any, http_status: int) -> Any:
    if not isinstance(payload, dict):
        raise Sub2ApiError(f"HTTP {http_status} 响应应为 JSON 对象，实际为 {type(payload).__name__}")

    if "code" not in payload:
        raise Sub2ApiError("响应缺少 sub2api 标准字段 code")

    code = payload.get("code")
    if code not in SUCCESS_API_CODES:
        message = payload.get("message") or "未知 API 错误"
        raise Sub2ApiError(
            f"HTTP {http_status}, API code={code!r}: {message}",
            http_status=http_status,
            api_code=code,
        )

    return payload.get("data")


def extract_api_error(payload: Any, fallback: Any) -> Tuple[Any, str]:
    if isinstance(payload, dict):
        return payload.get("code"), str(payload.get("message") or fallback)
    return None, str(fallback or "HTTP 请求失败")


def format_api_error(
    *,
    method: str,
    url: str,
    http_status: int,
    api_code: Any,
    message: str,
) -> str:
    parts = [f"{method} {redact_url(url)} 失败", f"HTTP {http_status}"]
    if api_code is not None:
        parts.append(f"API code={api_code!r}")
    parts.append(message)
    return "; ".join(parts)


def redact_url(url: str) -> str:
    """当前 URL 不含密钥；保留此函数防止未来查询参数扩展时意外泄漏。"""
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def retry_delay(
    *,
    attempt: int,
    base: float,
    maximum: float,
    retry_after: Optional[str],
) -> float:
    parsed_retry_after = parse_retry_after(retry_after)
    if parsed_retry_after is not None:
        return min(maximum, max(0.0, parsed_retry_after))

    exponential = min(maximum, base * (2**attempt))
    # Full jitter 可避免多个脚本在服务恢复时同时重试。
    return random.uniform(0.0, exponential)


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    value = value.strip()
    try:
        return float(value)
    except ValueError:
        pass

    try:
        target = email.utils.parsedate_to_datetime(value)
        if target.tzinfo is None:
            target = target.replace(tzinfo=timezone.utc)
        return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def print_retry(number: int, retries: int, delay: float, error: BaseException) -> None:
    LOGGER.warning(
        "请求失败，%.2f 秒后进行第 %d/%d 次重试：%s",
        delay,
        number,
        retries,
        error,
    )


def to_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else default
    except (TypeError, ValueError):
        return default


def normalize_name(name: Any, *, trim: bool, ignore_case: bool) -> str:
    result = "" if name is None else str(name)
    if trim:
        result = result.strip()
    if ignore_case:
        result = result.casefold()
    return result


def id_sort_key(account: Mapping[str, Any]) -> Tuple[int, Any]:
    value = account.get("id")
    try:
        return 0, int(value)
    except (TypeError, ValueError):
        return 1, str(value)


def created_at_sort_key(account: Mapping[str, Any]) -> Tuple[int, datetime, Tuple[int, Any]]:
    raw = account.get("created_at")
    if isinstance(raw, str) and raw.strip():
        text = raw.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            else:
                parsed = parsed.astimezone(timezone.utc)
            return 0, parsed, id_sort_key(account)
        except ValueError:
            pass
    return 1, datetime.max.replace(tzinfo=timezone.utc), id_sort_key(account)


def select_keeper(accounts: Sequence[Dict[str, Any]], policy: str) -> Dict[str, Any]:
    if policy == "lowest-id":
        return min(accounts, key=id_sort_key)
    if policy == "highest-id":
        return max(accounts, key=id_sort_key)
    if policy == "oldest":
        return min(accounts, key=created_at_sort_key)
    if policy == "newest":
        # 缺少或无法解析 created_at 的记录不应被误判为“最新”，因此先排除。
        valid = [a for a in accounts if created_at_sort_key(a)[0] == 0]
        if valid:
            return max(valid, key=created_at_sort_key)
        return max(accounts, key=id_sort_key)
    raise ValueError(f"未知保留策略: {policy}")


def build_duplicate_plan(
    accounts: Iterable[Dict[str, Any]],
    *,
    trim: bool,
    ignore_case: bool,
    keep_policy: str,
) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for account in accounts:
        if "name" not in account:
            raise Sub2ApiError(f"账号 ID={account.get('id')!r} 缺少 name 字段")
        key = normalize_name(account.get("name"), trim=trim, ignore_case=ignore_case)
        groups[key].append(account)

    plan: List[Dict[str, Any]] = []
    for normalized_name, members in groups.items():
        if len(members) < 2:
            continue
        keeper = select_keeper(members, keep_policy)
        delete = [a for a in members if str(a.get("id")) != str(keeper.get("id"))]
        delete.sort(key=id_sort_key)
        plan.append(
            {
                "normalized_name": normalized_name,
                "keep": keeper,
                "delete": delete,
                "members": sorted(members, key=id_sort_key),
            }
        )

    plan.sort(key=lambda group: (group["normalized_name"], id_sort_key(group["keep"])))
    return plan


def account_summary(account: Mapping[str, Any]) -> str:
    fields = [
        f"id={account.get('id')!r}",
        f"name={account.get('name')!r}",
        f"platform={account.get('platform')!r}",
        f"type={account.get('type')!r}",
        f"status={account.get('status')!r}",
    ]
    if account.get("created_at") is not None:
        fields.append(f"created_at={account.get('created_at')!r}")
    return ", ".join(fields)


def print_duplicate_plan(plan: Sequence[Dict[str, Any]]) -> Tuple[int, int]:
    duplicate_accounts = 0
    deletion_count = 0

    for index, group in enumerate(plan, start=1):
        members = group["members"]
        deletes = group["delete"]
        duplicate_accounts += len(members)
        deletion_count += len(deletes)

        raw_names = sorted({str(a.get("name", "")) for a in members})
        LOGGER.warning(
            "重复组 %d：匹配键=%r，原始名称=%r，共 %d 个",
            index,
            group["normalized_name"],
            raw_names,
            len(members),
        )
        keep_id = str(group["keep"].get("id"))
        for account in members:
            action = "保留" if str(account.get("id")) == keep_id else "删除"
            if action == "保留":
                LOGGER.info("  [保留] %s", account_summary(account))
            else:
                LOGGER.warning("  [删除] %s", account_summary(account))

    return duplicate_accounts, deletion_count


def flatten_deletions(plan: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for group in plan:
        for account in group["delete"]:
            result.append(account)
    return result


def execute_deletions(
    client: Sub2ApiClient,
    targets: Sequence[Dict[str, Any]],
    *,
    concurrency: int,
    start_interval: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """并发删除账号，返回（按原计划排序的结果，失败项）。"""
    if not targets:
        return [], []

    worker_count = min(max(1, concurrency), len(targets))
    limiter = StartRateLimiter(start_interval)
    results_by_index: Dict[int, Dict[str, Any]] = {}
    failures: List[Dict[str, Any]] = []
    completed = 0
    completed_lock = threading.Lock()

    def worker(index: int, account: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        limiter.wait()
        account_id = account.get("id")
        try:
            already_absent = client.delete_account(account_id)
            status = "already_absent" if already_absent else "deleted"
            return index, {"status": status, "account": account}
        except Sub2ApiError as exc:
            return index, {
                "status": "failed",
                "account": account,
                "error": str(exc),
            }

    LOGGER.warning(
        "开始并发删除 %d 个冗余账号，delete_concurrency=%d，启动间隔=%.3f 秒",
        len(targets),
        worker_count,
        start_interval,
    )

    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="sub2api-delete") as executor:
        futures: Dict[Future[Tuple[int, Dict[str, Any]]], int] = {}
        for index, account in enumerate(targets):
            futures[executor.submit(worker, index, account)] = index

        for future in as_completed(futures):
            index, result = future.result()
            results_by_index[index] = result
            with completed_lock:
                completed += 1
                progress = completed

            account = result["account"]
            if result["status"] == "failed":
                LOGGER.error(
                    "[%d/%d] 删除失败：%s；%s",
                    progress,
                    len(targets),
                    account_summary(account),
                    result["error"],
                )
                failures.append(result)
            else:
                label = "目标已不存在" if result["status"] == "already_absent" else "删除成功"
                LOGGER.info(
                    "[%d/%d] %s：%s",
                    progress,
                    len(targets),
                    label,
                    account_summary(account),
                )

    ordered_results = [results_by_index[index] for index in range(len(targets))]
    return ordered_results, failures


def prompt_for_deletion(count: int) -> bool:
    if not sys.stdin.isatty():
        LOGGER.error("标准输入不是交互终端；请传入 --yes 才能执行删除")
        return False
    LOGGER.warning("即将删除 %d 个账号；此操作不可撤销", count)
    answer = input("请输入 DELETE 继续: ").strip()
    return answer == "DELETE"


def write_json_report(path: str, report: Mapping[str, Any]) -> None:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(report, file, ensure_ascii=False, indent=2, default=str)
        file.write("\n")
    os.replace(temporary, target)


def plan_for_report(plan: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    output = []
    for group in plan:
        output.append(
            {
                "normalized_name": group["normalized_name"],
                "keep": group["keep"],
                "delete": group["delete"],
            }
        )
    return output


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="通过 sub2api Admin REST API 检查并清理同名重复账号。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SUB2API_BASE_URL"),
        help="sub2api 根地址；也可使用环境变量 SUB2API_BASE_URL",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("SUB2API_ADMIN_API_KEY"),
        help=("Admin API Key；也可使用环境变量 SUB2API_ADMIN_API_KEY。" "为避免密钥出现在进程参数中，优先使用环境变量"),
    )
    parser.add_argument("--page-size", type=int, default=1000, help="每页账号数，范围 1-1000")
    parser.add_argument(
        "--scan-concurrency",
        type=int,
        default=4,
        help="并发读取账号分页的线程数；第一页始终先同步读取",
    )
    parser.add_argument(
        "--delete-concurrency",
        type=int,
        default=4,
        help="并发删除冗余账号的线程数",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="单次 HTTP 请求超时秒数")
    parser.add_argument("--retries", type=int, default=4, help="每个请求失败后的最大重试次数")
    parser.add_argument("--backoff-base", type=float, default=1.0, help="指数退避基础秒数")
    parser.add_argument("--backoff-max", type=float, default=30.0, help="单次重试等待上限秒数")
    parser.add_argument(
        "--keep",
        choices=("lowest-id", "highest-id", "oldest", "newest"),
        default="lowest-id",
        help="每个同名组中保留哪个账号",
    )
    parser.add_argument("--trim-name", action="store_true", help="比较名称前去除首尾空白")
    parser.add_argument("--ignore-case", action="store_true", help="比较名称时忽略大小写")
    parser.add_argument("--apply", action="store_true", help="实际删除；不传时只做预览")
    parser.add_argument("--yes", action="store_true", help="与 --apply 一起使用，跳过交互确认")
    parser.add_argument(
        "--delete-interval",
        type=float,
        default=0.0,
        help="并发删除时，相邻 DELETE 请求启动之间的最小间隔秒数",
    )
    parser.add_argument("--insecure", action="store_true", help="关闭 TLS 证书验证（不推荐）")
    parser.add_argument("--report", help="将扫描、删除和验证结果写入指定 JSON 文件")
    parser.add_argument(
        "--fail-on-duplicates",
        action="store_true",
        help="预览模式发现重复账号时以退出码 3 结束，便于监控脚本判断",
    )
    parser.add_argument(
        "--log-level",
        choices=("info", "warning", "error"),
        default="info",
        help="最低输出等级：info、warning 或 error",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="日志颜色模式；auto 仅在终端中启用颜色",
    )

    # 以下参数直接映射到 GET /api/v1/admin/accounts 的可选筛选条件。
    parser.add_argument("--platform", help="只检查指定 platform")
    parser.add_argument("--account-type", dest="account_type", help="只检查指定账号 type")
    parser.add_argument("--status", help="只检查指定 status")
    parser.add_argument("--group", help="只检查指定 group")
    parser.add_argument("--search", help="只检查服务端 search 筛选后的账号")
    parser.add_argument(
        "--privacy-mode",
        choices=("true", "false"),
        help="只检查指定 privacy_mode 的账号",
    )

    args = parser.parse_args(argv)

    if not args.base_url:
        parser.error("缺少 --base-url 或环境变量 SUB2API_BASE_URL")
    if not args.api_key:
        parser.error("缺少 --api-key 或环境变量 SUB2API_ADMIN_API_KEY")
    if not 1 <= args.page_size <= 1000:
        parser.error("--page-size 必须在 1 到 1000 之间")
    if args.scan_concurrency < 1:
        parser.error("--scan-concurrency 必须大于或等于 1")
    if args.delete_concurrency < 1:
        parser.error("--delete-concurrency 必须大于或等于 1")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    if args.retries < 0:
        parser.error("--retries 不能小于 0")
    if args.backoff_base < 0 or args.backoff_max < 0:
        parser.error("退避时间不能小于 0")
    if args.delete_interval < 0:
        parser.error("--delete-interval 不能小于 0")
    if args.yes and not args.apply:
        parser.error("--yes 只能与 --apply 一起使用")

    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    global LOGGER
    args = parse_args(argv)
    LOGGER = configure_logging(args.log_level, args.color)

    LOGGER.info(
        "运行参数：scan_concurrency=%d, delete_concurrency=%d, retries=%d, backoff_base=%.2f, backoff_max=%.2f, timeout=%.2f",
        args.scan_concurrency,
        args.delete_concurrency,
        args.retries,
        args.backoff_base,
        args.backoff_max,
        args.timeout,
    )

    try:
        client = Sub2ApiClient(
            args.base_url,
            args.api_key,
            timeout=args.timeout,
            retries=args.retries,
            backoff_base=args.backoff_base,
            backoff_max=args.backoff_max,
            verify_tls=not args.insecure,
        )
    except ValueError as exc:
        LOGGER.error("参数错误：%s", exc)
        return 2

    if args.insecure:
        LOGGER.error("已关闭 TLS 证书验证，Admin API Key 可能遭到中间人窃取")

    filters = {
        "platform": args.platform,
        "type": args.account_type,
        "status": args.status,
        "group": args.group,
        "search": args.search,
        "privacy_mode": args.privacy_mode,
    }
    active_filters = {k: v for k, v in filters.items() if v is not None and v != ""}
    if active_filters:
        LOGGER.warning("当前仅在筛选结果内去重：%r", active_filters)

    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "apply" if args.apply else "dry-run",
        "accounts_url": client.accounts_url,
        "filters": active_filters,
        "name_matching": {
            "trim": args.trim_name,
            "ignore_case": args.ignore_case,
        },
        "keep_policy": args.keep,
        "concurrency": {
            "scan": args.scan_concurrency,
            "delete": args.delete_concurrency,
            "delete_start_interval": args.delete_interval,
        },
        "scan": {},
        "deletions": [],
        "verification": None,
    }

    try:
        LOGGER.info("正在读取账号列表：%s", client.accounts_url)
        accounts = client.list_all_accounts(
            page_size=args.page_size,
            filters=filters,
            concurrency=args.scan_concurrency,
        )
        plan = build_duplicate_plan(
            accounts,
            trim=args.trim_name,
            ignore_case=args.ignore_case,
            keep_policy=args.keep,
        )
    except (Sub2ApiError, OSError) as exc:
        LOGGER.error("扫描失败：%s", exc)
        report["fatal_error"] = str(exc)
        if args.report:
            write_json_report(args.report, report)
        return 1

    duplicate_accounts, deletion_count = print_duplicate_plan(plan)
    report["scan"] = {
        "account_count": len(accounts),
        "duplicate_group_count": len(plan),
        "accounts_in_duplicate_groups": duplicate_accounts,
        "planned_deletion_count": deletion_count,
        "groups": plan_for_report(plan),
    }

    if plan:
        LOGGER.warning(
            "扫描完成：共 %d 个账号，发现 %d 个重复名称组，计划删除 %d 个冗余账号",
            len(accounts),
            len(plan),
            deletion_count,
        )
    else:
        LOGGER.info("扫描完成：共 %d 个账号，未发现重复名称", len(accounts))

    if not plan:
        LOGGER.info("未发现重复账号，无需处理")
        if args.report:
            write_json_report(args.report, report)
            LOGGER.info("报告已写入：%s", args.report)
        return 0

    if not args.apply:
        LOGGER.info("当前为预览模式，未执行任何删除；传入 --apply 后才会实际删除")
        if args.report:
            write_json_report(args.report, report)
            LOGGER.info("报告已写入：%s", args.report)
        return 3 if args.fail_on_duplicates else 0

    if not args.yes and not prompt_for_deletion(deletion_count):
        LOGGER.warning("已取消，未执行删除")
        report["cancelled"] = True
        if args.report:
            write_json_report(args.report, report)
        return 2

    targets = flatten_deletions(plan)
    deletion_results, failures = execute_deletions(
        client,
        targets,
        concurrency=args.delete_concurrency,
        start_interval=args.delete_interval,
    )
    report["deletions"] = deletion_results

    try:
        LOGGER.info("正在重新扫描并验证去重结果")
        remaining_accounts = client.list_all_accounts(
            page_size=args.page_size,
            filters=filters,
            concurrency=args.scan_concurrency,
        )
        remaining_plan = build_duplicate_plan(
            remaining_accounts,
            trim=args.trim_name,
            ignore_case=args.ignore_case,
            keep_policy=args.keep,
        )
        report["verification"] = {
            "account_count": len(remaining_accounts),
            "duplicate_group_count": len(remaining_plan),
            "groups": plan_for_report(remaining_plan),
        }
    except (Sub2ApiError, OSError) as exc:
        LOGGER.error("验证扫描失败：%s", exc)
        report["verification"] = {"error": str(exc)}
        if args.report:
            write_json_report(args.report, report)
        return 1

    if remaining_plan:
        LOGGER.error("验证失败：仍存在以下重复账号：")
        print_duplicate_plan(remaining_plan)
    else:
        LOGGER.info("验证成功：当前筛选范围内已不存在同名重复账号")

    if failures:
        LOGGER.error("删除过程中共有 %d 个账号失败", len(failures))

    if args.report:
        write_json_report(args.report, report)
        LOGGER.info("报告已写入：%s", args.report)

    return 1 if failures or remaining_plan else 0


if __name__ == "__main__":
    raise SystemExit(main())

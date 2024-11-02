# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-11-02

import argparse
import concurrent.futures
import json
import os
import random
from copy import deepcopy
from datetime import datetime

import mailtm
import utils
from logger import logger

# 接口地址
API_ADDRESS = "https://api.agicto.cn/v1"

# 默认请求头
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Content-Type": "application/json",
    "Origin": "https://agicto.com",
    "Referrer": "https://agicto.com/",
    "User-Agent": utils.USER_AGENT,
}


def send_verify_code(email: str, retry: int = 3) -> bool:
    email = utils.trim(email)
    if not email:
        logger.error(f"[SendVerifyCode] email can not be empty")
        return False

    payload = {"email": email, "channel": ""}
    url = f"{API_ADDRESS}/sendVerifyCode"

    response = utils.http_post(url=url, headers=DEFAULT_HEADERS, params=payload, retry=max(retry, 1), timeout=10)
    data = utils.read_response(response=response, deserialize=True)
    return False if not data else data.get("code", 1) == 0


def login(email: str, verify_code: str, invite_code: str = "", retry: int = 3) -> str:
    email, verify_code = utils.trim(email), utils.trim(verify_code)
    if not email or not verify_code:
        logger.error(f"[Login] email and verify code can not be empty")
        return ""

    url = f"{API_ADDRESS}/loginByCode"
    payload = {"email": email, "verify_code": verify_code, "invite_code": utils.trim(invite_code)}

    response = utils.http_post(url=url, headers=DEFAULT_HEADERS, params=payload, retry=max(retry, 1), timeout=10)
    data = utils.read_response(response=response, deserialize=True, key="data")
    if not data or not isinstance(data, dict):
        logger.error(f"[Login] reqeust failed, email: {email}, verify_code: {verify_code}, invite_code: {invite_code}")
        return ""

    return data.get("access_token", "")


def query_quota(token: str) -> float:
    token = utils.trim(token)
    if not token:
        logger.error(f"[QueryQuota] access token can not be empty")
        return 0.0

    url = f"{API_ADDRESS}/me?withCredentials=true"
    headers = deepcopy(DEFAULT_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    content = utils.http_get(url=url, headers=headers, interval=1, retry=3, timeout=10)
    try:
        result = json.loads(content)
        if not result or not isinstance(result, dict) or result.get("code", 1) != 0:
            return 0.0

        data = result.get("data", {})
        if not data or not isinstance(data, dict):
            return 0.0

        remain = data.get("apiNum", "0.0")
        return float(remain) if isinstance(remain, str) else remain if isinstance(remain, (int, float)) else 0.0
    except:
        logger.error("[QueryQuota] request failed, token: {}".format(token))
        return 0.0


def list_keys(token: str) -> list[str]:
    token = utils.trim(token)
    if not token:
        logger.error(f"[ListKeys] access token can not be empty")
        return []

    url = f"{API_ADDRESS}/service/keyList"
    headers = deepcopy(DEFAULT_HEADERS)
    headers["Authorization"] = f"Bearer {token}"

    respone = utils.http_post(url=url, headers=headers, params={}, retry=3, timeout=10)
    data = utils.read_response(response=respone, deserialize=True, key="data")
    if not data or not isinstance(data, dict):
        logger.error(f"[ListKeys] request failed, token: {token}")
        return []

    records = data.get("recordList", [])
    if not records or not isinstance(records, list):
        logger.warning(f"[ListKeys] can not found any keys, token: {token}")
        return []

    return [utils.trim(item.get("openKey", "")) for item in records if item and isinstance(item, dict)]


def register(filepath: str, invite_code: str = "") -> None:
    filepath = utils.trim(filepath)
    if not filepath:
        logger.error(f"[Register] must specify file path to save registered keys")
        return

    mailbox = mailtm.create_instance()
    account = mailbox.get_account()
    if not account:
        logger.error(f"[Register] cannot create temporary email account, site: {mailbox.api_address}")
        return

    message, email, retry = None, account.address, 3
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(mailbox.monitor_account, account, 120, random.randint(1, 3))
            success = send_verify_code(email=account.address, retry=retry)
            if not success:
                executor.shutdown(wait=False)
                return

            logger.info(f"[Register] email has been sent, domain: {mailbox.api_address}, email: {email}")
            message = future.result(timeout=120)
        except concurrent.futures.TimeoutError:
            logger.error(f"[Register] receiving mail timeout, site: {mailbox.api_address}, email: {email}")

    if not message:
        logger.error(f"[Register] cannot receive any message, site: {mailbox.api_address}, email: {email}")
        return

    mask = mailbox.extract_mask(message.text, r"登录验证码\n+([0-9]{6})\n+")
    mailbox.delete_account(account=account)
    if not mask:
        logger.error(f"[Register] cannot fetch mask, message: {message.text}")
        return

    access_token = login(email=account.address, verify_code=mask, invite_code=invite_code, retry=retry)
    if not access_token:
        return

    quota = query_quota(token=access_token)
    if quota <= 0.0:
        logger.warning(f"[Register] register success but no quota, email: {email}")
        return
    else:
        logger.info(f"[Register] register success, email: {email}, quota: {quota}")

    keys = list_keys(token=access_token)
    if not keys:
        return

    url = f"{API_ADDRESS}/chat/completions"
    content = ",".join([x for x in keys if x])
    utils.write_file(
        filename=os.path.abspath(filepath),
        lines=f"api: {url}  address: {mailbox.api_address}  email: {email}  keys: {content}\n",
    )

    logger.info(f"[Register] register success, email: {email}, keys: {content}")


def main(filepath: str, num: int, invite_code: str = "") -> None:
    def _register_wrap(index: int, filepath: str, invite_code: str = "") -> None:
        logger.info(f"[Register] start register {index}th account")

        register(filepath=filepath, invite_code=invite_code)

        logger.info(f"[Register] finish register {index}th account")

    filepath = utils.trim(filepath)
    if not filepath:
        logger.error(f"[Main] must specify file path to save registered keys")
        return

    directory = os.path.abspath(filepath)
    if os.path.exists(directory):
        if not os.path.isfile(directory):
            logger.error(f"[Main] specified file path is not valid, path: {filepath}")
            return

        # rename and backup existing file
        now = datetime.strftime(datetime.now(), "%Y%m%d%H%M%S")
        backup = f"{directory}.{now}"
        os.rename(directory, backup)
        logger.info(f"[Main] existing file has been backuped, backup: {backup}")

    # limit the number of accounts to register
    num = min(max(1, num), 50)
    tasks = [[i, directory, invite_code] for i in range(1, num + 1)]

    # parallel register
    utils.multi_thread_run(func=_register_wrap, tasks=tasks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-f",
        "--filepath",
        type=str,
        required=False,
        default="accounts.txt",
        help="file path to save account info",
    )

    parser.add_argument(
        "-i",
        "--invite",
        type=str,
        required=False,
        default="",
        help="invite code to register",
    )

    parser.add_argument(
        "-n",
        "--num",
        type=int,
        required=False,
        default=1,
        help="number of accounts to register",
    )

    args = parser.parse_args()
    main(filepath=args.filepath, num=args.num, invite_code=args.invite)

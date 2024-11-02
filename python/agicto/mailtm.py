# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-07-15

import json
import random
import re
import time
import urllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.client import HTTPMessage
from typing import IO, Dict

import utils
from logger import logger


@dataclass
class Message:
    """simple data class that holds a message information."""

    text: str
    id: str = ""
    sender: Dict = None
    to: Dict = None
    subject: str = ""
    intro: str = ""
    html: str = ""
    data: Dict = None


@dataclass
class Account:
    """representing a temprary mailbox."""

    address: str
    password: str = ""
    id: str = ""


class TemporaryMail(object):
    """temporary mails collctions: https://www.cnblogs.com/perfectdata/p/15902582.html"""

    def __init__(self) -> None:
        self.api_address = ""

    def get_domains_list(self) -> list:
        raise NotImplementedError

    def get_account(self, retry: int = 3) -> Account:
        raise NotImplementedError

    def get_messages(self, account: Account) -> list:
        raise NotImplementedError

    def monitor_account(self, account: Account, timeout: int = 300, sleep: int = 3) -> Message:
        """keep waiting for new messages"""
        if not account:
            return None

        timeout = min(600, max(0, timeout))
        sleep = min(max(1, sleep), 10)
        endtime = time.time() + timeout
        try:
            messages = self.get_messages(account=account)
            start = len(messages)

            while True:
                messages = self.get_messages(account=account)
                if len(messages) != start or time.time() >= endtime:
                    break

                time.sleep(sleep)

            if not messages:
                return None

            return messages[0]
        except:
            logger.error(f"cannot get any message from address: {account.address}")
            return None

    def delete_account(self, account: Account) -> bool:
        raise NotImplementedError

    def extract_mask(self, text: str, regex: str = "您的验证码是：([0-9]{6})") -> str:
        if not text or not regex:
            return ""
        try:
            # return "".join(re.findall(regex, text))
            masks = re.findall(regex, text)
            return masks[0] if masks else ""
        except:
            logger.error(f"[MaskExtractError] regex exists problems, regex: {regex}")
            return ""

    def generate_address(self, bits: int = 10) -> str:
        bits = min(max(6, bits), 16)
        username = utils.random_chars(length=bits, punctuation=False).lower()
        email_domains = self.get_domains_list()
        if not email_domains:
            logger.error(f"[MailTMError] cannot found any email domains from remote, domain: {self.api_address}")
            return ""

        domain = random.choice(email_domains)
        address = "{}@{}".format(username, domain)

        return address


class MailTM(TemporaryMail):
    """a python wrapper for mail.tm web api, which is documented here: https://api.mail.tm/"""

    def __init__(self) -> None:
        self.api_address = "https://api.mail.tm"
        self.auth_headers = {}

    def get_domains_list(self) -> list:
        headers = {"Accept": "application/ld+json"}
        try:
            content = utils.http_get(url=f"{self.api_address}/domains?page=1", headers=headers)
            if not content:
                return []

            response = json.loads(content)
            return list(map(lambda x: x.get("domain", ""), response.get("hydra:member", [])))
        except:
            return []

    def _make_account_request(self, endpoint: str, address: str, password: str, retry: int = 3) -> Dict:
        if retry <= 0:
            return {}

        account = {"address": address, "password": password}
        headers = {"Accept": "application/ld+json", "Content-Type": "application/json"}

        data = bytes(json.dumps(account), encoding="UTF8")
        try:
            request = urllib.request.Request(
                url=f"{self.api_address}/{endpoint}",
                data=data,
                headers=headers,
                method="POST",
            )
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            if not response or response.getcode() not in [200, 201]:
                return {}

            return json.loads(response.read())
        except:
            return self._make_account_request(endpoint=endpoint, address=address, password=password, retry=retry - 1)

    def _generate_jwt(self, address: str, password: str, retry: int = 3):
        jwt = self._make_account_request(endpoint="token", address=address, password=password, retry=retry)
        if not jwt:
            logger.error(f"[JWTError] generate jwt token failed, domain: {self.api_address}")
            return

        self.auth_headers = {
            "Accept": "application/ld+json",
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(jwt["token"]),
        }

    def get_account(self, retry: int = 3) -> Account:
        """create and return a new account."""
        address = self.generate_address(random.randint(6, 12))
        if not address:
            return None

        password = utils.random_chars(length=random.randint(8, 16), punctuation=True)
        response = self._make_account_request(endpoint="accounts", address=address, password=password, retry=retry)
        if not response or "id" not in response or "address" not in response:
            logger.error(f"[MailTMError] failed to create temporary email, domain: {self.api_address}")
            return None

        account = Account(address=response["address"], password=password, id=response["id"])
        self._generate_jwt(address=address, password=password, retry=retry)

        return account

    def get_messages(self, account: Account) -> list:
        """download a list of messages currently in the account."""
        if not account or not self.auth_headers:
            return []

        content = utils.http_get(
            url="{}/messages?page={}".format(self.api_address, 1),
            headers=self.auth_headers,
            retry=2,
        )

        messages = []
        if not content:
            return messages

        try:
            dataset = json.loads(content).get("hydra:member", [])
            for message_data in dataset:
                content = utils.http_get(
                    url=f"{self.api_address}/messages/{message_data['id']}",
                    headers=self.auth_headers,
                )
                if not content:
                    continue

                data = json.loads(content)
                text = data.get("text", "")
                html = data.get("html", "")
                messages.append(
                    Message(
                        id=message_data["id"],
                        sender=message_data["from"],
                        to=message_data["to"],
                        subject=message_data["subject"],
                        intro=message_data["intro"],
                        text=text,
                        html=html,
                        data=message_data,
                    )
                )
        except:
            logger.error(f"failed to list messages, email: {self.address}")
        return messages

    def delete_account(self, account: Account) -> bool:
        """try to delete the account. returns True if it succeeds."""
        if account is None or not self.auth_headers:
            return False

        try:
            request = urllib.request.Request(
                url=f"{self.api_address}/accounts/{account.id}",
                headers=self.auth_headers,
                method="DELETE",
            )
            response = urllib.request.urlopen(request, timeout=10, context=utils.CTX)
            status_code = response.getcode()
            return status_code == 204
        except Exception:
            logger.info(f"[MailTMError] delete account failed, domain: {self.api_address}, address: {account.address}")
            return False


class MOAKT(TemporaryMail):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def http_error_302(
            self,
            req: urllib.request.Request,
            fp: IO[bytes],
            code: int,
            msg: str,
            headers: HTTPMessage,
        ) -> IO[bytes]:
            return fp

    def __init__(self) -> None:
        self.api_address = "https://www.moakt.com/zh"
        self.headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": self.api_address,
            "Referer": self.api_address,
            "User-Agent": utils.USER_AGENT,
        }

    def get_domains_list(self) -> list:
        content = utils.http_get(url=self.api_address)
        if not content:
            return []

        return re.findall(r'<option\s+value=".*">@([a-zA-Z0-9\.\-_]+)<\/option>', content)

    def _make_account_request(self, username: str, domain: str, retry: int = 3) -> Account:
        if retry <= 0:
            return None

        payload = {
            "domain": domain,
            "username": username,
            "preferred_domain": domain,
            "setemail": "创建",
        }

        data = bytes(json.dumps(payload), encoding="UTF8")
        try:
            # 禁止重定向
            opener = urllib.request.build_opener(self.NoRedirect)
            request = urllib.request.Request(
                url=f"{self.api_address}/inbox",
                data=data,
                headers=self.headers,
                method="POST",
            )
            response = opener.open(request, timeout=10)
            if not response or response.getcode() not in [200, 302]:
                return None

            self.headers["Cookie"] = response.getheader("Set-Cookie")
            return Account(address=f"{username}@{domain}")
        except:
            return self._make_account_request(username=username, domain=domain, retry=retry - 1)

    def get_account(self, retry: int = 3) -> Account:
        address = self.generate_address(bits=random.randint(6, 12))
        if not address or retry <= 0:
            return None

        username, domain = address.split("@", maxsplit=1)
        return self._make_account_request(username=username, domain=domain, retry=retry)

    def get_messages(self, account: Account) -> list:
        if not account:
            return []

        messages = []
        content = utils.http_get(url=f"{self.api_address}/inbox", headers=self.headers)
        if not content:
            return messages

        mails = re.findall(r'<a\s+href="/zh(/email/[a-z0-9\-]+)">', content)
        if not mails:
            return messages

        for mail in mails:
            url = f"{self.api_address}{mail}/content/"
            content = utils.http_get(url=url, headers=self.headers)
            if not content:
                continue
            messages.append(Message(text=content, html=content))
        return messages

    def delete_account(self, account: Account) -> bool:
        if not account:
            return False

        utils.http_get(url=f"{self.api_address}/inbox/logout", headers=self.headers)
        return True


def create_instance() -> TemporaryMail:
    return MailTM() if random.randint(0, 1) == 0 else MOAKT()

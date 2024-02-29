# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-02-28


import functools
import os
import threading

# 项目根目录
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


def trim(content: str) -> str:
    if isinstance(content, (str, int, float)):
        return str(content).strip()

    return ""


def is_blank(content: str, strip=False) -> bool:
    return not trim(content) if strip else not content


def singleton(obj):
    _instance_dict = {}
    _instance_lock = threading.Lock()

    @functools.wraps(obj)
    def wrapper(*args, **kwargs):
        if obj in _instance_dict:
            return _instance_dict.get(obj)

        with _instance_lock:
            if obj not in _instance_dict:
                _instance_dict[obj] = obj(*args, **kwargs)
        return _instance_dict.get(obj)

    return wrapper

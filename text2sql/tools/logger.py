# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-02-28

import logging
import os
import sys

from tools.utils import BASE_DIR

# 日志等级
DEFAULT_LOG_LEVEL = logging.INFO

# 日志格式
DEFAULT_LOG_FMT = "%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s: %(message)s"

DEFAULT_LOG_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_LOG_DIRECTORY = os.path.join(BASE_DIR, "logs")
DEFAULT_LOG_FILENAME = "text-2-sql.log"


class Logger:
    def __init__(self):
        self._logger = logging.getLogger()
        if not os.path.exists(DEFAULT_LOG_DIRECTORY) or os.path.isfile(DEFAULT_LOG_DIRECTORY):
            os.makedirs(DEFAULT_LOG_DIRECTORY)

        if not self._logger.handlers:
            self.formatter = logging.Formatter(fmt=DEFAULT_LOG_FMT, datefmt=DEFAULT_LOG_DATETIME_FORMAT)
            self._logger.addHandler(self._get_console_handler())
            self._logger.addHandler(
                self._get_file_handler(filename=os.path.join(DEFAULT_LOG_DIRECTORY, DEFAULT_LOG_FILENAME))
            )
            self._logger.setLevel(DEFAULT_LOG_LEVEL)

        # if python's version is 2, disable requests output info level log
        if sys.version_info.major == 2:
            logging.getLogger("requests").setLevel(logging.WARNING)

    def _get_file_handler(self, filename):
        """返回一个文件日志handler"""
        file_handler = logging.FileHandler(filename=filename, encoding="utf8")
        file_handler.setFormatter(self.formatter)
        return file_handler

    def _get_console_handler(self):
        """返回一个输出到终端日志handler"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(self.formatter)
        return console_handler

    @property
    def logger(self):
        return self._logger


logger = Logger().logger

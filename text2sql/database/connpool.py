# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-02-28

from dbutils.pooled_db import PooledDB

from database import config
from tools import utils


class MyConnectionPool(object):
    __pool = None

    def __verify__(self):
        """验证数据库配置是否正确"""
        for item in [config.DB_HOST, config.DB_USERNAME, config.DB_PASSWORD, config.DB_DATABASE]:
            if utils.is_blank(item, True):
                return False

        return isinstance(config.DB_PORT, int) and config.DB_PORT > 0 and config.DB_PORT <= 65535

    def __enter__(self):
        """创建数据库连接 conn 和游标 cursor"""
        self.conn = self.__getconn()
        self.cursor = self.conn.cursor()

    def __getconn(self):
        """创建数据库连接池"""
        if self.__pool is None:
            if not self.__verify__():
                raise ValueError("数据库连接配置错误")

            self.__pool = PooledDB(
                host=utils.trim(config.DB_HOST),
                port=config.DB_PORT,
                user=utils.trim(config.DB_USERNAME),
                passwd=utils.trim(config.DB_PASSWORD),
                db=utils.trim(config.DB_DATABASE),
                creator=config.DB_CREATOR,
                mincached=config.DB_MIN_CACHED,
                maxcached=config.DB_MAX_CACHED,
                maxshared=config.DB_MAX_SHARED,
                maxconnections=config.DB_MAX_CONNECYIONS,
                blocking=config.DB_BLOCKING,
                maxusage=config.DB_MAX_USAGE,
                setsession=config.DB_SET_SESSION,
                use_unicode=False,
                charset=config.DB_CHARSET,
            )

        return self.__pool.connection()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """释放连接池资源"""
        self.cursor.close()
        self.conn.close()

    def getconn(self):
        """从连接池中取出一个连接"""
        conn = self.__getconn()
        cursor = conn.cursor()
        return conn, cursor


@utils.singleton
def get_instance():
    return MyConnectionPool()

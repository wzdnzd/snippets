# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-02-28

import time
from datetime import datetime

from database.connpool import get_instance
from history import ChatHistory
from tools import utils
from tools.logger import logger


class MySqLClient(object):
    def __init__(self):
        # 从数据池中获取连接
        self.db = get_instance()

    def execute(self, sql, param=None, autoclose=False, retry=3):
        """执行SQL语句"""
        count, retry = 0, max(0, retry)

        # 从连接池获取连接
        conn, cursor = self.db.getconn()
        try:
            if param:
                count = cursor.execute(sql, param)
            else:
                count = cursor.execute(sql)

            conn.commit()
            if autoclose:
                self.close(conn, cursor)
        except Exception as e:
            logger.error(e)

            if retry > 0:
                conn.rollback()
                self.close(conn, cursor)
                return self.execute(sql, param, autoclose, retry - 1)

        return conn, cursor, count

    def close(self, conn, cursor):
        """释放连接归还给连接池"""
        if cursor:
            cursor.close()

        if conn:
            conn.close()

    def __select(self, sql, param=None, all=False):
        """查询单条数据"""
        conn, cursor = None, None

        try:
            conn, cursor, _ = self.execute(sql, param)
            result = cursor.fetchall() if all else cursor.fetchone()
            self.close(conn, cursor)
            return result
        except Exception as e:
            logger.error(e)
            self.close(conn, cursor)
            return None

    def selectone(self, sql, param=None):
        """查询单条数据"""
        return self.__select(sql, param, False)

    def selectall(self, sql, param=None):
        """查询所有数据"""
        return self.__select(sql, param, True)

    def insertmany(self, sql, param, retry=3):
        """插入多行数据"""
        conn, cursor = self.db.getconn()
        count, retry = -1, max(0, retry)

        try:
            cursor.executemany(sql, param)
            conn.commit()
        except Exception as e:
            logger.error(e)
            conn.rollback()

        self.close(conn, cursor)
        return count

    def update(self, sql, param=None):
        """更新数据"""
        conn, cursor, count = None, None, -1

        try:
            conn, cursor, count = self.execute(sql, param)
            conn.commit()
        except Exception as e:
            logger.error(e)
            conn.rollback()

        self.close(conn, cursor)
        return count

    def insertone(self, sql, param):
        """插入单行数据"""
        return self.update(sql, param)

    def delete(self, sql, param=None):
        """删除数据"""
        return self.update(sql, param)

    def create(self, table, sql, overwrite=False):
        """创建表"""
        table, success = utils.trim(table), False
        if not table:
            logger.error("创建表失败，表名不能为空")
            return success

        conn, cursor = self.db.getconn()
        try:
            if overwrite:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")

            cursor.execute(sql)
            conn.commit()
            success = True
        except Exception as e:
            logger.error(e)
            conn.rollback()
            success = False

        self.close(conn, cursor)
        return success


def create_table(table: str, client: MySqLClient = None):
    """如果表不存在则创建表"""
    table = utils.trim(table)
    if not table:
        logger.error("创建表失败，表名不能为空")
        return False

    sql = f"""
        CREATE TABLE IF NOT EXISTS `{table}` (
            `id` int NOT NULL AUTO_INCREMENT COMMENT '主键',
            `conversation_id` varchar(255) NOT NULL COMMENT '对话 id',
            `message_id` varchar(255) NOT NULL COMMENT '消息 id',
            `question` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '用户提问的问题',
            `answer` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL COMMENT '服务提供的答案',
            `model` varchar(255) DEFAULT NULL COMMENT '使用的模型名称',
            `created` timestamp NOT NULL COMMENT '提问时间戳',
            `fb_score` tinyint NOT NULL DEFAULT '0' COMMENT '用户反馈，-1 表示负反馈，1 表示正反馈，0 表示未反馈',
            `fb_detail` text CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci COMMENT '用户反馈文本内容',
            PRIMARY KEY (`id` DESC),
            UNIQUE KEY `uk_message_id` (`message_id`) USING BTREE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
    """

    if not client:
        client = MySqLClient()

    return client.create(table, sql, False)


def save_history(table: str, history: ChatHistory, client: MySqLClient = None) -> bool:
    """保存对话历史"""
    error, table = "保存对话历史失败，", utils.trim(table)
    if not table:
        logger.error(f"{error}表名不能为空")
        return False

    if not history or not isinstance(history, ChatHistory):
        logger.error(f"{error}对话历史数据不能为空")
        return False

    conversation_id = utils.trim(history.conversation_id)
    if not conversation_id:
        logger.error(f"{error}对话 id 不能为空")
        return False

    message_id = utils.trim(history.message_id)
    if not message_id:
        logger.error(f"{error}消息 id 不能为空")
        return False

    question = utils.trim(history.question)
    if not question:
        logger.error(f"{error}用户提问的问题不能为空")
        return False

    answer = utils.trim(history.answer)
    if not answer:
        logger.error(f"{error}服务提供的答案不能为空")
        return False

    created = history.created if history.created else int(time.time())
    model = utils.trim(history.model)
    timestamp = datetime.fromtimestamp(created).strftime("%Y-%m-%d %H:%M:%S")

    fb_score = history.fb_score if history.fb_score is not None else 0
    fb_detail = utils.trim(history.fb_detail)

    sql = f"INSERT INTO `{table}` (`conversation_id`, `message_id`, `question`, `answer`, `model`, `created`, `fb_score`, `fb_detail`) VALUES ('{conversation_id}', '{message_id}', '{question}', '{answer}', '{model}', '{timestamp}', '{fb_score}', '{fb_detail}');"

    client = MySqLClient() if not client else client
    return client.insertone(sql, None) == 1


def save_feedback(
    table: str, message_id: str, fb_score: int, fb_detail: str, client: MySqLClient = None, strict: bool = True
) -> tuple[bool, str]:
    """保存用户反馈"""
    goon, error, warn = True, "保存用户反馈失败，", ""

    table = utils.trim(table)
    message_id = utils.trim(message_id)
    fb_detail = utils.trim(fb_detail)

    if not table:
        goon, warn = False, "表名不能为空"
    if not message_id:
        goon, warn = False, "消息 id 不能为空"
    elif strict and fb_score < 0 and not fb_detail:
        goon, warn = False, "用户反馈内容不能为空"

    if not goon:
        logger.error(f"{error}{warn}")
        return False, warn

    sql = f"UPDATE `{table}` SET `fb_score` = '{fb_score}', `fb_detail` = '{fb_detail}' WHERE `message_id` = '{message_id}';"

    client = MySqLClient() if not client else client
    success = client.update(sql, None) == 1
    warn = "反馈失败，请重新提交" if not success else "提交成功，感谢您的反馈"

    return success, warn

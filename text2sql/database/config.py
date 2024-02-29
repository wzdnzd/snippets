# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-02-28

import pymysql

# 数据库服务器地址
DB_HOST = "127.0.0.1"

# 数据库服务器端口
DB_PORT = 3306

# 数据库用户名
DB_USERNAME = "root"

# 数据库密码
DB_PASSWORD = "MySQL"

# 数据库名称
DB_DATABASE = "text2sql"

# 数据库表名
DB_TABLENAME = "feedback"

# 数据库连接编码
DB_CHARSET = "utf8"

# mincached: 启动时开启的闲置连接数量（缺省值 0 开始时不创建连接）
DB_MIN_CACHED = 1

# maxcached: 连接池中允许的闲置的最多连接数量（缺省值 0 代表不闲置连接池大小）
DB_MAX_CACHED = 0

# maxshared: 共享连接数允许的最大数量（缺省值 0 代表所有连接都是专用的），如果达到了最大数量，被请求为共享的连接将会被共享使用
DB_MAX_SHARED = 10

# maxconnecyions: 创建连接池的最大数量（缺省值 0 代表不限制）
DB_MAX_CONNECYIONS = 300

# blocking: 设置在连接池达到最大数量时的行为（缺省值 0 或 False 代表返回一个错误）
DB_BLOCKING = True

# maxusage: 单个连接的最大允许复用次数（缺省值 0 或 False 代表不限制的复用），当达到最大数时连接会自动重新连接（关闭和重新打开）
DB_MAX_USAGE = 0

# setsession: 一个可选的SQL命令列表用于准备每个会话
DB_SET_SESSION = None

# creator : 使用连接数据库的模块
DB_CREATOR = pymysql

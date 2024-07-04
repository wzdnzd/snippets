# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-05-23

import multiprocessing
import random
import time

import pymysql
import requests
from lxml import etree

requests.DEFAULT_RETRIES = 20
MYSQL_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "MySQL",
    "database": "mydb",
    "table": "articles",
}

HTTPS_PROXY = "http://127.0.0.1:7890"


def crawl(num: int) -> list:
    url = f"https://www.thehindu.com/search/?q=china&start={num}"
    print(f"开始爬取{num}")
    headers = {
        "authority": "www.thehindu.com",
        "accept": "text/html",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.88 Safari/537.36",
    }
    try:
        response = requests.request("GET", url, headers=headers, proxies={"https": HTTPS_PROXY}).text
    except Exception as e:
        print(e)
        time.sleep(20)

    html = etree.HTML(response)
    node_list = html.xpath('//*[@id="scrolladvanced"]/div[2]/div[2]/section/div')

    articles = []
    for h in node_list[1:11]:
        # 文章的标题
        try:
            title = h.xpath("./div/div/div[1]/a/text()")[0].strip()
        except Exception as e:
            title = ""
        # 文章的类型
        try:
            type = h.xpath("./div/div/div[1]/span[1]/a/text()")[0].strip()
        except Exception as e:
            type = ""
        # 文章的摘要
        try:
            abs = h.xpath("./div/div/div[1]/span[2]/text()")[0].strip()
        except Exception as e:
            abs = ""
        # 文章的日期
        # 文章的日期节点
        t_node = h.xpath("./div/div/div[1]/span[3]/span[1]")
        for x in t_node:
            month = x.xpath("./span[1]/text()")[0]
            day = x.xpath("./span[2]/text()")[0]
            year = x.xpath("./span[3]/text()")[0]
            t_data = month + day + year
        # 获取文章的作者
        try:
            author = h.xpath("./div/div/div[1]/span[3]/span[3]/a/text()")[0]
        except Exception as e:
            author = ""
        # 文章的链接
        href = h.xpath("./div/div/div[1]/a/@href")[0].strip()
        # 文章具体的xpath
        try:
            response = requests.get(href, proxies={"https": HTTPS_PROXY}, headers=headers)
        except Exception as e:
            time.sleep(20)
            response = requests.get(href, proxies={"https": HTTPS_PROXY}, headers=headers)
        html = etree.HTML(response.text)
        k_id = href.split("/")[-1].strip(".ece").strip("article")
        content_xpath = html.xpath(f'//*[@id="content-body-{k_id}"]/p')
        content_list = []
        for i in content_xpath:
            try:
                content = i.xpath("./text()")[0]
            except Exception as e:
                content = ""
            try:
                xx_content = i.xpath("./a/text()")[0]
                # print(xx_content)
            except Exception as e:
                xx_content = ""
            content_1 = (content + xx_content).strip().replace("\n", "")
            content_list.append(content_1)
        content = "".join(content_list)
        articles.append((title, type, abs, t_data, author, href, content))

    return articles


def connect(connect_database: bool):
    host = MYSQL_CONFIG.get("host", "127.0.0.1")
    port = MYSQL_CONFIG.get("port", 3306)
    user = MYSQL_CONFIG.get("user", "root")
    password = MYSQL_CONFIG.get("password", "")
    database = MYSQL_CONFIG.get("database")

    if not connect_database:
        return pymysql.connect(host=host, port=port, user=user, password=password, charset="utf8mb4")
    else:
        if not database:
            raise ValueError("非法参数, 数据库名不能为空")
        else:
            return pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                charset="utf8mb4",
            )


def create_table():
    database = MYSQL_CONFIG.get("database")
    table = MYSQL_CONFIG.get("table")

    if not database or not table:
        raise ValueError("非法参数，数据库名或表名不能为空")

    conn = connect(connect_database=False)
    cursor = conn.cursor()
    sql = "CREATE DATABASE IF NOT EXISTS {}".format(database)
    cursor.execute(sql)
    cursor.execute("USE {}".format(database))
    cursor.execute("DROP TABLE IF EXISTS {}".format(table))
    sql = """CREATE TABLE `{}` (
            `id` INT AUTO_INCREMENT,
            `title` VARCHAR(1024),
            `type` VARCHAR(128),
            `abs` VARCHAR(300),
            `date` VARCHAR(100),
            `author` VARCHAR(256),
            `href` VARCHAR(512),
            `content` TEXT,
            PRIMARY KEY (`id`)
            )ENGINE=InnoDB DEFAULT CHARSET=utf8;
            """.format(
        table
    )

    cursor.execute(sql)
    conn.close()


def batch_insert(items: list, retry: int) -> bool:
    if retry <= 0:
        print("数据插入失败，已达最大重试次数")
        return False

    conn = connect(connect_database=True)
    cursor = conn.cursor()
    table = MYSQL_CONFIG.get("table")
    sql = "INSERT INTO {}(title, type, abs, date, author, href, content) VALUES(%s, %s, %s, %s, %s, %s, %s)".format(
        table
    )
    try:
        cursor.executemany(sql, items)
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        conn.rollback()
        conn.close()
        print(e)
        time.sleep(random.randint(1, 5))
        return batch_insert(items, retry - 1)


def main(start: int):
    items = crawl(num=start)
    if not items:
        print("***** [WARNING] 爬取{}页内容失败 *****".format(start))
        return

    success = batch_insert(items=items, retry=10)
    if not success:
        print("***** [WARNING] 插入第{}页数据失败 *****".format(start))


if __name__ == "__main__":
    pages = range(0, 60250, 10)

    create_table()

    cpu_count = multiprocessing.cpu_count()
    num = len(pages) if len(pages) <= cpu_count else cpu_count

    pool = multiprocessing.Pool(num)
    start = time.time()
    pool.map(main, pages)
    pool.close()
    pool.join()
    end = time.time()

    print("爬取完成，总共耗时{}s".format(end - start) / 1000)

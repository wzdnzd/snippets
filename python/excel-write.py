# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-03-28

import argparse
import os
import re

import xlrd
import xlwt
from xlutils.copy import copy

"""
需求：https://www.52pojie.cn/thread-1650015-1-1.html
"""


def convert(src: str, dest: str):
    if not os.path.exists(src) or not os.path.isfile(src):
        raise ValueError("文件{}不存在".format(src))

    if not dest.endswith(".xls"):
        raise ValueError("只支持保存为.xls格式的Excel文件")

    with open(src, "r", encoding="utf8") as f:
        items = []
        qas = []
        for line in f.readlines():
            content = ""
            if re.match("^([a-zA-Z]{1}\.|\d+\.)", line):
                index = line.find(".")
                content = line[index + 1 :].strip()
            else:
                content = qas.pop() + " " + line.replace("\n", "").strip()

            if re.match("^\d+\..*", line) and qas:
                items.append(qas)
                qas = []

            qas.append(content.replace("\n", ""))

            # 每100题写入一次，防止题目太多占用内存太大
            if len(items) == 100:
                write_excel(dest, items)
                items.clear()

        # 最后一题
        items.append(qas)

        # 不够100题，最后一次写入
        write_excel(dest, items)


def write_excel(path: str, items: list):
    if not os.path.exists(path) or not os.path.isfile(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        workbook = xlwt.Workbook()
        sheet = workbook.add_sheet("试题")
        for i in range(len(items)):
            for j in range(0, len(items[i])):
                sheet.write(i, j, items[i][j])
        workbook.save(path)
        return

    workbook = xlrd.open_workbook(path)
    sheets = workbook.sheet_names()
    worksheet = workbook.sheet_by_name(sheets[0])
    rows_old = worksheet.nrows
    new_workbook = copy(workbook)
    new_worksheet = new_workbook.get_sheet(0)
    for i in range(0, len(items)):
        for j in range(0, len(items[i])):
            new_worksheet.write(i + rows_old, j, items[i][j])
    new_workbook.save(path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-s",
        "--src",
        type=str,
        required=True,
        help="source file",
    )

    parser.add_argument(
        "-d",
        "--dest",
        type=str,
        required=True,
        help="directory for save result",
    )

    args = parser.parse_args()
    convert(args.src, args.dest)

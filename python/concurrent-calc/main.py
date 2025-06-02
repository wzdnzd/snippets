import json
import os
import random
import string
import time

import utils
import workflow
from logger import logger


def generate_random_str(m:int, n:int, candidates:str|list[str], sep:str="") -> str:
    if m <= 0 or n <= 0 or m > n:
        raise ValueError(f"m必须小于等于n")
    
    if not candidates or not isinstance(candidates, (str, list)):
        raise ValueError("候选词库不能为空且必须为字符串或字符串数组")
    
    k = m if m == n else random.randint(m, n)
    return sep.join(random.sample(candidates, k))


def load_dict(filename:str="dict.txt") -> list[str]:
    filename = utils.trim(filename)
    if not filename:
        raise ValueError(f"文件名不能为空")

    filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", filename))
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        raise ValueError(f"文件 {filepath} 不存在")
    
    with open(filepath, mode="r", encoding="utf8") as f:
        words = set()
        for line in f.readlines():
            line = utils.trim(line)
            if not line:
                continue
            
            words.add(line.split(" ")[0])

    return list(words)


LETTERS = string.ascii_lowercase + string.digits + "_"
VOCAB_CN = load_dict()


def generate_en_str(m:int, n:int) -> str:
    return generate_random_str(m=m, n=n, candidates=LETTERS)


def generate_cn_str(m:int, n:int, short:int, long:int) -> list[dict]:
    if m <= 0 or n <= 0 or m > n:
        raise ValueError(f"m必须小于等于n")

    if short <= 0 or long <= 0 or short > long:
        raise ValueError(f"short必须小于等于long")
    
    k = m if m == n else random.randint(m, n)
    tasks = [[short, long, VOCAB_CN] for _ in range(k)]
    return utils.multi_process_run(func=generate_random_str, tasks=tasks)


def generate_data(table_num:int, len_min:int, len_max:int, column_min:int, column_max:int, enum_min:int, enum_max:int) -> dict:
    if table_num <= 0:
        raise ValueError(f"'table_num'必须大于0")

    if len_min <= 0 or len_max <= 0 or len_min > len_max:
        raise ValueError(f"'len_min'必须小于等于'len_max'")

    if column_min <= 0 or column_max <= 0 or column_min > column_max:
        raise ValueError(f"'column_min'必须小于等于'column_max'")

    if enum_min <= 0 or enum_max <= 0 or column_min > enum_max:
        raise ValueError(f"'enum_min'必须小于等于'enum_max'")

    arrays = list()
    for _ in range(table_num):
        table_name = generate_en_str(len_min, len_max)

        column_infos = list()
        for _ in range(column_min if column_min == column_max else random.randint(column_min, column_max)):
            column_name = generate_en_str(len_min, len_max)

            data_type, enum_values = "", None
            if random.random() >= 0.8:
                # 随机生成int类型的列名信息
                data_type = "int"
                m = enum_min if enum_min == enum_max else random.randint(enum_min, enum_max)
                enum_values = [random.randint(0, 100000) for _ in range(m)]
            else:
                # 随机生成字符串类型的列名消息
                data_type = "str"
                enum_values = generate_cn_str(enum_min, enum_max, len_min, len_max)

            column_infos.append({"data_format": data_type, "column_name": column_name, "column_enum_value":enum_values})

        arrays.append({"table_name":table_name, "column_info":column_infos})

    return arrays

def load_data(filename:str) -> list[dict]:
    filename = utils.trim(filename)
    if not filename:
        raise ValueError(f"文件名不能为空")

    filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", filename))
    if os.path.exists(filepath) and os.path.isfile(filepath):
        with open(filepath, mode="r", encoding="utf8") as f:
            return json.load(f)
    else:
        raise ValueError(f"文件 {filepath} 不存在")


def save_data(filename:str, data:list[dict])->None:
    filename = utils.trim(filename)
    if not filename or not isinstance(filename, str):
        raise ValueError(f"文件路径不能为空")

    if not data or not isinstance(data, list):
        raise ValueError(f"数据不能为空")

    filepath = os.path.abspath(os.path.join(os.path.dirname(__file__), "data", filename))

    # 文件夹不存在则自动创建
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, mode="w+", encoding="utf8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    logger.info(f"数据已保存到 {filepath}")


if __name__ == "__main__":
    question = "数字能源装备部的效能指数是多少？"
    filename = "table_columns_info.json"

    table_column_info = None
    try:
        table_column_info = load_data(filename)
    except:
        logger.warning(f"文件 {filename} 不存在，将自动生成数据")
        table_column_info = generate_data(1, 3, 20, 2, 2, 10000, 10000)
        save_data(filename, table_column_info)

    costs = list()
    for i in range(11):
        start_time = time.time()
        result = workflow.retrieve_column_value_options_name(question=question, tables=table_column_info)
        
        if i != 0:
            costs.append(time.time() - start_time)

        save_data(f"result-{i}.json", result)

    logger.info(f"平均耗时: {sum(costs) / len(costs):.2f}s")

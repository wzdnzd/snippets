# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2022-04-19

num_dict = {
    0: "零",
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
}
unit_map = [
    ["", "十", "百", "千"],
    ["万", "十万", "百万", "千万"],
    ["亿", "十亿", "百亿", "千亿"],
    ["兆", "十兆", "百兆", "千兆"],
]
unit_step = ["万", "亿", "兆"]


def number_to_str(num: int) -> str:
    """一万以内的数转成大写"""
    res = []
    count = 0

    # 倒转
    content = reversed(str(num))
    for i in content:
        if i != "0":
            count_cos = count // 4
            count_col = count % 4
            res.append(unit_map[count_cos][count_col])
            res.append(num_dict[int(i)])
            count += 1
        else:
            count += 1
            if not res:
                res.append("零")
            elif res[-1] != "零":
                res.append("零")

    # 再次倒序，这次变为正序了
    res.reverse()
    # 去掉"一十零"这样整数的“零”
    if res[-1] == "零" and len(res) != 1:
        res.pop()

    s = "".join(res)
    if s.startswith("一十"):
        s = s[1:]

    return s

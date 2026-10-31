#!/usr/bin/env python3
"""
查找指定目录下所有有未提交修改或未推送提交的 git 仓库

用法示例:
    python check_dirty.py                        # 检查当前目录, 默认深度: 1
    python check_dirty.py /path/to/projects      # 检查指定目录
    python check_dirty.py /path/to/projects -d 3 # 向下递归 3 层
    python check_dirty.py -q                     # 只打印仓库路径
    python check_dirty.py --exclude node_modules --exclude .venv
"""

import argparse
import os
import subprocess
import sys


def run_git(path, *args, timeout=10):
    """执行 git 命令，失败返回 None。"""
    try:
        r = subprocess.run(["git", "-C", path, *args], capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def find_repos(root, max_depth, excludes):
    """递归查找 git 仓库根目录, 包含 .git 的目录

    depth: 0 表示 root 本身, 1 表示 root 的下一层，以此类推
    """
    repos = []
    root = os.path.abspath(root)
    root_depth = root.rstrip(os.sep).count(os.sep)

    for dirpath, dirnames, filenames in os.walk(root):
        depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth

        # 1) 先判断当前目录是否是仓库 —— 此时 dirnames 还是完整的
        if depth <= max_depth and (".git" in dirnames or ".git" in filenames):
            repos.append(dirpath)

        # 2) 再决定要不要继续向下遍历
        if depth >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = [d for d in dirnames if d != ".git" and d not in excludes]

    return repos


def check_repo(path, include_untracked=True, check_unpushed=True):
    """返回 (是否有问题, 明细字典)。"""
    details = {}

    status_args = ["status", "--porcelain"]
    if not include_untracked:
        status_args.append("--untracked-files=no")
    porcelain = (run_git(path, *status_args) or "").strip()
    if porcelain:
        details["uncommitted"] = porcelain

    if check_unpushed:
        unpushed = (run_git(path, "log", "--oneline", "@{u}..HEAD") or "").strip()
        if unpushed:
            details["unpushed"] = unpushed

    return bool(details), details


def main():
    parser = argparse.ArgumentParser(description="查找目录下所有有未提交修改或未推送提交的 git 仓库")
    parser.add_argument("-f", "--folder", dest="folder", default=".", help="要扫描的父目录, 默认当前目录")
    parser.add_argument("-d", "--depth", type=int, default=1, help="向下递归查找的层数, 0 表示只看 folder 本身，默认 1")
    parser.add_argument("--no-untracked", action="store_true", help="忽略未跟踪文件")
    parser.add_argument("--no-unpushed", action="store_true", help="不检查未推送的提交")
    parser.add_argument(
        "-e",
        "--exclude",
        action="append",
        default=[],
        metavar="NAME",
        help="按目录名排除, 可多次使用，如 -e node_modules -e .venv",
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="只输出有问题的仓库路径，不打印明细")
    args = parser.parse_args()

    root = os.path.abspath(args.folder)
    if not os.path.isdir(root):
        sys.exit(f"错误: 目录不存在: {root}")

    repos = find_repos(root, args.depth, set(args.exclude))
    dirty = []

    for repo in repos:
        has_issue, details = check_repo(
            repo,
            include_untracked=not args.no_untracked,
            check_unpushed=not args.no_unpushed,
        )
        if has_issue:
            dirty.append((repo, details))

    if args.quiet:
        for repo, _ in dirty:
            print(repo)
    else:
        for repo, details in dirty:
            branch = (run_git(repo, "rev-parse", "--abbrev-ref", "HEAD") or "").strip()
            print(f"▶ {repo}  (分支: {branch})")
            if "uncommitted" in details:
                print("  未提交的改动:")
                for line in details["uncommitted"].splitlines():
                    print(f"    {line}")
            if "unpushed" in details:
                print("  未推送的提交:")
                for line in details["unpushed"].splitlines():
                    print(f"    {line}")
            print()

        print("-" * 40)

    print(f"共检查 {len(repos)} 个 git 仓库，{len(dirty)} 个有未提交/未推送内容")

    # 有脏仓库时返回非 0 退出码，方便脚本判断
    return 1 if dirty else 0


if __name__ == "__main__":
    sys.exit(main())

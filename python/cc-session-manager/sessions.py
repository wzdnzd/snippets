# -*- coding: utf-8 -*-
"""扫描并管理 Claude Code 会话

默认读取用户主目录下的 .claude/projects，按项目列出 Session。标题优先用 JSONL 里的 customTitle；没有时再取第一条 parentUuid 明确为 null、且能解析出正文的记录
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_PARENT_NULL_RE = re.compile(r'"parentUuid"\s*:\s*null\b')
_LEADING_IDE_RE = re.compile(
    r"^(?:<(ide_[\w.-]*)(?:\s[^>]*)?>.*?</\1>\s*)+",
    re.DOTALL,
)
_IDE_OPEN_RE = re.compile(r"^</?ide_[\w.-]*")
_HOT_SECONDS = 90
_STATUS_SECONDS = 2.5


@dataclass
class Session:
    path: Path
    project_dir: Path
    project_name: str
    project_label: str
    title: str
    size: int
    mtime: float
    number: int = 0


@dataclass
class Project:
    name: str
    label: str
    directory: Path
    sessions: list[Session] = field(default_factory=list)
    number: int = 0

    @property
    def size(self) -> int:
        return sum(item.size for item in self.sessions)

    @property
    def latest(self) -> float:
        return max(item.mtime for item in self.sessions)


def configure_stdio() -> None:
    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    for stream in (sys.stdout, sys.stderr, sys.stdin):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def enable_windows_vt() -> bool:
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def windows_console_input() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)
        mode = ctypes.c_uint()
        return bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
    except Exception:
        return False


def default_claude_dir() -> Path:
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or str(Path.home())
    return Path(home) / ".claude"


def char_width(ch: str) -> int:
    if unicodedata.combining(ch):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1


def disp_width(text: str) -> int:
    return sum(char_width(ch) for ch in text)


def trunc(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if disp_width(text) <= width:
        return text
    if width <= 3:
        out: list[str] = []
        used = 0
        for ch in text:
            width_ch = char_width(ch)
            if used + width_ch > width:
                break
            out.append(ch)
            used += width_ch
        return "".join(out)
    limit = width - 3
    out = []
    used = 0
    for ch in text:
        width_ch = char_width(ch)
        if used + width_ch > limit:
            break
        out.append(ch)
        used += width_ch
    return "".join(out) + "..."


def pad_display(text: str, width: int) -> str:
    text = trunc(text, width)
    gap = width - disp_width(text)
    if gap > 0:
        text += " " * gap
    return text


def pack_segments(segments: list[str], width: int, *, indent: str = " ", gap: str = "  ") -> list[str]:
    """按显示宽度把若干片段排成尽量少的行，不从片段中间断开。若最后一行只剩很少几个字，就把上一行末尾的片段一并挪下来，避免孤行"""
    usable = width - disp_width(indent)
    if usable < 1:
        usable = max(1, width)
        indent = ""
    gap_width = disp_width(gap)

    def row_width(parts: list[str]) -> int:
        if not parts:
            return 0
        return sum(disp_width(part) for part in parts) + gap_width * (len(parts) - 1)

    rows: list[list[str]] = []
    current: list[str] = []
    for raw in segments:
        if not raw:
            continue
        seg = raw if disp_width(raw) <= usable else trunc(raw, usable)
        if current and row_width(current + [seg]) > usable:
            rows.append(current)
            current = [seg]
        else:
            current.append(seg)
    if current:
        rows.append(current)

    min_tail = min(18, max(8, usable // 4))
    while len(rows) >= 2 and row_width(rows[-1]) < min_tail and len(rows[-2]) >= 2:
        moved = rows[-2][-1]
        if row_width([moved, *rows[-1]]) > usable:
            break
        rows[-2].pop()
        rows[-1].insert(0, moved)
    return [indent + gap.join(parts) for parts in rows if parts]


_LIST_HINTS = (
    "↑↓移动",
    "空格选择",
    "a全选",
    "c清空",
    "d删会话",
    "p删项目",
    "/搜索",
    "r刷新",
    "?帮助",
    "q退出",
)
_CONFIRM_HINTS = (
    "Tab切换",
    "Enter执行",
    "y确认",
    "n取消",
    "Esc取消并返回",
)


def fmt_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    if size < 1024**3:
        return f"{size / 1024 / 1024:.1f} MB"
    return f"{size / 1024 ** 3:.2f} GB"


def fmt_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


def decode_project_name(name: str) -> str:
    """Claude 把路径里的非字母数字换成连字符，这里尽量还原成可读路径"""
    if len(name) >= 3 and name[0].isalpha() and name[1:3] == "--":
        rest = name[3:].replace("-", "\\")
        return f"{name[0].upper()}:\\{rest}"
    if "-" in name:
        return name.replace("-", "\\")
    return name


def normalize_match(text: str) -> str:
    return text.casefold().replace("/", "\\")


def project_matches(name: str, label: str, pattern: str) -> bool:
    needle = normalize_match(pattern)
    return needle in normalize_match(name) or needle in normalize_match(label)


def clean_title(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\r", " ").replace("\n", " ")).strip()


def usable_text(text: str) -> str | None:
    """丢掉整段被 ide_* 标签包住的上下文，保留用户真正输入的正文"""
    stripped = text.strip()
    if not stripped:
        return None
    match = _LEADING_IDE_RE.match(stripped)
    if match:
        stripped = stripped[match.end() :].strip()
        if not stripped:
            return None
    if _IDE_OPEN_RE.match(stripped):
        return None
    return stripped


def iter_texts(content: object) -> list[str]:
    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, str):
                texts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                value = item.get("text")
                if isinstance(value, str):
                    texts.append(value)
    elif isinstance(content, dict) and content.get("type") == "text":
        value = content.get("text")
        if isinstance(value, str):
            texts.append(value)
    return texts


def custom_title_from_record(record: dict) -> str | None:
    title = record.get("customTitle")
    if not isinstance(title, str):
        return None
    cleaned = clean_title(title)
    return cleaned or None


def title_from_record(record: dict) -> str | None:
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    for text in iter_texts(message.get("content")):
        usable = usable_text(text)
        if usable is None:
            continue
        cleaned = clean_title(usable)
        if cleaned:
            return cleaned
    return None


def extract_title(path: Path) -> str | None:
    """有 customTitle 就用最后一条；否则用第一条能解析出的正文"""
    custom: str | None = None
    content_title: str | None = None
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if '"customTitle"' in line:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    record = None
                if isinstance(record, dict):
                    found = custom_title_from_record(record)
                    if found:
                        custom = found
                        continue
            if content_title is not None or not _PARENT_NULL_RE.search(line):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if "parentUuid" not in record or record["parentUuid"] is not None:
                continue
            title = title_from_record(record)
            if title:
                content_title = title
    return custom or content_title


def resolve_projects_dir(root: Path) -> Path:
    direct = root / "projects"
    if direct.is_dir():
        return direct
    if root.name.lower() == "projects" and root.is_dir():
        return root
    return direct


def split_patterns(values: list[str]) -> list[str]:
    patterns: list[str] = []
    for value in values:
        for piece in value.split(","):
            piece = piece.strip()
            if piece:
                patterns.append(piece)
    return patterns


def scan(claude_dir: Path, include: list[str], exclude: list[str]) -> tuple[list[Project], list[str]]:
    projects_dir = resolve_projects_dir(claude_dir)
    if not projects_dir.is_dir():
        raise FileNotFoundError(f"未找到 projects 目录: {projects_dir}")

    include = split_patterns(include)
    exclude = split_patterns(exclude)
    projects: list[Project] = []
    errors: list[str] = []

    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        name = project_dir.name
        label = decode_project_name(name)
        if include and not any(project_matches(name, label, item) for item in include):
            continue
        if exclude and any(project_matches(name, label, item) for item in exclude):
            continue

        sessions: list[Session] = []
        try:
            entries = list(project_dir.iterdir())
        except OSError as exc:
            errors.append(f"{label}: 无法读取目录，错误信息：{exc}")
            continue
        for entry in entries:
            if not entry.is_file() or entry.suffix.lower() != ".jsonl":
                continue
            try:
                stat = entry.stat()
                title = extract_title(entry) or "无标题"
            except OSError as exc:
                errors.append(f"{entry.name}: 读取失败，错误信息: {exc}")
                title = "无法读取"
                try:
                    stat = entry.stat()
                except OSError:
                    continue
            sessions.append(
                Session(
                    path=entry,
                    project_dir=project_dir,
                    project_name=name,
                    project_label=label,
                    title=title,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
            )
        if not sessions:
            continue
        sessions.sort(key=lambda item: item.mtime, reverse=True)
        projects.append(Project(name=name, label=label, directory=project_dir, sessions=sessions))

    projects.sort(key=lambda item: item.latest, reverse=True)
    number = 1
    for index, project in enumerate(projects, start=1):
        project.number = index
        for session in project.sessions:
            session.number = number
            number += 1
    return projects, errors


def all_sessions(projects: list[Project]) -> list[Session]:
    return [session for project in projects for session in project.sessions]


def sidecar_dir(session: Session) -> Path | None:
    if not _UUID_RE.fullmatch(session.path.stem):
        return None
    side = session.path.parent / session.path.stem
    if side.is_dir() and not side.is_symlink():
        return side
    return None


def delete_session(projects_root: Path, session: Session) -> tuple[list[str], list[str]]:
    removed: list[str] = []
    problems: list[str] = []
    path = session.path.resolve()
    root = projects_root.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return [], [f"不在 projects 目录下，拒绝删除: {path}"]
    if len(relative.parts) != 2 or path.suffix.lower() != ".jsonl":
        return [], [f"路径异常，拒绝删除: {path}"]

    side = sidecar_dir(session)
    try:
        path.unlink()
    except OSError as exc:
        return [], [f"删除失败 {path.name}: {exc}"]
    removed.append(str(path))

    if side is not None:
        try:
            shutil.rmtree(side)
            removed.append(str(side))
        except OSError as exc:
            problems.append(f"JSONL 已删除，但附属目录删除失败 {side.name}: {exc}")
    return removed, problems


def delete_project(projects_root: Path, project: Project) -> tuple[bool, list[str]]:
    """删除整个项目目录，其中所有 JSONL 会先逐个删除"""
    problems: list[str] = []
    directory = project.directory.resolve()
    root = projects_root.resolve()
    try:
        relative = directory.relative_to(root)
    except ValueError:
        return False, [f"不在 projects 下，拒绝删除: {directory}"]
    if len(relative.parts) != 1 or relative.parts[0] in {".", ".."}:
        return False, [f"路径异常，拒绝删除: {directory}"]
    if project.directory.is_symlink() or directory.is_symlink():
        return False, [f"项目目录是符号链接，拒绝删除: {directory}"]

    for session in project.sessions:
        _removed, failed = delete_session(projects_root, session)
        problems.extend(failed)
    if directory.is_dir():
        for entry in list(directory.glob("*.jsonl")):
            if not entry.is_file():
                continue
            try:
                entry.unlink()
            except OSError as exc:
                problems.append(f"删除失败 {entry.name}: {exc}")
        try:
            shutil.rmtree(directory)
        except OSError as exc:
            problems.append(f"项目目录删除失败 {directory.name}: {exc}")
            return False, problems
    if directory.exists():
        return False, problems or [f"项目目录仍存在: {directory.name}"]
    return True, []


def parse_target(text: str, session_count: int, project_count: int) -> tuple[str, list[int]]:
    raw = text.strip()
    if re.fullmatch(r"(?i)p[\d\s,\-p]+", raw):
        body = re.sub(r"(?i)p", "", raw)
        return "project", parse_selection(body, project_count)
    return "session", parse_selection(raw, session_count)


def parse_selection(text: str, count: int) -> list[int]:
    raw = text.strip()
    if raw.casefold() == "all":
        return list(range(1, count + 1))
    numbers: list[int] = []
    seen: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            left, right = part.split("-", 1)
            start, end = int(left), int(right)
            if start > end:
                start, end = end, start
            chunk = range(start, end + 1)
        else:
            chunk = (int(part),)
        for number in chunk:
            if number < 1 or number > count:
                raise ValueError(f"编号超出范围: {number}")
            if number not in seen:
                seen.add(number)
                numbers.append(number)
    if not numbers:
        raise ValueError("没有有效编号")
    return numbers


def render_plain(projects: list[Project], claude_dir: Path, errors: list[str]) -> None:
    sessions = all_sessions(projects)
    fields = [
        f"目录：{claude_dir}",
        f"项目：{len(projects)}",
        f"会话：{len(sessions)}",
        f"体积：{fmt_size(sum(item.size for item in sessions))}",
    ]
    width = max(20, shutil.get_terminal_size((80, 24)).columns - 1)
    for line in pack_segments(fields, width, indent="", gap=" "):
        print(line)
    if not sessions:
        print("没有找到会话")
    if sys.stdout.isatty():
        enable_windows_vt()
    last_label = None
    for session in sessions:
        if session.project_label != last_label:
            project = next(item for item in projects if item.name == session.project_name)
            print()
            heading = f" 项目 {project.number}  {session.project_label}"
            if sys.stdout.isatty():
                heading = pad_display(heading, max(20, shutil.get_terminal_size((80, 24)).columns - 1))
                print(f"\033[1;37;44m{heading}\033[0m")
            else:
                print(heading)
            last_label = session.project_label
        title = trunc(session.title, 72)
        meta = f"{fmt_size(session.size)}  {fmt_time(session.mtime)}"
        print(f"{session.number:>3}. {title}")
        print(f"     {meta}  {session.path.name}")
    if errors:
        print()
        print("扫描提示：")
        for error in errors:
            print(f"  - {error}")


def run_plain(claude_dir: Path, include: list[str], exclude: list[str]) -> int:
    while True:
        try:
            projects, errors = scan(claude_dir, include, exclude)
        except FileNotFoundError as exc:
            print(exc)
            return 1
        render_plain(projects, claude_dir, errors)
        sessions = all_sessions(projects)
        if not sessions:
            return 0
        print()
        print("删除会话: 编号，如 1,3,5-7 或 all")
        print("删除整个项目: p 加项目编号，如 p1 或 p1,p2")
        print("直接回车或 q 退出")
        try:
            answer = input("> ").strip()
        except EOFError:
            print()
            return 0
        if answer == "" or answer.casefold() in {"q", "quit", "exit"}:
            return 0
        try:
            kind, numbers = parse_target(answer, len(sessions), len(projects))
        except ValueError as exc:
            print(f"无法识别: {exc}")
            print()
            continue
        projects_root = resolve_projects_dir(claude_dir)
        print()
        if kind == "project":
            by_number = {project.number: project for project in projects}
            chosen_projects = [by_number[number] for number in numbers]
            session_count = sum(len(project.sessions) for project in chosen_projects)
            total = sum(project.size for project in chosen_projects)
            print(
                f"即将删除 {len(chosen_projects)} 个项目目录，共 {session_count} 个会话的 JSONL，合计 {fmt_size(total)}"
            )
            print("项目目录会整目录删除，附属目录和 memory 也会一并去掉。此操作不可恢复")
            hot = [
                item
                for project in chosen_projects
                for item in project.sessions
                if time.time() - item.mtime < _HOT_SECONDS
            ]
            if hot:
                print(f"注意: {len(hot)} 个会话在 {_HOT_SECONDS} 秒内有写入，可能正在使用")
            for project in chosen_projects:
                print(f"  项目 {project.number}  {project.label}  包含 {len(project.sessions)} 个会话")
                print(f"       {project.directory}")
            try:
                confirm = input("确认删除? [y/N] ").strip().casefold()
            except EOFError:
                print()
                return 0
            if confirm not in {"y", "yes"}:
                print("已取消")
                print()
                continue
            ok = 0
            for project in chosen_projects:
                removed, problems = delete_project(projects_root, project)
                if removed:
                    ok += 1
                for problem in problems:
                    print(problem)
            print(f"已删除 {ok} 个项目")
            print()
            continue
        by_number = {session.number: session for session in sessions}
        chosen = [by_number[number] for number in numbers]
        print(f"即将删除 {len(chosen)} 个会话的 JSONL 文件，合计 {fmt_size(sum(item.size for item in chosen))}")
        print("同名附属目录如 tool-results 等若存在会一并删除，项目目录和 memory 会保留")
        hot = [item for item in chosen if time.time() - item.mtime < _HOT_SECONDS]
        if hot:
            print(f"注意: {len(hot)} 个会话在 {_HOT_SECONDS} 秒内有写入，可能正在使用")
        for session in chosen:
            print(f"  {session.number:>3}. {trunc(session.title, 60)}")
            print(f"       {session.path}")
        try:
            confirm = input("确认删除? [y/N] ").strip().casefold()
        except EOFError:
            print()
            return 0
        if confirm not in {"y", "yes"}:
            print("已取消")
            print()
            continue
        projects_root = resolve_projects_dir(claude_dir)
        ok = 0
        for session in chosen:
            removed, problems = delete_session(projects_root, session)
            if removed:
                ok += 1
            for problem in problems:
                print(problem)
        print(f"已删除 {ok} 个会话")
        print()


class App:
    def __init__(self, claude_dir: Path, include: list[str], exclude: list[str]) -> None:
        self.claude_dir = claude_dir
        self.include = include
        self.exclude = exclude
        self.projects: list[Project] = []
        self.errors: list[str] = []
        self.selected: set[str] = set()
        self.cursor = 0
        self.scroll = 0
        self.query = ""
        self.query_backup = ""
        self.mode = "list"
        self.status = ""
        self.status_until = 0.0
        self.pending: list[Session] = []
        self.pending_projects: list[Project] = []
        self.confirm_kind = "session"
        self.confirm_focus = 0
        self.deleted = 0
        self.deleted_projects = 0
        self.load_error = ""

    def set_status(self, text: str, seconds: float = _STATUS_SECONDS) -> None:
        self.status = text
        self.status_until = time.monotonic() + seconds if text else 0.0

    def clear_status(self) -> None:
        self.status = ""
        self.status_until = 0.0

    def expire_status(self) -> None:
        if self.status and self.status_until and time.monotonic() >= self.status_until:
            self.clear_status()

    def status_timeout(self) -> float | None:
        if not self.status or not self.status_until:
            return None
        return max(0.0, self.status_until - time.monotonic())

    def reload(self) -> None:
        current = self.current_identity()
        try:
            self.projects, self.errors = scan(self.claude_dir, self.include, self.exclude)
            self.load_error = ""
        except FileNotFoundError as exc:
            self.projects, self.errors = [], []
            self.load_error = str(exc)
        alive = {str(session.path.resolve()) for session in all_sessions(self.projects)}
        self.selected &= alive
        self.restore_cursor(current)

    def rows(self) -> list[tuple[str, Project, Session | None]]:
        query = self.query.casefold().strip()
        rows: list[tuple[str, Project, Session | None]] = []
        for project in self.projects:
            visible = []
            for session in project.sessions:
                if not query:
                    visible.append(session)
                    continue
                haystack = f"{session.title}\n{session.project_label}\n{session.path.name}".casefold()
                if query in haystack:
                    visible.append(session)
            if not visible:
                continue
            rows.append(("proj", project, None))
            for session in visible:
                rows.append(("sess", project, session))
        return rows

    def current_identity(self) -> tuple[str, str] | None:
        rows = self.rows()
        if not rows or self.cursor >= len(rows):
            return None
        kind, project, session = rows[self.cursor]
        if session is not None:
            return ("sess", str(session.path))
        return ("proj", project.name)

    def restore_cursor(self, identity: tuple[str, str] | None) -> None:
        rows = self.rows()
        if identity is not None:
            for index, (kind, project, session) in enumerate(rows):
                if identity[0] == "sess" and session is not None and str(session.path) == identity[1]:
                    self.cursor = index
                    return
                if identity[0] == "proj" and session is None and project.name == identity[1]:
                    self.cursor = index
                    return
        self.cursor = min(self.cursor, max(0, len(rows) - 1))

    def visible_sessions(self) -> list[Session]:
        return [session for kind, _project, session in self.rows() if session is not None]

    def toggle_current(self) -> None:
        rows = self.rows()
        if not rows:
            return
        kind, project, session = rows[self.cursor]
        if session is not None:
            key = str(session.path.resolve())
            if key in self.selected:
                self.selected.remove(key)
            else:
                self.selected.add(key)
            return
        visible_paths = {item.path for item in self.visible_sessions()}
        visible = [item for item in project.sessions if item.path in visible_paths]
        keys = [str(item.path.resolve()) for item in visible]
        if keys and all(key in self.selected for key in keys):
            for key in keys:
                self.selected.discard(key)
            self.set_status(f"已取消 {project.label} 的勾选")
        else:
            self.selected.update(keys)
            self.set_status(f"已勾选 {project.label} 的 {len(keys)} 个会话")

    def select_all_visible(self) -> None:
        visible = self.visible_sessions()
        keys = [str(item.path.resolve()) for item in visible]
        if keys and all(key in self.selected for key in keys):
            for key in keys:
                self.selected.discard(key)
            self.set_status("已取消当前列表的勾选")
        else:
            self.selected.update(keys)
            self.set_status(f"已勾选 {len(keys)} 个会话")

    def clear_selection(self) -> None:
        self.selected.clear()
        self.set_status("已清空勾选")

    def chosen_sessions(self) -> list[Session]:
        rows = self.rows()
        chosen = [session for session in all_sessions(self.projects) if str(session.path.resolve()) in self.selected]
        if chosen:
            return chosen
        if not rows:
            return []
        _kind, _project, session = rows[self.cursor]
        return [session] if session is not None else []

    def move(self, delta: int) -> None:
        rows = self.rows()
        if not rows:
            self.cursor = 0
            return
        self.cursor = max(0, min(len(rows) - 1, self.cursor + delta))

    def term_size(self) -> tuple[int, int]:
        size = shutil.get_terminal_size((80, 24))
        return max(40, size.columns - 1), max(12, size.lines)

    def paint(self, text: str, width: int, current: bool = False, color: str | None = None) -> str:
        plain = pad_display(text, width)
        if current:
            return f"\033[7m{plain}\033[0m"
        if color:
            return f"\033[{color}m{plain}\033[0m"
        return plain

    def paint_segments(self, segments: list[tuple[str, str | None]], width: int) -> str:
        """同一行里给不同片段上色。宽度按可见字符计算，不把 ANSI 算进去"""
        used = 0
        parts: list[str] = []
        for text, color in segments:
            if used >= width:
                break
            room = width - used
            if disp_width(text) > room:
                text = trunc(text, room)
            if not text:
                continue
            if color:
                parts.append(f"\033[{color}m{text}\033[0m")
            else:
                parts.append(text)
            used += disp_width(text)
        if used < width:
            parts.append(" " * (width - used))
        return "".join(parts)

    def confirm_actions(self, width: int) -> str:
        delete_on = self.confirm_focus == 0
        segments: list[tuple[str, str | None]] = [
            (" ", None),
            (" 确认删除 ", "1;97;41" if delete_on else "31"),
            ("  ", None),
            (" 取消 ", "1;30;47" if not delete_on else "37"),
        ]
        return self.paint_segments(segments, width)

    def render(self) -> list[str]:
        width, height = self.term_size()
        if self.mode == "help":
            body = self.render_help(width)
        elif self.mode == "confirm":
            footer = [self.paint(line, width, color="2") for line in pack_segments(_CONFIRM_HINTS, width)]
            content = self.render_confirm(width)
            room = max(1, height - len(footer))
            content = content[:room]
            return content + [self.paint("", width)] * (room - len(content)) + footer
        else:
            body = self.render_list(width, height)
        body = body[:height]
        while len(body) < height:
            body.append(self.paint("", width))
        return body

    def render_list(self, width: int, height: int) -> list[str]:
        sessions = all_sessions(self.projects)
        total_size = sum(item.size for item in sessions)
        include = ", ".join(split_patterns(self.include)) or "—"
        exclude = ", ".join(split_patterns(self.exclude)) or "—"
        summary = [
            f"目录：{self.claude_dir}",
            f"项目：{len(self.projects)}",
            f"会话：{len(sessions)}",
            f"已选：{len(self.selected)}",
            f"体积：{fmt_size(total_size)}",
        ]
        filters = [f"包含：{include}", f"排除：{exclude}"]
        if self.query and self.mode != "search":
            filters.append(f"搜索：{self.query}")
        header = [self.paint(" Claude Code 会话管理", width, color="1;36")]
        stat_gap = "   "
        header.extend(self.paint(line, width, color="38;5;245") for line in pack_segments(summary, width, gap=stat_gap))
        header.extend(self.paint(line, width, color="38;5;245") for line in pack_segments(filters, width, gap=stat_gap))
        if self.load_error:
            header.append(self.paint(f" {self.load_error}", width, color="31"))
        if self.errors:
            header.append(self.paint(f" 扫描提示：{len(self.errors)} 条，按 ? 查看帮助", width, color="33"))
        header.append(self.paint("", width))

        if self.mode == "search":
            footer = [self.paint(f" 搜索：{self.query}", width, color="1;33")]
            footer.extend(
                self.paint(line, width, color="2")
                for line in pack_segments(("Enter 结束", "Esc 取消", "退格删除"), width)
            )
        else:
            footer = []
            if self.status:
                footer.append(self.paint(f" {self.status}", width, color="33"))
            footer.extend(self.paint(line, width, color="2") for line in pack_segments(_LIST_HINTS, width))

        if len(header) + len(footer) > height - 1:
            footer = footer[: max(1, (height - 1) // 3)]
            header = header[: max(1, height - 1 - len(footer))]
        rows = self.rows()
        slots: list[tuple[str, int | None]] = []
        seen_project = False
        for index, (kind, _project, _session) in enumerate(rows):
            if kind == "proj":
                if seen_project:
                    slots.append(("gap", None))
                seen_project = True
            slots.append(("row", index))

        room = max(1, height - len(header) - len(footer))
        cursor_slot = 0
        for slot_index, (slot_kind, row_index) in enumerate(slots):
            if slot_kind == "row" and row_index == self.cursor:
                cursor_slot = slot_index
                break
        if cursor_slot < self.scroll:
            self.scroll = cursor_slot
        elif cursor_slot >= self.scroll + room:
            self.scroll = cursor_slot - room + 1
        if (
            room >= 2
            and cursor_slot > 0
            and slots
            and slots[cursor_slot - 1][0] == "gap"
            and cursor_slot - 1 < self.scroll
        ):
            self.scroll = cursor_slot - 1
        max_scroll = max(0, len(slots) - room)
        self.scroll = max(0, min(self.scroll, max_scroll))

        body: list[str] = []
        if not rows:
            body.append(self.paint(" 没有可显示的会话", width, color="2"))
        else:
            for slot_kind, row_index in slots[self.scroll : self.scroll + room]:
                if slot_kind == "gap" or row_index is None:
                    body.append(self.paint("", width))
                    continue
                kind, project, session = rows[row_index]
                current = row_index == self.cursor
                if kind == "proj":
                    shown = sum(
                        1
                        for item in project.sessions
                        if any(item is other for _k, _p, other in rows if other is not None)
                    )
                    text = f" 项目 {project.number}  {project.label}    {shown} 个    {fmt_size(project.size)}"
                    color = "1;30;43" if current else "1;37;44"
                    body.append(self.paint(text, width, color=color))
                elif session is not None:
                    mark = "[x]" if str(session.path.resolve()) in self.selected else "[ ]"
                    prefix = f" {mark} {session.number:>3}. "
                    meta = f"{fmt_size(session.size)}  {fmt_time(session.mtime)}  {session.path.stem[:8]}"
                    room_title = width - disp_width(prefix) - disp_width(meta) - 2
                    if room_title < 4:
                        text = prefix + trunc(session.title, max(1, width - disp_width(prefix)))
                    else:
                        title = trunc(session.title, room_title)
                        gap = width - disp_width(prefix) - disp_width(title) - disp_width(meta)
                        text = prefix + title + (" " * max(gap, 1)) + meta
                    body.append(self.paint(text, width, current=current))
        while len(body) < room:
            body.append(self.paint("", width))
        return header + body + footer

    def render_confirm(self, width: int) -> list[str]:
        if self.confirm_kind == "project":
            return self.render_confirm_projects(width)
        chosen = self.pending
        size = fmt_size(sum(item.size for item in chosen))
        summary = f" 将删除 {len(chosen)} 个会话共 {size}。附属目录一并删除，项目和 memory 保留，不可恢复"
        lines = [
            self.paint(" 确认删除会话", width, color="1;31"),
            self.paint("", width),
            self.paint(summary, width),
        ]
        hot = [item for item in chosen if time.time() - item.mtime < _HOT_SECONDS]
        if hot:
            lines.append(
                self.paint(f" 注意: {len(hot)} 个会话在 {_HOT_SECONDS} 秒内有写入，可能正在使用", width, color="33")
            )
        lines.append(self.paint("", width))
        room = 12
        for session in chosen[:room]:
            side = " +目录" if sidecar_dir(session) else ""
            prefix = f" {session.number}. "
            title_width = max(1, width - disp_width(prefix) - disp_width(side))
            lines.append(self.paint(prefix + trunc(session.title, title_width) + side, width))
            indent = " " * disp_width(prefix)
            lines.append(self.paint(indent + trunc(str(session.path), max(1, width - len(indent))), width, color="2"))
        if len(chosen) > room:
            lines.append(self.paint(f" ... 另有 {len(chosen) - room} 个", width, color="2"))
        lines.append(self.paint("", width))
        lines.append(self.confirm_actions(width))
        return lines

    def render_confirm_projects(self, width: int) -> list[str]:
        chosen = self.pending_projects
        session_count = sum(len(project.sessions) for project in chosen)
        total = sum(project.size for project in chosen)
        summary = (
            f" 将删除 {len(chosen)} 个项目共 {session_count} 个会话，{fmt_size(total)}。"
            "目录、JSONL、附属文件和 memory 全部删除，不可恢复"
        )
        lines = [
            self.paint(" 确认删除整个项目", width, color="1;31"),
            self.paint("", width),
            self.paint(summary, width),
        ]
        hot = [item for project in chosen for item in project.sessions if time.time() - item.mtime < _HOT_SECONDS]
        if hot:
            lines.append(
                self.paint(f" 注意: {len(hot)} 个会话在 {_HOT_SECONDS} 秒内有写入，可能正在使用", width, color="33")
            )
        lines.append(self.paint("", width))
        for project in chosen[:8]:
            prefix = f" {project.number}. "
            suffix = f"  {len(project.sessions)} 个会话"
            label_width = max(1, width - disp_width(prefix) - disp_width(suffix))
            lines.append(self.paint(prefix + trunc(project.label, label_width) + suffix, width))
            indent = " " * disp_width(prefix)
            lines.append(
                self.paint(indent + trunc(str(project.directory), max(1, width - len(indent))), width, color="2")
            )
        if len(chosen) > 8:
            lines.append(self.paint(f" ... 另有 {len(chosen) - 8} 个项目", width, color="2"))
        lines.append(self.paint("", width))
        lines.append(self.confirm_actions(width))
        return lines

    def render_help(self, width: int) -> list[str]:
        include = ", ".join(split_patterns(self.include)) or "无"
        exclude = ", ".join(split_patterns(self.exclude)) or "无"
        rows = [
            " 操作说明",
            "",
            "  ↑ / ↓ 或 j / k     移动",
            "  PgUp / PgDn        翻页",
            "  空格               勾选会话；停在项目行上则勾选该项目全部",
            "  a                  勾选或取消当前列表",
            "  c                  清空勾选",
            "  d                  删除已勾选会话；没有勾选时删除光标所在会话",
            "  p                  删除光标所在的整个项目目录及全部 JSONL 文件",
            "  /                  按标题、路径、文件名过滤",
            "  r                  重新扫描",
            "  q / Esc            退出，确认界面中 Esc 为取消",
            "  确认页             Tab / ←→ 切换按钮，Enter 执行；y / n / Esc 仍可用",
            "",
            " 标题优先用 JSONL 里的 customTitle；没有时，再从 parentUuid 为 null 的正文提取并跳过被 <ide_opened_file>、<ide_selection> 等标签包裹的文本",
            "",
            f" 包含：{include}",
            f" 排除：{exclude}",
            "",
            " 按任意键返回",
        ]
        if self.errors:
            rows.extend(["", " 扫描提示："])
            rows.extend(f"  - {error}" for error in self.errors[:8])
        return [
            self.paint(trunc(row, width), width, color="1;36" if index == 0 else None) for index, row in enumerate(rows)
        ]

    def draw(self) -> None:
        lines = self.render()
        sys.stdout.write("\033[H" + "\033[K\n".join(lines) + "\033[K\033[J")
        sys.stdout.flush()

    def begin_delete(self) -> None:
        chosen = self.chosen_sessions()
        if not chosen:
            self.set_status("没有可删除的会话")
            return
        self.confirm_kind = "session"
        self.pending = chosen
        self.pending_projects = []
        self.confirm_focus = 0
        self.mode = "confirm"
        self.clear_status()

    def begin_delete_project(self) -> None:
        rows = self.rows()
        if not rows or self.cursor >= len(rows):
            self.set_status("没有可删除的项目")
            return
        project = rows[self.cursor][1]
        self.confirm_kind = "project"
        self.pending_projects = [project]
        self.pending = []
        self.confirm_focus = 0
        self.mode = "confirm"
        self.clear_status()

    def perform_delete(self) -> None:
        projects_root = resolve_projects_dir(self.claude_dir)
        problems: list[str] = []
        if self.confirm_kind == "project":
            ok = 0
            gone_sessions = 0
            for project in self.pending_projects:
                session_paths = [session.path for session in project.sessions]
                removed, failed = delete_project(projects_root, project)
                problems.extend(failed)
                if removed:
                    ok += 1
                    gone_sessions += len(session_paths)
                else:
                    gone_sessions += sum(1 for path in session_paths if not path.exists())
            self.deleted += gone_sessions
            self.deleted_projects += ok
            self.pending_projects = []
            self.mode = "list"
            self.reload()
            if problems:
                self.set_status(f"已删除 {ok} 个项目，另有 {len(problems)} 个问题: {problems[0]}")
            else:
                self.set_status(f"已删除 {ok} 个项目")
            return
        ok = 0
        for session in self.pending:
            removed, failed = delete_session(projects_root, session)
            if removed:
                ok += 1
            problems.extend(failed)
        self.deleted += ok
        self.pending = []
        self.mode = "list"
        self.reload()
        if problems:
            self.set_status(f"已删除 {ok} 个，另有 {len(problems)} 个问题: {problems[0]}")
        else:
            self.set_status(f"已删除 {ok} 个会话")

    def handle_list(self, key: str) -> bool:
        rows = self.rows()
        page = max(1, self.term_size()[1] - 8)
        if key in {"q", "Q"}:
            return False
        if key == "esc":
            if self.query:
                self.query = ""
                self.restore_cursor(None)
                self.set_status("已清除搜索")
                return True
            return False
        if key in {"up", "k"}:
            self.move(-1)
        elif key in {"down", "j"}:
            self.move(1)
        elif key == "pgup":
            self.move(-page)
        elif key == "pgdn":
            self.move(page)
        elif key == "home":
            self.cursor = 0
        elif key == "end":
            self.cursor = max(0, len(rows) - 1)
        elif key in {"space", " "}:
            self.toggle_current()
        elif key in {"a", "A"}:
            self.select_all_visible()
        elif key in {"c", "C"}:
            self.clear_selection()
        elif key in {"d", "D", "del"}:
            self.begin_delete()
        elif key in {"p", "P"}:
            self.begin_delete_project()
        elif key in {"r", "R"}:
            self.reload()
            self.set_status("已重新扫描")
        elif key == "/":
            self.query_backup = self.query
            self.mode = "search"
            self.clear_status()
        elif key == "?":
            self.mode = "help"
        elif key:
            self.clear_status()
        return True

    def handle_search(self, key: str) -> None:
        if key == "enter":
            self.mode = "list"
            self.set_status(f"搜索: {self.query}" if self.query else "已清除搜索")
            return
        if key == "esc":
            self.query = self.query_backup
            self.mode = "list"
            self.restore_cursor(None)
            self.set_status("已取消搜索")
            return
        if key == "backspace":
            self.query = self.query[:-1]
        elif key and len(key) == 1 and key.isprintable() and key not in {"\x00", "\xe0"}:
            self.query += key
        else:
            return
        self.cursor = 0
        self.scroll = 0

    def cancel_delete(self) -> None:
        self.mode = "list"
        self.pending = []
        self.pending_projects = []
        self.confirm_focus = 0
        self.set_status("已取消删除")

    def handle_confirm(self, key: str) -> None:
        if key in {"tab", "right"}:
            self.confirm_focus = (self.confirm_focus + 1) % 2
            return
        if key in {"btab", "left"}:
            self.confirm_focus = (self.confirm_focus - 1) % 2
            return
        if key == "enter":
            if self.confirm_focus == 0:
                self.perform_delete()
            else:
                self.cancel_delete()
            return
        if key in {"y", "Y"}:
            self.perform_delete()
        elif key in {"n", "N", "esc", "q", "Q"}:
            self.cancel_delete()

    def handle_help(self, key: str) -> None:
        if key:
            self.mode = "list"

    def handle(self, key: str) -> bool:
        if self.mode == "search":
            self.handle_search(key)
            return True
        if self.mode == "confirm":
            self.handle_confirm(key)
            return True
        if self.mode == "help":
            self.handle_help(key)
            return True
        return self.handle_list(key)


def read_key_windows(timeout: float | None = None) -> str | None:
    import msvcrt

    deadline = None if timeout is None else time.monotonic() + timeout
    while not msvcrt.kbhit():
        if deadline is not None and time.monotonic() >= deadline:
            return None
        pause = 0.05
        if deadline is not None:
            pause = min(pause, max(0.0, deadline - time.monotonic()))
        if pause:
            time.sleep(pause)
    ch = msvcrt.getwch()
    if ch in {"\x00", "\xe0"}:
        ch2 = msvcrt.getwch()
        return {
            "H": "up",
            "P": "down",
            "K": "left",
            "M": "right",
            "I": "pgup",
            "Q": "pgdn",
            "G": "home",
            "O": "end",
            "S": "del",
            "\x0f": "btab",
        }.get(ch2, "")
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch in {"\r", "\n"}:
        return "enter"
    if ch == "\x1b":
        return "esc"
    if ch == "\t":
        return "tab"
    if ch in {"\x08", "\x7f"}:
        return "backspace"
    return ch


def read_utf8_char(fd: int) -> str:
    data = os.read(fd, 1)
    if not data:
        return ""
    first = data[0]
    if first < 0x80:
        need = 0
    elif first < 0xE0:
        need = 1
    elif first < 0xF0:
        need = 2
    else:
        need = 3
    while len(data) < need + 1:
        more = os.read(fd, need + 1 - len(data))
        if not more:
            break
        data += more
    return data.decode("utf-8", errors="replace")


def read_key_unix(timeout: float | None = None) -> str | None:
    import select

    fd = sys.stdin.fileno()
    readable, _, _ = select.select([fd], [], [], timeout)
    if not readable:
        return None
    ch = read_utf8_char(fd)
    if ch == "\x03":
        raise KeyboardInterrupt
    if ch == "\x1b":
        readable, _, _ = select.select([fd], [], [], 0.05)
        if not readable:
            return "esc"
        nxt = read_utf8_char(fd)
        if nxt != "[":
            return "esc"
        seq = ""
        while True:
            part = read_utf8_char(fd)
            if not part:
                break
            seq += part
            if part.isalpha() or part == "~":
                break
        return {
            "A": "up",
            "B": "down",
            "C": "right",
            "D": "left",
            "H": "home",
            "F": "end",
            "Z": "btab",
            "5~": "pgup",
            "6~": "pgdn",
            "3~": "del",
        }.get(seq, "")
    if ch in {"\r", "\n"}:
        return "enter"
    if ch == "\t":
        return "tab"
    if ch in {"\x7f", "\x08"}:
        return "backspace"
    return ch


class UnixCbreak:
    def __init__(self) -> None:
        import termios

        self.termios = termios
        self.fd = sys.stdin.fileno()
        self.old = termios.tcgetattr(self.fd)

    def __enter__(self) -> "UnixCbreak":
        import tty

        tty.setcbreak(self.fd)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.termios.tcsetattr(self.fd, self.termios.TCSADRAIN, self.old)


def run_tui(claude_dir: Path, include: list[str], exclude: list[str]) -> int:
    app = App(claude_dir, include, exclude)
    app.reload()
    if app.load_error:
        print(app.load_error)
        return 1

    interrupted = False
    sys.stdout.write("\033[?1049h\033[?25l")
    sys.stdout.flush()
    try:
        if os.name == "nt":
            while True:
                app.expire_status()
                app.draw()
                key = read_key_windows(app.status_timeout())
                if key is None:
                    continue
                if not app.handle(key):
                    break
        else:
            with UnixCbreak():
                while True:
                    app.expire_status()
                    app.draw()
                    key = read_key_unix(app.status_timeout())
                    if key is None:
                        continue
                    if not app.handle(key):
                        break
    except KeyboardInterrupt:
        interrupted = True
    finally:
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()
    if app.deleted_projects or app.deleted:
        parts: list[str] = []
        if app.deleted_projects:
            parts.append(f"{app.deleted_projects} 个项目")
        if app.deleted:
            parts.append(f"{app.deleted} 个会话")
        print("已删除 " + "、".join(parts))
    return 130 if interrupted else 0


def can_use_tui() -> bool:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        return windows_console_input() and enable_windows_vt()
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sessions",
        description="扫描并管理 Claude Code 的 Session。按项目列出，可删除会话或整个项目",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  sessions.bat
  sessions.bat --include abc
  sessions.bat --exclude abc,xyz
  sessions.bat -d D:\\data\\.claude --include foo
  sessions.bat --plain

项目过滤是不区分大小写的子串匹配，同时比较目录名和解码后的路径。--include 可重复，多个条件为“或”；--exclude 同样可重复。一个参数里用逗号分隔也相当于多个条件

TUI:
  上/下        移动
  空格         勾选；在项目行上勾选该项目全部会话
  a            全选或取消当前列表
  c            清空勾选
  d            删除已勾选会话，未勾选时删除当前会话
  p            删除光标所在的整个项目目录
  /            按标题过滤
  r            重新扫描
  q            退出
""".strip(),
    )
    parser.add_argument("-d", "--directory", help="Claude 配置目录，默认用户主目录下的 .claude")
    parser.add_argument(
        "-i", "--include", action="append", default=[], metavar="TEXT", help="只保留项目名包含 TEXT 的项目，可重复"
    )
    parser.add_argument(
        "-e", "--exclude", action="append", default=[], metavar="TEXT", help="排除项目名包含 TEXT 的项目，可重复"
    )
    parser.add_argument("--plain", action="store_true", help="使用纯文本菜单，不进入 TUI")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.directory:
        claude_dir = Path(os.path.expandvars(os.path.expanduser(args.directory)))
    else:
        claude_dir = default_claude_dir()
    claude_dir = Path(os.path.abspath(os.fspath(claude_dir)))

    if args.plain or not can_use_tui():
        if not args.plain and sys.stdout.isatty():
            print("当前终端不支持全屏 TUI，改用文本菜单")
        return run_plain(claude_dir, args.include, args.exclude)
    return run_tui(claude_dir, args.include, args.exclude)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print()
        raise SystemExit(130)

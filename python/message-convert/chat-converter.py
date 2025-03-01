import argparse
import json
import os
import random
import shutil
import string
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional
import uuid
from tzlocal import get_localzone

import psycopg2

DATABASE_URL = ""


def trim(text: str) -> str:
    """清理文本，去除空白字符"""
    if not text or type(text) != str:
        return ""
    return text.strip()


def random_chars(length: int, punctuation: bool = False) -> str:
    """生成指定长度的随机字符串"""
    length = max(length, 1)
    if punctuation:
        chars = "".join(random.sample(string.ascii_letters + string.digits + string.punctuation, length))
    else:
        chars = "".join(random.sample(string.ascii_letters + string.digits, length))
    return chars


def get_session_id() -> str:
    """生成会话ID，长度为21，由字母、数字和下划线组成"""
    chars = string.ascii_letters + string.digits + "_"
    return "".join(random.sample(chars, 21))


def build_qa_pairs(messages: List[Tuple]) -> List[Dict]:
    """构建有序的问答对，基于parent_id关系，处理一个问题可能有多个回答的情况"""
    # 构建消息ID到消息的映射
    msg_map = {}
    # 构建问题ID到回答列表的映射
    answers_map = {}
    # 按时间顺序存储所有用户问题
    questions = []

    local_tz = get_localzone()

    # 第一遍：构建基本映射
    for msg in messages:
        msg_id, role, content, model, provider, msg_created_at, parent_id = msg

        # 转换时间格式
        date_str = msg_created_at.astimezone(local_tz).strftime("%Y/%m/%d %H:%M:%S")

        message = {
            "id": get_session_id(),
            "role": role,
            "content": content,
            "date": date_str,
            "created_at": msg_created_at,  # 用于排序
        }

        if role == "assistant" and model:
            message["model"] = model
            message["provider"] = provider

        msg_map[msg_id] = message

        # 如果是用户问题
        if role == "user":
            questions.append((msg_id, message))
            answers_map[msg_id] = []
        # 如果是助手回答
        elif role == "assistant" and parent_id:
            if parent_id in answers_map:
                answers_map[parent_id].append(message)

    # 构建最终的有序消息列表
    ordered_messages = []

    # 按时间顺序处理每个问题
    questions.sort(key=lambda x: x[1]["created_at"])

    for question_id, question in questions:
        # 添加问题
        ordered_messages.append(question)

        # 获取该问题的所有回答并按时间排序
        answers = answers_map.get(question_id, [])
        answers.sort(key=lambda x: x["created_at"])

        # 添加所有回答
        ordered_messages.extend(answers)

    # 清理临时字段
    for msg in ordered_messages:
        msg.pop("created_at", None)

    return ordered_messages


class ChatFormat:
    """聊天格式枚举"""

    LOBECHAT = "lobechat"
    NEXTCHAT = "nextchat"
    CHERRYSTUDIO = "cherrystudio"


def parse_cherry_studio_data(filepath: str) -> List[Dict]:
    """解析Cherry Studio格式的数据"""
    with open(filepath, "r", encoding="utf8") as f:
        data = json.loads(f.read())
        if not isinstance(data, dict):
            return []

        # 获取topics数据
        indexed_db = data.get("indexedDB", {})
        topics = indexed_db.get("topics", [])
        if not isinstance(topics, list):
            topics = []

        local_stotage = data.get("localStorage", {})
        if not isinstance(local_stotage, dict):
            local_stotage = {}

        cherry_studio_data = local_stotage.get("persist:cherry-studio", "{}")
        if not isinstance(cherry_studio_data, str):
            return topics

        try:
            cherry_studio = json.loads(cherry_studio_data)
            if not isinstance(cherry_studio, dict):
                return topics

            # 获取assistants数据
            assistants_data = cherry_studio.get("assistants", "{}")
            if not isinstance(assistants_data, str):
                return topics

            assistants = json.loads(assistants_data)
            if not isinstance(assistants, dict):
                return topics

            # 获取所有助手的topics
            assistant_list = assistants.get("assistants", [])
            if not isinstance(assistant_list, list):
                return topics

            # 遍历每个助手的topics
            for assistant in assistant_list:
                assistant_topics = assistant.get("topics", [])
                if not isinstance(assistant_topics, list):
                    continue

                for topic in assistant_topics:
                    topic_id = topic.get("id")
                    topic_name = topic.get("name")
                    topic_created_at = topic.get("createdAt")

                    # 更新topics列表中对应topic的信息
                    for t in topics:
                        if t.get("id") == topic_id:
                            t["name"] = topic_name
                            t["createdAt"] = topic_created_at
                            break

        except json.JSONDecodeError:
            return topics

        return topics


def parse_nextchat_data(filepath: str) -> List[Dict]:
    """解析NextChat格式的数据"""
    with open(filepath, "r", encoding="utf8") as f:
        data = json.loads(f.read())
        store = data.get("chat-next-web-store", {})
        sessions = store.get("sessions", [])
        if not isinstance(sessions, list):
            sessions = []
        return sessions


def fetch_lobechat_data(database_url: str, user_id: str) -> List[Dict]:
    """从LobeChat数据库获取数据"""
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    try:
        # 获取所有topics
        cur.execute(
            "SELECT id, title, created_at, updated_at, history_summary FROM topics WHERE user_id = %s ORDER BY created_at",
            (user_id,),
        )
        topics = cur.fetchall()

        result = []
        local_tz = get_localzone()

        for topic in topics:
            topic_id, title, created_at, updated_at, summary = topic

            # 获取topic下的所有messages
            cur.execute(
                """
                SELECT id, role, content, model, provider, created_at, parent_id 
                FROM messages 
                WHERE topic_id = %s 
                ORDER BY created_at
                """,
                (topic_id,),
            )
            messages = cur.fetchall()

            # 构建问答对
            converted_messages = build_qa_pairs(messages)

            # 构建基础会话数据
            session = {
                "title": title,
                "summary": summary,
                "messages": converted_messages,
                "created_at": created_at.astimezone(local_tz),
                "updated_at": updated_at.astimezone(local_tz),
            }

            result.append(session)

        return result

    finally:
        cur.close()
        conn.close()


def convert_nextchat_to_lobechat(data: List[Dict]) -> List[Dict]:
    """将NextChat格式数据转换为LobeChat格式"""
    result = []
    for session in data:
        if not isinstance(session, dict):
            continue

        messages = session.get("messages", [])
        if not messages:
            continue

        # 构建LobeChat格式的消息列表
        converted_messages = []
        last_question_id = None
        for msg in messages:
            if not isinstance(msg, dict):
                continue

            message_id = f"msg_{random_chars(14, False)}"
            role = trim(msg.get("role", "")).lower()
            content = msg.get("content", "")

            # 解析消息时间
            date_str = msg.get("date", "")
            try:
                msg_created_at = datetime.strptime(date_str, "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except:
                msg_created_at = datetime.now(timezone.utc)

            message = {
                "id": message_id,
                "role": role,
                "content": content,
                "created_at": msg_created_at,
            }

            if role == "user":
                last_question_id = message_id
            else:
                message["model"] = msg.get("model", "gpt-4o")
                message["provider"] = "openai"
                message["parent_id"] = last_question_id

            converted_messages.append(message)

        # 获取最后更新时间
        timestamp = session.get("lastUpdate", int(datetime.now(timezone.utc).timestamp() * 1000))
        date = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)

        # 构建LobeChat格式的会话
        result.append(
            {
                "title": session.get("topic", "新的聊天"),
                "summary": session.get("memoryPrompt", ""),
                "messages": converted_messages,
                "created_at": date,
                "updated_at": date,
            }
        )

    return result


def convert_cherrystudio_to_lobechat(data: List[Dict]) -> List[Dict]:
    """将Cherry Studio格式数据转换为LobeChat格式"""
    result = []
    for topic in data:
        if not isinstance(topic, dict):
            continue

        messages = topic.get("messages", [])
        if not messages:
            continue

        # 构建LobeChat格式的消息列表
        converted_messages = []
        last_question_id = None
        for msg in messages:
            if not isinstance(msg, dict):
                continue

            message_id = f"msg_{random_chars(14, False)}"
            role = trim(msg.get("role", "")).lower()
            content = msg.get("content", "")
            reasoning_content = trim(msg.get("reasoning_content", ""))
            if reasoning_content:
                content = f"<think>{reasoning_content}</think>\n{content}"

            # 解析消息时间
            date_str = msg.get("createdAt", "")
            try:
                msg_created_at = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except:
                msg_created_at = datetime.now(timezone.utc)

            message = {
                "id": message_id,
                "role": role,
                "content": content,
                "created_at": msg_created_at,
            }

            if role == "user":
                last_question_id = message_id
            else:
                item = msg.get("model", None)
                if item and isinstance(item, dict):
                    model = item.get("id", "gpt-4o")
                    provider = item.get("provider", "openai")
                else:
                    model = "gpt-4o"
                    provider = "openai"

                message["model"] = model
                message["provider"] = provider
                message["parent_id"] = last_question_id

            converted_messages.append(message)

        # 获取创建和更新时间
        if topic.get("createdAt", ""):
            created_at = datetime.strptime(topic.get("createdAt"), "%Y-%m-%dT%H:%M:%S.%f")
        else:
            created_at = converted_messages[0]["created_at"] if converted_messages else datetime.now(timezone.utc)

        updated_at = converted_messages[-1]["created_at"] if converted_messages else created_at

        # 构建LobeChat格式的会话
        result.append(
            {
                "title": topic.get("name", "默认话题"),
                "summary": topic.get("summary", ""),
                "messages": converted_messages,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )

    return result


def convert_lobechat_to_nextchat(data: List[Dict]) -> List[Dict]:
    """将LobeChat格式数据转换为NextChat格式"""
    result = []
    for session in data:
        if not isinstance(session, dict):
            continue

        messages = session.get("messages", [])
        if not messages:
            continue

        # 构建NextChat格式的消息列表
        converted_messages = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue

            date = msg.get("date", None) or msg.get("created_at", None)
            if not date:
                date = datetime.now(timezone.utc)

            if type(date) != str:
                date = date.strftime("%Y/%m/%d %H:%M:%S")

            message = {
                "role": msg.get("role", ""),
                "content": msg.get("content", ""),
                "date": date,
            }

            if msg.get("role") == "assistant" and msg.get("model"):
                message["model"] = msg.get("model")

            converted_messages.append(message)

        # 构建NextChat格式的会话
        result.append(
            {
                "id": get_session_id(),
                "topic": session.get("title", "新的聊天"),
                "memoryPrompt": session.get("summary", ""),
                "messages": converted_messages,
                "stat": {
                    "tokenCount": 0,
                    "wordCount": 0,
                    "charCount": sum(len(msg["content"]) for msg in converted_messages),
                },
                "lastUpdate": int(session.get("updated_at").timestamp() * 1000),
                "lastSummarizeIndex": 0,
                "mask": {
                    "id": get_session_id(),
                    "avatar": "gpt-bot",
                    "name": session.get("title", "新的聊天"),
                    "context": [],
                    "syncGlobalConfig": True,
                    "modelConfig": {
                        "model": "gpt-3.5-turbo",
                        "temperature": 0.5,
                        "top_p": 1,
                        "max_tokens": 4000,
                        "presence_penalty": 0,
                        "frequency_penalty": 0,
                        "sendMemory": True,
                        "historyMessageCount": 4,
                        "compressMessageLengthThreshold": 1000,
                        "enableInjectSystemPrompts": True,
                        "template": "{{input}}",
                    },
                    "lang": "cn",
                    "builtin": False,
                    "createdAt": int(session.get("created_at").timestamp() * 1000),
                },
            }
        )

    return result


def convert_lobechat_to_cherrystudio(data: List[Dict]) -> List[Dict]:
    """将LobeChat格式数据转换为Cherry Studio格式"""
    result = []
    for session in data:
        if not isinstance(session, dict):
            continue

        messages = session.get("messages", [])
        if not messages:
            continue

        # 构建Cherry Studio格式的消息列表
        converted_messages = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue

            date = msg.get("date", None)
            if not date or not isinstance(date, (datetime, str)):
                date = datetime.now(timezone.utc)

            if type(date) != str:
                date = date.strftime("%Y-%m-%d %H:%M:%S")

            message = {
                "id": str(uuid.uuid4()).lower(),
                "role": msg.get("role", ""),
                "content": msg.get("content", ""),
                "createdAt": date,
                "type": "text",
                "status": "success",
            }

            if msg.get("role") == "assistant":
                model_id = msg.get("model", "gpt-4o")
                message["model"] = {
                    "id": model_id,
                    "provider": msg.get("provider", "openai"),
                    "name": model_id,
                    "group": model_id,
                    "owned_by": "Other",
                }

            converted_messages.append(message)

        # 构建Cherry Studio格式的主题
        topic = {
            "id": str(uuid.uuid4()).lower(),
            "messages": converted_messages,
            "name": session.get("title", "默认话题"),
            "summary": session.get("summary", ""),
            "createdAt": session.get("created_at").strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3],
        }
        result.append(topic)

    return result


def get_assistant_id(local_storage: dict) -> str:
    """从 localStroage 的 assistants 获取第一个 assistant 的 id"""
    try:
        # 获取 persist:cherry-studio 数据
        cherry_studio_data = local_storage.get("persist:cherry-studio", "{}")

        # 解析 JSON 字符串
        cherry_studio_json = json.loads(cherry_studio_data)

        # 获取 assistants 字段并解析
        assistants_data = json.loads(cherry_studio_json.get("assistants", "{}"))

        # 获取 assistants 数组中的第一个 assistant
        first_assistant = assistants_data.get("assistants", [])[0]

        # 返回 assistant 的 id
        return first_assistant.get("id", "")
    except (json.JSONDecodeError, IndexError, KeyError):
        return ""


def save_to_lobechat(
    data: List[Dict], database_url: str, user_id: str, append: bool = True, source_format: str = ""
) -> None:
    """保存数据到LobeChat数据库"""
    # 根据源格式转换数据
    if source_format == ChatFormat.NEXTCHAT:
        data = convert_nextchat_to_lobechat(data)
    elif source_format == ChatFormat.CHERRYSTUDIO:
        data = convert_cherrystudio_to_lobechat(data)

    # 连接数据库
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    try:
        if not append:
            # 如果是覆盖模式，先删除现有数据
            cur.execute("DELETE FROM messages WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM topics WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM threads WHERE user_id = %s", (user_id,))
            conn.commit()

        for session in data:
            topic_id = f"tpc_{random_chars(12, False)}"
            title = session.get("title", "")
            summary = session.get("summary", "")
            created_at = session.get("created_at")
            updated_at = session.get("updated_at")

            # 插入topic
            sql = "INSERT INTO topics (id, user_id, title, created_at, updated_at, history_summary) VALUES (%s, %s, %s, %s, %s, %s);"
            cur.execute(sql, (topic_id, user_id, title, created_at, updated_at, summary))
            conn.commit()

            # 插入消息
            for message in session.get("messages", []):
                message_id = message.get("id")
                role = message.get("role")
                content = message.get("content")
                created_at = message.get("created_at")

                if role == "user":
                    sql = "INSERT INTO messages (id, role, content, user_id, topic_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s);"
                    cur.execute(sql, (message_id, role, content, user_id, topic_id, created_at, created_at))
                else:
                    model = message.get("model")
                    provider = message.get("provider")
                    parent_id = message.get("parent_id")

                    sql = "INSERT INTO messages (id, role, content, model, provider, user_id, topic_id, parent_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
                    cur.execute(
                        sql,
                        (
                            message_id,
                            role,
                            content,
                            model,
                            provider,
                            user_id,
                            topic_id,
                            parent_id,
                            created_at,
                            created_at,
                        ),
                    )
                conn.commit()

    finally:
        cur.close()
        conn.close()


def save_to_nextchat(data: List[Dict], filepath: str, append: bool = True, source_format: str = "") -> None:
    """保存数据到NextChat格式文件"""
    # 根据源格式转换数据
    if source_format == ChatFormat.LOBECHAT:
        data = convert_lobechat_to_nextchat(data)
    elif source_format == ChatFormat.CHERRYSTUDIO:
        # 先转换成LobeChat格式，再转换成NextChat格式
        data = convert_lobechat_to_nextchat(convert_cherrystudio_to_lobechat(data))

    # 读取现有NextChat文件（如果存在）
    nextchat_data = {"chat-next-web-store": {"sessions": []}}
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf8") as f:
            nextchat_data = json.load(f)

    # 根据append参数决定是追加还是覆盖
    if append:
        # 追加模式：添加新会话到现有会话列表
        nextchat_data["chat-next-web-store"]["sessions"].extend(data)
    else:
        # 覆盖模式：用新会话替换现有会话
        nextchat_data["chat-next-web-store"]["sessions"] = data

    # 确保输出目录存在
    output_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(output_dir, exist_ok=True)

    # 写入文件
    with open(filepath, "w", encoding="utf8") as f:
        json.dump(nextchat_data, f, ensure_ascii=False, indent=2)


def save_to_cherry_studio(data: List[Dict], filepath: str, append: bool = True, source_format: str = "") -> None:
    """保存数据到Cherry Studio格式文件"""
    # 根据源格式转换数据
    if source_format == ChatFormat.LOBECHAT:
        data = convert_lobechat_to_cherrystudio(data)
    elif source_format == ChatFormat.NEXTCHAT:
        # 先转换成LobeChat格式，再转换成Cherry Studio格式
        data = convert_lobechat_to_cherrystudio(convert_nextchat_to_lobechat(data))

    # 读取现有Cherry Studio文件（如果存在）
    cherry_data = {"indexedDB": {"topics": []}, "localStorage": {}}
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf8") as f:
            cherry_data = json.load(f)

    assistant_id = get_assistant_id(cherry_data.get("localStorage", {}))
    if not assistant_id:
        print("警告：未找到 assistant_id，跳过转换")
        return

    # 为每个topic的消息添加assistantId
    for topic in data:
        if not isinstance(topic, dict):
            continue

        messages = topic.get("messages", [])
        if not isinstance(messages, list):
            continue

        for message in messages:
            if not isinstance(message, dict):
                continue
            message["assistantId"] = assistant_id
            message["topicId"] = topic.get("id")

    # 根据append参数决定是追加还是覆盖
    if append:
        # 追加模式：添加新topics到现有列表
        cherry_data["indexedDB"]["topics"].extend(data)
    else:
        # 覆盖模式：用新topics替换现有topics
        cherry_data["indexedDB"]["topics"] = data

    # 更新localStorage中的persist:cherry-studio数据
    persist_key = "persist:cherry-studio"
    local_storage = cherry_data.get("localStorage", {})
    if not isinstance(local_storage, dict):
        local_storage = {}

    # 构建topics摘要数据
    topics_summary = []
    if append:
        # 如果是追加模式，先获取现有的topics摘要
        try:
            pcs = json.loads(local_storage.get(persist_key, "{}"))
            tools = json.loads(pcs.get("assistants", "{}"))
            assistants = tools.get("assistants", [])
            if assistants and isinstance(assistants, list) and isinstance(assistants[0], dict):
                topics_summary = assistants[0].get("topics", [])
        except:
            topics_summary = []

    # 添加新topics的摘要
    for topic in data:
        if not isinstance(topic, dict):
            continue

        topic_id = topic.get("id")
        topic_name = topic.get("name", "")
        created_at = topic.get("createdAt", "")

        summary = {
            "id": topic_id,
            "assistantId": assistant_id,
            "createdAt": created_at,
            "updatedAt": created_at,
            "name": topic_name,
            "messages": [],
        }
        topics_summary.append(summary)

    # 更新localStorage
    try:
        pcs = json.loads(local_storage.get(persist_key, "{}"))
        tools = json.loads(pcs.get("assistants", "{}"))
        assistants = tools.get("assistants", [])

        if not assistants or not isinstance(assistants, list):
            # 如果没有assistants数据，创建新的
            assistants = [
                {
                    "id": assistant_id,
                    "topics": topics_summary,
                    "name": "Default Assistant",
                    "avatar": "",
                    "description": "",
                    "systemRole": "",
                    "defaultModel": {
                        "id": "gpt-4o",
                        "name": "GPT-4",
                        "provider": "openai",
                        "group": "gpt-4",
                        "owned_by": "Other",
                    },
                }
            ]
        else:
            # 查找 id 为 assistant_id 的 assistant 并更新 topics
            assistant = next((a for a in assistants if a["id"] == assistant_id), None)
            if assistant:
                assistant["topics"] = topics_summary

        tools["assistants"] = assistants
        pcs["assistants"] = json.dumps(tools, ensure_ascii=False)
        local_storage[persist_key] = json.dumps(pcs, ensure_ascii=False)
        cherry_data["localStorage"] = local_storage
    except:
        print("警告：更新localStorage数据失败")

    # 确保输出目录存在
    output_dir = os.path.dirname(os.path.abspath(filepath))
    os.makedirs(output_dir, exist_ok=True)

    # 写入文件
    with open(filepath, "w", encoding="utf8") as f:
        json.dump(cherry_data, f, ensure_ascii=False, indent=2)


def convert_chat_format(
    source_format: str,
    target_format: str,
    input_path: str,
    output_path: str,
    database_url: Optional[str] = None,
    user_id: Optional[str] = None,
    append: bool = True,
) -> None:
    """转换聊天记录格式"""
    # 验证格式
    valid_formats = [ChatFormat.LOBECHAT, ChatFormat.NEXTCHAT, ChatFormat.CHERRYSTUDIO]
    if source_format not in valid_formats or target_format not in valid_formats:
        print(f"不支持的格式：source_format={source_format}, target_format={target_format}")
        return

    if source_format == target_format:
        print("源格式和目标格式相同，无需转换")
        return

    # 读取源数据
    source_data = []
    if source_format == ChatFormat.LOBECHAT:
        if not database_url or not user_id:
            print("转换LobeChat格式需要提供 database_url 和 user_id")
            return
        source_data = fetch_lobechat_data(database_url, user_id)
    elif source_format == ChatFormat.NEXTCHAT:
        source_data = parse_nextchat_data(input_path)
    elif source_format == ChatFormat.CHERRYSTUDIO:
        source_data = parse_cherry_studio_data(input_path)

    if not source_data:
        print("源数据为空，跳过转换")
        return

    if append and target_format != ChatFormat.LOBECHAT and (not output_path or not os.path.exists(output_path)):
        print("追加输出路径不存在，跳过转换")
        return

    # 如果 output_path 存在，则先备份
    if os.path.exists(output_path):
        backup_path = f"{output_path}.backup"
        shutil.copy2(output_path, backup_path)
        print(f"初始文件已备份到 {backup_path}")

    # 保存为目标格式
    if target_format == ChatFormat.LOBECHAT:
        if not database_url or not user_id:
            print("转换到LobeChat格式需要提供 database_url 和 user_id")
            return
        save_to_lobechat(source_data, database_url, user_id, append, source_format)
    elif target_format == ChatFormat.NEXTCHAT:
        save_to_nextchat(source_data, output_path, append, source_format)
    elif target_format == ChatFormat.CHERRYSTUDIO:
        save_to_cherry_studio(source_data, output_path, append, source_format)

    action = "追加到" if append else "覆盖"
    print(f"转换完成，已将数据{action}目标位置")


def main():
    parser = argparse.ArgumentParser(description="聊天记录格式转换工具")
    parser.add_argument(
        "-s",
        "--source",
        type=str,
        required=True,
        choices=[ChatFormat.LOBECHAT, ChatFormat.NEXTCHAT, ChatFormat.CHERRYSTUDIO],
        dest="source",
        help="源格式",
    )
    parser.add_argument(
        "-t",
        "--target",
        type=str,
        required=True,
        choices=[ChatFormat.LOBECHAT, ChatFormat.NEXTCHAT, ChatFormat.CHERRYSTUDIO],
        dest="target",
        help="目标格式",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=str,
        dest="input",
        help="输入文件路径（对于LobeChat格式，此参数被忽略）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        dest="output",
        help="输出文件路径（对于LobeChat格式，此参数被忽略）",
    )
    parser.add_argument(
        "-d",
        "--database-url",
        type=str,
        dest="database_url",
        help="LobeChat数据库URL（仅当源格式或目标格式为LobeChat时需要）",
    )
    parser.add_argument(
        "-u",
        "--user-id",
        type=str,
        dest="user_id",
        help="用户ID（仅当源格式或目标格式为LobeChat时需要）",
    )
    parser.add_argument(
        "-w",
        "--overwrite",
        action="store_true",
        dest="overwrite",
        help="覆盖现有数据而不是追加（默认：追加）",
    )

    args = parser.parse_args()

    # 验证参数
    if args.source == ChatFormat.LOBECHAT or args.target == ChatFormat.LOBECHAT:
        if not args.database_url or not args.user_id:
            print("Error: 使用LobeChat格式时需要提供 --database-url 和 --user-id 参数")
            return

    if args.source != ChatFormat.LOBECHAT and not args.input:
        print("Error: 非LobeChat源格式需要提供 --input 参数")
        return

    if args.target != ChatFormat.LOBECHAT and not args.output:
        print("Error: 非LobeChat目标格式需要提供 --output 参数")
        return

    # 执行转换
    convert_chat_format(
        source_format=args.source,
        target_format=args.target,
        input_path=args.input,
        output_path=args.output,
        database_url=args.database_url,
        user_id=args.user_id,
        append=not args.overwrite,
    )


if __name__ == "__main__":
    main()

import argparse
import json
import os
import random
import string
from datetime import datetime, timedelta, timezone

from psycopg2 import pool

DATABASE_URL = ""


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def random_chars(length: int, punctuation: bool = False) -> str:
    length = max(length, 1)
    if punctuation:
        chars = "".join(random.sample(string.ascii_letters + string.digits + string.punctuation, length))
    else:
        chars = "".join(random.sample(string.ascii_letters + string.digits, length))

    return chars


def main(filename: str, user_id: str, database_url: str, append: bool = True) -> None:
    filename = trim(filename)
    if not filename:
        print("chat histories file cannot be empty")
        return

    filepath = os.path.abspath(filename)
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        print(f"file {filepath} not exists")
        return

    sessions = None
    with open(filepath, "r", encoding="utf8") as f:
        store = json.loads(f.read()).get("chat-next-web-store", None)
        sessions = store.get("sessions", None)
        if not isinstance(sessions, list):
            sessions = []

    if not sessions:
        print(f"skip migrate due to chat histories is empty")
        return

    user_id = trim(user_id)
    if not user_id:
        print(f"user id cannot be empty")
        return

    # Get the connection string from the environment variable
    database = trim(database_url) or trim(DATABASE_URL)
    if not database:
        print(f"cannot load database info, please check your config")
        return

    # Create a connection pool
    conn_pool = pool.SimpleConnectionPool(1, 10, database)

    # Check if the pool was created successfully
    if not conn_pool:
        print("connection pool created failed")
        return

    # Get a connection from the pool
    conn = conn_pool.getconn()

    # Create a cursor object
    cur = conn.cursor()

    try:
        if not append:
            # Clear all messages and topics for the user if overwrite
            cur.execute("DELETE FROM messages WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM topics WHERE user_id = %s", (user_id,))
            conn.commit()

        for session in sessions:
            if not session or not isinstance(session, dict):
                continue

            topic_id = f"tpc_{random_chars(12, False)}"
            title = session.get("topic", "")
            summary = session.get("memoryPrompt", "")

            timestamp = session.get("lastUpdate")
            date = datetime.fromtimestamp(timestamp / 1000.0, tz=timezone.utc)

            messages = session.get("messages", [])
            if not messages or not isinstance(messages, list):
                print(f"skip session '{title}' due to messages is empty")
                continue

            # Insert data into topic table
            sql = "INSERT INTO topics (id, user_id, title, created_at, updated_at, history_summary) VALUES (%s, %s, %s, %s, %s, %s);"
            cur.execute(sql, (topic_id, user_id, title, date, date, summary))
            conn.commit()

            last_question_id = None
            for message in messages:
                if not message or not isinstance(message, dict):
                    continue

                message_id = f"msg_{random_chars(14, False)}"
                role = trim(message.get("role")).lower()
                text, content = "", message.get("content")
                if isinstance(content, str):
                    text = content
                else:
                    array = list()
                    for item in content:
                        msg_type = item.get("type", "")
                        if msg_type == "text":
                            array.append(item.get("text"))
                        elif msg_type == "image_url":
                            url = item.get("image_url").get("url")
                            if url:
                                array.append(f"图片链接：{url}")

                    text = "。".join(array)

                zone = timezone(timedelta(hours=8))
                created_at = (
                    datetime.strptime(message.get("date"), "%Y/%m/%d %H:%M:%S")
                    .replace(tzinfo=zone)
                    .astimezone(timezone.utc)
                )

                if role == "user":
                    sql = "INSERT INTO messages (id, role, content, user_id, topic_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s);"
                    cur.execute(sql, (message_id, role, text, user_id, topic_id, created_at, created_at))
                    conn.commit()

                    last_question_id = message_id
                else:
                    model = trim(message.get("model"))
                    provider = "openai"
                    parent_id = last_question_id

                    sql = "INSERT INTO messages (id, role, content, model, provider, user_id, topic_id, parent_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
                    cur.execute(
                        sql,
                        (message_id, role, text, model, provider, user_id, topic_id, parent_id, created_at, created_at),
                    )
                    conn.commit()

    finally:
        # Close the cursor and return the connection to the pool
        cur.close()
        conn_pool.putconn(conn)

        # Close all connections in the pool
        conn_pool.closeall()

    action = "appended to" if append else "replaced in"
    print(f"Migrate completed, sessions {action} database")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f",
        "--file",
        type=str,
        required=True,
        dest="file",
        help="nextchat chat history data file path",
    )
    parser.add_argument(
        "-u",
        "--user-id",
        type=str,
        required=True,
        dest="user_id",
        help="user id who owns the chat history",
    )
    parser.add_argument(
        "-d",
        "--database-url",
        type=str,
        required=True,
        dest="database_url",
        help="database url for lobechat",
    )
    parser.add_argument(
        "-o",
        "--overwrite",
        action="store_true",
        dest="overwrite",
        help="overwrite existing sessions instead of appending (default: append)",
    )

    args = parser.parse_args()
    main(
        filename=args.file,
        user_id=args.user_id,
        database_url=args.database_url,
        append=not args.overwrite,
    )

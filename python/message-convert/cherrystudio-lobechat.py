import argparse
import json
import os
import random
import string
from datetime import datetime, timezone
from typing import Dict, List

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


def parse_cherry_studio_data(filepath: str) -> List[Dict]:
    with open(filepath, "r", encoding="utf8") as f:
        data = json.loads(f.read())
        if not isinstance(data, dict):
            return []

        # Get topics data
        indexed_db = data.get("indexedDB", {})
        topics = indexed_db.get("topics", [])
        if not isinstance(topics, list):
            topics = []

        return topics


def main(filename: str, user_id: str, database_url: str, append: bool = True) -> None:
    filename = trim(filename)
    if not filename:
        print("cherry studio data file cannot be empty")
        return

    filepath = os.path.abspath(filename)
    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        print(f"file {filepath} not exists")
        return

    topics = parse_cherry_studio_data(filepath)
    if not topics:
        print(f"skip migrate due to topics is empty")
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

        for topic in topics:
            if not isinstance(topic, dict):
                continue

            topic_id = f"tpc_{random_chars(12, False)}"
            messages = topic.get("messages", [])
            if not messages or not isinstance(messages, list):
                continue

            # Use the first message's time as topic creation time
            first_msg = messages[0]
            if not isinstance(first_msg, dict):
                continue

            created_at_str = first_msg.get("createdAt", "")
            try:
                created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except:
                created_at = datetime.now(timezone.utc)

            # Use the last message's time as topic update time
            last_msg = messages[-1]
            if not isinstance(last_msg, dict):
                continue

            updated_at_str = last_msg.get("createdAt", "")
            try:
                updated_at = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except:
                updated_at = datetime.now(timezone.utc)

            # Extract topic title from the first message
            title = ""
            if isinstance(first_msg, dict) and first_msg.get("role") == "user":
                title = first_msg.get("content", "")[:50]  # Use first 50 characters as title

            # Insert topic
            sql = "INSERT INTO topics (id, user_id, title, created_at, updated_at, history_summary) VALUES (%s, %s, %s, %s, %s, %s);"
            cur.execute(sql, (topic_id, user_id, title, created_at, updated_at, ""))
            conn.commit()

            last_question_id = None
            for message in messages:
                if not isinstance(message, dict):
                    continue

                message_id = f"msg_{random_chars(14, False)}"
                role = trim(message.get("role", "")).lower()
                content = trim(message.get("content", ""))
                created_at_str = message.get("createdAt", "")

                try:
                    msg_created_at = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                except:
                    msg_created_at = datetime.now(timezone.utc)

                if role == "user":
                    sql = "INSERT INTO messages (id, role, content, user_id, topic_id, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s);"
                    cur.execute(sql, (message_id, role, content, user_id, topic_id, msg_created_at, msg_created_at))
                    conn.commit()
                    last_question_id = message_id
                else:
                    model = "gpt-3.5-turbo"  # Default model used by Cherry Studio
                    provider = "openai"
                    parent_id = last_question_id

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
                            msg_created_at,
                            msg_created_at,
                        ),
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
        "--filename",
        type=str,
        required=True,
        dest="filename",
        help="cherry studio data file path",
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
        filename=args.filename,
        user_id=args.user_id,
        database_url=args.database_url,
        append=not args.overwrite,
    )

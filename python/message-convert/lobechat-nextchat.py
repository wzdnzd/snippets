import argparse
import json
import os
from datetime import timezone
import random
import string
from typing import Dict, List, Tuple

import psycopg2


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def random_session_id() -> str:
    """Generate a session ID of length 21, consisting of letters, numbers, and underscores"""
    chars = string.ascii_letters + string.digits + "_"
    return "".join(random.sample(chars, 21))


def build_qa_pairs(messages: List[Tuple]) -> List[Dict]:
    """Build ordered question-answer pairs based on parent_id, handling the case where one question may have multiple answers"""
    # Build a mapping of msg_id to messages
    msg_map = {}
    # Build a mapping of question ID to answer lists
    answers_map = {}
    # Store all user questions in chronological order
    questions = []

    # First pass: Build basic mappings
    for msg in messages:
        msg_id, role, content, model, msg_created_at, parent_id = msg

        # Convert time format
        date_str = msg_created_at.astimezone(timezone.utc).strftime("%Y/%m/%d %H:%M:%S")

        message = {
            "id": random_session_id(),
            "role": role,
            "content": content,
            "date": date_str,
            "created_at": msg_created_at,  # for sorting
        }

        if role == "assistant" and model:
            message["model"] = model

        msg_map[msg_id] = message

        # If it's a user question
        if role == "user":
            questions.append((msg_id, message))
            answers_map[msg_id] = []
        # If it's an assistant answer
        elif role == "assistant" and parent_id:
            if parent_id in answers_map:
                answers_map[parent_id].append(message)

    # Build the final ordered message list
    ordered_messages = []

    # Process each question in chronological order
    questions.sort(key=lambda x: x[1]["created_at"])

    for question_id, question in questions:
        # Add the question
        ordered_messages.append(question)

        # Get all answers for this question and sort them by time
        answers = answers_map.get(question_id, [])
        answers.sort(key=lambda x: x["created_at"])

        # Add all answers
        ordered_messages.extend(answers)

    # Clean up temporary fields
    for msg in ordered_messages:
        msg.pop("created_at", None)

    return ordered_messages


def fetch_topics_and_messages(database_url: str, user_id: str) -> List[Dict]:
    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    try:
        # Get all topics
        cur.execute(
            "SELECT id, title, created_at, updated_at, history_summary FROM topics WHERE user_id = %s ORDER BY created_at",
            (user_id,),
        )
        topics = cur.fetchall()

        result = []
        for topic in topics:
            topic_id, title, created_at, updated_at, summary = topic

            # Get all messages under the topic
            cur.execute(
                """
                SELECT id, role, content, model, created_at, parent_id 
                FROM messages 
                WHERE topic_id = %s 
                ORDER BY created_at
                """,
                (topic_id,),
            )
            messages = cur.fetchall()

            # Build question-answer pairs
            converted_messages = build_qa_pairs(messages)

            # Calculate the total number of characters
            char_count = sum(len(msg["content"]) for msg in converted_messages)

            # Build session object
            session = {
                "id": random_session_id(),
                "topic": title or "新的聊天",
                "memoryPrompt": summary or "",
                "messages": converted_messages,
                "stat": {"tokenCount": 0, "wordCount": 0, "charCount": char_count},
                "lastUpdate": int(updated_at.timestamp() * 1000),
                "lastSummarizeIndex": 0,
                "mask": {
                    "id": random_session_id(),
                    "avatar": "gpt-bot",
                    "name": title or "新的聊天",
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
                    "createdAt": int(created_at.timestamp() * 1000),
                },
            }

            result.append(session)

        return result

    finally:
        cur.close()
        conn.close()


def main(database_url: str, user_id: str, nextchat_file: str, append: bool = True) -> None:
    database_url = trim(database_url)
    if not database_url:
        print("database url cannot be empty")
        return

    user_id = trim(user_id)
    if not user_id:
        print("user id cannot be empty")
        return

    nextchat_file = trim(nextchat_file)
    if not nextchat_file:
        print("nextchat file path cannot be empty")
        return

    print(f"start to fetch sessions from database")

    # Get all session data
    new_sessions = fetch_topics_and_messages(database_url, user_id)

    # Read existing NextChat file (if exists)
    nextchat_data = {"chat-next-web-store": {"sessions": []}}
    if os.path.exists(nextchat_file):
        with open(nextchat_file, "r", encoding="utf8") as f:
            nextchat_data = json.load(f)

    # Decide whether to append or overwrite based on append parameter
    if append:
        # Append mode: add new sessions to existing session list
        nextchat_data["chat-next-web-store"]["sessions"].extend(new_sessions)
    else:
        # Overwrite mode: replace existing sessions with new sessions
        nextchat_data["chat-next-web-store"]["sessions"] = new_sessions

    # Ensure output directory exists
    output_dir = os.path.dirname(os.path.abspath(nextchat_file))
    os.makedirs(output_dir, exist_ok=True)

    # Write to file
    with open(nextchat_file, "w", encoding="utf8") as f:
        json.dump(nextchat_data, f, ensure_ascii=False, indent=2)

    action = "appended to" if append else "replaced in"
    print(f"Convert completed, {len(new_sessions)} sessions {action} {nextchat_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-d",
        "--database-url",
        type=str,
        required=True,
        dest="database_url",
        help="database url for lobechat",
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
        "-f",
        "--file",
        type=str,
        required=True,
        dest="file",
        help="nextchat json file path",
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
        database_url=args.database_url,
        user_id=args.user_id,
        nextchat_file=args.file,
        append=not args.overwrite,
    )

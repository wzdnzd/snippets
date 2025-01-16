# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2025-01-15

import argparse
import json
import logging
import os
import time
import traceback
import uuid
from datetime import datetime, timezone

PATH = os.path.abspath(os.path.dirname(__file__))

logging.basicConfig(
    format="%(asctime)s %(filename)s [line:%(lineno)d] %(levelname)s: %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)


def trim(text: str) -> str:
    if not text or type(text) != str:
        return ""

    return text.strip()


def main(nextchat: str, cherrystudio: str, result: str = "") -> None:
    def generate_key(topic_name: str, created_at: str, assistant_id: str) -> str:
        return f"{trim(topic_name)}#@#{trim(created_at)}#@#{trim(assistant_id)}"

    nextchat = os.path.abspath(trim(nextchat))
    cherrystudio = os.path.abspath(trim(cherrystudio))
    result = os.path.abspath(os.path.join(PATH, (trim(result) or "migrated.json")))

    if not os.path.exists(nextchat) or not os.path.isfile(nextchat):
        logging.error("nextchat chat history file not exist")
        return

    if not os.path.exists(cherrystudio) or not os.path.isfile(cherrystudio):
        logging.error("cherry studio data file not exist")
        return

    try:
        sessions = None
        with open(nextchat, "r", encoding="utf8") as f:
            store = json.loads(f.read()).get("chat-next-web-store", None)
            if isinstance(store, dict):
                sessions = store.get("sessions", None)
                if not isinstance(sessions, list):
                    sessions = []

        if not sessions:
            logging.error(f"skip migrate due to nextchat not exist any history")
            return

        topics, topics_summary, data = [], [], None
        assistant_id, local_storage, persist_key_name = None, {}, "persist:cherry-studio"

        with open(cherrystudio, "r", encoding="utf8") as f:
            data = json.loads(f.read())
            if not isinstance(data, dict):
                logging.error(f"invalid cherry studio data file: ${cherrystudio}")
                return

            # load exists topics
            indexed_db = data.get("indexedDB", None)
            if isinstance(indexed_db, dict):
                topics = indexed_db.get("topics", None)
                if not isinstance(topics, list):
                    topics = []

            # load exists topics summary
            local_storage = data.get("localStorage", None)
            if not isinstance(local_storage, dict):
                logging.error(f"skip migrate due to localStorage data missing for cherry studio")
                return

            content = local_storage.get(persist_key_name, "")
            try:
                old_summary = json.loads(content)
                tools = json.loads(old_summary.get("assistants", ""))
                if not isinstance(tools, dict):
                    logging.error(f"skip migrate due to assistants config missing")
                    return

                assistants = tools.get("assistants", [])
                if not assistants or not isinstance(assistants, list):
                    logging.error(f"skip migrate due to assistants list is empty")
                    return

                default_assistant = assistants[0]
                if not isinstance(default_assistant, dict):
                    logging.error(f"skip migrate due to cannot extract assistant id")
                    return

                assistant_id = default_assistant.get("id", None)
                topics_summary = default_assistant.get("topics", [])
            except:
                logging.error(f"failed to parse cherry studio persist, content: {content}")
                return

        if not assistant_id:
            assistant_id = get_assistantid(topics=topics)

        # unique topic
        records, added = set(), False
        for t in topics_summary:
            if not isinstance(t, dict):
                continue

            key = generate_key(t.get("name"), t.get("createdAt"), t.get("assistantId"))
            records.add(key)

        # convert nextchat data to cherry studio data
        for session in sessions:
            if not isinstance(session, dict):
                continue

            messages = session.get("messages", [])
            if not isinstance(messages, list):
                logging.error(f"A topic with an empty message list has been ignored")
                continue

            topic_id = str(uuid.uuid4()).lower()
            topic_name = trim(session.get("topic", ""))

            timestamp = session.get("lastUpdate") / 1000 or time.time()
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            updated_at = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")[:-3]

            key = generate_key(topic_name, updated_at, assistant_id)
            if key in records:
                logging.error(f"topic {topic_name} already in assistant {assistant_id} chat histories, ignore it")
                continue

            converted_messages = list()
            for message in messages:
                if not isinstance(message, dict):
                    continue

                message_id = str(uuid.uuid4()).lower()
                role = trim(message.get("role")) or "user"
                content = message.get("content", "")
                date = trim(message.get("date", ""))

                if date:
                    created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.strptime(date, "%Y/%m/%d %H:%M:%S"))
                else:
                    created_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time()))

                item = {
                    "id": message_id,
                    "role": role,
                    "content": content,
                    "assistantId": assistant_id,
                    "topicId": topic_id,
                    "createdAt": created_at,
                    "type": "text",
                    "status": "success",
                }
                converted_messages.append(item)

            if converted_messages:
                topic = {"id": topic_id, "messages": converted_messages}
                topics.append(topic)

                summary = {
                    "id": topic_id,
                    "assistantId": assistant_id,
                    "createdAt": updated_at,
                    "updatedAt": updated_at,
                    "name": topic_name,
                    "messages": [],
                }
                topics_summary.append(summary)
                added = added or True

        if not added:
            logging.error(f"No new data added, skip migrate, nextchat: {nextchat}, cherry-studio: {cherrystudio}")
            return

        directory = os.path.dirname(result)
        os.makedirs(directory, exist_ok=True)

        data["indexedDB"]["topics"] = topics

        # replace persist data
        pcs = json.loads(local_storage.get(persist_key_name, ""))
        tools = json.loads(pcs.get("assistants", ""))
        assistants = tools.get("assistants", [])

        default_assistant = assistants[0]
        default_assistant["topics"] = topics_summary
        assistants[0] = default_assistant
        tools["assistants"] = assistants
        pcs["assistants"] = json.dumps(tools, ensure_ascii=False)

        local_storage[persist_key_name] = json.dumps(pcs, ensure_ascii=False)
        data["localStorage"] = local_storage

        # save data to target file
        with open(result, "w+", encoding="utf8") as f:
            json.dump(data, f, ensure_ascii=False)

        logging.info(f"migrate finished, result file: {result}")
    except:
        traceback.print_exc()


def get_assistantid(topics: list) -> str:
    topics = [] if not isinstance(topics, list) else topics

    for topic in topics:
        if not isinstance(topic, dict):
            continue

        messages = topic.get("messages", None)
        if not isinstance(messages, list):
            continue

        for message in messages:
            if not isinstance(message, dict):
                continue

            assistant_id = trim(message.get("assistantId", ""))
            if assistant_id:
                return assistant_id

    return str(uuid.uuid4()).lower()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-c",
        "--cherry-studio",
        dest="cherrystudio",
        type=str,
        required=True,
        help="cherry studio data file path",
    )

    parser.add_argument(
        "-n",
        "--nextchat",
        dest="nextchat",
        type=str,
        required=True,
        help="nextchat data file path",
    )

    parser.add_argument(
        "-r",
        "--result",
        dest="result",
        type=str,
        required=True,
        help="migrated data file path",
    )

    args = parser.parse_args()
    main(nextchat=args.nextchat, cherrystudio=args.cherrystudio, result=args.result)

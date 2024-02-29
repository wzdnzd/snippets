# -*- coding: utf-8 -*-

# @Author  : wzdnzd
# @Time    : 2024-02-28

import uuid

import streamlit as st

import llm
from config import API_KEY, LLM_API, MODEL_NAME, STRICT_FEEDBACK
from database.config import DB_TABLENAME
from database.dbclient import MySqLClient, create_table, save_feedback, save_history
from history import ChatHistory
from streamlit_feedback import streamlit_feedback
from tools import utils
from tools.logger import logger

st.set_page_config(page_title="鼎磐小助手", layout="centered", page_icon="🔥")

# 对话历史记录
CACHES = []

# 数据库客户端
DB_CLIENT = MySqLClient()

# 如果表不存在则创建
create_table(table=DB_TABLENAME, client=DB_CLIENT)


def get_text(role, content):
    jsoncon = {"role": role, "content": content}
    CACHES.append(jsoncon)
    return CACHES


def get_length(text):
    return 0 if not text else sum([len(content["content"]) for content in text])


def check_length(text):
    while get_length(text) > 8000:
        del text[0]

    return text


def handler_feedback(feedback: dict, message_id: str, strict: bool = False) -> tuple[bool, str, str]:
    if not feedback or not isinstance(feedback, dict):
        return False, "反馈内容不能为空", "😒"

    message_id = utils.trim(message_id)
    if not message_id:
        logger.error("消息 ID 不能为空")
        return True, "", ""

    score, text = feedback.get("score"), feedback.get("text")
    fb_score = 0 if not score else (-1 if score == "👎" else 1)
    fb_detail = utils.trim(text)

    if strict and fb_score == -1 and not fb_detail:
        return False, "亲，别忘了填写反馈内容~", "😱"

    success, error = save_feedback(
        table=DB_TABLENAME,
        message_id=message_id,
        fb_score=fb_score,
        fb_detail=fb_detail,
        client=DB_CLIENT,
        strict=strict,
    )

    icon = "🎉" if success else "😭"
    if not success:
        logger.error(f"保存反馈失败，message_id: {message_id}, score: {score}, text: {text}, error: {error}")

    return success, error, icon


def render(message: tuple | list) -> None:
    if not isinstance(message, (tuple, list)) or len(message) < 3:
        return

    roles = ["user", "assistant"]
    for i in range(len(roles)):
        st.chat_message(roles[i]).write(message[i])

    message_id, init_score, label = message[2], None, "[选填] 请告诉我们您期望的答案"
    if message_id not in st.session_state:
        st.session_state[message_id] = None
    else:
        state = st.session_state.get(message_id, None)
        if state and isinstance(state, dict):
            init_score = state.get("score", None)
            text = utils.trim(state.get("text", ""))
            label = text if text else label

    feedback = streamlit_feedback(
        feedback_type="thumbs",
        optional_text_label=label,
        key=message_id,
        disable_with_score=init_score,
        submit_text_label="提交",
        cancel_text_label="关闭",
    )

    if feedback:
        success, tips, icon = handler_feedback(feedback, message_id, STRICT_FEEDBACK)
        if tips:
            st.toast(tips, icon=icon)

        # 如果保存反馈失败，则清除反馈状态
        if not success:
            del st.session_state[message_id]
            del st.session_state[f"feedback_submitted_{message_id}"]


if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []
    st.session_state["conversation_id"] = str(uuid.uuid4())


if __name__ == "__main__":
    st.success("欢迎与【鼎磐小助手】进行交流")
    user_input = st.chat_input("请输入你想咨询的问题，按回车键提交！")
    refresh = st.session_state["chat_history"] is not None and len(st.session_state["chat_history"]) > 0

    if user_input is not None or refresh:
        if user_input:
            progress_bar = st.empty()
            with st.spinner("内容已提交，鼎磐小助手正在作答中！"):
                question = check_length(get_text("user", user_input))

                response = llm.chat(url=LLM_API, messages=question, apikey=API_KEY)
                if response.success:
                    progress_bar.progress(100)
                    content = get_text("assistant", response.content)[-1]["content"]
                    st.session_state["chat_history"].append((user_input, content, response.id))

                    # 渲染对话历史
                    for message in st.session_state["chat_history"]:
                        render(message)

                    # 保存对话历史
                    history = ChatHistory(
                        conversation_id=st.session_state["conversation_id"],
                        message_id=response.id,
                        question=user_input,
                        answer=content,
                        model=response.model or MODEL_NAME,
                        created=response.created,
                    )
                    save_history(table=DB_TABLENAME, history=history, client=DB_CLIENT)

                    with st.sidebar:
                        if st.sidebar.button("清除对话历史"):
                            st.session_state["chat_history"] = []
                            st.session_state["conversation_id"] = str(uuid.uuid4())
                else:
                    st.info(f"对不起，我回答不了这个问题，错误信息：{response.error}")
        else:
            for message in st.session_state["chat_history"]:
                render(message)

FROM python:3.10-slim

WORKDIR /app

# 复制所需文件到容器中
COPY ./requirements.txt /app
COPY ./app /app/app

RUN pip install --no-cache-dir -r requirements.txt

# 配置 Token 及 API 提供者
ENV AUTH_TOKEN='your_auth_token'
ENV ALLOWED_TOKENS='["your_token_1"]'
ENV API_PROVIDERS='["your_api_service"]'

# 通用配置
ENV MAX_FAILURES=10
ENV SHOW_SEARCH_LINK=true
ENV SHOW_THINKING_PROCESS=true
ENV X_GOOG_API_CLIENT=genai-js/0.21.0
ENV TOOLS_CODE_EXECUTION_ENABLED=false

# 图片生成与网络搜索模型配置
ENV TEST_MODEL='gemini-1.5-flash'
ENV SEARCH_MODELS='["gemini-2.0-flash-exp"]'
ENV IMAGE_MODELS='["gemini-2.0-flash-exp"]'
ENV FILTERED_MODELS='["gemini-1.0-pro-vision-latest", "gemini-pro-vision", "chat-bison-001", "text-bison-001", "embedding-gecko-001"]'

# 图片上传配置
ENV UPLOAD_PROVIDER='smms'
ENV SMMS_SECRET_TOKEN='XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX'
ENV PICGO_API_KEY='xxxx'

# Stream Optimizer 相关配置
ENV STREAM_CHUNK_SIZE=5
ENV STREAM_MIN_DELAY=0.016
ENV STREAM_MAX_DELAY=0.024
ENV STREAM_LONG_TEXT_THRESHOLD=50
ENV STREAM_SHORT_TEXT_THRESHOLD=10

# Expose port
EXPOSE 7860

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--no-access-log"]

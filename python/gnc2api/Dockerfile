FROM python:3.10-slim

WORKDIR /app

# 复制所需文件到容器中
COPY ./app /app/app
COPY ./requirements.txt /app

RUN pip install --no-cache-dir -r requirements.txt
ENV API_PROVIDERS='["your_api_service"]'
ENV ALLOWED_TOKENS='["your_token_1"]'
ENV AUTH_TOKEN='your_auth_token'
ENV TOOLS_CODE_EXECUTION_ENABLED=true
ENV MODEL_SEARCH='["gemini-2.0-flash-exp"]'
ENV SHOW_SEARCH_LINK=true
ENV SHOW_THINKING_PROCESS=true
ENV MAX_FAILURES=10
ENV X_GOOG_API_CLIENT=genai-js/0.21.0

# Expose port
EXPOSE 7860

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--no-access-log"]

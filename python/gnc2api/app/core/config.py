from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    API_PROVIDERS: List[str]
    ALLOWED_TOKENS: List[str]
    MODEL_SEARCH: List[str] = ["gemini-2.0-flash-exp"]
    TOOLS_CODE_EXECUTION_ENABLED: bool = False
    SHOW_SEARCH_LINK: bool = True
    SHOW_THINKING_PROCESS: bool = True
    AUTH_TOKEN: str = ""
    MAX_FAILURES: int = 3
    TEST_MODEL: str = "gemini-1.5-flash"
    X_GOOG_API_CLIENT: str = ""

    def __init__(self):
        super().__init__()
        if not self.AUTH_TOKEN:
            self.AUTH_TOKEN = self.ALLOWED_TOKENS[0] if self.ALLOWED_TOKENS else ""

        if not self.X_GOOG_API_CLIENT:
            self.X_GOOG_API_CLIENT = "genai-js/0.21.0"

    class Config:
        env_file = ".env"


settings = Settings()

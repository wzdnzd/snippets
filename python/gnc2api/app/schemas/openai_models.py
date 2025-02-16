from typing import List, Optional, Union

from pydantic import BaseModel


class ChatRequest(BaseModel):
    messages: List[dict]
    model: str = "gemini-1.5-flash-002"
    temperature: Optional[float] = 0.7
    stream: Optional[bool] = False
    tools: Optional[List[dict]] = []
    max_tokens: Optional[int] = 8192
    stop: Optional[List[str]] = []
    top_p: Optional[float] = 0.9
    top_k: Optional[int] = 40


class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]]
    model: str = "text-embedding-004"
    encoding_format: Optional[str] = "float"


class ImageGenerationRequest(BaseModel):
    model: str = "DALL-E-3"
    prompt: str = ""
    n: int = 1
    size: Optional[str] = "1024x1024"
    quality: Optional[str] = ""
    style: Optional[str] = ""
    response_format: Optional[str] = "url"

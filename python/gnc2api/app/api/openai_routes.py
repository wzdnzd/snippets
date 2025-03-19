from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.core.logger import get_openai_logger
from app.core.security import SecurityService
from app.schemas.openai_models import ChatRequest, EmbeddingRequest
from app.services.chat.retry_handler import RetryHandler
from app.services.embedding_service import EmbeddingService
from app.services.key_generator import get_key
from app.services.model_service import ModelService
from app.services.openai_chat_service import OpenAIChatService
from app.services.provider_manager import ProviderManager, get_provider_manager_instance

router = APIRouter()
logger = get_openai_logger()

# 初始化服务
security_service = SecurityService(settings.ALLOWED_TOKENS, settings.AUTH_TOKEN)
model_service = ModelService(settings.SEARCH_MODELS, settings.IMAGE_MODELS)
embedding_service = EmbeddingService()


async def get_provider_manager():
    return await get_provider_manager_instance()


async def get_next_working_provider_wrapper(provider_manager: ProviderManager = Depends(get_provider_manager)):
    return await provider_manager.get_next_working_provider()


@router.get("/v1/models")
@router.get("/hf/v1/models")
async def list_models(
    _=Depends(security_service.verify_authorization), provider_manager: ProviderManager = Depends(get_provider_manager)
):
    logger.info("-" * 50 + "list_models" + "-" * 50)
    logger.info("Handling models list request")
    provider = await provider_manager.get_next_working_provider()
    logger.info(f"Using API provider: {provider}")
    try:
        return model_service.get_gemini_openai_models(provider)
    except Exception as e:
        logger.error(f"Error getting models list: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error while fetching models list") from e


@router.post("/v1/chat/completions")
@router.post("/hf/v1/chat/completions")
@RetryHandler(max_retries=3, key_arg="provider")
async def chat_completion(
    request: ChatRequest,
    _=Depends(security_service.verify_authorization),
    provider: str = Depends(get_next_working_provider_wrapper),
    api_key: str = Depends(get_key),
    provider_manager: ProviderManager = Depends(get_provider_manager),
):
    chat_service = OpenAIChatService(provider_manager)
    logger.info("-" * 50 + "chat_completion" + "-" * 50)
    logger.info(f"Handling chat completion request for model: {request.model}")
    logger.info(f"Request: \n{request.model_dump_json(indent=2)}")
    logger.info(f"Using API Provider: {provider}, API Key: {api_key}")

    if not model_service.check_model_support(request.model):
        raise HTTPException(status_code=400, detail=f"Model {request.model} is not supported")

    try:
        response = await chat_service.create_chat_completion(provider, request, api_key)

        # 处理流式响应
        if request.stream:
            return StreamingResponse(response, media_type="text/event-stream")
        logger.info("Chat completion request successful")
        return response
    except Exception as e:
        logger.error(f"Chat completion failed after retries: {str(e)}")
        raise HTTPException(status_code=500, detail="Chat completion failed") from e


@router.post("/v1/embeddings")
@router.post("/hf/v1/embeddings")
async def embedding(
    request: EmbeddingRequest,
    _=Depends(security_service.verify_authorization),
    provider_manager: ProviderManager = Depends(get_provider_manager),
):
    logger.info("-" * 50 + "embedding" + "-" * 50)
    logger.info(f"Handling embedding request for model: {request.model}")
    provider = await provider_manager.get_next_working_provider()
    logger.info(f"Using API Provider: {provider}")
    try:
        response = await embedding_service.create_embedding(
            base_url=provider,
            input_text=request.input,
            model=request.model,
            api_key=get_key(),
        )
        logger.info("Embedding request successful")
        return response
    except Exception as e:
        logger.error(f"Embedding request failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Embedding request failed") from e


@router.get("/v1/providers/list")
@router.get("/hf/v1/providers/list")
async def get_keys_list(
    _=Depends(security_service.verify_auth_token), provider_manager: ProviderManager = Depends(get_provider_manager)
):
    """获取有效和无效的API provider列表"""
    logger.info("-" * 50 + "get_providers_list" + "-" * 50)
    logger.info("Handling providers list request")
    try:
        providers_status = await provider_manager.get_providers_by_status()
        return {
            "status": "success",
            "data": {
                "valid_providers": providers_status["valid_providers"],
                "invalid_providers": providers_status["invalid_providers"],
            },
            "total": len(providers_status["valid_providers"]) + len(providers_status["invalid_providers"]),
        }
    except Exception as e:
        logger.error(f"Error getting providers list: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error while fetching providers list") from e

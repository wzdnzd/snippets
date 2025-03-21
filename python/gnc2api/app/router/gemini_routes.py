import base64
from copy import deepcopy
from app.config.config import settings
from app.log.logger import get_gemini_logger
from app.core.security import SecurityService
from app.domain.gemini_models import GeminiContent, GeminiRequest
from app.service.chat.gemini_chat_service import GeminiChatService
from app.service.model.model_service import ModelService
from app.handler.retry_handler import RetryHandler
from app.core.constants import API_VERSION

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from app.service.key.key_generator import get_key
from app.service.provider.provider_manager import ProviderManager, get_provider_manager_instance

# 路由设置
router = APIRouter(prefix=f"/gemini/{API_VERSION}")
router_v1beta = APIRouter(prefix=f"/{API_VERSION}")
logger = get_gemini_logger()

# 初始化服务
security_service = SecurityService(settings.ALLOWED_TOKENS, settings.AUTH_TOKEN)
model_service = ModelService(settings.SEARCH_MODELS, settings.IMAGE_MODELS)


async def get_provider_manager():
    return await get_provider_manager_instance()


async def get_next_working_provider_wrapper(provider_manager: ProviderManager = Depends(get_provider_manager)):
    return await provider_manager.get_next_working_provider()


model_service = ModelService(settings.SEARCH_MODELS, settings.IMAGE_MODELS)


@router.get("/models")
@router_v1beta.get("/models")
async def list_models(
    _=Depends(security_service.verify_key), provider_manager: ProviderManager = Depends(get_provider_manager)
):
    """获取可用的Gemini模型列表"""
    logger.info("-" * 50 + "list_gemini_models" + "-" * 50)
    logger.info("Handling Gemini models list request")

    provider = await provider_manager.get_next_working_provider()
    logger.info(f"Using API Provider: {provider}")

    models_json = model_service.get_gemini_models(provider)
    model_mapping = {x.get("name", "").split("/", maxsplit=1)[1]: x for x in models_json["models"]}

    # 添加搜索模型
    if model_service.search_models:
        for name in model_service.search_models:
            model = model_mapping.get(name)
            if not model:
                continue

            item = deepcopy(model)
            item["name"] = f"models/{name}-search"
            display_name = f'{item.get("displayName")} For Search'
            item["displayName"] = display_name
            item["description"] = display_name

            models_json["models"].append(item)

    # 添加图像生成模型
    if model_service.image_models:
        for name in model_service.image_models:
            model = model_mapping.get(name)
            if not model:
                continue

            item = deepcopy(model)
            item["name"] = f"models/{name}-image"
            display_name = f'{item.get("displayName")} For Image'
            item["displayName"] = display_name
            item["description"] = display_name

            models_json["models"].append(item)

    return models_json


@router.post("/models/{model_name}:generateContent")
@router_v1beta.post("/models/{model_name}:generateContent")
@RetryHandler(max_retries=3, key_arg="provider")
async def generate_content(
    model_name: str,
    request: GeminiRequest,
    _=Depends(security_service.verify_goog_api_key),
    provider: str = Depends(get_next_working_provider_wrapper),
    api_key: str = Depends(get_key),
    provider_manager: ProviderManager = Depends(get_provider_manager),
):
    """非流式生成内容"""
    logger.info("-" * 50 + "gemini_generate_content" + "-" * 50)
    logger.info(f"Handling Gemini content generation request for model: {model_name}")
    logger.info(f"Request: \n{request.model_dump_json(indent=2)}")
    logger.info(f"Using API Provider: {provider}, API Key: {api_key}")

    if not model_service.check_model_support(model_name):
        raise HTTPException(status_code=400, detail=f"Model {model_name} is not supported")

    try:
        chat_service = GeminiChatService(provider_manager)
        response = await chat_service.generate_content(
            base_url=provider,
            model=model_name,
            request=request,
            api_key=api_key,
        )
        return response
    except Exception as e:
        logger.error(f"Chat completion failed after retries: {str(e)}")
        raise HTTPException(status_code=500, detail="Chat completion failed") from e


@router.post("/models/{model_name}:streamGenerateContent")
@router_v1beta.post("/models/{model_name}:streamGenerateContent")
@RetryHandler(max_retries=3, key_arg="provider")
async def stream_generate_content(
    model_name: str,
    request: GeminiRequest,
    _=Depends(security_service.verify_goog_api_key),
    provider: str = Depends(get_next_working_provider_wrapper),
    api_key: str = Depends(get_key),
    provider_manager: ProviderManager = Depends(get_provider_manager),
):
    """流式生成内容"""
    logger.info("-" * 50 + "gemini_stream_generate_content" + "-" * 50)
    logger.info(f"Handling Gemini streaming content generation for model: {model_name}")
    logger.info(f"Request: \n{request.model_dump_json(indent=2)}")
    logger.info(f"Using API Provider: {provider}, API Key: {api_key}")

    if not model_service.check_model_support(model_name):
        raise HTTPException(status_code=400, detail=f"Model {model_name} is not supported")

    try:
        chat_service = GeminiChatService(provider_manager)
        response_stream = chat_service.stream_generate_content(
            base_url=provider,
            model=model_name,
            request=request,
            api_key=api_key,
        )
        return StreamingResponse(response_stream, media_type="text/event-stream")
    except Exception as e:
        logger.error(f"Streaming request failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Streaming request failed") from e


@router.post("/verify/{provider}")
async def verify_provider(provider: str):
    provider_manager = await get_provider_manager()
    chat_service = GeminiChatService(provider_manager)
    """验证Gemini API接口的有效性"""
    logger.info("-" * 50 + "verify_gemini_provider" + "-" * 50)
    logger.info("Verifying API provider validity")

    try:
        base_url = base64.b64decode(provider).decode(encoding="utf8")
        gemini_requset = GeminiRequest(contents=[GeminiContent(role="user", parts=[{"text": "hi"}])])
        response = chat_service.generate_content(base_url, settings.TEST_MODEL, gemini_requset, get_key())
        if response:
            return JSONResponse({"status": "valid"})
        return JSONResponse({"status": "invalid"})
    except Exception as e:
        logger.error(f"Provider verification failed: {str(e)}")
        return JSONResponse({"status": "invalid", "error": str(e)})

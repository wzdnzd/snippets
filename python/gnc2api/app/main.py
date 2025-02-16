import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import gemini_routes, openai_routes
from app.core.config import settings
from app.core.logger import get_main_logger
from app.core.security import verify_auth_token
from app.services.provider_manager import get_provider_manager_instance

# 配置日志
logger = get_main_logger()

app = FastAPI()

# 配置Jinja2模板
templates = Jinja2Templates(directory="app/templates")

# 配置静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# 创建 ProviderManager 实例
provider_manager = None


@app.on_event("startup")
async def startup_event():
    global provider_manager
    logger.info("Application starting up...")
    try:
        provider_manager = await get_provider_manager_instance(settings.API_PROVIDERS)
        logger.info("ProviderManager initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize ProviderManager: {str(e)}")
        raise


# 添加中间件来处理未经身份验证的请求
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # 允许 gemini_routes 和 openai_routes 中的端点绕过身份验证
    if (
        request.url.path not in ["/", "/auth"]
        and not request.url.path.startswith("/static")
        and not request.url.path.startswith("/gemini")
        and not request.url.path.startswith("/v1")
        and not request.url.path.startswith("/v1beta")
        and not request.url.path.startswith("/health")
        and not request.url.path.startswith("/hf")
    ):
        auth_token = request.cookies.get("auth_token")
        if not auth_token or not verify_auth_token(auth_token):
            logger.warning(f"Unauthorized access attempt to {request.url.path}")
            return RedirectResponse(url="/")
        logger.debug("Request authenticated successfully")
    response = await call_next(request)
    return response


# 配置CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议配置具体的域名
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],  # 明确指定允许的HTTP方法
    allow_headers=["*"],  # 生产环境建议配置具体的请求头
    expose_headers=["*"],  # 允许前端访问的响应头
    max_age=600,  # 预检请求缓存时间(秒)
)

# 包含所有路由
app.include_router(openai_routes.router)
app.include_router(gemini_routes.router)
app.include_router(gemini_routes.router_v1beta)


@app.get("/", response_class=HTMLResponse)
async def auth_page(request: Request):
    return templates.TemplateResponse("auth.html", {"request": request})


@app.post("/auth")
async def authenticate(request: Request):
    try:
        form = await request.form()
        auth_token = form.get("auth_token")
        if not auth_token:
            logger.warning("Authentication attempt with empty token")
            return RedirectResponse(url="/", status_code=302)

        if verify_auth_token(auth_token):
            logger.info("Successful authentication")
            response = RedirectResponse(url="/providers", status_code=302)
            response.set_cookie(key="auth_token", value=auth_token, httponly=True, max_age=3600)
            return response
        logger.warning("Failed authentication attempt with invalid token")
        return RedirectResponse(url="/", status_code=302)
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        return RedirectResponse(url="/", status_code=302)


@app.get("/providers", response_class=HTMLResponse)
async def keys_page(request: Request):
    try:
        auth_token = request.cookies.get("auth_token")
        if not auth_token or not verify_auth_token(auth_token):
            logger.warning("Unauthorized access attempt to providers page")
            return RedirectResponse(url="/", status_code=302)

        providers_status = await provider_manager.get_providers_by_status()
        total = len(providers_status["valid_providers"]) + len(providers_status["invalid_providers"])
        logger.info(f"Providers status retrieved successfully. Total providers: {total}")
        return templates.TemplateResponse(
            "providers_status.html",
            {
                "request": request,
                "valid_providers": providers_status["valid_providers"],
                "invalid_providers": providers_status["invalid_providers"],
                "total": total,
            },
        )
    except Exception as e:
        logger.error(f"Error retrieving providers status: {str(e)}")
        raise


@app.get("/health")
async def health_check(request: Request):
    logger.info("Health check endpoint called")
    return {"status": "healthy"}


if __name__ == "__main__":
    logger.info("Starting application server...")
    uvicorn.run(app, host="0.0.0.0", port=8001)

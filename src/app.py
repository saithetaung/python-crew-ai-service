from contextlib import asynccontextmanager
from fastapi import FastAPI

from src.api.routes.chat import router as chat_router
from src.api.routes.health import router as health_router
from src.core.config import get_settings
from src.core.resources import Resources


@asynccontextmanager
async def lifespan(app: FastAPI):
    resources = Resources(get_settings())
    await resources.start()
    app.state.resources = resources
    try:
        yield
    finally:
        await resources.close()


settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)
app.include_router(health_router, tags=["health"])
app.include_router(chat_router, prefix="/internal/v1", tags=["chat"])

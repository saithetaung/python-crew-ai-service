from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health/live")
async def live():
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request):
    resources = getattr(request.app.state, "resources", None)
    if resources is None or resources.redis is None:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    try:
        await resources.redis.ping()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return {"status": "ready"}

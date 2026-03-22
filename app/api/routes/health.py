from __future__ import annotations

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    settings = get_settings(request)
    if not settings.redis_url:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "ready": True, "note": "redis_optional"},
        )

    redis_client = request.app.state.redis
    if redis_client is None:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "ready": False,
                "dependencies": {"redis": "error"},
                "detail": request.app.state.redis_error or "redis_unavailable",
            },
        )

    try:
        await redis_client.ping()
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "error",
                "ready": False,
                "dependencies": {"redis": "error"},
                "detail": str(exc),
            },
        )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ok", "ready": True, "dependencies": {"redis": "ok"}},
    )

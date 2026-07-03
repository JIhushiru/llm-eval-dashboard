"""Backend/provider availability listing."""

from fastapi import APIRouter

from app import adapters
from app.schemas import BackendInfo

router = APIRouter(prefix="/api", tags=["backends"])


@router.get("/backends", response_model=list[BackendInfo])
async def get_backends() -> list[BackendInfo]:
    return [BackendInfo.model_validate(info) for info in await adapters.list_backends()]

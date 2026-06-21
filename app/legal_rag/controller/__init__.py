from fastapi import APIRouter

from .indexing_controller import router as indexing_router
from .ingestion_controller import router as ingestion_router


router = APIRouter()
router.include_router(ingestion_router)
router.include_router(indexing_router)

__all__ = ["router"]

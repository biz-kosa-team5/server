from fastapi import APIRouter

from .indexing_controller import router as indexing_router
from .ingestion_controller import router as ingestion_router
from .query_controller import router as query_router


router = APIRouter()
router.include_router(ingestion_router)
router.include_router(indexing_router)
router.include_router(query_router)

__all__ = ["router"]

from __future__ import annotations

from fastapi import APIRouter

from .complex_controller import router as complex_router
from .map_controller import router as map_router
from .region_controller import router as region_router
from .search_controller import router as search_router
from .trade_controller import router as trade_router


router = APIRouter(prefix="/api/v1")
router.include_router(map_router)
router.include_router(search_router)
router.include_router(region_router)
router.include_router(complex_router)
router.include_router(trade_router)

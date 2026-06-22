from __future__ import annotations

from fastapi import APIRouter

from .complex.controller import router as complex_router
from .health.controller import router as health_router
from .map.controller import router as map_router
from .region.controller import router as region_router
from .search.controller import router as search_router
from .trade.controller import router as trade_router


router = APIRouter()
router.include_router(health_router)
router.include_router(map_router)
router.include_router(search_router)
router.include_router(region_router)
router.include_router(complex_router)
router.include_router(trade_router)

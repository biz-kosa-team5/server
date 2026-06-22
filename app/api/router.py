from __future__ import annotations

from fastapi import APIRouter

from .chatbot import router as chatbot_router
from .health import router as health_router
from .real_estate import router as real_estate_router
from ..chatbot.features.legal_contract.rag.controller import router as legal_contract_rag_router


router = APIRouter()
router.include_router(health_router)
router.include_router(real_estate_router)
router.include_router(chatbot_router)
router.include_router(legal_contract_rag_router)

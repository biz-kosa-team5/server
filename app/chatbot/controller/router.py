from __future__ import annotations

from fastapi import APIRouter

from app.chatbot.features.legal_contract.rag.controller.router import router as legal_contract_rag_router

from .chatbot_controller import router as chatbot_router


router = APIRouter()
v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(chatbot_router)

router.include_router(v1_router)
router.include_router(legal_contract_rag_router)

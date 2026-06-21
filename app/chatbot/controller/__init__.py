from fastapi import APIRouter

from .chatbot_controller import router as chatbot_router
from .intent_query_controller import router as intent_query_router


router = APIRouter()
router.include_router(intent_query_router)
router.include_router(chatbot_router)

__all__ = ["router"]


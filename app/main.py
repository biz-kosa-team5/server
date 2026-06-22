from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .chatbot.service.classifier import get_intent_classifier
from .database import initialize_database
from .api import router as api_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
  initialize_database()
  get_intent_classifier()
  yield


app = FastAPI(
  title="Gangnam Three-District Real Estate API",
  version="0.1.0",
  lifespan=lifespan,
)
app.include_router(api_router)

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import health
from .chatbot.controller import router as chatbot_router
from .chatbot.service.classifier import get_intent_classifier
from .database import initialize_database
from .real_estate.controller import router as real_estate_router


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
app.add_middleware(
  CORSMiddleware,
  allow_origins=[
    origin.strip()
    for origin in os.getenv(
      "CORS_ALLOW_ORIGINS",
      "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if origin.strip()
  ],
  allow_methods=["*"],
  allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(chatbot_router)
app.include_router(real_estate_router)

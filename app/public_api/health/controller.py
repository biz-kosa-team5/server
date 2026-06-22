from __future__ import annotations

from fastapi import APIRouter

from .dto import HealthResponse
from .service import health


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check() -> dict[str, str]:
  return health()

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv


_ENV_LOADED = False


def load_environment() -> None:
  global _ENV_LOADED
  if _ENV_LOADED:
    return
  if "pytest" in sys.modules:
    _ENV_LOADED = True
    return

  env_path = Path(__file__).resolve().parents[1] / ".env"
  load_dotenv(env_path, override=False)
  _ENV_LOADED = True

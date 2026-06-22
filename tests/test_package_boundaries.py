import inspect
from pathlib import Path

from app import repository
from app.main import app
import app.main as main_module


def test_main_only_composes_routers():
  source = inspect.getsource(main_module)

  assert "@app.get" not in source
  assert "@app.post" not in source
  assert "include_router(api_router)" in source


def test_openapi_keeps_existing_public_paths_registered():
  paths = app.openapi()["paths"]

  expected_paths = {
    "/health",
    "/api/v1/map/regions",
    "/api/v1/map/complexes",
    "/api/v1/search/complexes/suggestions",
    "/api/v1/search/complexes",
    "/api/v1/region",
    "/api/v1/region/{region_id}",
    "/api/v1/region/{region_id}/complexes",
    "/api/v1/detail/{parcel_id}",
    "/api/v1/detail/{parcel_id}/complexes",
    "/api/v1/trade/{parcel_id}",
    "/api/v1/trade/{parcel_id}/trend",
    "/api/v1/complex/{complex_id}",
    "/api/v1/complex/{complex_id}/trades",
    "/api/v1/complex/{complex_id}/trade-trend",
  }

  assert expected_paths.issubset(paths)


def test_http_entry_points_are_grouped_under_api_package():
  assert Path("app/api/health.py").exists()
  assert Path("app/api/real_estate.py").exists()
  assert Path("app/api/chatbot.py").exists()
  assert not Path("app/public_api").exists()


def test_chatbot_flow_packages_own_slot_extraction_and_execution():
  assert Path("app/chatbot/slots/recommendation.py").exists()
  assert Path("app/chatbot/slots/comparison.py").exists()
  assert Path("app/chatbot/flows/recommendation.py").exists()
  assert Path("app/chatbot/flows/comparison.py").exists()
  assert not Path("app/recommendation").exists()
  assert not Path("app/comparison").exists()


def test_only_legal_rag_keeps_dto_package_for_api_contract_models():
  assert Path("app/legal_rag/dto").exists()
  assert not Path("app/dtos").exists()
  assert not Path("app/chatbot/dto").exists()
  assert not Path("app/api/map/dto.py").exists()
  assert not Path("app/api/complex/dto.py").exists()


def test_repository_shim_keeps_legacy_public_functions():
  expected_functions = {
    "health",
    "region_markers",
    "complex_markers",
    "search_suggestions",
    "search_complexes",
    "root_regions",
    "region_detail",
    "region_complexes",
    "detail_by_parcel",
    "detail_by_complex",
    "parcel_complexes",
    "trades_by_parcel",
    "trades_by_complex",
    "trend_by_parcel",
    "trend_by_complex",
    "latest_trade_for_complex",
    "complexes_for_parcel",
    "clamp",
    "optional_float",
  }

  for name in expected_functions:
    assert callable(getattr(repository, name))

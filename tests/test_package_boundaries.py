import inspect
from pathlib import Path

from app import repository
from app.main import app
import app.main as main_module


def test_main_only_composes_routers():
  source = inspect.getsource(main_module)

  assert "@app.get" not in source
  assert "@app.post" not in source
  assert "include_router(health.router)" in source
  assert "include_router(chatbot_router)" in source
  assert "include_router(real_estate_router)" in source


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
    "/api/v1/query",
    "/api/v1/chatbot/query",
    "/api/laws/query",
  }

  assert expected_paths.issubset(paths)


def test_http_entry_points_are_grouped_under_domain_packages():
  assert not Path("app/api").exists()
  assert Path("app/health.py").exists()
  assert Path("app/real_estate/controller/router.py").exists()
  assert Path("app/chatbot/controller/router.py").exists()
  assert not Path("app/public_api").exists()


def test_chatbot_flow_packages_own_slot_extraction_and_execution():
  expected_features = {"simple_lookup", "recommendation", "comparison", "price_trend", "legal_contract"}

  for feature in expected_features:
    assert Path("app/chatbot/features", feature).exists()

  assert Path("app/chatbot/features/recommendation/slots.py").exists()
  assert Path("app/chatbot/features/recommendation/service.py").exists()
  assert Path("app/chatbot/features/comparison/slots.py").exists()
  assert Path("app/chatbot/features/comparison/service.py").exists()
  assert Path("app/chatbot/features/simple_lookup/slots.py").exists()
  assert Path("app/chatbot/features/simple_lookup/dto.py").exists()
  assert Path("app/chatbot/features/simple_lookup/policy.py").exists()
  assert Path("app/chatbot/features/simple_lookup/dao.py").exists()
  assert Path("app/chatbot/features/simple_lookup/service.py").exists()
  assert Path("app/chatbot/features/price_trend/slots.py").exists()
  assert Path("app/chatbot/features/price_trend/dto.py").exists()
  assert Path("app/chatbot/features/price_trend/policy.py").exists()
  assert Path("app/chatbot/features/price_trend/dao.py").exists()
  assert Path("app/chatbot/features/price_trend/service.py").exists()
  assert Path("app/chatbot/service/handler.py").exists()
  assert Path("app/chatbot/service/registry.py").exists()
  assert not Path("app/chatbot/handler").exists()
  assert not Path("app/chatbot/slots").exists()
  assert not Path("app/chatbot/flows").exists()
  assert not Path("app/recommendation").exists()
  assert not Path("app/comparison").exists()
  assert not Path("app/simple_lookup").exists()
  assert not Path("app/h4").exists()


def test_legal_contract_rag_is_nested_under_chatbot_feature():
  assert Path("app/chatbot/features/legal_contract/rag/dto").exists()
  assert Path("app/chatbot/features/legal_contract/rag/service/query_service.py").exists()
  assert Path("app/chatbot/features/legal_contract/rag/service/indexing_service.py").exists()
  assert Path("app/chatbot/features/legal_contract/rag/service/ingestion_service.py").exists()
  assert not Path("app/legal_rag").exists()


def test_infrastructure_packages_are_nested_under_product_boundaries():
  assert Path("app/chatbot/embedding").exists()
  assert Path("app/real_estate/support/poi.py").exists()
  assert Path("app/real_estate/controller").exists()
  assert Path("app/real_estate/service").exists()
  assert Path("app/real_estate/dao").exists()
  assert Path("app/real_estate/dto").exists()
  assert not Path("app/embeddings").exists()
  assert not Path("app/poi").exists()
  assert not Path("app/dtos").exists()
  assert not Path("app/api/map/dto.py").exists()
  assert not Path("app/api/complex/dto.py").exists()


def test_generic_registry_covers_every_intent():
  from app.chatbot.dto import Intent
  from app.chatbot.service.registry import FEATURE_REGISTRY

  assert set(FEATURE_REGISTRY) == set(Intent)


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

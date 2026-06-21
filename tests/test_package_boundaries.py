import inspect

from app import repository
from app.main import app
import app.main as main_module


def test_main_only_composes_routers():
  source = inspect.getsource(main_module)

  assert "@app.get" not in source
  assert "@app.post" not in source
  assert "include_router(public_api_router)" in source


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

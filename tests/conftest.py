from __future__ import annotations

import sys
from pathlib import Path

import pytest

import app.legacy_api as legacy_module


ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)

if root_str not in sys.path:
    sys.path.insert(0, root_str)


@pytest.fixture(autouse=True)
def _clear_response_caches() -> None:
    legacy_module._search_response_cache.clear()
    legacy_module._hot_response_cache.clear()
    yield
    legacy_module._search_response_cache.clear()
    legacy_module._hot_response_cache.clear()

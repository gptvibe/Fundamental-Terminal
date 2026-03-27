from __future__ import annotations

import sys
from pathlib import Path

import pytest

import app.main as main_module


ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)

if root_str not in sys.path:
    sys.path.insert(0, root_str)


@pytest.fixture(autouse=True)
def _clear_response_caches() -> None:
    main_module._search_response_cache.clear()
    main_module._hot_response_cache.clear()
    yield
    main_module._search_response_cache.clear()
    main_module._hot_response_cache.clear()
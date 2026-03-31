from __future__ import annotations

import importlib
import inspect
from functools import wraps
from typing import Any

from app.api.handlers import _shared


def route_handler(name: str):
    target = getattr(_shared, name)
    if inspect.iscoroutinefunction(target):
        @wraps(target)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            main_module = importlib.import_module("app.main")
            return await getattr(main_module, name)(*args, **kwargs)

        return async_wrapper

    @wraps(target)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        main_module = importlib.import_module("app.main")
        return getattr(main_module, name)(*args, **kwargs)

    return sync_wrapper
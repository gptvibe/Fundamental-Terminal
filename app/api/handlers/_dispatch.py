from __future__ import annotations

import importlib
import inspect
from functools import wraps
from typing import Any

from app.api.handlers import _shared


def _should_call_wrapped_target(target: Any, exported: Any) -> bool:
    wrapped = getattr(target, "__wrapped__", None)
    if wrapped is None:
        return False
    if not inspect.iscoroutinefunction(target) or inspect.iscoroutinefunction(exported):
        return False
    if not inspect.isfunction(wrapped) or not inspect.isfunction(exported):
        return False
    return exported.__code__ is wrapped.__code__


def route_handler(name: str):
    target = getattr(_shared, name)
    target_signature = inspect.signature(target)
    if inspect.iscoroutinefunction(target):
        @wraps(target)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            main_module = importlib.import_module("app.main")
            exported = getattr(main_module, name)
            result = target(*args, **kwargs) if _should_call_wrapped_target(target, exported) else exported(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        async_wrapper.__signature__ = target_signature  # type: ignore[attr-defined]
        return async_wrapper

    @wraps(target)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        main_module = importlib.import_module("app.main")
        return getattr(main_module, name)(*args, **kwargs)

    sync_wrapper.__signature__ = target_signature  # type: ignore[attr-defined]
    return sync_wrapper
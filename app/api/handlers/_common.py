from __future__ import annotations

import inspect
import sys
import typing
from functools import wraps
from typing import Any, Callable, TypeVar, cast


FunctionT = TypeVar("FunctionT", bound=Callable[..., Any])


def _legacy_module() -> Any:
    legacy_module = sys.modules.get("app.legacy_api")
    if legacy_module is None:
        import app.legacy_api as legacy_module

    return legacy_module


def main_bound(function: FunctionT) -> FunctionT:
    signature = inspect.signature(function)
    session_parameter = signature.parameters.get("session")
    dependency_marker = None if session_parameter is None else session_parameter.default
    has_session_dependency = getattr(getattr(dependency_marker, "dependency", None), "__name__", None) == "get_db_session"

    if inspect.iscoroutinefunction(function):
        @wraps(function)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            legacy_module = _legacy_module()
            rebound = legacy_module.clone_legacy_function(function)
            result = rebound(*args, **kwargs)
            if inspect.isawaitable(result):
                return await result
            return result

        async_wrapper.__signature__ = signature  # type: ignore[attr-defined]
        return cast(FunctionT, async_wrapper)

    if has_session_dependency:
        parameters = [parameter for parameter in signature.parameters.values() if parameter.name != "session"]

        @wraps(function)
        async def session_wrapper(*args: Any, **kwargs: Any) -> Any:
            legacy_module = _legacy_module()
            shared_module = sys.modules.get("app.api.handlers._shared")
            if shared_module is None:
                raise RuntimeError("app.api.handlers._shared must be loaded before invoking split handlers")
            async with shared_module._session_scope() as session:
                def invoke(sync_session: Any) -> Any:
                    rebound = legacy_module.clone_legacy_function(function)
                    with legacy_module.bind_request_sync_session(sync_session):
                        return rebound(*args, **kwargs, session=sync_session)

                return await shared_module._run_with_session_binding(session, invoke)

        session_wrapper.__signature__ = signature.replace(parameters=parameters)  # type: ignore[attr-defined]
        try:
            resolved_annotations = typing.get_type_hints(function, include_extras=True)
        except Exception:
            resolved_annotations = dict(getattr(function, "__annotations__", {}))
        resolved_annotations.pop("session", None)
        session_wrapper.__annotations__ = resolved_annotations
        return cast(FunctionT, session_wrapper)

    @wraps(function)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        legacy_module = _legacy_module()
        rebound = legacy_module.clone_legacy_function(function)
        return rebound(*args, **kwargs)

    sync_wrapper.__signature__ = signature  # type: ignore[attr-defined]
    return cast(FunctionT, sync_wrapper)


__all__ = ["main_bound"]

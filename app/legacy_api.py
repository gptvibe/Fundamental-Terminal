from __future__ import annotations

import inspect
import sys
from types import FunctionType
from typing import Any, MutableMapping

from app.api.handlers import _shared as _legacy_api


def clone_legacy_function(
    function: Any,
    namespace: MutableMapping[str, Any] | None = None,
    *,
    module_name: str | None = None,
) -> Any:
    if namespace is None:
        main_module = sys.modules.get("app.main")
        if main_module is not None:
            target_globals = vars(main_module)
            for name, value in function.__globals__.items():
                target_globals.setdefault(name, value)
        else:
            target_globals = function.__globals__
    else:
        target_globals = namespace
        for name, value in function.__globals__.items():
            target_globals.setdefault(name, value)
    cloned = FunctionType(
        function.__code__,
        target_globals,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    cloned.__kwdefaults__ = getattr(function, "__kwdefaults__", None)
    cloned.__annotations__ = dict(getattr(function, "__annotations__", {}))
    cloned.__doc__ = function.__doc__
    cloned.__module__ = module_name or __name__
    cloned.__qualname__ = function.__qualname__
    cloned.__dict__.update(getattr(function, "__dict__", {}))
    return cloned


def _export_legacy_api(
    namespace: MutableMapping[str, Any] | None = None,
    *,
    reserved_names: set[str] | None = None,
    module_name: str | None = None,
) -> None:
    target = globals() if namespace is None else namespace
    reserved = set(target) if reserved_names is None else set(reserved_names)

    for name, value in vars(_legacy_api).items():
        if name.startswith("__") or name in reserved:
            continue
        if inspect.isfunction(value) and getattr(value, "__module__", None) == _legacy_api.__name__:
            export_value = value
            wrapped = getattr(value, "__wrapped__", None)
            if inspect.iscoroutinefunction(value) and inspect.isfunction(wrapped) and not inspect.iscoroutinefunction(wrapped):
                export_value = wrapped
            target[name] = clone_legacy_function(
                export_value,
                namespace=target,
                module_name=module_name or __name__,
            )
            continue
        if inspect.iscoroutinefunction(value):
            wrapped = getattr(value, "__wrapped__", None)
            if inspect.isfunction(wrapped) and not inspect.iscoroutinefunction(wrapped):
                target[name] = clone_legacy_function(
                    wrapped,
                    namespace=target,
                    module_name=module_name or __name__,
                )
                continue
        target[name] = value


_export_legacy_api()


def __getattr__(name: str) -> Any:
    return getattr(_legacy_api, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(dir(_legacy_api)))

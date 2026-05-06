"""Backward-compatible SEC service module.

The implementation lives in :mod:`app.services.sec.refresh_orchestrator`.
Expose that module object directly so existing imports, monkeypatches, and
runtime attribute updates keep affecting the implementation globals.
"""

from __future__ import annotations

import sys
from types import ModuleType

from app.services.sec import refresh_orchestrator as _refresh_orchestrator


if __name__ == "__main__":
    raise SystemExit(_refresh_orchestrator.worker_main())


class _SecEdgarCompatibilityModule(ModuleType):
    def __getattr__(self, name: str):
        return getattr(_refresh_orchestrator, name)

    def __setattr__(self, name: str, value):
        if name.startswith("__") or name == "_refresh_orchestrator":
            super().__setattr__(name, value)
            return
        setattr(_refresh_orchestrator, name, value)

    def __delattr__(self, name: str) -> None:
        if name.startswith("__") or name == "_refresh_orchestrator":
            super().__delattr__(name)
            return
        delattr(_refresh_orchestrator, name)

    def __dir__(self) -> list[str]:
        return sorted(set(super().__dir__()) | set(dir(_refresh_orchestrator)))


__all__ = [name for name in dir(_refresh_orchestrator) if not name.startswith("__")]
sys.modules[__name__].__class__ = _SecEdgarCompatibilityModule

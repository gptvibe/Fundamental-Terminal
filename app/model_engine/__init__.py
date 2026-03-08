from __future__ import annotations

from typing import Any


def precompute_core_models(*args: Any, **kwargs: Any):
    from app.model_engine.engine import precompute_core_models as _precompute_core_models

    return _precompute_core_models(*args, **kwargs)


def run_model_job(*args: Any, **kwargs: Any):
    from app.model_engine.engine import run_model_job as _run_model_job

    return _run_model_job(*args, **kwargs)


__all__ = ["precompute_core_models", "run_model_job"]

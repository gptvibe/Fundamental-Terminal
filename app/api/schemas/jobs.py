from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.api.schemas.common import RefreshState


class RefreshQueuedResponse(BaseModel):
    status: Literal["queued"]
    ticker: str
    force: bool
    refresh: RefreshState

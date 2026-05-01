from __future__ import annotations

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.services.refresh_state as refresh_state


def test_after_commit_hot_cache_invalidation_logs_and_continues(monkeypatch, caplog) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    calls: list[tuple[str | None, str, str | None]] = []

    def _invalidate_sync(*, ticker: str | None, dataset: str, schema_version: str | None):
        calls.append((ticker, dataset, schema_version))
        if dataset == "financials":
            raise RuntimeError("boom")
        return {"local": 1, "remote": 0, "tags": ["dataset"]}

    monkeypatch.setattr(refresh_state.shared_hot_response_cache, "invalidate_sync", _invalidate_sync)
    caplog.set_level(logging.ERROR, logger=refresh_state.logger.name)

    with session_factory() as session:
        session.info[refresh_state._SESSION_INVALIDATION_KEY] = [
            refresh_state._PendingHotCacheInvalidation(
                ticker="AAPL",
                dataset="financials",
                schema_version="v1",
            ),
            refresh_state._PendingHotCacheInvalidation(
                ticker="AAPL",
                dataset="prices",
                schema_version="v2",
            ),
        ]
        session.execute(text("SELECT 1"))
        session.commit()

    assert calls == [
        ("AAPL", "financials", "v1"),
        ("AAPL", "prices", "v2"),
    ]
    assert "Failed hot-cache invalidation after commit" in caplog.text
    assert "dataset=financials" in caplog.text
    assert "RuntimeError: boom" in caplog.text

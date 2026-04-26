from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db import get_db_session
from app.main import app
from app.models.research_workspace import ResearchWorkspace


@pytest.fixture()
async def research_workspace_client() -> AsyncGenerator[TestClient, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as connection:
        await connection.run_sync(ResearchWorkspace.__table__.create)

    async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_get_db_session

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.anyio
async def test_research_workspace_crud_round_trip(research_workspace_client: TestClient) -> None:
    save_response = research_workspace_client.post(
        "/api/research-workspace/save?workspace_key=team-alpha",
        json={
            "saved_companies": [
                {
                    "ticker": "aapl",
                    "name": "Apple",
                    "sector": "Technology",
                    "saved_at": "2026-04-26T00:00:00Z",
                    "updated_at": "2026-04-26T00:00:00Z",
                }
            ],
            "notes": [
                {
                    "ticker": "aapl",
                    "name": "Apple",
                    "sector": "Technology",
                    "note": "Margin durability still underpriced.",
                    "updated_at": "2026-04-26T00:00:00Z",
                }
            ],
            "pinned_metrics": [
                {
                    "metric_key": "roic",
                    "label": "ROIC",
                    "updated_at": "2026-04-26T00:00:00Z",
                }
            ],
            "pinned_charts": [
                {
                    "chart_key": "revenue-trend",
                    "label": "Revenue Trend",
                    "updated_at": "2026-04-26T00:00:00Z",
                }
            ],
            "compare_baskets": [
                {
                    "basket_id": "mega-cap-tech",
                    "name": "Mega Cap Tech",
                    "tickers": ["AAPL", "MSFT"],
                    "updated_at": "2026-04-26T00:00:00Z",
                }
            ],
            "memo_draft": "Working thesis draft.",
        },
    )
    assert save_response.status_code == 200

    payload = save_response.json()
    assert payload["workspace_key"] == "team-alpha"
    assert payload["saved_companies"][0]["ticker"] == "AAPL"
    assert payload["notes"][0]["ticker"] == "AAPL"
    assert payload["pinned_metrics"][0]["metric_key"] == "roic"
    assert payload["pinned_charts"][0]["chart_key"] == "revenue-trend"
    assert payload["compare_baskets"][0]["tickers"] == ["AAPL", "MSFT"]
    assert payload["memo_draft"] == "Working thesis draft."

    get_response = research_workspace_client.get("/api/research-workspace?workspace_key=team-alpha")
    assert get_response.status_code == 200
    read_payload = get_response.json()
    assert read_payload["workspace_key"] == "team-alpha"
    assert len(read_payload["saved_companies"]) == 1
    assert len(read_payload["notes"]) == 1

    delete_response = research_workspace_client.post("/api/research-workspace/delete?workspace_key=team-alpha")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted"] is True

    get_after_delete = research_workspace_client.get("/api/research-workspace?workspace_key=team-alpha")
    assert get_after_delete.status_code == 200
    cleared = get_after_delete.json()
    assert cleared["saved_companies"] == []
    assert cleared["notes"] == []
    assert cleared["memo_draft"] is None


@pytest.mark.anyio
async def test_research_workspace_validation_rejects_invalid_ticker(research_workspace_client: TestClient) -> None:
    response = research_workspace_client.post(
        "/api/research-workspace/save",
        json={
            "saved_companies": [
                {
                    "ticker": "",
                    "name": "Broken",
                    "sector": None,
                    "saved_at": "2026-04-26T00:00:00Z",
                    "updated_at": "2026-04-26T00:00:00Z",
                }
            ],
            "notes": [],
            "pinned_metrics": [],
            "pinned_charts": [],
            "compare_baskets": [],
            "memo_draft": None,
        },
    )
    assert response.status_code == 422


@pytest.mark.anyio
async def test_research_workspace_import_local_merge_preserves_existing_data(research_workspace_client: TestClient) -> None:
    seed = research_workspace_client.post(
        "/api/research-workspace/save?workspace_key=portable",
        json={
            "saved_companies": [
                {
                    "ticker": "MSFT",
                    "name": "Microsoft",
                    "sector": "Technology",
                    "saved_at": "2026-04-01T00:00:00Z",
                    "updated_at": "2026-04-01T00:00:00Z",
                }
            ],
            "notes": [],
            "pinned_metrics": [],
            "pinned_charts": [],
            "compare_baskets": [],
            "memo_draft": None,
        },
    )
    assert seed.status_code == 200

    merged = research_workspace_client.post(
        "/api/research-workspace/import-local?workspace_key=portable",
        json={
            "watchlist": [
                {"ticker": "aapl", "name": "Apple", "sector": "Technology", "savedAt": "2026-04-20T00:00:00Z"}
            ],
            "notes": {
                "AAPL": {
                    "ticker": "aapl",
                    "name": "Apple",
                    "sector": "Technology",
                    "note": "Imported from local storage",
                    "updatedAt": "2026-04-22T00:00:00Z",
                }
            },
            "mode": "merge",
        },
    )
    assert merged.status_code == 200
    merged_payload = merged.json()
    assert {item["ticker"] for item in merged_payload["saved_companies"]} == {"AAPL", "MSFT"}
    assert merged_payload["notes"][0]["ticker"] == "AAPL"

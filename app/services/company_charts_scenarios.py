from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.contracts.company_charts import (
    CompanyChartsScenarioCloneRequest,
    CompanyChartsScenarioPayload,
    CompanyChartsScenarioUpsertRequest,
)
from app.models.company_charts_scenario import CompanyChartsScenario


def list_company_charts_scenarios(
    session: Session,
    *,
    company_id: int,
    viewer_key: str | None,
) -> list[CompanyChartsScenario]:
    statement = select(CompanyChartsScenario).where(CompanyChartsScenario.company_id == company_id)
    if viewer_key:
        statement = statement.where(
            or_(
                CompanyChartsScenario.visibility == "public",
                CompanyChartsScenario.owner_key == viewer_key,
            )
        )
    else:
        statement = statement.where(CompanyChartsScenario.visibility == "public")

    statement = statement.order_by(CompanyChartsScenario.updated_at.desc(), CompanyChartsScenario.created_at.desc())
    return list(session.execute(statement).scalars().all())


def get_company_charts_scenario(
    session: Session,
    *,
    company_id: int,
    scenario_id: str,
) -> CompanyChartsScenario | None:
    statement = select(CompanyChartsScenario).where(
        CompanyChartsScenario.company_id == company_id,
        CompanyChartsScenario.id == scenario_id,
    )
    return session.execute(statement).scalar_one_or_none()


def viewer_can_access_company_charts_scenario(
    scenario: CompanyChartsScenario,
    *,
    viewer_key: str | None,
) -> bool:
    return scenario.visibility == "public" or bool(viewer_key and scenario.owner_key == viewer_key)


def viewer_can_edit_company_charts_scenario(
    scenario: CompanyChartsScenario,
    *,
    viewer_key: str | None,
) -> bool:
    return bool(viewer_key and scenario.owner_key == viewer_key)


def create_company_charts_scenario(
    session: Session,
    *,
    company_id: int,
    payload: CompanyChartsScenarioUpsertRequest,
    viewer_key: str | None,
) -> CompanyChartsScenario:
    now = datetime.now(timezone.utc)
    scenario = CompanyChartsScenario(
        id=str(uuid4()),
        company_id=company_id,
        owner_key=viewer_key,
        name=payload.name,
        visibility=payload.visibility,
        source=payload.source,
        schema_version=1,
        override_count=max(0, payload.override_count),
        forecast_year=payload.forecast_year,
        as_of=payload.as_of,
        overrides={str(key): float(value) for key, value in payload.overrides.items()},
        metrics=[metric.model_dump(mode="json") for metric in payload.metrics],
        cloned_from_scenario_id=None,
        created_at=now,
        updated_at=now,
    )
    session.add(scenario)
    session.flush()
    return scenario


def update_company_charts_scenario(
    session: Session,
    *,
    scenario: CompanyChartsScenario,
    payload: CompanyChartsScenarioUpsertRequest,
) -> CompanyChartsScenario:
    scenario.name = payload.name
    scenario.visibility = payload.visibility
    scenario.source = payload.source
    scenario.schema_version = 1
    scenario.override_count = max(0, payload.override_count)
    scenario.forecast_year = payload.forecast_year
    scenario.as_of = payload.as_of
    scenario.overrides = {str(key): float(value) for key, value in payload.overrides.items()}
    scenario.metrics = [metric.model_dump(mode="json") for metric in payload.metrics]
    scenario.updated_at = datetime.now(timezone.utc)
    session.add(scenario)
    session.flush()
    return scenario


def clone_company_charts_scenario(
    session: Session,
    *,
    company_id: int,
    source_scenario: CompanyChartsScenario,
    payload: CompanyChartsScenarioCloneRequest,
    viewer_key: str | None,
) -> CompanyChartsScenario:
    now = datetime.now(timezone.utc)
    scenario = CompanyChartsScenario(
        id=str(uuid4()),
        company_id=company_id,
        owner_key=viewer_key,
        name=payload.name or f"{source_scenario.name} Copy",
        visibility=payload.visibility or source_scenario.visibility,
        source=source_scenario.source,
        schema_version=source_scenario.schema_version,
        override_count=source_scenario.override_count,
        forecast_year=source_scenario.forecast_year,
        as_of=source_scenario.as_of,
        overrides=dict(source_scenario.overrides or {}),
        metrics=list(source_scenario.metrics or []),
        cloned_from_scenario_id=source_scenario.id,
        created_at=now,
        updated_at=now,
    )
    session.add(scenario)
    session.flush()
    return scenario


def serialize_company_charts_scenario(
    scenario: CompanyChartsScenario,
    *,
    ticker: str,
    viewer_key: str | None,
) -> CompanyChartsScenarioPayload:
    return CompanyChartsScenarioPayload(
        schema_version=scenario.schema_version,
        id=scenario.id,
        ticker=ticker,
        name=scenario.name,
        visibility="public" if scenario.visibility == "public" else "private",
        source="user_scenario" if scenario.source == "user_scenario" else "sec_base_forecast",
        override_count=scenario.override_count,
        forecast_year=scenario.forecast_year,
        as_of=scenario.as_of,
        overrides={str(key): float(value) for key, value in (scenario.overrides or {}).items()},
        metrics=list(scenario.metrics or []),
        share_path=_build_company_charts_scenario_share_path(ticker, scenario.id),
        cloned_from_scenario_id=scenario.cloned_from_scenario_id,
        owned_by_viewer=bool(viewer_key and scenario.owner_key == viewer_key),
        editable=viewer_can_edit_company_charts_scenario(scenario, viewer_key=viewer_key),
        created_at=scenario.created_at,
        updated_at=scenario.updated_at,
    )


def _build_company_charts_scenario_share_path(ticker: str, scenario_id: str) -> str:
    return f"/company/{quote(ticker)}/charts?mode=studio&scenario={quote(scenario_id)}"

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects import postgresql

import app.services.cache_queries as cache_queries


class _ScalarResult:
    def __init__(self, values):
        self._values = list(values)

    def __iter__(self):
        return iter(self._values)

    def all(self):
        return list(self._values)


class _Result:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)

    def scalars(self):
        return _ScalarResult(self._values)

    def scalar_one_or_none(self):
        if not self._values:
            return None
        if len(self._values) != 1:
            raise AssertionError("expected at most one scalar row")
        return self._values[0]


class _CaptureSession:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return _Result([])


class _LatestChecksSession:
    def __init__(self):
        self.statements = []
        self._call_count = 0

    def execute(self, statement):
        self.statements.append(statement)
        self._call_count += 1
        if self._call_count == 1:
            return _Result(
                [
                    (7, datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)),
                    (8, datetime(2026, 4, 9, 8, 30, tzinfo=timezone.utc)),
                ]
            )
        if self._call_count == 2:
            return _Result(
                [
                    (7, datetime(2026, 4, 11, 9, 15, tzinfo=timezone.utc)),
                    (9, datetime(2026, 4, 11, 10, 45, tzinfo=timezone.utc)),
                ]
            )
        raise AssertionError("unexpected query execution")


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_search_company_snapshots_uses_company_only_match_query() -> None:
    session = _CaptureSession()

    results = cache_queries.search_company_snapshots(
        session,
        "apple",
        allow_contains_fallback=False,
    )

    assert results == []
    assert len(session.statements) == 1

    sql = _compile(session.statements[0])
    assert "FROM companies" in sql
    assert "dataset_refresh_state" not in sql
    assert "financial_statements" not in sql
    assert "lower(companies.name) LIKE" in sql
    assert " ILIKE " not in sql


def test_load_latest_checks_by_company_ids_prefers_refresh_state() -> None:
    session = _LatestChecksSession()

    latest_checks = cache_queries._load_latest_checks_by_company_ids(session, [7, 8, 9])

    assert latest_checks == {
        7: datetime(2026, 4, 11, 9, 15, tzinfo=timezone.utc),
        8: datetime(2026, 4, 9, 8, 30, tzinfo=timezone.utc),
        9: datetime(2026, 4, 11, 10, 45, tzinfo=timezone.utc),
    }

    assert len(session.statements) == 2
    assert "financial_statements" in _compile(session.statements[0])
    assert "dataset_refresh_state" in _compile(session.statements[1])
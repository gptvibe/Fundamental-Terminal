from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

import app.services.cache_queries as cache_queries
import app.services.market_data as market_data


class _Result:
    def __init__(self, values):
        self._values = list(values)

    def __iter__(self):
        return iter(self._values)

    def scalar_one_or_none(self):
        if not self._values:
            return None
        if len(self._values) != 1:
            raise AssertionError("expected at most one scalar row")
        return self._values[0]

    def scalars(self):
        return self


class _CaptureSession:
    def __init__(self, values=None):
        self.statements = []
        self._values = [] if values is None else list(values)

    def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._values)


def _compile(statement) -> str:
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_latest_trade_date_uses_desc_limit_query_shape() -> None:
    session = _CaptureSession([date(2026, 4, 22)])

    latest = market_data.get_company_latest_trade_date(session, 17)

    assert latest == date(2026, 4, 22)
    sql = _compile(session.statements[0])
    assert 'SELECT price_history.trade_date' in sql
    assert 'max(price_history.trade_date)' not in sql.lower()
    assert 'WHERE price_history.company_id = 17' in sql
    assert 'ORDER BY price_history.trade_date DESC' in sql
    assert 'LIMIT 1' in sql


def test_price_last_checked_uses_desc_limit_and_marks_refresh_state(monkeypatch) -> None:
    checked_at = datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc)
    session = _CaptureSession([checked_at])
    marks: list[tuple[int, str, datetime, bool]] = []

    monkeypatch.setattr(market_data, 'cache_state_for_dataset', lambda *_args, **_kwargs: (None, 'missing'))
    monkeypatch.setattr(
        market_data,
        'mark_dataset_checked',
        lambda _session, company_id, dataset, *, checked_at, success, **_kwargs: marks.append((company_id, dataset, checked_at, success)),
    )

    latest = market_data.get_company_price_last_checked(session, 23)

    assert latest == checked_at
    assert marks == [(23, 'prices', checked_at, True)]
    sql = _compile(session.statements[0])
    assert 'SELECT price_history.last_checked' in sql
    assert 'max(price_history.last_checked)' not in sql.lower()
    assert 'WHERE price_history.company_id = 23' in sql
    assert 'ORDER BY price_history.last_checked DESC' in sql
    assert 'LIMIT 1' in sql


def test_price_history_tail_projects_only_needed_columns() -> None:
    session = _CaptureSession([(date(2026, 4, 20), 101.5, 1200), (date(2026, 4, 21), 102.0, None)])

    bars = market_data.get_company_price_history_tail(session, 5, start_date=date(2026, 4, 20))

    assert bars == [
        market_data.PriceBar(trade_date=date(2026, 4, 20), close=101.5, volume=1200),
        market_data.PriceBar(trade_date=date(2026, 4, 21), close=102.0, volume=None),
    ]
    sql = _compile(session.statements[0])
    assert 'SELECT price_history.trade_date, price_history.close, price_history.volume' in sql
    assert 'price_history.source = ' in sql
    assert 'ORDER BY price_history.trade_date ASC' in sql


def test_price_history_latest_query_shape_uses_desc_limit() -> None:
    row_a = SimpleNamespace(id=10, trade_date=date(2026, 4, 20), close=101.5, volume=1200)
    row_b = SimpleNamespace(id=11, trade_date=date(2026, 4, 21), close=102.0, volume=1300)
    session = _CaptureSession([row_b, row_a])

    rows = market_data.get_company_price_history_latest(session, 9, limit=2)

    assert [row.trade_date for row in rows] == [date(2026, 4, 20), date(2026, 4, 21)]
    sql = _compile(session.statements[0])
    assert 'WHERE price_history.company_id = 9' in sql
    assert 'ORDER BY price_history.trade_date DESC' in sql
    assert 'LIMIT 2' in sql


def test_price_history_between_query_shape_uses_date_bounds() -> None:
    row = SimpleNamespace(id=12, trade_date=date(2026, 4, 21), close=102.0, volume=1300)
    session = _CaptureSession([row])

    rows = market_data.get_company_price_history_between(
        session,
        14,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 4, 30),
    )

    assert len(rows) == 1
    sql = _compile(session.statements[0])
    assert 'WHERE price_history.company_id = 14' in sql
    assert 'price_history.trade_date >= ' in sql
    assert 'price_history.trade_date <= ' in sql
    assert 'ORDER BY price_history.trade_date ASC' in sql


def test_decimate_price_rows_handles_empty_sparse_duplicates_and_long_history() -> None:
    assert market_data._decimate_price_rows([], target_points=100) == []

    sparse = [
        SimpleNamespace(id=1, trade_date=date(2026, 1, 1)),
        SimpleNamespace(id=2, trade_date=date(2026, 2, 1)),
        SimpleNamespace(id=3, trade_date=date(2026, 3, 1)),
    ]
    assert market_data._decimate_price_rows(sparse, target_points=10) == sparse

    duplicate_dates = [
        SimpleNamespace(id=1, trade_date=date(2026, 1, 1)),
        SimpleNamespace(id=2, trade_date=date(2026, 1, 1)),
        SimpleNamespace(id=3, trade_date=date(2026, 1, 2)),
    ]
    deduped = market_data._decimate_price_rows(duplicate_dates, target_points=2)
    assert [row.trade_date for row in deduped] == [date(2026, 1, 1), date(2026, 1, 2)]
    assert deduped[0].id == 2

    long_history = [
        SimpleNamespace(id=index + 1, trade_date=date(2020, 1, 1).fromordinal(date(2020, 1, 1).toordinal() + index))
        for index in range(1000)
    ]
    decimated = market_data._decimate_price_rows(long_history, target_points=120)
    assert len(decimated) <= 120
    assert decimated[0].trade_date == long_history[0].trade_date
    assert decimated[-1].trade_date == long_history[-1].trade_date


def test_price_cache_status_uses_desc_limit_when_refresh_state_missing(monkeypatch) -> None:
    checked_at = datetime.now(timezone.utc)
    session = _CaptureSession([checked_at])
    marks: list[tuple[int, str, datetime, bool]] = []

    monkeypatch.setattr(cache_queries, 'cache_state_for_dataset', lambda *_args, **_kwargs: (None, 'missing'))
    monkeypatch.setattr(
        cache_queries,
        'mark_dataset_checked',
        lambda _session, company_id, dataset, *, checked_at, success, **_kwargs: marks.append((company_id, dataset, checked_at, success)),
    )

    status = cache_queries.get_company_price_cache_status(session, 11)

    assert status == (checked_at, 'fresh')
    assert marks == [(11, 'prices', checked_at, True)]
    sql = _compile(session.statements[0])
    assert 'SELECT price_history.last_checked' in sql
    assert 'max(price_history.last_checked)' not in sql.lower()
    assert 'WHERE price_history.company_id = 11' in sql
    assert 'ORDER BY price_history.last_checked DESC' in sql
    assert 'LIMIT 1' in sql
from __future__ import annotations

from types import SimpleNamespace

from app.services.company_research_brief import _statement_value


def test_statement_value_supports_legacy_weighted_share_alias():
    statement = SimpleNamespace(data={"weighted_average_diluted_shares": 388900000})

    assert _statement_value(statement, "weighted_average_shares_diluted") == 388900000
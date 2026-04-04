from __future__ import annotations

import pytest

from app.services.sec_edgar import EdgarClient


def test_resolve_company_falls_back_to_browse_edgar_atom(monkeypatch) -> None:
    client = EdgarClient()
    try:
        monkeypatch.setattr(client, "get_company_tickers", lambda: [])

        atom_payload = """<?xml version=\"1.0\" encoding=\"ISO-8859-1\"?>
<feed xmlns=\"http://www.w3.org/2005/Atom\">
  <company-info>
    <cik>0001509589</cik>
    <conformed-name>CIVITAS RESOURCES, INC.</conformed-name>
  </company-info>
</feed>
"""
        monkeypatch.setattr(client, "_get_text", lambda _url: atom_payload)

        identity = client.resolve_company("CIVI")

        assert identity.cik == "0001509589"
        assert identity.ticker == "CIVI"
        assert identity.name == "CIVITAS RESOURCES, INC."
    finally:
        client.close()


def test_resolve_company_falls_back_to_browse_edgar_html(monkeypatch) -> None:
    client = EdgarClient()
    try:
        monkeypatch.setattr(client, "get_company_tickers", lambda: [])

        html_payload = """
<html>
  <body>
    <span class=\"companyName\">Some Energy Corp CIK#: 0001234567 (see all company filings)</span>
  </body>
</html>
"""
        monkeypatch.setattr(client, "_get_text", lambda _url: html_payload)

        identity = client.resolve_company("SOME")

        assert identity.cik == "0001234567"
        assert identity.ticker == "SOME"
        assert identity.name == "Some Energy Corp"
    finally:
        client.close()


def test_resolve_company_raises_when_browse_edgar_has_no_match(monkeypatch) -> None:
    client = EdgarClient()
    try:
        monkeypatch.setattr(client, "get_company_tickers", lambda: [])
        monkeypatch.setattr(client, "_get_text", lambda _url: "No matching Ticker Symbol.")

        with pytest.raises(ValueError, match="Unable to resolve SEC company for 'VTLE'"):
            client.resolve_company("VTLE")
    finally:
        client.close()

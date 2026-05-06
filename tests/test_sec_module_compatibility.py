from __future__ import annotations

import importlib


def test_sec_edgar_module_is_refresh_orchestrator() -> None:
    old_module = importlib.import_module("app.services.sec_edgar")
    new_module = importlib.import_module("app.services.sec.refresh_orchestrator")

    assert old_module.EdgarClient is new_module.EdgarClient
    assert old_module.EdgarIngestionService is new_module.EdgarIngestionService
    assert old_module.worker_main is new_module.worker_main


def test_sec_facade_modules_reexport_expected_symbols() -> None:
    orchestrator = importlib.import_module("app.services.sec.refresh_orchestrator")
    client = importlib.import_module("app.services.sec.client")
    submissions = importlib.import_module("app.services.sec.submissions")
    ownership = importlib.import_module("app.services.sec.ownership")
    normalizer = importlib.import_module("app.services.sec.xbrl_normalizer")

    assert client.EdgarClient is orchestrator.EdgarClient
    assert submissions.FilingMetadata is orchestrator.FilingMetadata
    assert ownership._parse_form4_transactions is orchestrator._parse_form4_transactions
    assert ownership._parse_form144_filings is orchestrator._parse_form144_filings
    assert normalizer.EdgarNormalizer is orchestrator.EdgarNormalizer

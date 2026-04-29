from __future__ import annotations

from contextlib import contextmanager

import app.macro_worker as macro_worker


@contextmanager
def _noop_observe_worker_job(**_kwargs):
    yield


def test_macro_worker_logs_exception_and_returns_failure(monkeypatch, caplog):
    def _raise_failure() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(macro_worker, "observe_worker_job", _noop_observe_worker_job)
    monkeypatch.setattr(macro_worker, "run_market_context_refresh_job", _raise_failure)

    caplog.set_level("ERROR", logger=macro_worker.logger.name)

    result = macro_worker.macro_worker_main()

    assert result == 1
    assert "Macro worker failed" in caplog.text
    assert "Traceback" in caplog.text
    assert "RuntimeError: boom" in caplog.text

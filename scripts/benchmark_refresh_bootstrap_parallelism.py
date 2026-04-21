from __future__ import annotations

import argparse
import json
import statistics
import time
from types import SimpleNamespace
from typing import Any

import app.services.sec_edgar as sec_edgar


def benchmark_refresh_bootstrap_parallelism(*, rounds: int = 20) -> dict[str, Any]:
    serial = _run_scenario(rounds=rounds, refresh_aux_io_max_workers=1)
    parallel = _run_scenario(rounds=rounds, refresh_aux_io_max_workers=2)
    return {"rounds": rounds, "results": [serial, parallel]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark refresh bootstrap timing with and without bounded Yahoo profile prefetch")
    parser.add_argument("--rounds", type=int, default=20, help="Synthetic refresh bootstrap rounds per scenario")
    args = parser.parse_args()

    print(json.dumps(benchmark_refresh_bootstrap_parallelism(rounds=args.rounds), indent=2))
    return 0


def _run_scenario(*, rounds: int, refresh_aux_io_max_workers: int) -> dict[str, Any]:
    timings_ms: list[float] = []
    original_settings = sec_edgar.settings
    original_fingerprint_builder = sec_edgar._build_financials_refresh_fingerprint
    original_sic_resolver = sec_edgar.resolve_sec_sic_profile

    try:
        sec_edgar.settings = SimpleNamespace(
            strict_official_mode=False,
            refresh_aux_io_max_workers=refresh_aux_io_max_workers,
        )
        sec_edgar._build_financials_refresh_fingerprint = lambda *_args, **_kwargs: "financials-fingerprint"
        sec_edgar.resolve_sec_sic_profile = (
            lambda *_args, **_kwargs: SimpleNamespace(market_sector="Technology", market_industry="Software")
        )

        for _ in range(rounds):
            service = object.__new__(sec_edgar.EdgarIngestionService)
            service.client = SimpleNamespace(
                resolve_company=lambda identifier: _sleep_then_return(
                    0.02,
                    sec_edgar.CompanyIdentity(cik="0000789019", ticker=identifier, name="Microsoft", sector="Technology"),
                ),
                get_submissions=lambda _cik: _sleep_then_return(
                    0.18,
                    {
                        "sic": "3571",
                        "sicDescription": "Technology",
                        "tickers": ["MSFT"],
                        "name": "Microsoft",
                        "exchanges": ["NASDAQ"],
                    },
                ),
                build_filing_index=lambda _submissions: _sleep_then_return(0.01, {}),
                get_companyfacts=lambda _cik: _sleep_then_return(0.2, {"facts": {"us-gaap": {}}}),
            )
            service.market_data = SimpleNamespace(
                get_market_profile=lambda _ticker: _sleep_then_return(
                    0.16,
                    sec_edgar.MarketProfile(sector="Technology", industry="Software"),
                )
            )

            started = time.perf_counter()
            service._load_refresh_bootstrap_inputs("MSFT", _Reporter())
            timings_ms.append((time.perf_counter() - started) * 1000.0)
    finally:
        sec_edgar.settings = original_settings
        sec_edgar._build_financials_refresh_fingerprint = original_fingerprint_builder
        sec_edgar.resolve_sec_sic_profile = original_sic_resolver

    return {
        "name": "parallel_market_profile_prefetch" if refresh_aux_io_max_workers > 1 else "serial_market_profile_lookup",
        "refresh_aux_io_max_workers": refresh_aux_io_max_workers,
        "latency_ms": _summarize(timings_ms),
    }


class _Reporter:
    def step(self, _stage: str, _message: str) -> None:
        return None


def _sleep_then_return(delay_seconds: float, value):
    time.sleep(delay_seconds)
    return value


def _summarize(durations_ms: list[float]) -> dict[str, float]:
    ordered = sorted(durations_ms)
    p95_index = min(len(ordered) - 1, max(0, int(round(0.95 * len(ordered))) - 1))
    return {
        "min": round(min(durations_ms), 2),
        "p50": round(statistics.median(durations_ms), 2),
        "p95": round(ordered[p95_index], 2),
        "max": round(max(durations_ms), 2),
        "avg": round(statistics.mean(durations_ms), 2),
    }


if __name__ == "__main__":
    raise SystemExit(main())

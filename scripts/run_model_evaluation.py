from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import SessionLocal, get_engine
from app.services.model_evaluation import (
    FIXTURE_CANDIDATE_LABEL,
    FIXTURE_SUITE_KEY,
    OIL_OVERLAY_FIXTURE_CANDIDATE_LABEL,
    OIL_OVERLAY_FIXTURE_SUITE_KEY,
    build_baseline_payload,
    build_fixed_risk_free_provider,
    load_company_bundles,
    load_fixture_bundles,
    load_oil_overlay_fixture_bundles,
    run_model_evaluation,
    run_oil_overlay_point_in_time_evaluation,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the historical model evaluation harness and optionally compare it with a checked-in baseline")
    parser.add_argument("--fixture", default="", help="Named in-memory fixture suite to evaluate")
    parser.add_argument("--tickers", default="", help="Comma-separated cached tickers to evaluate from PostgreSQL")
    parser.add_argument("--evaluation-target", default="general", choices=["general", "oil_overlay"], help="Which evaluation harness to run")
    parser.add_argument("--models", default="", help="Comma-separated model names to evaluate")
    parser.add_argument("--suite-key", default="", help="Logical suite key to persist and report")
    parser.add_argument("--candidate-label", default="current", help="Label for the candidate run")
    parser.add_argument("--horizon-days", type=int, default=420, help="Forward horizon used for valuation and ROIC backtests")
    parser.add_argument("--earnings-horizon-days", type=int, default=30, help="Forward horizon used for earnings signal backtests")
    parser.add_argument("--baseline-file", default="", help="Optional JSON baseline file to diff against")
    parser.add_argument("--write-baseline", default="", help="Write the current metrics as a baseline JSON file")
    parser.add_argument("--persist", action="store_true", help="Persist the completed evaluation run into PostgreSQL")
    parser.add_argument("--fail-on-delta", action="store_true", help="Exit non-zero when the current run differs from the supplied baseline")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    baseline = _load_json(args.baseline_file) if args.baseline_file else None
    requested_models = [item.strip().lower() for item in args.models.split(",") if item.strip()]
    tickers = [item.strip().upper() for item in args.tickers.split(",") if item.strip()]

    session = None
    try:
        if args.fixture:
            if args.evaluation_target == "oil_overlay":
                suite_key = args.suite_key or OIL_OVERLAY_FIXTURE_SUITE_KEY
                candidate_label = args.candidate_label if args.candidate_label != "current" else OIL_OVERLAY_FIXTURE_CANDIDATE_LABEL
                bundles = load_oil_overlay_fixture_bundles(suite_key)
                risk_free_provider = None
            else:
                suite_key = args.suite_key or args.fixture
                candidate_label = args.candidate_label if args.candidate_label != "current" else FIXTURE_CANDIDATE_LABEL
                bundles = load_fixture_bundles(args.fixture)
                risk_free_provider = build_fixed_risk_free_provider()
            if args.persist:
                get_engine()
                session = SessionLocal()
        else:
            if not tickers:
                parser.error("Either --fixture or --tickers is required")
            suite_key = args.suite_key or (OIL_OVERLAY_FIXTURE_SUITE_KEY if args.evaluation_target == "oil_overlay" else "postgres_historical_cache")
            candidate_label = args.candidate_label
            get_engine()
            session = SessionLocal()
            bundles = load_company_bundles(session, tickers)
            risk_free_provider = None

        if not bundles:
            raise SystemExit("No evaluation bundles were available for the requested suite")

        if args.evaluation_target == "oil_overlay":
            result = run_oil_overlay_point_in_time_evaluation(
                bundles=bundles,
                suite_key=suite_key,
                candidate_label=candidate_label,
                baseline=baseline,
                horizon_days=args.horizon_days,
                persist_session=session if args.persist else None,
            )
        else:
            result = run_model_evaluation(
                bundles=bundles,
                suite_key=suite_key,
                candidate_label=candidate_label,
                baseline=baseline,
                model_names=requested_models or None,
                horizon_days=args.horizon_days,
                earnings_horizon_days=args.earnings_horizon_days,
                persist_session=session if args.persist else None,
                risk_free_rate_provider=risk_free_provider,
            )

        if session is not None:
            session.commit()

        if args.write_baseline:
            baseline_path = Path(args.write_baseline)
            baseline_path.write_text(
                json.dumps(build_baseline_payload(result), indent=2, sort_keys=True, default=str),
                encoding="utf-8",
            )

        print(json.dumps(result, indent=2, sort_keys=True, default=str))

        if args.fail_on_delta and result.get("deltas_present"):
            logging.error("Model evaluation deltas detected against baseline %s", args.baseline_file or "<none>")
            return 1
        return 0
    finally:
        if session is not None:
            session.close()


def _load_json(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())

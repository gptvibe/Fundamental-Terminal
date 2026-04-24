from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.charts_validation import (
    GOLDEN_SNAPSHOT_PATH,
    build_validation_summary,
    render_validation_summary_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run chart/driver forecast validation checks and emit regression + benchmark reports."
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/performance",
        help="Directory for validation report outputs",
    )
    parser.add_argument(
        "--write-golden",
        action="store_true",
        help="Update the golden regression snapshot file used by tests",
    )
    args = parser.parse_args()

    summary = build_validation_summary()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "charts_validation_summary.json"
    md_path = output_dir / "charts_validation_summary.md"

    json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(render_validation_summary_markdown(summary), encoding="utf-8")

    if args.write_golden:
        GOLDEN_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        golden_payload = summary.get("golden_snapshot", {})
        GOLDEN_SNAPSHOT_PATH.write_text(
            json.dumps(golden_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    print(json.dumps({
        "json_report": str(json_path),
        "markdown_report": str(md_path),
        "golden_written": bool(args.write_golden),
        "golden_path": str(GOLDEN_SNAPSHOT_PATH),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_sec_edgar_module_help_invokes_cli() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)

    result = subprocess.run(
        [sys.executable, "-m", "app.services.sec_edgar", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert result.returncode == 0
    assert "Refresh SEC EDGAR filings into PostgreSQL" in result.stdout
    assert "--force" in result.stdout
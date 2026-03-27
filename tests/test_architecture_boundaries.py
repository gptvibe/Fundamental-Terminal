from __future__ import annotations

from pathlib import Path

from scripts.check_architecture_boundaries import collect_boundary_violations


def test_backend_architecture_boundaries_hold() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    violations = collect_boundary_violations(repo_root)
    assert [violation.format(repo_root) for violation in violations] == []
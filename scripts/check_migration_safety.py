from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from alembic.config import Config
from alembic.script import ScriptDirectory


@dataclass(frozen=True, slots=True)
class MigrationIssue:
    level: str
    message: str
    revision: str | None = None
    file_path: str | None = None


@dataclass(frozen=True, slots=True)
class MigrationSafetyReport:
    ok: bool
    issues: tuple[MigrationIssue, ...]


def check_migration_safety(*, alembic_ini_path: Path = Path("alembic.ini")) -> MigrationSafetyReport:
    config = Config(str(alembic_ini_path))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()

    issues: list[MigrationIssue] = []
    if len(heads) != 1:
        issues.append(
            MigrationIssue(
                level="error",
                message=f"Expected exactly one Alembic head, found {len(heads)}: {', '.join(heads) or '<none>'}",
            )
        )

    for revision in script.walk_revisions(base="base", head="heads"):
        path = Path(revision.path)
        source = path.read_text(encoding="utf-8")

        downgrade_status = _downgrade_status(source)
        is_merge = isinstance(revision.down_revision, tuple) and len(revision.down_revision) > 1

        if downgrade_status == "missing":
            issues.append(
                MigrationIssue(
                    level="error",
                    message="Migration is missing a downgrade function",
                    revision=revision.revision,
                    file_path=str(path),
                )
            )
        elif downgrade_status == "noop" and not is_merge:
            issues.append(
                MigrationIssue(
                    level="error",
                    message="Non-merge migration has a no-op downgrade; provide a reversible downgrade implementation",
                    revision=revision.revision,
                    file_path=str(path),
                )
            )

        if _has_unbounded_raw_drop_execute(source):
            issues.append(
                MigrationIssue(
                    level="error",
                    message="Migration executes raw DROP TABLE/INDEX SQL; prefer explicit Alembic operations with guarded checks",
                    revision=revision.revision,
                    file_path=str(path),
                )
            )

    ok = not any(issue.level == "error" for issue in issues)
    return MigrationSafetyReport(ok=ok, issues=tuple(issues))


def _downgrade_status(source: str) -> str:
    module = ast.parse(source)
    downgrade = next((node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "downgrade"), None)
    if downgrade is None:
        return "missing"
    body = [node for node in downgrade.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))]
    if len(body) == 0:
        return "noop"
    if len(body) == 1 and isinstance(body[0], ast.Pass):
        return "noop"
    return "implemented"


def _has_unbounded_raw_drop_execute(source: str) -> bool:
    lowered = source.lower()
    for token in ('op.execute("drop table', "op.execute('drop table", 'op.execute("drop index', "op.execute('drop index"):
        if token in lowered:
            return True
    return False


def _format_issues(issues: Iterable[MigrationIssue]) -> str:
    lines: list[str] = []
    for issue in issues:
        location = ""
        if issue.file_path:
            location = f" [{issue.file_path}]"
        revision = ""
        if issue.revision:
            revision = f" revision={issue.revision}"
        lines.append(f"- {issue.level.upper()}: {issue.message}{revision}{location}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Alembic migration safety rules")
    parser.add_argument("--alembic-ini", default="alembic.ini", help="Path to alembic.ini")
    args = parser.parse_args()

    report = check_migration_safety(alembic_ini_path=Path(args.alembic_ini))
    if report.issues:
        print(_format_issues(report.issues))

    if not report.ok:
        return 1

    print("Migration safety checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

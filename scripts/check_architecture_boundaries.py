from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER_DIR = ROOT / "app" / "api" / "routers"
SERVICE_DIR = ROOT / "app" / "services"

ROUTER_ALLOWED_PREFIXES = (
    "__future__",
    "typing",
    "fastapi",
    "starlette",
    "app.api.schemas",
    "app.api.routers",
)
SERVICE_FORBIDDEN_PREFIXES = (
    "app.api",
)


@dataclass(slots=True)
class BoundaryViolation:
    rule: str
    file_path: Path
    line_number: int
    import_name: str

    def format(self, root: Path) -> str:
        relative_path = self.file_path.relative_to(root).as_posix()
        return f"{relative_path}:{self.line_number}: {self.rule}: {self.import_name}"


def _iter_python_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.rglob("*.py") if path.is_file())


def _iter_imports(file_path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    imports: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                continue
            if node.module:
                imports.append((node.lineno, node.module))

    return imports


def _is_allowed_router_import(import_name: str) -> bool:
    return any(import_name == prefix or import_name.startswith(f"{prefix}.") for prefix in ROUTER_ALLOWED_PREFIXES)


def _is_forbidden_service_import(import_name: str) -> bool:
    return any(import_name == prefix or import_name.startswith(f"{prefix}.") for prefix in SERVICE_FORBIDDEN_PREFIXES)


def collect_boundary_violations(root: Path | None = None) -> list[BoundaryViolation]:
    repo_root = root or ROOT
    violations: list[BoundaryViolation] = []

    for file_path in _iter_python_files(repo_root / "app" / "api" / "routers"):
        for line_number, import_name in _iter_imports(file_path):
            if _is_allowed_router_import(import_name):
                continue
            violations.append(
                BoundaryViolation(
                    rule="routers may only import router-local dependencies and frontend-facing schemas",
                    file_path=file_path,
                    line_number=line_number,
                    import_name=import_name,
                )
            )

    for file_path in _iter_python_files(repo_root / "app" / "services"):
        for line_number, import_name in _iter_imports(file_path):
            if not _is_forbidden_service_import(import_name):
                continue
            violations.append(
                BoundaryViolation(
                    rule="services may not import app.api modules or frontend-facing schemas",
                    file_path=file_path,
                    line_number=line_number,
                    import_name=import_name,
                )
            )

    return violations


def main() -> int:
    violations = collect_boundary_violations(ROOT)
    if not violations:
        print("Architecture boundary check passed.")
        return 0

    for violation in violations:
        print(violation.format(ROOT))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROUTER_DIR = ROOT / "app" / "api" / "routers"
HANDLER_DIR = ROOT / "app" / "api" / "handlers"
SERVICE_DIR = ROOT / "app" / "services"

ROUTER_ALLOWED_PREFIXES = (
    "__future__",
    "typing",
    "fastapi",
    "starlette",
    "app.api.handlers",
    "app.api.schemas",
    "app.api.source_contracts",
    "app.api.routers",
)
HANDLER_FORBIDDEN_PREFIXES = (
    "app.main",
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


def _parse_tree(file_path: Path) -> ast.AST:
    return ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))


def _is_allowed_router_import(import_name: str) -> bool:
    return any(import_name == prefix or import_name.startswith(f"{prefix}.") for prefix in ROUTER_ALLOWED_PREFIXES)


def _is_forbidden_service_import(import_name: str) -> bool:
    return any(import_name == prefix or import_name.startswith(f"{prefix}.") for prefix in SERVICE_FORBIDDEN_PREFIXES)


def _is_forbidden_handler_import(import_name: str) -> bool:
    return any(import_name == prefix or import_name.startswith(f"{prefix}.") for prefix in HANDLER_FORBIDDEN_PREFIXES)


def _node_text(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "<unknown>"


def _collect_router_structure_violations(file_path: Path) -> list[BoundaryViolation]:
    tree = _parse_tree(file_path)
    handler_module_aliases: set[str] = set()
    handler_symbol_names: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.module == "app.api.handlers":
            for alias in node.names:
                handler_module_aliases.add(alias.asname or alias.name)
        elif node.module.startswith("app.api.handlers."):
            for alias in node.names:
                handler_symbol_names.add(alias.asname or alias.name)

    build_router = next(
        (
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build_router"
        ),
        None,
    )

    if build_router is None:
        return [
            BoundaryViolation(
                rule="router modules must expose a zero-argument build_router entrypoint",
                file_path=file_path,
                line_number=1,
                import_name="build_router",
            )
        ]

    all_args = [
        *build_router.args.posonlyargs,
        *build_router.args.args,
        *build_router.args.kwonlyargs,
    ]
    if build_router.args.vararg is not None:
        all_args.append(build_router.args.vararg)
    if build_router.args.kwarg is not None:
        all_args.append(build_router.args.kwarg)

    violations: list[BoundaryViolation] = []
    if all_args:
        violations.append(
            BoundaryViolation(
                rule="router modules must expose a zero-argument build_router entrypoint",
                file_path=file_path,
                line_number=build_router.lineno,
                import_name=", ".join(argument.arg for argument in all_args),
            )
        )

    for node in ast.walk(build_router):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id not in {"add_user_visible_route", "add_internal_route"}:
            continue
        if len(node.args) < 3:
            continue

        endpoint = node.args[2]
        is_handler_reference = (
            isinstance(endpoint, ast.Attribute)
            and isinstance(endpoint.value, ast.Name)
            and endpoint.value.id in handler_module_aliases
        ) or (
            isinstance(endpoint, ast.Name)
            and endpoint.id in handler_symbol_names
        )
        if is_handler_reference:
            continue

        violations.append(
            BoundaryViolation(
                rule="router routes must be wired through app.api.handlers symbols",
                file_path=file_path,
                line_number=node.lineno,
                import_name=_node_text(endpoint),
            )
        )

    return violations


def _iter_dynamic_main_imports(file_path: Path) -> list[tuple[int, str]]:
    tree = _parse_tree(file_path)
    uses: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "importlib"
            and node.func.attr == "import_module"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "app.main"
        ):
            uses.append((node.lineno, "importlib.import_module('app.main')"))
            continue
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "app.main"
        ):
            uses.append((node.lineno, "__import__('app.main')"))

    return uses


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
        if file_path.name != "__init__.py":
            violations.extend(_collect_router_structure_violations(file_path))

    for file_path in _iter_python_files(repo_root / "app" / "api" / "handlers"):
        for line_number, import_name in _iter_imports(file_path):
            if not _is_forbidden_handler_import(import_name):
                continue
            violations.append(
                BoundaryViolation(
                    rule="handlers may not import app.main or router modules",
                    file_path=file_path,
                    line_number=line_number,
                    import_name=import_name,
                )
            )
        if file_path.name == "_dispatch.py":
            continue
        for line_number, import_name in _iter_dynamic_main_imports(file_path):
            violations.append(
                BoundaryViolation(
                    rule="only the handler compatibility shim may resolve app.main dynamically",
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
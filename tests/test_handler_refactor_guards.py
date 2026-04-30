from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.api.handlers import _dispatch as dispatch_handlers
from app.api.handlers import company_overview as company_overview_handlers
from app.api.handlers import events as event_handlers
from app.api.handlers import filings as filing_handlers
from app.api.handlers import financials as financial_handlers
from app.api.handlers import governance as governance_handlers
from app.api.handlers import jobs as job_handlers
from app.api.handlers import market_context as market_context_handlers
from app.api.handlers import models as model_handlers
from app.api.handlers import search as search_handlers
from fastapi.routing import APIRoute
from starlette.responses import StreamingResponse

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
ROUTE_DECORATOR_NAMES = {"delete", "get", "patch", "post", "put"}


def _parse_module(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _find_route(path: str, method: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in (route.methods or set()):
            return route
    raise AssertionError(f"Route {method} {path} was not registered")


def test_main_stays_bootstrap_only() -> None:
    tree = _parse_module(ROOT / "app" / "main.py")

    route_definitions = []
    create_app = None
    app_assignment_found = False
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets):
                if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "create_app":
                    app_assignment_found = True
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "create_app":
            create_app = node
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name) or decorator.func.value.id != "app":
                continue
            if decorator.func.attr in ROUTE_DECORATOR_NAMES:
                route_definitions.append((node.name, node.lineno))

    assert route_definitions == []
    assert create_app is not None
    assert app_assignment_found

    register_calls = [
        node
        for node in ast.walk(create_app)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "register_routers"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "app"
    ]
    assert len(register_calls) == 1


def test_jobs_routes_keep_streaming_and_async_contracts() -> None:
    stream_route = _find_route("/api/jobs/{job_id}/events", "GET")
    refresh_route = _find_route("/api/companies/{ticker}/refresh", "POST")

    assert stream_route.response_class is StreamingResponse
    assert stream_route.endpoint.__name__ == "stream_job_events"
    assert inspect.iscoroutinefunction(inspect.unwrap(stream_route.endpoint))
    assert list(inspect.signature(stream_route.endpoint, follow_wrapped=True).parameters) == ["job_id", "request"]

    assert refresh_route.status_code == 202
    assert refresh_route.endpoint.__name__ == "refresh_company"
    assert list(inspect.signature(refresh_route.endpoint, follow_wrapped=True).parameters) == [
        "ticker",
        "force",
    ]


def test_dispatch_module_uses_static_resolution() -> None:
    dispatch_path = ROOT / "app" / "api" / "handlers" / "_dispatch.py"
    tree = _parse_module(dispatch_path)

    has_importlib_import = any(
        isinstance(node, ast.Import) and any(alias.name == "importlib" for alias in node.names)
        for node in tree.body
    ) or any(
        isinstance(node, ast.ImportFrom) and node.module == "importlib"
        for node in tree.body
    )
    assert not has_importlib_import

    has_import_module_call = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "importlib"
        and node.func.attr == "import_module"
        for node in ast.walk(tree)
    )
    assert not has_import_module_call

    assert dispatch_handlers.route_handler("search_companies") is dispatch_handlers.ROUTE_HANDLERS["search_companies"]


def test_key_routes_bind_to_expected_handler_exports() -> None:
    expected_routes = [
        ("/api/companies/search", "GET", search_handlers.search_companies),
        ("/api/companies/resolve", "GET", search_handlers.resolve_company_identifier),
        ("/api/companies/{ticker}/peers", "GET", company_overview_handlers.company_peers),
        ("/api/companies/{ticker}/brief", "GET", company_overview_handlers.company_brief),
        ("/api/companies/{ticker}/overview", "GET", company_overview_handlers.company_overview),
        ("/api/companies/{ticker}/workspace-bootstrap", "GET", company_overview_handlers.company_workspace_bootstrap),
        ("/api/companies/{ticker}/financials", "GET", financial_handlers.company_financials),
        ("/api/companies/{ticker}/charts", "GET", financial_handlers.company_charts),
        ("/api/companies/{ticker}/filings", "GET", filing_handlers.company_filings),
        ("/api/companies/{ticker}/governance", "GET", governance_handlers.company_governance),
        ("/api/companies/{ticker}/governance/summary", "GET", governance_handlers.company_governance_summary),
        ("/api/companies/{ticker}/executive-compensation", "GET", governance_handlers.company_executive_compensation),
        ("/api/companies/{ticker}/events", "GET", event_handlers.company_events),
        ("/api/companies/{ticker}/models", "GET", model_handlers.company_models),
        ("/api/companies/{ticker}/market-context", "GET", market_context_handlers.company_market_context),
        ("/api/market-context", "GET", market_context_handlers.global_market_context),
        ("/api/jobs/{job_id}/events", "GET", job_handlers.stream_job_events),
        ("/api/companies/{ticker}/refresh", "POST", job_handlers.refresh_company),
    ]

    for path, method, expected_handler in expected_routes:
        route = _find_route(path, method)
        assert inspect.unwrap(route.endpoint) is inspect.unwrap(expected_handler)


def test_extracted_sync_db_handlers_are_async_wrapped() -> None:
    wrapped_handlers = [
        company_overview_handlers.company_brief,
        company_overview_handlers.company_overview,
        company_overview_handlers.company_workspace_bootstrap,
        governance_handlers.company_governance,
        governance_handlers.company_governance_summary,
        governance_handlers.company_executive_compensation,
        market_context_handlers.company_market_context,
        market_context_handlers.global_market_context,
    ]

    for handler in wrapped_handlers:
        assert inspect.iscoroutinefunction(handler)
        assert "session" not in inspect.signature(handler).parameters


def test_moved_sync_handlers_can_reuse_wrapped_shared_handlers_synchronously() -> None:
    def sync_handler() -> str:
        return "ok"

    async def wrapped_handler() -> str:
        return "wrapped"

    wrapped_handler.__wrapped__ = sync_handler  # type: ignore[attr-defined]

    assert company_overview_handlers._sync_route_handler(wrapped_handler) is sync_handler


def test_dispatch_map_covers_all_handler_shim_targets() -> None:
    handlers_dir = ROOT / "app" / "api" / "handlers"
    discovered_targets: set[str] = set()

    for path in handlers_dir.glob("*.py"):
        if path.name in {"_dispatch.py", "_shared.py", "__init__.py", "research_workspace.py"}:
            continue
        tree = _parse_module(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "route_handler":
                continue
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                continue
            discovered_targets.add(node.args[0].value)

    assert discovered_targets == set(dispatch_handlers.ROUTE_HANDLERS)

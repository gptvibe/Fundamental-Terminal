from __future__ import annotations

import ast
import inspect
from pathlib import Path

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

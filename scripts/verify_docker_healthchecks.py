from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE_FILES = (Path("docker-compose.yml"), Path("docker-compose.build.yml"))
REQUIRED_HEALTHCHECK_SERVICES = frozenset({"postgres", "redis", "backend", "data-fetcher", "frontend"})
CHEAP_COMMAND_TOKENS = (
    " sleep ",
    "docker compose",
    "docker-compose",
    "apt-get",
    "apk add",
    "pip install",
    "npm install",
    "alembic ",
)
URL_PATTERN = re.compile(r"https?://[^\s'\")]+")
REPO_SCRIPT_PATHS = {
    "/app/docker/backend/healthcheck-data-fetcher.sh": ROOT / "docker" / "backend" / "healthcheck-data-fetcher.sh",
}
EXPECTED_HTTP_TARGETS = {
    "backend": "http://127.0.0.1:8000/health",
    "frontend": "http://127.0.0.1:3000/",
}


@dataclass(frozen=True, slots=True)
class HealthcheckIssue:
    level: str
    compose_file: str
    service: str
    message: str


@dataclass(frozen=True, slots=True)
class HealthcheckReport:
    ok: bool
    issues: tuple[HealthcheckIssue, ...]


def validate_compose_healthchecks(*, compose_files: tuple[Path, ...] = DEFAULT_COMPOSE_FILES) -> HealthcheckReport:
    issues: list[HealthcheckIssue] = []
    for compose_file in compose_files:
        compose_path = ROOT / compose_file
        payload = _load_compose(compose_path)
        services = payload.get("services")
        if not isinstance(services, dict):
            issues.append(
                HealthcheckIssue(
                    level="error",
                    compose_file=str(compose_file),
                    service="services",
                    message="Compose file is missing a top-level services mapping",
                )
            )
            continue

        for service_name in sorted(REQUIRED_HEALTHCHECK_SERVICES):
            service = services.get(service_name)
            if not isinstance(service, dict):
                issues.append(
                    HealthcheckIssue(
                        level="error",
                        compose_file=str(compose_file),
                        service=service_name,
                        message="Required service is missing from compose file",
                    )
                )
                continue

            healthcheck = service.get("healthcheck")
            if not isinstance(healthcheck, dict):
                issues.append(
                    HealthcheckIssue(
                        level="error",
                        compose_file=str(compose_file),
                        service=service_name,
                        message="Required service is missing a healthcheck block",
                    )
                )
                continue

            issues.extend(_validate_healthcheck(compose_file=compose_file, service_name=service_name, healthcheck=healthcheck))

    report = tuple(issues)
    return HealthcheckReport(ok=not any(issue.level == "error" for issue in report), issues=report)


def _load_compose(compose_path: Path) -> dict[str, object]:
    with compose_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Compose file {compose_path} does not contain a YAML mapping")
    return payload


def _validate_healthcheck(*, compose_file: Path, service_name: str, healthcheck: dict[str, object]) -> list[HealthcheckIssue]:
    issues: list[HealthcheckIssue] = []
    test = healthcheck.get("test")
    command_mode, command_text = _normalize_healthcheck_test(test)
    if command_mode is None or command_text is None:
        issues.append(
            HealthcheckIssue(
                level="error",
                compose_file=str(compose_file),
                service=service_name,
                message="Healthcheck test must be a non-empty CMD/CMD-SHELL array",
            )
        )
        return issues

    issues.extend(_validate_duration_fields(compose_file=compose_file, service_name=service_name, healthcheck=healthcheck))

    lowered_command = f" {command_text.lower()} "
    for forbidden_token in CHEAP_COMMAND_TOKENS:
        if forbidden_token in lowered_command:
            issues.append(
                HealthcheckIssue(
                    level="error",
                    compose_file=str(compose_file),
                    service=service_name,
                    message=f"Healthcheck command is not cheap enough for CI: contains '{forbidden_token.strip()}'",
                )
            )

    if service_name == "postgres" and "pg_isready" not in lowered_command:
        issues.append(
            HealthcheckIssue(
                level="error",
                compose_file=str(compose_file),
                service=service_name,
                message="Postgres healthcheck must use pg_isready",
            )
        )
    if service_name == "redis" and not ("redis-cli" in lowered_command and "ping" in lowered_command):
        issues.append(
            HealthcheckIssue(
                level="error",
                compose_file=str(compose_file),
                service=service_name,
                message="Redis healthcheck must use redis-cli ping",
            )
        )

    expected_url = EXPECTED_HTTP_TARGETS.get(service_name)
    if expected_url is not None:
        url_matches = URL_PATTERN.findall(command_text)
        if expected_url not in url_matches:
            issues.append(
                HealthcheckIssue(
                    level="error",
                    compose_file=str(compose_file),
                    service=service_name,
                    message=f"Healthcheck must probe {expected_url}",
                )
            )
        else:
            issues.extend(_validate_local_http_targets(compose_file=compose_file, service_name=service_name, urls=url_matches))
            if service_name == "backend" and not _backend_health_route_exists():
                issues.append(
                    HealthcheckIssue(
                        level="error",
                        compose_file=str(compose_file),
                        service=service_name,
                        message="Backend /health route is missing from the repository",
                    )
                )
            if service_name == "frontend" and not (ROOT / "frontend" / "app" / "page.tsx").exists():
                issues.append(
                    HealthcheckIssue(
                        level="error",
                        compose_file=str(compose_file),
                        service=service_name,
                        message="Frontend root route file frontend/app/page.tsx is missing",
                    )
                )

    script_path = _extract_repo_script_path(command_text)
    if service_name == "data-fetcher":
        expected_script = REPO_SCRIPT_PATHS["/app/docker/backend/healthcheck-data-fetcher.sh"]
        if script_path != expected_script:
            issues.append(
                HealthcheckIssue(
                    level="error",
                    compose_file=str(compose_file),
                    service=service_name,
                    message="Data fetcher healthcheck must call /app/docker/backend/healthcheck-data-fetcher.sh",
                )
            )
        elif not expected_script.exists():
            issues.append(
                HealthcheckIssue(
                    level="error",
                    compose_file=str(compose_file),
                    service=service_name,
                    message=f"Referenced healthcheck script does not exist: {expected_script}",
                )
            )

    if command_mode == "CMD-SHELL" and not command_text.strip():
        issues.append(
            HealthcheckIssue(
                level="error",
                compose_file=str(compose_file),
                service=service_name,
                message="CMD-SHELL healthcheck must contain a non-empty command string",
            )
        )

    return issues


def _normalize_healthcheck_test(test: object) -> tuple[str | None, str | None]:
    if not isinstance(test, list) or not test or not all(isinstance(item, str) and item.strip() for item in test):
        return None, None
    mode = test[0]
    if mode not in {"CMD", "CMD-SHELL"}:
        return None, None
    if mode == "CMD-SHELL":
        if len(test) != 2:
            return None, None
        return mode, test[1]
    if len(test) < 2:
        return None, None
    return mode, " ".join(test[1:])


def _validate_duration_fields(*, compose_file: Path, service_name: str, healthcheck: dict[str, object]) -> list[HealthcheckIssue]:
    issues: list[HealthcheckIssue] = []
    interval = _parse_duration_seconds(healthcheck.get("interval"))
    timeout = _parse_duration_seconds(healthcheck.get("timeout"))
    start_period = _parse_duration_seconds(healthcheck.get("start_period"))
    retries = healthcheck.get("retries")

    if interval is None or timeout is None:
        issues.append(
            HealthcheckIssue(
                level="error",
                compose_file=str(compose_file),
                service=service_name,
                message="Healthcheck interval and timeout must use parseable duration strings",
            )
        )
        return issues

    if start_period is None:
        issues.append(
            HealthcheckIssue(
                level="error",
                compose_file=str(compose_file),
                service=service_name,
                message="Healthcheck start_period must use a parseable duration string",
            )
        )

    if timeout > 10:
        issues.append(
            HealthcheckIssue(
                level="error",
                compose_file=str(compose_file),
                service=service_name,
                message="Healthcheck timeout must stay at or below 10 seconds",
            )
        )
    if interval < timeout:
        issues.append(
            HealthcheckIssue(
                level="error",
                compose_file=str(compose_file),
                service=service_name,
                message="Healthcheck interval must be greater than or equal to timeout",
            )
        )

    if not isinstance(retries, int) or retries < 1 or retries > 10:
        issues.append(
            HealthcheckIssue(
                level="error",
                compose_file=str(compose_file),
                service=service_name,
                message="Healthcheck retries must be an integer between 1 and 10",
            )
        )

    return issues


def _parse_duration_seconds(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(?P<number>\d+)(?P<unit>ms|s|m|h)", value.strip())
    if match is None:
        return None
    number = int(match.group("number"))
    unit = match.group("unit")
    multipliers = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
    return number * multipliers[unit]


def _validate_local_http_targets(*, compose_file: Path, service_name: str, urls: list[str]) -> list[HealthcheckIssue]:
    issues: list[HealthcheckIssue] = []
    for url in urls:
        parsed = urlsplit(url)
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            issues.append(
                HealthcheckIssue(
                    level="error",
                    compose_file=str(compose_file),
                    service=service_name,
                    message=f"Healthcheck URL must stay local to the container: {url}",
                )
            )
    return issues


def _extract_repo_script_path(command_text: str) -> Path | None:
    for container_path, repo_path in REPO_SCRIPT_PATHS.items():
        if container_path in command_text:
            return repo_path
    return None


def _backend_health_route_exists() -> bool:
    for path in (ROOT / "app").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if '@app.get("/health")' in source or '"/health"' in source:
            return True
    return False


def _format_issues(issues: tuple[HealthcheckIssue, ...]) -> str:
    return "\n".join(f"- {issue.level.upper()}: [{issue.compose_file}] {issue.service}: {issue.message}" for issue in issues)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Docker compose healthcheck commands and references")
    parser.add_argument(
        "compose_files",
        nargs="*",
        default=[str(path) for path in DEFAULT_COMPOSE_FILES],
        help="Compose files to validate, relative to the repository root",
    )
    args = parser.parse_args()

    compose_files = tuple(Path(path) for path in args.compose_files)
    report = validate_compose_healthchecks(compose_files=compose_files)
    if report.issues:
        print(_format_issues(report.issues))
    if not report.ok:
        return 1

    print("Docker healthcheck verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
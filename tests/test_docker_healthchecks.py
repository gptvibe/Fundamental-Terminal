from __future__ import annotations

from pathlib import Path

import yaml

from scripts.verify_docker_healthchecks import validate_compose_healthchecks


def test_compose_healthchecks_validate_for_checked_in_files() -> None:
    report = validate_compose_healthchecks()

    assert report.ok, "\n".join(issue.message for issue in report.issues)


def test_main_compose_healthchecks_reference_expected_endpoints_and_scripts() -> None:
    compose = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["backend"]["healthcheck"]["test"] == [
        "CMD",
        "python",
        "-c",
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()",
    ]
    assert services["data-fetcher"]["healthcheck"]["test"] == [
        "CMD",
        "/bin/sh",
        "/app/docker/backend/healthcheck-data-fetcher.sh",
    ]
    assert services["frontend"]["healthcheck"]["test"] == [
        "CMD",
        "node",
        "-e",
        "fetch('http://127.0.0.1:3000/', { signal: AbortSignal.timeout(5000) }).then((response) => process.exit(response.ok ? 0 : 1)).catch(() => process.exit(1))",
    ]
    assert Path("docker/backend/healthcheck-data-fetcher.sh").exists()
    assert Path("frontend/app/page.tsx").exists()


def test_build_compose_reuses_shared_data_fetcher_healthcheck_script() -> None:
    compose = yaml.safe_load(Path("docker-compose.build.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert services["data-fetcher"]["healthcheck"]["test"] == [
        "CMD",
        "/bin/sh",
        "/app/docker/backend/healthcheck-data-fetcher.sh",
    ]
    assert services["frontend"]["healthcheck"]["test"][3].startswith("fetch('http://127.0.0.1:3000/'")
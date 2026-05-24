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


    def test_compose_backend_services_include_external_service_env_passthrough() -> None:
        required_env_keys = {
            "CENSUS_API_KEY",
            "BLS_API_KEY",
            "EIA_API_KEY",
            "BEA_API_KEY",
            "FRED_API_KEY",
            "SEC_USER_AGENT",
            "MARKET_USER_AGENT",
        }

        for compose_path in ("docker-compose.yml", "docker-compose.build.yml"):
            compose = yaml.safe_load(Path(compose_path).read_text(encoding="utf-8"))
            services = compose["services"]

            for service_name in ("backend", "data-fetcher", "sp500-prewarm"):
                service_env = set((services[service_name].get("environment") or {}).keys())
                missing_keys = required_env_keys - service_env
                assert not missing_keys, f"{compose_path}:{service_name} missing env keys: {sorted(missing_keys)}"
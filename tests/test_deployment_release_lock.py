from __future__ import annotations

from pathlib import Path


def test_published_compose_defaults_to_latest_images_with_explicit_overrides() -> None:
    compose_text = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "APP_IMAGE_TAG" not in compose_text
    assert "${BACKEND_IMAGE:-gptvibe/fundamentalterminal:backend-latest}" in compose_text
    assert "${FRONTEND_IMAGE:-gptvibe/fundamentalterminal:frontend-latest}" in compose_text
    assert "healthcheck-data-fetcher.sh" in compose_text
    assert "http://127.0.0.1:3000/" in compose_text


def test_python_runtime_and_dev_requirements_stay_split() -> None:
    runtime_requirements = Path("requirements.txt").read_text(encoding="utf-8")
    dev_requirements = Path("requirements-dev.txt").read_text(encoding="utf-8")
    backend_dockerfile = Path("docker/backend/Dockerfile").read_text(encoding="utf-8")
    ci_workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "pytest" not in runtime_requirements
    assert "-r requirements.txt" in dev_requirements
    assert "pytest>=8.0,<9.0" in dev_requirements
    assert "pip install -r requirements.txt" in backend_dockerfile
    assert "pip install -r requirements-dev.txt" in ci_workflow

from __future__ import annotations

from pathlib import Path


def test_published_compose_defaults_to_latest_images_with_explicit_overrides() -> None:
    compose_text = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "APP_IMAGE_TAG" not in compose_text
    assert "${BACKEND_IMAGE:-gptvibe/fundamentalterminal:backend-latest}" in compose_text
    assert "${FRONTEND_IMAGE:-gptvibe/fundamentalterminal:frontend-latest}" in compose_text

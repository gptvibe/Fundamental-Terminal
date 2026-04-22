from __future__ import annotations

from pathlib import Path


def test_published_compose_uses_one_shared_image_tag_selector() -> None:
    compose_text = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "APP_IMAGE_TAG" in compose_text
    assert "BACKEND_IMAGE" not in compose_text
    assert "FRONTEND_IMAGE" not in compose_text
    assert "backend-latest" not in compose_text
    assert "frontend-latest" not in compose_text

    assert "gptvibe/fundamentalterminal:backend-${APP_IMAGE_TAG" in compose_text
    assert "gptvibe/fundamentalterminal:frontend-${APP_IMAGE_TAG" in compose_text

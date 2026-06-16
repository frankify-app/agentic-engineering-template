from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import copier
import pytest

PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def base_answers() -> dict[str, str]:
    return {
        "agentic_project_name": "Snake Farm",
        "agentic_project_description": "A sample Snake farming project.",
        "agentic_project_slug": "snake-farm",
        "agentic_precommit": "prek",
        "agentic_forge": "github",
        "agentic_repo_owner": "actions-user",
    }


@pytest.fixture
def render_project(tmp_path: Path, base_answers: dict[str, str]):
    """Render the Copier template into an isolated directory under ``tmp_path``."""

    def _render(
        *,
        dst_name: str | None = None,
        **overrides: str,
    ) -> Path:
        answers = {**base_answers, **overrides}
        slug = answers.get("agentic_project_slug", "project")
        dst_path = tmp_path / (dst_name or slug)
        copier.run_copy(
            src_path=str(PROJECT_ROOT),
            dst_path=dst_path,
            data=answers,
            defaults=True,
            unsafe=True,
            skip_tasks=True,
        )
        return dst_path

    return _render

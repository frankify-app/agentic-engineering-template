from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import copier

PROJECT_ROOT = Path(__file__).parent.parent


def _check_file_contents(
    file_path: Path,
    expected_strs: Sequence[str] = (),
    unexpect_strs: Sequence[str] = (),
) -> None:
    assert file_path.exists(), f"Expected file missing: {file_path}"
    file_content = file_path.read_text()
    for content in expected_strs:
        assert content in file_content, f"Expected {content!r} in {file_path}"
    for content in unexpect_strs:
        assert content not in file_content, f"Unexpected {content!r} in {file_path}"


def test_slug_auto_derived(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    answers = {
        **base_answers,
        "agentic_project_name": "My Cool App",
    }
    del answers["agentic_project_slug"]

    dst_path = tmp_path / "my-cool-app"
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data=answers,
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )

    assert (dst_path / "docs" / "glossary" / "my-cool-app.md").exists()
    _check_file_contents(
        dst_path / "AGENTS.md",
        ["https://github.com/actions-user/my-cool-app"],
    )

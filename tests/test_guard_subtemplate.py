"""Render tests for the guard subtemplate (agentic_subtemplate=guard).

The guard subtemplate vendors the decision-memory CI guard — and
nothing else — into a data repo, keyed by a minimal answers file.
"""

from __future__ import annotations

from pathlib import Path

import copier

PROJECT_ROOT = Path(__file__).parent.parent

GUARD_FILES = frozenset(
    {
        ".copier-answers.agentic.yml",
        ".github/guards/decision_validator.py",
        ".github/guards/guards.py",
        ".github/workflows/guards.yml",
        ".gitignore",
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "docs/conventions.md",
        "docs/extraction-prompt.md",
        "preferences.md",
    }
)


def _render_guard(tmp_path: Path) -> Path:
    dst_path = tmp_path / "decision-memory"
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data={"agentic_subtemplate": "guard"},
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        # Pin HEAD: with release tags present locally, copier would
        # otherwise render the latest RELEASE instead of this branch.
        vcs_ref="HEAD",
    )
    return dst_path


def test_guard_render_produces_exactly_the_guard_files(tmp_path: Path) -> None:
    dst_path = _render_guard(tmp_path)
    rendered = {
        str(p.relative_to(dst_path)) for p in dst_path.rglob("*") if p.is_file()
    }
    assert rendered == GUARD_FILES


def test_vendored_validator_is_byte_identical_to_source(
    tmp_path: Path,
) -> None:
    dst_path = _render_guard(tmp_path)
    source_dir = PROJECT_ROOT / "guard" / ".github" / "guards"
    for name in ("decision_validator.py", "guards.py"):
        vendored = (dst_path / ".github" / "guards" / name).read_text()
        assert vendored == (source_dir / name).read_text()


def test_guard_answers_file_is_minimal(tmp_path: Path) -> None:
    """Project-scaffold questions are skipped, so the data repo records
    only the subtemplate choice — it stays consumer-ignorant."""
    dst_path = _render_guard(tmp_path)
    answers = (dst_path / ".copier-answers.agentic.yml").read_text()
    assert "agentic_subtemplate: guard" in answers
    for key in (
        "agentic_project_name",
        "agentic_tracker_cli",
        "agentic_precommit",
    ):
        assert key not in answers


def test_store_docs_are_vendored_and_preferences_seeded(
    tmp_path: Path,
) -> None:
    """Docs travel with the schema (vendored, byte-identical); the
    preference set is seeded once and never overwritten on update."""
    dst_path = _render_guard(tmp_path)
    source = PROJECT_ROOT / "guard" / "docs" / "conventions.md"
    assert (dst_path / "docs" / "conventions.md").read_text() == source.read_text()

    preferences = dst_path / "preferences.md"
    assert "Seeded once by the store subtemplate" in preferences.read_text()
    # Owned by the store: a local edit must survive a re-render.
    preferences.write_text("# Active Preference Set\n\n- my rule\n")
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data={"agentic_subtemplate": "guard"},
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        overwrite=True,
        vcs_ref="HEAD",
    )
    assert preferences.read_text() == "# Active Preference Set\n\n- my rule\n"


def test_default_render_contains_no_guard_files(
    render_project,
) -> None:
    dst_path = render_project()
    assert not (dst_path / ".github" / "guards").exists()
    assert not (dst_path / ".github" / "workflows" / "guards.yml").exists()

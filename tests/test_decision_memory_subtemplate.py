"""Render tests for the decision-memory subtemplate.

Selected by `agentic_subtemplate=decision-memory`, it vendors
everything a store needs — the recorder, the CI guards, the
preference-set lifecycle and the store docs — into a data repo, keyed
by a minimal answers file.
"""

from __future__ import annotations

from pathlib import Path

import copier

PROJECT_ROOT = Path(__file__).parent.parent

STORE_FILES = frozenset(
    {
        ".agents/skills/compact-preferences/SKILL.md",
        ".copier-answers.agentic.yml",
        ".github/guards/decision_validator.py",
        ".github/guards/guards.py",
        ".github/store/README.md",
        ".github/store/budget.py",
        ".github/store/config.py",
        ".github/store/preferences_guard.py",
        ".github/store/replay.py",
        ".github/store/tests/test_store.py",
        ".github/workflows/preferences-budget.yml",
        ".github/workflows/preferences-guard.yml",
        ".github/workflows/guards.yml",
        ".gitignore",
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        "docs/conventions.md",
        "docs/extraction-prompt.md",
        "preferences.md",
        "store.config.json",
        "tools/record.py",
    }
)


def _render_store(tmp_path: Path) -> Path:
    dst_path = tmp_path / "decision-memory"
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data={"agentic_subtemplate": "decision-memory"},
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        # Pin HEAD: with release tags present locally, copier would
        # otherwise render the latest RELEASE instead of this branch.
        vcs_ref="HEAD",
    )
    return dst_path


def test_store_render_produces_exactly_the_store_files(tmp_path: Path) -> None:
    dst_path = _render_store(tmp_path)
    rendered = {
        str(p.relative_to(dst_path)) for p in dst_path.rglob("*") if p.is_file()
    }
    assert rendered == STORE_FILES


def test_vendored_validator_is_byte_identical_to_source(
    tmp_path: Path,
) -> None:
    dst_path = _render_store(tmp_path)
    source_dir = PROJECT_ROOT / "decision-memory" / ".github" / "guards"
    for name in ("decision_validator.py", "guards.py"):
        vendored = (dst_path / ".github" / "guards" / name).read_text()
        assert vendored == (source_dir / name).read_text()


def test_guard_answers_file_is_minimal(tmp_path: Path) -> None:
    """Project-scaffold questions are skipped, so the data repo records
    only the subtemplate choice — it stays consumer-ignorant."""
    dst_path = _render_store(tmp_path)
    answers = (dst_path / ".copier-answers.agentic.yml").read_text()
    assert "agentic_subtemplate: decision-memory" in answers
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
    dst_path = _render_store(tmp_path)
    source = PROJECT_ROOT / "decision-memory" / "docs" / "conventions.md"
    assert (dst_path / "docs" / "conventions.md").read_text() == source.read_text()

    preferences = dst_path / "preferences.md"
    assert "Seeded once by the decision-memory subtemplate" in preferences.read_text()
    # Owned by the store: a local edit must survive a re-render.
    preferences.write_text("# Active Preference Set\n\n- my rule\n")
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data={"agentic_subtemplate": "decision-memory"},
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        overwrite=True,
        vcs_ref="HEAD",
    )
    assert preferences.read_text() == "# Active Preference Set\n\n- my rule\n"


def test_store_render_bridges_claude_skills_to_the_canonical_dir(
    tmp_path: Path,
) -> None:
    """Skills live in `.agents/skills/`; `.claude/` links to them.

    Same bridge the main template renders, so an agent discovers the
    store's skills the way it discovers any other repo's.
    """
    dst_path = _render_store(tmp_path)
    bridge = dst_path / ".claude" / "skills"
    assert bridge.is_symlink(), ".claude/skills must stay a symlink, not a copy"
    assert bridge.readlink().as_posix() == "../.agents/skills"
    assert (bridge / "compact-preferences" / "SKILL.md").is_file()


def test_store_config_survives_a_re_render(tmp_path: Path) -> None:
    """The knobs are the store's to tune, so `copier update` must never
    revert a human's budget back to the template's seed."""
    dst_path = _render_store(tmp_path)
    config = dst_path / "store.config.json"
    tuned = '{"budget_tokens": 1500, "replay_window": 40}\n'
    config.write_text(tuned)
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data={"agentic_subtemplate": "decision-memory"},
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        overwrite=True,
        vcs_ref="HEAD",
    )
    assert config.read_text() == tuned


def test_default_render_contains_no_guard_files(
    render_project,
) -> None:
    dst_path = render_project()
    assert not (dst_path / ".github" / "guards").exists()
    assert not (dst_path / ".github" / "workflows" / "guards.yml").exists()


def test_default_render_contains_no_recorder(
    render_project,
) -> None:
    """The recorder is store tooling: it ships to decision-memory
    stores through the decision-memory subtemplate, never to consumer repos."""
    dst_path = render_project()
    assert not (dst_path / "tools" / "record.py").exists()

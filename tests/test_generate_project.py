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


# Prose that only applies to ghx (the GitHub/Forgejo parity paragraph).
GHX_PARITY_PROSE = "same `gh`-style interface against both GitHub and Forgejo"


def _render(tmp_path: Path, answers: dict[str, str], dst_name: str) -> Path:
    dst_path = tmp_path / dst_name
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data=answers,
        defaults=True,
        unsafe=True,
        skip_tasks=True,
    )
    return dst_path


def test_tracker_cli_default_renders_ghx_docs_and_gh_tea_shims(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Default answer (ghx): ghx-flavored docs, shims for gh and tea only."""
    dst_path = _render(tmp_path, base_answers, "tracker-default")

    _check_file_contents(
        dst_path / "AGENTS.md",
        [
            "Use `ghx` for all repository interaction",
            "`gh` and `tea` are disabled",
            GHX_PARITY_PROSE,
            "`ghx issue create`",
        ],
    )

    shim_dir = dst_path / "scripts" / "agent-shims"
    assert not (shim_dir / "ghx").exists(), "chosen CLI must not be shimmed"
    for shim_name in ("gh", "tea"):
        shim = shim_dir / shim_name
        _check_file_contents(
            shim,
            [f"{shim_name}: disabled — use ghx (see AGENTS.md)", "exit 1"],
        )
        assert shim.stat().st_mode & 0o111, f"shim {shim_name} must be executable"

    _check_file_contents(
        dst_path / "scripts" / "doctor.sh",
        ['warn_tool ghx "not installed'],
    )
    _check_file_contents(
        dst_path / ".copier-answers.agentic.yml",
        ["agentic_tracker_cli: ghx"],
    )


def test_tracker_cli_gh_renders_gh_docs_and_ghx_tea_shims(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Choosing gh: gh-flavored docs without ghx prose, shims for ghx and tea."""
    answers = {**base_answers, "agentic_tracker_cli": "gh"}
    dst_path = _render(tmp_path, answers, "tracker-gh")

    _check_file_contents(
        dst_path / "AGENTS.md",
        [
            "Use `gh` for all repository interaction",
            "`ghx` and `tea` are disabled",
            "`gh issue create`",
        ],
        unexpect_strs=[GHX_PARITY_PROSE],
    )

    shim_dir = dst_path / "scripts" / "agent-shims"
    assert not (shim_dir / "gh").exists(), "chosen CLI must not be shimmed"
    for shim_name in ("ghx", "tea"):
        _check_file_contents(
            shim_dir / shim_name,
            [f"{shim_name}: disabled — use gh (see AGENTS.md)", "exit 1"],
        )

    # gh is already a required host tool, so doctor.sh must not warn on it.
    _check_file_contents(
        dst_path / "scripts" / "doctor.sh",
        unexpect_strs=["warn_tool gh ", "warn_tool ghx", "warn_tool tea"],
    )
    _check_file_contents(
        dst_path / ".copier-answers.agentic.yml",
        ["agentic_tracker_cli: gh"],
    )


def test_claude_settings_put_shims_on_agent_path(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Repo-committed Claude Code config wires the shim dir onto agent PATH."""
    dst_path = _render(tmp_path, base_answers, "tracker-settings")

    _check_file_contents(
        dst_path / ".claude" / "settings.json",
        ["SessionStart", "scripts/enable-agent-shims.sh"],
    )
    hook = dst_path / "scripts" / "enable-agent-shims.sh"
    _check_file_contents(hook, ["scripts/agent-shims", "CLAUDE_ENV_FILE"])
    assert hook.stat().st_mode & 0o111, "PATH hook must be executable"

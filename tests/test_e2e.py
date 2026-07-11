"""End-to-end Copier render tests — full template output in isolated temp dirs."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

import copier
import pytest

PROJECT_ROOT = Path(__file__).parent.parent

# Exact file set the template must produce (no orphans, no omissions).
COMMON_FILES = frozenset(
    {
        ".claude/settings.json",
        ".codespellrc",
        ".copier-answers.agentic.yml",
        ".editorconfig",
        ".markdownlint-cli2.yaml",
        ".yamllint.yaml",
        "AGENTS.md",
        "CLAUDE.md",
        "commitlint.config.mjs",
        "docs/architecture.md",
        "docs/glossary/.markdownlint-cli2.yaml",
        "docs/glossary/snake-farm.md",
        "scripts/agent-shims/gh",
        "scripts/agent-shims/tea",
        "scripts/doctor.sh",
        "scripts/enable-agent-shims.sh",
        "skills-lock.json",
    }
)

EXPECTED_WITH_PREK = COMMON_FILES | {".pre-commit-config.yaml"}
EXPECTED_WITHOUT_PREK = COMMON_FILES


def _relative_file_tree(root: Path) -> frozenset[str]:
    return frozenset(
        path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()
    )


def _assert_tree(root: Path, expected: frozenset[str]) -> None:
    actual = _relative_file_tree(root)
    extra = actual - expected
    missing = expected - actual
    assert not extra, f"Unexpected files rendered: {sorted(extra)}"
    assert not missing, f"Expected files missing: {sorted(missing)}"


def test_e2e_copy_defaults_renders_expected_tree(
    render_project: Callable[..., Path],
) -> None:
    """``copier copy --defaults`` produces exactly the owned file set (prek on)."""
    dst_path = render_project()

    _assert_tree(dst_path, EXPECTED_WITH_PREK)

    agents = (dst_path / "AGENTS.md").read_text()
    assert "# Snake Farm — Agent Guidelines" in agents
    assert "https://github.com/actions-user/snake-farm" in agents
    assert "`prek` must pass on every commit" in agents

    precommit = (dst_path / ".pre-commit-config.yaml").read_text()
    assert "commitlint" in precommit
    assert "check-json" in precommit
    assert "markdownlint-cli2" in precommit
    assert "codespell" in precommit
    assert "commitizen" not in precommit

    answers = (dst_path / ".copier-answers.agentic.yml").read_text()
    assert "agentic_project_slug: snake-farm" in answers
    assert "agentic_precommit: prek" in answers

    doctor = dst_path / "scripts" / "doctor.sh"
    assert doctor.stat().st_mode & 0o111, "doctor.sh must be executable after render"


def test_e2e_copy_precommit_none_renders_expected_tree(
    render_project: Callable[..., Path],
) -> None:
    """``agentic_precommit=none`` omits ``.pre-commit-config.yaml`` entirely."""
    dst_path = render_project(agentic_precommit="none")

    _assert_tree(dst_path, EXPECTED_WITHOUT_PREK)
    assert not (dst_path / ".pre-commit-config.yaml").exists()

    agents = (dst_path / "AGENTS.md").read_text()
    assert "`prek` must pass on every commit" not in agents

    doctor = (dst_path / "scripts" / "doctor.sh").read_text()
    assert "REQUIRED_TOOLS+=(prek)" not in doctor


@pytest.mark.parametrize(
    ("overrides", "slug", "repo_url"),
    [
        (
            {
                "agentic_project_name": "My Cool App",
                "agentic_project_slug": "my-cool-app",
            },
            "my-cool-app",
            "https://github.com/actions-user/my-cool-app",
        ),
        (
            {
                "agentic_forge": "forgejo",
                "agentic_forgejo_host": "git.example.com",
            },
            "snake-farm",
            "https://git.example.com/actions-user/snake-farm",
        ),
    ],
)
def test_e2e_copy_variants_render_clean_tree(
    render_project: Callable[..., Path],
    overrides: dict[str, str],
    slug: str,
    repo_url: str,
) -> None:
    """Variant answers still render the same owned file set with substituted values."""
    dst_path = render_project(**overrides)

    expected = {path.replace("snake-farm", slug) for path in EXPECTED_WITH_PREK}
    _assert_tree(dst_path, frozenset(expected))

    assert repo_url in (dst_path / "AGENTS.md").read_text()
    assert (dst_path / "docs" / "glossary" / f"{slug}.md").exists()


# Host tools the post-render _tasks invoke. Missing any → skip the smoke test
# rather than fail, so the suite stays green on machines without the toolchain.
SMOKE_REQUIRED_TOOLS = ("git", "npx", "uvx", "prek")


def test_e2e_prek_install_registers_git_hooks(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Post-render tasks run ``prek install`` so commits trigger prek hooks.

    Without this, a rendered repo has ``.pre-commit-config.yaml`` but no
    ``.git/hooks/pre-commit`` script, so prek never runs on commit. The task
    only fires inside a git work tree, so we init one before rendering.
    """
    missing = [tool for tool in SMOKE_REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        pytest.skip(f"prek hook test needs host tools on PATH: {missing}")

    dst_path = tmp_path / "hooks"
    dst_path.mkdir()
    subprocess.run(["git", "init"], cwd=dst_path, check=True, capture_output=True)

    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data=base_answers,
        defaults=True,
        unsafe=True,
    )

    hook = dst_path / ".git" / "hooks" / "pre-commit"
    assert hook.exists(), "prek install must register a pre-commit git hook"


def test_e2e_smoke_full_render_runs_tasks(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Full ``copier copy`` (post-render tasks included) yields a clean tree.

    Replaces the manual ``copier copy . /tmp/smoke --defaults --trust`` smoke
    check from the spec: it exercises the real generation path end to end,
    including the ``_tasks`` step that the other e2e tests skip.
    """
    missing = [tool for tool in SMOKE_REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        pytest.skip(f"smoke test needs host tools on PATH: {missing}")

    dst_path = tmp_path / "smoke"
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data=base_answers,
        defaults=True,
        unsafe=True,
    )

    # Post-render tasks add files (e.g. .agents/skills/), so the tree is a
    # superset of the owned set rather than an exact match.
    rendered = _relative_file_tree(dst_path)
    missing = EXPECTED_WITH_PREK - rendered
    assert not missing, f"Smoke render missing owned files: {sorted(missing)}"
    assert (dst_path / ".agents" / "skills").is_dir(), (
        "post-render skills install must populate .agents/skills/"
    )

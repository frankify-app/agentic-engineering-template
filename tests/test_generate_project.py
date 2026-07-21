from __future__ import annotations

from collections.abc import Sequence
import json
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
        # Pin HEAD: with release tags present locally, copier would
        # otherwise render the latest RELEASE instead of this branch
        # (CI checkouts have no tags and already fall back to HEAD).
        vcs_ref="HEAD",
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
        # Pin HEAD: with release tags present locally, copier would
        # otherwise render the latest RELEASE instead of this branch
        # (CI checkouts have no tags and already fall back to HEAD).
        vcs_ref="HEAD",
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


def test_claude_skills_symlink_bridges_agents_skills(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Claude Code loads skills from .claude/skills — shipped as a symlink so
    .agents/skills stays the single canonical location."""
    dst_path = _render(tmp_path, base_answers, "skills-bridge")

    link = dst_path / ".claude" / "skills"
    assert link.is_symlink(), ".claude/skills must be a symlink, not a copy"
    assert link.readlink() == Path("../.agents/skills")

    # Lint configs must exclude the bridged dir, else skill files get linted
    # through the symlink.
    _check_file_contents(dst_path / ".markdownlint-cli2.yaml", [".claude/skills/**"])
    _check_file_contents(dst_path / ".pre-commit-config.yaml", ["\\.claude/skills"])


def test_project_kind_code_renders_code_artifacts(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Default kind (code): coding rules, code skills, and architecture stub."""
    dst_path = _render(tmp_path, base_answers, "kind-code")

    _check_file_contents(
        dst_path / "AGENTS.md",
        [
            "Read [docs/architecture.md](docs/architecture.md)",
            "### Errors",
            "docstring contracts",
            "#### Implement",
            "#### Review",
            "#### Apply Review Comments",
            "## Documentation",
            "| `tdd` ",
            "| `requesting-code-review` ",
            "| `to-tickets` ",
        ],
    )
    assert (dst_path / "docs" / "architecture.md").exists()
    _check_file_contents(
        dst_path / "skills-lock.json",
        ['"tdd"', '"requesting-code-review"', '"to-tickets"'],
    )


def test_project_kind_docs_omits_code_artifacts(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """docs kind: no coding sections, no code skills, no architecture stub."""
    answers = {**base_answers, "agentic_project_kind": "docs"}
    dst_path = _render(tmp_path, answers, "kind-docs")

    _check_file_contents(
        dst_path / "AGENTS.md",
        [
            # Universal core survives the gate.
            "uvx disambiguate==",
            "#### Plan",
            "docs/conventions.md",
            "| `documenting-decisions` ",
            "| `to-spec` ",
        ],
        unexpect_strs=[
            "docs/architecture.md",
            "### Errors",
            "docstring contracts",
            "#### Implement",
            "#### Review",
            "## Documentation",
            "`tdd`",
            "`requesting-code-review`",
            "`to-tickets`",
        ],
    )
    assert not (dst_path / "docs" / "architecture.md").exists()

    lock = json.loads((dst_path / "skills-lock.json").read_text())
    assert set(lock["skills"]) == {
        "caveman",
        "documenting-decisions",
        "domain-modeling",
        "grill-me",
        "grill-with-docs",
        "grilling",
        "to-spec",
        "writing-adrs",
    }


def test_skills_tables_sorted_alphabetically(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Both skills tables stay alphabetically sorted, as AGENTS.md instructs."""
    dst_path = _render(tmp_path, base_answers, "skills-sorted")

    content = (dst_path / "AGENTS.md").read_text()
    skills_section = content.split("## Skills")[1].split("### Repo-Local")[0]
    tables = [
        block
        for block in skills_section.split("\n\n")
        if block.lstrip().startswith("| Skill")
    ]
    assert len(tables) == 2, "expected a universal and a code-specific table"
    for table in tables:
        names = [
            line.split("`")[1] for line in table.splitlines() if line.startswith("| `")
        ]
        assert names, f"no skill rows found in table:\n{table}"
        assert names == sorted(names), f"skills table not sorted: {names}"


def test_conventions_file_seeded_once_and_never_overwritten(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """docs/conventions.md is seeded, then left alone on re-render."""
    dst_path = _render(tmp_path, base_answers, "conventions")

    conventions = dst_path / "docs" / "conventions.md"
    _check_file_contents(conventions, ["Snake Farm — Project Conventions"])

    conventions.write_text("# Hand-written vault rules\n")
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=dst_path,
        data=base_answers,
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        overwrite=True,
        vcs_ref="HEAD",
    )
    assert conventions.read_text() == "# Hand-written vault rules\n"


def test_language_non_english_omits_codespell(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Non-English content: no codespell hook, no .codespellrc."""
    answers = {**base_answers, "agentic_language": "de"}
    dst_path = _render(tmp_path, answers, "lang-de")

    assert not (dst_path / ".codespellrc").exists()
    _check_file_contents(
        dst_path / ".pre-commit-config.yaml",
        ["disambiguate-lint"],
        unexpect_strs=["codespell"],
    )
    _check_file_contents(
        dst_path / ".copier-answers.agentic.yml",
        ["agentic_language: de"],
    )


def test_disambiguate_version_pins_hook_and_docs_commands(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """The pinned disambiguate version flows into AGENTS.md and the prek hook."""
    answers = {**base_answers, "agentic_disambiguate_version": "0.9.9"}
    dst_path = _render(tmp_path, answers, "disambiguate-pin")

    _check_file_contents(
        dst_path / "AGENTS.md",
        ["uvx disambiguate==0.9.9"],
        unexpect_strs=["uvx disambiguate <term>", "uvx disambiguate --from"],
    )
    _check_file_contents(
        dst_path / ".pre-commit-config.yaml",
        [
            "disambiguate-lint",
            "entry: uvx disambiguate==0.9.9 --lint",
            "files: ^docs/glossary/",
        ],
    )


def test_disambiguate_roots_default_renders_bare_lint(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Empty roots answer (default): hook entry stays bare `--lint`."""
    dst_path = _render(tmp_path, base_answers, "disambiguate-roots-default")

    precommit = (dst_path / ".pre-commit-config.yaml").read_text()
    entry_lines = [
        line for line in precommit.splitlines() if "entry: uvx disambiguate" in line
    ]
    assert len(entry_lines) == 1, f"Expected one disambiguate entry: {entry_lines}"
    assert entry_lines[0].endswith("--lint"), (
        f"Default must render bare --lint, got: {entry_lines[0]!r}"
    )


def test_disambiguate_roots_answer_appends_lint_args(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """A roots answer is appended verbatim to the hook's `--lint` entry."""
    roots = "docs/glossary/ --roots docs/conventions.md 'docs/notes/*.md'"
    answers = {**base_answers, "agentic_disambiguate_roots": roots}
    dst_path = _render(tmp_path, answers, "disambiguate-roots")

    _check_file_contents(
        dst_path / ".pre-commit-config.yaml",
        [f"--lint {roots}"],
    )
    # Roots survive `copier update` as data in the answers file.
    _check_file_contents(
        dst_path / ".copier-answers.agentic.yml",
        ["agentic_disambiguate_roots:"],
    )


def test_github_forge_ships_template_update_workflow(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """GitHub forge: scheduled copier-update workflow rendered verbatim."""
    dst_path = _render(tmp_path, base_answers, "updater-github")

    _check_file_contents(
        dst_path / ".github" / "workflows" / "template-update.yml",
        [
            "workflow_dispatch",
            "copier update",
            "--defaults --trust --skip-tasks",
            "copier-template-extensions",
            "actions/create-github-app-token",
            "RELEASE_BOT_CLIENT_ID",
            "RELEASE_BOT_PRIVATE_KEY",
            "chore/template-update-",
            # GitHub expressions must survive rendering (file is not Jinja).
            "${{ steps.app-token.outputs.token }}",
        ],
    )


def test_forgejo_forge_ships_no_github_workflow(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Forgejo forge: no .github directory — the updater is GitHub-only."""
    answers = {
        **base_answers,
        "agentic_forge": "forgejo",
        "agentic_forgejo_host": "git.example.com",
    }
    dst_path = _render(tmp_path, answers, "updater-forgejo")

    assert not (dst_path / ".github").exists()


def test_grilling_pinned_to_frankify_derivation(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """`grilling` pins the frankify-app/skills derivation, not upstream."""
    dst_path = _render(tmp_path, base_answers, "grilling-pin")

    lock = json.loads((dst_path / "skills-lock.json").read_text())
    grilling = lock["skills"]["grilling"]
    assert grilling["source"] == "frankify-app/skills"
    assert grilling["skillPath"] == "derived/grilling/SKILL.md"


def test_decision_memory_repo_env_var_contract(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """DECISION_MEMORY_REPO is an env-var-only contract: no copier question,
    no value in any committed artifact (.copier-answers* included); AGENTS.md
    documents the contract and doctor.sh checks the env var."""
    # Even if a consumer passes a URL as copier data, it must render nowhere.
    stray_url = "https://github.com/acme/decision-memory"
    answers = {**base_answers, "agentic_decision_memory_repo": stray_url}
    dst_path = _render(tmp_path, answers, "decision-memory")

    for path in dst_path.rglob("*"):
        if path.is_file():
            assert stray_url not in path.read_text(), (
                f"DECISION_MEMORY_REPO value leaked into {path}"
            )

    # Not an init-time answer: no question, so nothing recorded on update.
    _check_file_contents(
        dst_path / ".copier-answers.agentic.yml",
        unexpect_strs=["decision_memory"],
    )
    _check_file_contents(
        dst_path / "AGENTS.md",
        ["DECISION_MEMORY_REPO", "skips recording"],
    )
    _check_file_contents(
        dst_path / "scripts" / "doctor.sh",
        ["DECISION_MEMORY_REPO", 'git ls-remote "$DECISION_MEMORY_REPO"'],
    )


def test_copier_has_no_decision_memory_question() -> None:
    """The template must never ask for the decision-memory URL at init time."""
    copier_yml = (PROJECT_ROOT / "copier.yml").read_text()
    assert "decision_memory" not in copier_yml


def test_github_forge_ships_lint_workflow_with_prek_job(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """GitHub forge + prek: lint workflow with marker check and prek jobs."""
    dst_path = _render(tmp_path, base_answers, "lint-github-prek")

    _check_file_contents(
        dst_path / ".github" / "workflows" / "lint.yml",
        [
            "pull_request",
            "cancel-in-progress: true",
            "git grep -nE",
            "::error::",
            ":!.agents/skills",
            "uvx prek run --all-files --show-diff-on-failure",
            "astral-sh/setup-uv",
            # GitHub expressions must survive Jinja rendering.
            "${{ github.ref }}",
        ],
    )


def test_lint_workflow_without_prek_keeps_marker_check(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """agentic_precommit=none: marker check stays (guards the updater
    contract), the prek job is omitted."""
    answers = {**base_answers, "agentic_precommit": "none"}
    dst_path = _render(tmp_path, answers, "lint-github-none")

    _check_file_contents(
        dst_path / ".github" / "workflows" / "lint.yml",
        ["git grep -nE", "::error::"],
        unexpect_strs=["prek"],
    )

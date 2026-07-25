"""Render tests for the skills source-trust policy (#58).

Vendored skills are executable instructions running with full agent
permissions, so an install that fetches latest from every source is a
remote-write channel into every future session. Trust is per SOURCE
repo: sources whose changes already passed our review gate auto-update;
everything else is quarantined for a human.
"""

from __future__ import annotations

import json
from pathlib import Path

import copier

PROJECT_ROOT = Path(__file__).parent.parent


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
        # otherwise render the latest RELEASE instead of this branch.
        vcs_ref="HEAD",
    )
    return dst_path


def test_policy_file_seeds_the_trusted_source(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    dst_path = _render(tmp_path, base_answers, "policy")

    policy = json.loads((dst_path / "skills-policy.json").read_text())

    assert policy["trustedSources"] == ["frankify-app/skills"]


def test_update_wrapper_is_rendered_executable(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    dst_path = _render(tmp_path, base_answers, "wrapper")

    wrapper = dst_path / "scripts" / "update-skills.py"

    assert wrapper.exists()
    assert wrapper.stat().st_mode & 0o111, "wrapper must be executable"


def test_update_workflow_has_two_lanes_and_gates_the_untrusted_one(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Trusted drift may auto-merge; untrusted drift never may.

    The whole policy reduces to this asymmetry, so it is asserted on the
    rendered workflow rather than trusted to prose.
    """
    dst_path = _render(tmp_path, base_answers, "workflow")

    workflow = (dst_path / ".github" / "workflows" / "skills-update.yml").read_text()

    assert "scripts/update-skills.py" in workflow
    assert "skills-auto" in workflow
    assert "needs-human-review" in workflow
    # Auto-merge belongs to the trusted lane only.
    trusted_lane, _, untrusted_lane = workflow.partition("needs-human-review")
    assert "auto-merge" in trusted_lane
    assert "auto-merge" not in untrusted_lane


def test_codeowners_guards_vendored_skills(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    """Branch protection, not convention, is what stops an unreviewed merge."""
    dst_path = _render(tmp_path, base_answers, "codeowners")

    codeowners = (dst_path / ".github" / "CODEOWNERS").read_text()

    assert ".agents/skills/" in codeowners


def test_agents_doc_forbids_calling_the_installer_directly(
    tmp_path: Path,
    base_answers: dict[str, str],
) -> None:
    dst_path = _render(tmp_path, base_answers, "agents-doc")

    agents = (dst_path / "AGENTS.md").read_text()

    assert "update-skills.py" in agents
    assert "experimental_install" in agents

"""The repo root must match what `template/` renders.

This repo is the template AND uses itself as a template, so root files
with a `template/` counterpart are render output. That is also the only
way the shared glossary terms become lintable: they live under
`template/`, which is never a glossary root, and only become real terms
once stamped into this repo's own `docs/glossary/`.

A stale stamp therefore means the glossary being linted is not the
glossary being shipped, which is why this is a gate rather than a
convention.
"""

from __future__ import annotations

from pathlib import Path
import re

import copier
import yaml

PROJECT_ROOT = Path(__file__).parent.parent

# Root paths that deliberately diverge from the render. Everything NOT
# listed here must match, so adding a template file forces a decision:
# adopt it at root, or list it with a reason.
DELIBERATE_DIVERGENCE = {
    # Carries jinja lint hooks the generated config must not have.
    ".pre-commit-config.yaml": "template-development hooks",
    # Globs *.md.jinja so the template's own sources are linted.
    ".markdownlint-cli2.yaml": "lints jinja sources",
    # This repo has its own ci.yml/release.yml; the rendered workflows
    # target generated repos, not the template itself.
    ".github/workflows/lint.yml": "repo has its own CI",
    ".github/workflows/template-update.yml": "template does not update itself",
    # The template is not stamped from another template.
    ".copier-answers.agentic.yml": "not a generated repo",
    # Agent settings here are repo-local, not the generated defaults.
    ".claude/settings.json": "repo-local agent settings",
}


def _skip_if_exists_paths() -> set[str]:
    """Paths copier seeds once and never overwrites.

    These can never match after seeding, so they are excluded
    structurally rather than listed as a choice.
    """
    config = yaml.safe_load((PROJECT_ROOT / "copier.yml").read_text())
    paths: set[str] = set()
    for entry in config.get("_skip_if_exists", []):
        # Entries are jinja-guarded per subtemplate, e.g.
        # "{% if ... %}docs/conventions.md{% endif %}" — keep the literal
        # text between the tags.
        for literal in re.findall(r"%\}([^{]+)\{%", entry):
            if literal.strip():
                paths.add(literal.strip())
        if "{%" not in entry and entry.strip():
            paths.add(entry.strip())
    return paths


def test_repo_root_matches_the_rendered_template(tmp_path: Path) -> None:
    render = tmp_path / "self"
    copier.run_copy(
        src_path=str(PROJECT_ROOT),
        dst_path=render,
        data={
            "agentic_project_name": "Agentic Engineering Template",
            "agentic_project_description": (
                "Copier template for agentic engineering scaffolding"
            ),
            "agentic_project_slug": "agentic-engineering-template",
            "agentic_repo_owner": "frankify-app",
        },
        defaults=True,
        unsafe=True,
        skip_tasks=True,
        vcs_ref="HEAD",
    )

    excluded = set(DELIBERATE_DIVERGENCE) | _skip_if_exists_paths()
    stale: list[str] = []
    missing: list[str] = []

    for rendered in sorted(render.rglob("*")):
        if not rendered.is_file():
            continue
        relative = rendered.relative_to(render).as_posix()
        if relative in excluded:
            continue
        root_file = PROJECT_ROOT / relative
        if not root_file.is_file():
            missing.append(relative)
        elif root_file.read_bytes() != rendered.read_bytes():
            stale.append(relative)

    assert not stale, (
        f"Root files differ from the template render: {stale}. "
        "Re-run the self-application step (docs/conventions.md)."
    )
    assert not missing, (
        f"Rendered files absent from the repo root: {missing}. "
        "Adopt them, or add them to DELIBERATE_DIVERGENCE with a reason."
    )

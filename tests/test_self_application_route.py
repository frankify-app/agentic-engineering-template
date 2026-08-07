"""The provenance half of self-application (#130).

`test_self_application` asks whether the root MATCHES the render;
these ask how it got there. The distinction is the whole point of the
guard: the commit that motivated the ticket produced a byte-identical
tree to the correct two-commit route, so state could not tell them
apart and only the diff could.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import load_module

PROJECT_ROOT = Path(__file__).parent.parent
route = load_module(
    "self_application", PROJECT_ROOT / "scripts" / "dev" / "self_application.py"
)


@pytest.mark.parametrize(
    ("source", "stamp"),
    [
        # A jinja source and its rendered root file.
        ("template/AGENTS.md.jinja", "AGENTS.md"),
        # Copied verbatim, no jinja suffix — the shape of the commit
        # that prompted this guard.
        ("template/scripts/ci/check_gate.py", "scripts/ci/check_gate.py"),
        # A conditional path segment renders to the literal inside it.
        (
            "template/{% if agentic_forge == 'github' %}.github{% endif %}"
            "/workflows/ci-ok.yml.jinja",
            ".github/workflows/ci-ok.yml",
        ),
        # A conditional FILE name, jinja-suffixed.
        (
            "template/docs/{% if agentic_project_kind == 'code' %}architecture.md{% endif %}.jinja",
            "docs/architecture.md",
        ),
    ],
)
def test_stamp_of_maps_a_source_to_its_render(source: str, stamp: str) -> None:
    assert route.stamp_of(source) == stamp


@pytest.mark.parametrize(
    "path",
    [
        # Outside the template: a stamp is not a source.
        "AGENTS.md",
        "tests/test_self_application.py",
        # Only a render can resolve an answer interpolated into a name,
        # so this pair is not knowable here and is not guessed at.
        "template/docs/glossary/{{ agentic_project_slug }}.md.jinja",
    ],
)
def test_stamp_of_declines_what_it_cannot_know(path: str) -> None:
    assert route.stamp_of(path) is None


def test_editing_a_source_and_its_stamp_together_is_the_violation() -> None:
    """The #129 shape: one commit hand-editing both halves."""
    found = route.route_violations(["template/AGENTS.md.jinja", "AGENTS.md"])
    assert found == [("template/AGENTS.md.jinja", "AGENTS.md")]


def test_both_legs_of_the_documented_route_stay_quiet() -> None:
    """The correct two-commit route, judged one commit at a time."""
    template_leg = [
        "template/AGENTS.md.jinja",
        "template/scripts/ci/check_gate.py",
        "copier.yml",
        "tests/test_ci_gate.py",
    ]
    restamp_leg = ["AGENTS.md", "scripts/ci/check_gate.py"]
    assert route.route_violations(template_leg) == []
    assert route.route_violations(restamp_leg) == []


def test_a_deliberate_divergence_may_be_edited_with_its_source() -> None:
    """Listed paths are not render output, so no route applies to them."""
    assert (
        route.route_violations(
            [
                "template/{% if agentic_precommit == 'prek' %}.pre-commit-config.yaml{% endif %}.jinja",
                ".pre-commit-config.yaml",
            ]
        )
        == []
    )


def test_every_violation_is_reported_not_just_the_first() -> None:
    found = route.route_violations(
        [
            "template/AGENTS.md.jinja",
            "AGENTS.md",
            "template/scripts/ci/check_gate.py",
            "scripts/ci/check_gate.py",
        ]
    )
    assert found == [
        ("template/AGENTS.md.jinja", "AGENTS.md"),
        ("template/scripts/ci/check_gate.py", "scripts/ci/check_gate.py"),
    ]


def test_a_seeded_file_is_not_render_output() -> None:
    """`_skip_if_exists` paths stop being output the moment they exist,
    so this repo's own conventions doc may be edited beside the template
    source that once seeded it.
    """
    assert (
        route.route_violations(
            ["template/docs/conventions.md.jinja", "docs/conventions.md"]
        )
        == []
    )


def test_the_seeded_list_reads_the_same_without_a_yaml_parser() -> None:
    """The guard reads copier.yml with no dependency so a commit hook
    never fails for want of one; this pins that reading against a real
    parse of the same block.
    """
    state_test = load_module(
        "test_self_application", PROJECT_ROOT / "tests" / "test_self_application.py"
    )
    parsed = route.skip_if_exists((PROJECT_ROOT / "copier.yml").read_text())
    assert parsed == state_test._skip_if_exists_paths()
    assert parsed, "the block is not empty, so an empty parse means a broken reader"


def test_the_divergence_list_has_one_home() -> None:
    """The state check reads this module's list rather than keeping its
    own; a second copy would drift into a different idea of divergence.

    Both halves are asserted, because either alone passes for the wrong
    reason: equal contents today says nothing about a literal that can
    drift tomorrow, and an absent literal says nothing about what the
    state check ended up reading.
    """
    state_test = load_module(
        "test_self_application", PROJECT_ROOT / "tests" / "test_self_application.py"
    )
    assert state_test.DELIBERATE_DIVERGENCE == route.DELIBERATE_DIVERGENCE
    source = (PROJECT_ROOT / "tests" / "test_self_application.py").read_text()
    assert "DELIBERATE_DIVERGENCE = {" not in source

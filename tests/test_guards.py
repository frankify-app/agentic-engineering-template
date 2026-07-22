"""Tests for the pure functions of the vendored CI guard (guards.py)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import load_module

PROJECT_ROOT = Path(__file__).parent.parent
GUARDS_PATH = PROJECT_ROOT / "guard" / ".github" / "guards" / "guards.py"

guards = load_module("guards", GUARDS_PATH)


def test_commit_subjects_of_the_repo_types_pass() -> None:
    for subject in (
        "decision(factory): repo hosting — private GitHub over self-hosted",
        "pref-proposal: prefers CI-enforced integrity over access control",
        "pref-promote: rejects new infrastructure dependencies",
        "pref-confirm: rejects new infrastructure dependencies (n=4)",
        "chore: initialize repository",
        "chore(ci): tighten guards",
    ):
        assert guards.check_commit_subject(subject) is None, subject


def test_foreign_commit_subjects_fail() -> None:
    for subject in (
        "feat: add a feature",
        "decision: missing project scope",
        "decision(factory): no separator between slug and chosen",
        "pref-confirm: missing counter suffix",
        "update stuff",
    ):
        assert guards.check_commit_subject(subject) is not None, subject


def test_pref_confirm_counter_math_accepts_single_bump() -> None:
    removed = ["- Rejects new deps. [confirmed: 3, last: 2026-07-15]"]
    added = ["- Rejects new deps. [confirmed: 4, last: 2026-07-21]"]
    assert guards.validate_pref_confirm_change(removed, added) == []


def test_pref_confirm_counter_math_rejects_bad_increment() -> None:
    removed = ["- Rejects new deps. [confirmed: 3, last: 2026-07-15]"]
    added = ["- Rejects new deps. [confirmed: 5, last: 2026-07-21]"]
    errors = guards.validate_pref_confirm_change(removed, added)
    assert any("increment" in e for e in errors)


def test_pref_confirm_counter_math_rejects_text_change() -> None:
    removed = ["- Rejects new deps. [confirmed: 3, last: 2026-07-15]"]
    added = ["- Accepts new deps. [confirmed: 4, last: 2026-07-21]"]
    errors = guards.validate_pref_confirm_change(removed, added)
    assert any("rule text" in e for e in errors)


def test_pref_confirm_counter_math_rejects_line_removal() -> None:
    removed = ["- Rejects new deps. [confirmed: 3, last: 2026-07-15]"]
    errors = guards.validate_pref_confirm_change(removed, [])
    assert errors


def test_parse_unified_diff_pairs_changed_lines() -> None:
    diff = (
        "diff --git a/preferences.md b/preferences.md\n"
        "--- a/preferences.md\n"
        "+++ b/preferences.md\n"
        "@@ -5 +5 @@\n"
        "-- Old rule. [confirmed: 1, last: 2026-07-15]\n"
        "+- Old rule. [confirmed: 2, last: 2026-07-21]\n"
    )
    removed, added = guards.parse_unified_diff(diff)
    assert removed == ["- Old rule. [confirmed: 1, last: 2026-07-15]"]
    assert added == ["- Old rule. [confirmed: 2, last: 2026-07-21]"]

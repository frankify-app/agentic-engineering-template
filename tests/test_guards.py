"""Tests for the pure functions of the vendored CI guard (guards.py)."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import load_module

PROJECT_ROOT = Path(__file__).parent.parent
GUARDS_PATH = PROJECT_ROOT / "decision-memory" / ".github" / "guards" / "guards.py"

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
    removed = ["- Rejects new deps. [confirmed: 3, independent: 0, last: 2026-07-15]"]
    added = ["- Rejects new deps. [confirmed: 4, independent: 0, last: 2026-07-21]"]
    assert guards.validate_pref_confirm_change(removed, added) == []


def test_pref_confirm_counter_math_rejects_bad_increment() -> None:
    removed = ["- Rejects new deps. [confirmed: 3, independent: 0, last: 2026-07-15]"]
    added = ["- Rejects new deps. [confirmed: 5, independent: 0, last: 2026-07-21]"]
    errors = guards.validate_pref_confirm_change(removed, added)
    assert any("increment" in e for e in errors)


def test_pref_confirm_counter_math_rejects_text_change() -> None:
    removed = ["- Rejects new deps. [confirmed: 3, independent: 0, last: 2026-07-15]"]
    added = ["- Accepts new deps. [confirmed: 4, independent: 0, last: 2026-07-21]"]
    errors = guards.validate_pref_confirm_change(removed, added)
    assert any("rule text" in e for e in errors)


def test_pref_confirm_counter_math_rejects_line_removal() -> None:
    removed = ["- Rejects new deps. [confirmed: 3, independent: 0, last: 2026-07-15]"]
    errors = guards.validate_pref_confirm_change(removed, [])
    assert errors


def test_parse_unified_diff_pairs_changed_lines() -> None:
    diff = (
        "diff --git a/preferences.md b/preferences.md\n"
        "--- a/preferences.md\n"
        "+++ b/preferences.md\n"
        "@@ -5 +5 @@\n"
        "-- Old rule. [confirmed: 1, independent: 0, last: 2026-07-15]\n"
        "+- Old rule. [confirmed: 2, independent: 0, last: 2026-07-21]\n"
    )
    removed, added = guards.parse_unified_diff(diff)
    assert removed == ["- Old rule. [confirmed: 1, independent: 0, last: 2026-07-15]"]
    assert added == ["- Old rule. [confirmed: 2, independent: 0, last: 2026-07-21]"]


# --- metadata suffix grammar -----------------------------------------


def test_suffix_keys_may_appear_in_any_order() -> None:
    removed = ["- A rule. [last: 2026-07-15, independent: 0, confirmed: 3]"]
    added = ["- A rule. [independent: 0, last: 2026-07-21, confirmed: 4]"]
    assert guards.validate_pref_confirm_change(removed, added) == []


def test_an_unknown_suffix_key_is_rejected() -> None:
    error = guards.decision_validator.check_metadata_suffix(
        "- A rule. [confirmed: 3, independent: 0, last: 2026-07-15, src: x]"
    )
    assert error and "src" in error


# --- the independent counter -----------------------------------------


def test_a_bump_may_raise_independent_by_one() -> None:
    removed = ["- A rule. [confirmed: 3, independent: 1, last: 2026-07-15]"]
    added = ["- A rule. [confirmed: 4, independent: 2, last: 2026-07-21]"]
    assert guards.validate_pref_confirm_change(removed, added) == []


def test_a_bump_may_not_lower_independent() -> None:
    removed = ["- A rule. [confirmed: 3, independent: 2, last: 2026-07-15]"]
    added = ["- A rule. [confirmed: 4, independent: 1, last: 2026-07-21]"]
    errors = guards.validate_pref_confirm_change(removed, added)
    assert errors and "independent" in errors[0]


def test_a_rule_without_independent_is_rejected() -> None:
    removed = ["- A rule. [confirmed: 3, last: 2026-07-15]"]
    added = ["- A rule. [confirmed: 4, last: 2026-07-21]"]
    errors = guards.validate_pref_confirm_change(removed, added)
    assert errors and "independent" in errors[0]


def test_independent_may_not_exceed_confirmed() -> None:
    # Independent confirmations are a subset of all of them, so a
    # suffix claiming more of the subset than the whole is incoherent
    # regardless of how it got there.
    error = guards.decision_validator.check_metadata_suffix(
        "- A rule. [confirmed: 2, independent: 3, last: 2026-07-15]"
    )
    assert error and "independent" in error


def test_a_rule_set_missing_counters_fails_the_corpus_check() -> None:
    # Deliberately NOT run against this repo's own preferences.md: the
    # template ships the seed, which has no rules, so the same assertion
    # there would pass for as long as the file stays empty and prove
    # nothing. The live store runs this guard over its real file.
    text = (
        "## Process\n\n"
        "- A counted rule. [confirmed: 1, independent: 0, last: 2026-07-15]\n"
        "- A rule someone hand-added without counters.\n"
    )
    errors = [
        error
        for error in map(
            guards.decision_validator.check_metadata_suffix, guards._rule_bullets(text)
        )
        if error
    ]
    assert len(errors) == 1
    assert "hand-added" in errors[0]


def test_a_wrapped_rule_is_checked_as_one_bullet() -> None:
    # The suffix sits on the entry's last line, so a check that looked
    # at lines rather than entries would report every continuation line
    # as a rule missing its counters.
    text = (
        "## Heading\n\n"
        "- A rule that runs onto\n"
        "  a second line. [confirmed: 1, independent: 0, last: 2026-07-15]\n"
    )
    assert len(guards._rule_bullets(text)) == 1
    assert (
        guards.decision_validator.check_metadata_suffix(guards._rule_bullets(text)[0])
        is None
    )

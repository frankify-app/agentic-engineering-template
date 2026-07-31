"""CI guard for the decision-memory repo.

Copier-vendored from the agentic-engineering-template decision-memory subtemplate
(single shared source with the writer tool's validation — both import
decision_validator.py, which lives next to this file). Stdlib only:
the guard must keep working even if the template repo disappears.

Checks, per PR (run with --base <base-sha> from a full checkout):

1. Append-only: no modify/delete/rename under decisions/** or
   predictions/**; line
   removals in preferences.md only from pref-confirm/pref-promote/
   pref-compact commits, with pref-confirm counter math validated
   mechanically.
2. Full-corpus schema check: EVERY decisions/*.json and
   predictions/*.json validates (not just added files), so guard
   updates re-validate the entire corpus.
3. Dangling-reference check across the corpus.
4. Token budget on preferences.md, against the repo-local budget.
5. Commit lint: every PR commit subject uses one of the repo's own
   types (decision/prediction/pref-proposal/pref-promote/
   pref-confirm/pref-compact/pref-drift/pref-extract/chore).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "store"),
)

import config as store_config  # noqa: E402  (path bootstrap above)
import decision_validator  # noqa: E402  (path bootstrap above)

# Match-side of the repo's own commit types. Grammar authority:
# docs/conventions.md (§ Commit types, vendored with this file); the
# writer composes these subjects in record.py.
COMMIT_SUBJECT_RES = (
    re.compile(r"^decision\([a-z0-9][a-z0-9-]*\): .+ — .+$"),
    re.compile(r"^prediction\([a-z0-9][a-z0-9-]*\): .+ — .+$"),
    re.compile(r"^pref-proposal: .+$"),
    re.compile(r"^pref-promote: .+$"),
    re.compile(r"^pref-confirm: .+ \(n=\d+\)$"),
    re.compile(r"^pref-compact: .+$"),
    re.compile(r"^pref-drift: .+$"),
    re.compile(r"^pref-extract: .+$"),
    re.compile(r"^chore(\([\w-]+\))?: .+$"),
)

parse_metadata = decision_validator.parse_metadata
strip_metadata = decision_validator.strip_metadata
counter_of = decision_validator.counter_of
COUNTER_KEY = decision_validator.COUNTER_KEY
INDEPENDENT_KEY = decision_validator.INDEPENDENT_KEY

# The types permitted to REMOVE lines from preferences.md. Promotion and
# compaction are different acts on the same file: promotion adds a rule a
# human decided to adopt (and may demote another to make room); compaction
# rewrites the set without adding anything that was not already promoted.
# Typing them apart is what lets a reader tell one from the other in the
# log — the human gate on both is the merge, not the commit subject.
PREF_EDIT_TYPES = ("pref-confirm:", "pref-promote:", "pref-compact:")


def check_commit_subject(subject: str) -> str | None:
    """Return an error string if the subject matches none of the repo's
    commit types, else None."""
    if any(pattern.match(subject) for pattern in COMMIT_SUBJECT_RES):
        return None
    return (
        f"commit subject {subject!r} matches none of the repo's types: "
        "decision(<project>): <slug> — <chosen> | "
        "prediction(<project>): <slug> — <chosen> | pref-proposal: | "
        "pref-promote: | pref-confirm: ... (n=N) | pref-compact: | "
        "pref-drift: | pref-extract: | chore:"
    )


def parse_unified_diff(diff_text: str) -> tuple[list[str], list[str]]:
    """Split a unified diff into (removed_lines, added_lines), without
    the +/- prefixes and without file headers."""
    removed: list[str] = []
    added: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            removed.append(line[1:])
        elif line.startswith("+"):
            added.append(line[1:])
    return removed, added


def validate_pref_confirm_change(removed: list[str], added: list[str]) -> list[str]:
    """Validate the counter math of a pref-confirm commit's
    preferences.md diff: only paired counter-line updates, rule text
    unchanged, counter incremented by exactly 1."""
    errors: list[str] = []
    if len(removed) != len(added):
        errors.append(
            "pref-confirm: must only update counter lines "
            f"({len(removed)} removed vs {len(added)} added)"
        )
        return errors
    for old, new in zip(removed, added):
        old_count = counter_of(old)
        new_count = counter_of(new)
        if old_count is None or new_count is None:
            errors.append(
                "pref-confirm: changed a line without a "
                f"[{COUNTER_KEY}: N, ...] suffix: {old!r} -> {new!r}"
            )
            continue
        if strip_metadata(old) != strip_metadata(new):
            errors.append(f"pref-confirm: rule text changed: {old!r} -> {new!r}")
        if new_count != old_count + 1:
            errors.append(
                "pref-confirm: counter must increment by exactly 1: "
                f"{old_count} -> {new_count}"
            )
        errors.extend(_check_suffix_rest(old, new))
    return errors


def _check_suffix_rest(old: str, new: str) -> list[str]:
    """The part of the suffix that is not the counter or its date.

    `independent` is a second count, earned differently: it rises only
    when a confirmation was NOT the rule crediting itself. A bump may
    move it by at most one and never downwards, since lowering it under
    a mechanical subject would erase evidence as routine bookkeeping.
    """
    old_ind = _int_or_none((parse_metadata(old) or {}).get(INDEPENDENT_KEY))
    new_ind = _int_or_none((parse_metadata(new) or {}).get(INDEPENDENT_KEY))
    if old_ind is None or new_ind is None:
        return [
            f"pref-confirm: every rule carries {INDEPENDENT_KEY}; "
            f"{old!r} -> {new!r} is missing it"
        ]
    if new_ind not in (old_ind, old_ind + 1):
        return [
            f"pref-confirm: {INDEPENDENT_KEY} moved {old_ind} -> {new_ind}; a bump "
            "may hold it or raise it by exactly 1"
        ]
    return []


def _rule_bullets(text: str) -> list[str]:
    """Each `- ` rule in preferences.md, wrapped lines rejoined.

    A rule may span several lines with its suffix on the last, so the
    check has to see the whole entry rather than one line of it.
    """
    bullets: list[str] = []
    current: list[str] | None = None
    for line in text.splitlines():
        if line.startswith("- "):
            if current is not None:
                bullets.append(" ".join(current))
            current = [line.strip()]
        elif current is not None:
            if not line.strip() or line.startswith("#"):
                bullets.append(" ".join(current))
                current = None
            else:
                current.append(line.strip())
    if current is not None:
        bullets.append(" ".join(current))
    return bullets


def _int_or_none(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout


APPEND_ONLY_DIRS = (
    f"{decision_validator.STORE_DIR}/",
    f"{decision_validator.PREDICTIONS_DIR}/",
)


def check_append_only(base: str) -> list[str]:
    """No modify/delete/rename ever touches a recorded ruling.

    Predictions are covered too: an agent's recorded choice is the
    input a counterfactual replay reads, and a corpus that can be
    quietly rewritten cannot support one.
    """
    errors: list[str] = []
    diff = _git("diff", "--name-status", "--find-renames", f"{base}...HEAD")
    for line in diff.splitlines():
        parts = line.split("\t")
        status = parts[0]
        paths = parts[1:]
        touched = [p for p in paths if p.startswith(APPEND_ONLY_DIRS)]
        if touched and status != "A":
            directory = touched[0].split("/", 1)[0]
            errors.append(
                f"append-only: {directory}/ change {status} {' '.join(paths)} "
                "— existing records are never modified, deleted, or renamed"
            )
    return errors


def check_commits(base: str) -> list[str]:
    """Commit lint + preferences.md edit discipline, per commit."""
    errors: list[str] = []
    shas = _git("rev-list", "--no-merges", "--reverse", f"{base}..HEAD").split()
    for sha in shas:
        subject = _git("log", "-1", "--format=%s", sha).strip()
        subject_error = check_commit_subject(subject)
        if subject_error:
            errors.append(f"{sha[:9]}: {subject_error}")

        pref_diff = _git(
            "show", "--format=", "--unified=0", sha, "--", "preferences.md"
        )
        removed, added = parse_unified_diff(pref_diff)
        if not removed:
            continue
        if not subject.startswith(PREF_EDIT_TYPES):
            errors.append(
                f"{sha[:9]}: removes lines from preferences.md but is not "
                "a pref-confirm/pref-promote/pref-compact commit"
            )
        elif subject.startswith("pref-confirm:"):
            errors.extend(
                f"{sha[:9]}: {e}" for e in validate_pref_confirm_change(removed, added)
            )
    return errors


def _check_records_in(root: str, directory: str, records: dict[str, dict]) -> list[str]:
    """Validate every record in one corpus directory.

    Records from both directories share the ID namespace and the link
    graph, so they accumulate into one ``records`` map: a prediction
    may reference a decision, and a dangling link is dangling either
    way.
    """
    errors: list[str] = []
    path_dir = os.path.join(root, directory)
    if not os.path.isdir(path_dir):
        return errors
    for name in sorted(os.listdir(path_dir)):
        if name.startswith("."):
            continue
        path = os.path.join(path_dir, name)
        if not name.endswith(".json"):
            errors.append(f"{path}: non-JSON file in {directory}/")
            continue
        stem = name[: -len(".json")]
        try:
            with open(path, encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: unreadable or invalid JSON: {exc}")
            continue
        errors.extend(
            f"{path}: {e}"
            for e in decision_validator.validate_record(record, filename_stem=stem)
        )
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            records[record["id"]] = record
    return errors


def check_corpus(root: str = ".") -> list[str]:
    """Validate BOTH record corpora + refs + token budget.

    The token budget comes from the repo-local `store.config.json`
    (`budget_tokens`), not from a constant in this file: the budget is
    per-principal, and a second authority for it would only ever
    disagree with the first. `decision_validator`'s constant is the
    DEFAULT that config falls back to when a store ships no file.
    """
    errors: list[str] = []
    records: dict[str, dict] = {}
    try:
        config = store_config.load_config(root)
    except store_config.ConfigError as exc:
        return [str(exc)]
    for directory in (decision_validator.STORE_DIR, decision_validator.PREDICTIONS_DIR):
        errors.extend(_check_records_in(root, directory, records))
    errors.extend(decision_validator.validate_corpus(records))
    preferences_path = os.path.join(root, "preferences.md")
    if os.path.isfile(preferences_path):
        with open(preferences_path, encoding="utf-8") as handle:
            preferences_text = handle.read()
        errors.extend(
            decision_validator.check_preferences_budget(
                preferences_text, int(config["budget_tokens"])
            )
        )
        # Every rule carries its counters. A rule that lost them reads
        # as one nobody has ever confirmed, which is the same shape the
        # counters exist to distinguish.
        errors.extend(
            f"preferences.md: {error}"
            for error in map(
                decision_validator.check_metadata_suffix,
                _rule_bullets(preferences_text),
            )
            if error
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        required=True,
        help="base SHA of the PR (github.event.pull_request.base.sha)",
    )
    args = parser.parse_args(argv)

    errors = check_append_only(args.base) + check_commits(args.base) + check_corpus()
    for error in errors:
        print(f"GUARD FAIL: {error}")
    if not errors:
        print("All guards passed.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

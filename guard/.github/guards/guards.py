"""CI guard for the decision-memory repo.

Copier-vendored from the agentic-engineering-template guard subtemplate
(single shared source with the writer tool's validation — both import
decision_validator.py, which lives next to this file). Stdlib only:
the guard must keep working even if the template repo disappears.

Checks, per PR (run with --base <base-sha> from a full checkout):

1. Append-only: no modify/delete/rename under decisions/**; line
   removals in preferences.md only from pref-confirm/pref-promote
   commits, with pref-confirm counter math validated mechanically.
2. Full-corpus schema check: EVERY decisions/*.json validates (not
   just added files), so guard updates re-validate the entire corpus.
3. Dangling-reference check across the corpus.
4. Token budget on preferences.md.
5. Commit lint: every PR commit subject uses one of the repo's own
   types (decision/pref-proposal/pref-promote/pref-confirm/chore).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import decision_validator  # noqa: E402  (path bootstrap above)

# Match-side of the repo's own commit types. Grammar authority:
# docs/conventions.md (§ Commit types, vendored with this file); the
# writer composes these subjects in record.py.
COMMIT_SUBJECT_RES = (
    re.compile(r"^decision\([a-z0-9][a-z0-9-]*\): .+ — .+$"),
    re.compile(r"^pref-proposal: .+$"),
    re.compile(r"^pref-promote: .+$"),
    re.compile(r"^pref-confirm: .+ \(n=\d+\)$"),
    re.compile(r"^chore(\([\w-]+\))?: .+$"),
)

COUNTER_RE = decision_validator.COUNTER_RE

PREF_EDIT_TYPES = ("pref-confirm:", "pref-promote:")


def check_commit_subject(subject: str) -> str | None:
    """Return an error string if the subject matches none of the repo's
    commit types, else None."""
    if any(pattern.match(subject) for pattern in COMMIT_SUBJECT_RES):
        return None
    return (
        f"commit subject {subject!r} matches none of the repo's types: "
        "decision(<project>): <slug> — <chosen> | pref-proposal: | "
        "pref-promote: | pref-confirm: ... (n=N) | chore:"
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
        old_match = COUNTER_RE.search(old)
        new_match = COUNTER_RE.search(new)
        if not old_match or not new_match:
            errors.append(
                "pref-confirm: changed a line without a "
                f"[confirmed: N, last: DATE] counter: {old!r} -> {new!r}"
            )
            continue
        if COUNTER_RE.sub("", old) != COUNTER_RE.sub("", new):
            errors.append(f"pref-confirm: rule text changed: {old!r} -> {new!r}")
        if int(new_match.group(1)) != int(old_match.group(1)) + 1:
            errors.append(
                "pref-confirm: counter must increment by exactly 1: "
                f"{old_match.group(1)} -> {new_match.group(1)}"
            )
    return errors


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout


def check_append_only(base: str) -> list[str]:
    """No modify/delete/rename ever touches existing decision records."""
    errors: list[str] = []
    diff = _git("diff", "--name-status", "--find-renames", f"{base}...HEAD")
    for line in diff.splitlines():
        parts = line.split("\t")
        status = parts[0]
        paths = parts[1:]
        if any(p.startswith("decisions/") for p in paths) and not (status == "A"):
            errors.append(
                f"append-only: decisions/ change {status} {' '.join(paths)} "
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
                "a pref-confirm/pref-promote commit"
            )
        elif subject.startswith("pref-confirm:"):
            errors.extend(
                f"{sha[:9]}: {e}" for e in validate_pref_confirm_change(removed, added)
            )
    return errors


def check_corpus() -> list[str]:
    """Validate the ENTIRE decisions/ corpus + refs + token budget."""
    errors: list[str] = []
    records: dict[str, dict] = {}
    decisions_dir = "decisions"
    if os.path.isdir(decisions_dir):
        for name in sorted(os.listdir(decisions_dir)):
            if name.startswith("."):
                continue
            path = os.path.join(decisions_dir, name)
            if not name.endswith(".json"):
                errors.append(f"{path}: non-JSON file in decisions/")
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
        errors.extend(decision_validator.validate_corpus(records))
    if os.path.isfile("preferences.md"):
        with open("preferences.md", encoding="utf-8") as handle:
            errors.extend(decision_validator.check_preferences_budget(handle.read()))
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

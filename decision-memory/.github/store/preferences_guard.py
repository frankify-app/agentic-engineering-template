"""PR guard for `preferences.md`.

Copier-vendored from the agentic-engineering-template guard
subtemplate — change it there, pull via `copier update`.

Sits on top of the record guard (`.github/guards/guards.py`), which
stays untouched and keeps enforcing append-only `decisions/`, the
schema, and its own hard token backstop. This layer adds the three
rules the compaction flow needs:

1. **Carve-out label.** Editing an EXISTING line in `preferences.md`
   requires the carve-out label on the PR. Pure additions never need
   it; mechanical `pref-confirm` counter bumps are exempt (the vendored
   guard already validates their counter math). `decisions/` gets NO
   carve-out — append-only there is absolute, and this guard never
   touches that rule.
2. **Replay regression.** A carve-out PR must carry a replay report in
   its description, gated `pass`, and produced against the exact
   `preferences.md` in the PR head — the report embeds the file's
   sha256, so a stale report from an earlier round fails.
3. **Budget.** A PR that touches `preferences.md` fails when the file
   is over 100% of the repo-local budget; at or above the warn
   threshold it prints a warning but passes.

The git-facing parts are thin adapters; the decisions live in pure
functions so they are testable without a fixture repo.

Stdlib only. Usage (see .github/workflows/preferences-guard.yml):

    python .github/store/preferences_guard.py \
        --base <sha> --labels "a,b" --body-file body.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guards"),
)

import budget as store_budget  # noqa: E402  (path bootstrap above)
import config as store_config  # noqa: E402  (path bootstrap above)
import guards  # noqa: E402  (path bootstrap above; vendored, read-only)

PREFERENCES_FILENAME = store_budget.PREFERENCES_FILENAME

REPLAY_MARKER = "<!-- replay-report -->"
_REPLAY_FENCE_RE = re.compile(
    re.escape(REPLAY_MARKER) + r"\s*```(?:json)?\s*\n(.*?)\n```",
    re.DOTALL,
)


def preferences_sha256(text: str) -> str:
    """Content address of a preference set — what ties a replay report
    to the exact rules it was scored against."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_pref_commits(commits: list[dict]) -> tuple[bool, list[str]]:
    """Decide whether a PR's commits edit EXISTING preference lines.

    ``commits`` is a list of ``{"sha", "subject", "pref_diff"}`` dicts,
    oldest first. Returns ``(carve_out_required, notes)``.
    """
    required = False
    notes: list[str] = []
    for commit in commits:
        removed, added = guards.parse_unified_diff(commit["pref_diff"])
        if not removed:
            continue
        short = commit["sha"][:9]
        subject = commit["subject"]
        if subject.startswith("pref-confirm:"):
            if not guards.validate_pref_confirm_change(removed, added):
                notes.append(f"{short}: mechanical pref-confirm counter bump — exempt")
                continue
        required = True
        notes.append(
            f"{short}: rewrites {len(removed)} existing preferences.md "
            f"line(s) ({subject!r})"
        )
    return required, notes


def extract_replay_report(body: str) -> tuple[dict | None, str | None]:
    """Pull the replay report out of a PR description.

    Returns ``(report, error)`` — exactly one is None.
    """
    match = _REPLAY_FENCE_RE.search(body or "")
    if not match:
        return None, (
            "no replay report in the PR description: add a "
            f"{REPLAY_MARKER} marker followed by a ```json fence holding the "
            "output of `replay.py gate`"
        )
    try:
        report = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return None, f"replay report is not valid JSON: {exc}"
    if not isinstance(report, dict):
        return None, "replay report must be a JSON object"
    return report, None


def check_replay_report(body: str, head_preferences: str) -> list[str]:
    """Validate the replay report of a carve-out PR."""
    report, error = extract_replay_report(body)
    if error:
        return [error]
    assert report is not None
    errors: list[str] = []
    gate = report.get("gate")
    if gate != "pass":
        errors.append(
            f"replay report gate is {gate!r}, not 'pass' — the compacted rule "
            "set must not degrade the preference-driven hit rate"
        )
    reported = report.get("candidate_preferences_sha256")
    actual = preferences_sha256(head_preferences)
    if reported != actual:
        errors.append(
            "replay report was produced against a different preferences.md "
            f"(report {str(reported)[:12]}… vs head {actual[:12]}…) — re-run "
            "the replay after the last edit"
        )
    return errors


def evaluate(
    *,
    commits: list[dict],
    labels: list[str],
    body: str,
    head_preferences: str,
    preferences_touched: bool,
    config: dict,
) -> tuple[list[str], list[str]]:
    """Pure core: return ``(errors, notes)`` for one PR."""
    errors: list[str] = []
    carve_out_required, notes = classify_pref_commits(commits)
    label = config["carve_out_label"]

    if carve_out_required:
        if label not in labels:
            errors.append(
                f"preferences.md: existing lines were edited without the "
                f"{label!r} label — only a labelled compaction PR may rewrite "
                "the active set (counter bumps via pref-confirm are exempt)"
            )
        else:
            errors.extend(check_replay_report(body, head_preferences))
    elif label in labels:
        notes.append(
            f"{label!r} label present but no existing line was edited — nothing to gate"
        )

    status = store_budget.budget_status(head_preferences, config)
    notes.append(store_budget.status_line(status))
    if status["level"] == store_budget.LEVEL_OVER:
        if preferences_touched:
            errors.append(
                f"preferences.md: {status['percent']}% of the "
                f"{status['budget_tokens']}-token budget — PRs touching the "
                "file are blocked until it is compacted back under budget"
            )
        else:
            notes.append(
                "preferences.md is over budget; this PR does not touch it, so "
                "it is not blocked"
            )
    elif status["level"] == store_budget.LEVEL_WARN:
        notes.append(
            "compression due: at or above the warn threshold — run the compaction skill"
        )
    return errors, notes


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=True)
    return result.stdout


def collect_commits(base: str) -> list[dict]:
    """Every non-merge PR commit with its `preferences.md` diff."""
    commits: list[dict] = []
    for sha in _git("rev-list", "--no-merges", "--reverse", f"{base}..HEAD").split():
        commits.append(
            {
                "sha": sha,
                "subject": _git("log", "-1", "--format=%s", sha).strip(),
                "pref_diff": _git(
                    "show", "--format=", "--unified=0", sha, "--", PREFERENCES_FILENAME
                ),
            }
        )
    return commits


def preferences_touched(base: str) -> bool:
    changed = _git("diff", "--name-only", f"{base}...HEAD").split("\n")
    return PREFERENCES_FILENAME in [name.strip() for name in changed]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="base SHA of the PR")
    parser.add_argument("--labels", default="", help="comma-separated PR label names")
    parser.add_argument("--body-file", help="file holding the PR description")
    parser.add_argument("--root", default=".", help="repo root (default: cwd)")
    args = parser.parse_args(argv)

    try:
        config = store_config.load_config(args.root)
    except store_config.ConfigError as exc:
        print(f"GUARD FAIL: {exc}")
        return 1

    body = ""
    if args.body_file and os.path.isfile(args.body_file):
        with open(args.body_file, encoding="utf-8") as handle:
            body = handle.read()

    errors, notes = evaluate(
        commits=collect_commits(args.base),
        labels=[name.strip() for name in args.labels.split(",") if name.strip()],
        body=body,
        head_preferences=store_budget.read_preferences(args.root),
        preferences_touched=preferences_touched(args.base),
        config=config,
    )
    for note in notes:
        print(f"note: {note}")
    for error in errors:
        print(f"GUARD FAIL: {error}")
    if not errors:
        print("Preference guards passed.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

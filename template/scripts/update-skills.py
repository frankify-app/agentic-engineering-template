#!/usr/bin/env python3
"""
Guarded skills install: auto-update trusted sources, quarantine the rest.

Vendored skills are executable instructions that run with full agent
permissions, so `skills … install` — which fetches latest from EVERY
source — is a remote-write channel into every future agent session.

Trust is a property of the SOURCE repo, not of a hash: a source whose
changes already pass a human review gate upstream (our own skills repo)
can auto-update, because the review already happened. Everything else is
held at the vendored state until a human reads the diff.

Drift is detected by comparing CONTENT, never `computedHash`: the lock is
a manifest that the installer rewrites to match whatever it just fetched,
so its hash carries no integrity signal.

Exit codes: 0 = nothing quarantined; 1 = untrusted drift was reverted and
written to the review report; 2 = the install itself failed.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

POLICY_FILE = Path("skills-policy.json")
LOCK_FILE = Path("skills-lock.json")
SKILLS_DIR = Path(".agents/skills")
REPORT_FILE = Path("skills-review.md")
INSTALL_CMD = ["npx", "--yes", "skills@latest", "experimental_install"]


def trusted_sources() -> set[str]:
    """Read the trusted-source allowlist; absent policy trusts nothing."""
    if not POLICY_FILE.exists():
        return set()
    policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    return set(policy.get("trustedSources", []))


def read_lock() -> dict:
    """Return the lock as a dict; a missing lock reads as empty."""
    if not LOCK_FILE.exists():
        return {"skills": {}}
    return json.loads(LOCK_FILE.read_text(encoding="utf-8"))


def skill_files(root: Path) -> dict[str, str]:
    """Map relative path -> text for every file under `root`."""
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def content_diff(before: Path, after: Path, name: str) -> str:
    """Unified diff of a skill's files, for the human reading the report."""
    old, new = skill_files(before), skill_files(after)
    chunks: list[str] = []
    for rel in sorted(set(old) | set(new)):
        if old.get(rel) == new.get(rel):
            continue
        chunks.extend(
            difflib.unified_diff(
                old.get(rel, "").splitlines(keepends=True),
                new.get(rel, "").splitlines(keepends=True),
                fromfile=f"a/{name}/{rel}",
                tofile=f"b/{name}/{rel}",
            )
        )
    return "".join(chunks)


def write_report(quarantined: list[dict]) -> None:
    """Write the review report for skills held back from the vendored tree."""
    lines = [
        "# Skills awaiting review",
        "",
        "These changes come from sources that are NOT in "
        "`skills-policy.json`'s `trustedSources`, so they were reverted to "
        "the vendored state rather than applied.",
        "",
        "Skills are executable instructions with full agent permissions. "
        "Read each diff for instructions that escalate access, touch "
        "credentials, reach external services, or countermand existing "
        "rules — not just for style.",
        "",
        "To accept a change: apply the diff deliberately, or add its source "
        "to `trustedSources` if every change to that source already passes "
        "a review gate you control.",
        "",
    ]
    for item in quarantined:
        lines += [
            f"## `{item['name']}` — from `{item['source']}`",
            "",
            item["summary"],
            "",
        ]
        if item["diff"]:
            lines += ["```diff", item["diff"].rstrip("\n"), "```", ""]
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


def restore(name: str, snapshot_root: Path) -> None:
    """Put a skill's vendored directory back exactly as it was."""
    current = SKILLS_DIR / name
    previous = snapshot_root / name
    if current.exists():
        shutil.rmtree(current)
    if previous.exists():
        shutil.copytree(previous, current)


def main() -> int:
    """Run the installer, then revert anything from an untrusted source."""
    allowed = trusted_sources()
    before_lock = read_lock()

    with tempfile.TemporaryDirectory() as tmp:
        snapshot_root = Path(tmp) / "skills"
        if SKILLS_DIR.is_dir():
            shutil.copytree(SKILLS_DIR, snapshot_root)
        else:
            snapshot_root.mkdir(parents=True)

        result = subprocess.run(INSTALL_CMD, check=False)  # noqa: S603
        if result.returncode != 0:
            print("update-skills: installer failed", file=sys.stderr)
            return 2

        after_lock = read_lock()
        quarantined: list[dict] = []

        for name in sorted(after_lock.get("skills", {})):
            entry = after_lock["skills"][name]
            source = entry.get("source", "<unknown>")
            if source in allowed:
                continue

            previous_entry = before_lock.get("skills", {}).get(name)
            diff = content_diff(snapshot_root / name, SKILLS_DIR / name, name)

            if previous_entry is None:
                # First-time vendoring is the highest-risk moment, not just
                # updates: nobody has ever read this skill.
                summary = (
                    f"New skill vendored from an untrusted source "
                    f"(`{source}`). Removed pending review."
                )
                if (SKILLS_DIR / name).exists():
                    shutil.rmtree(SKILLS_DIR / name)
                after_lock["skills"].pop(name, None)
            elif diff:
                summary = "Upstream changed the vendored content. Reverted."
                restore(name, snapshot_root)
                after_lock["skills"][name] = previous_entry
            else:
                continue

            quarantined.append(
                {"name": name, "source": source, "summary": summary, "diff": diff}
            )

    if quarantined:
        LOCK_FILE.write_text(json.dumps(after_lock, indent=2) + "\n", encoding="utf-8")
        write_report(quarantined)
        names = ", ".join(item["name"] for item in quarantined)
        print(
            f"update-skills: quarantined {len(quarantined)} skill(s): {names}\n"
            f"update-skills: see {REPORT_FILE}",
            file=sys.stderr,
        )
        return 1

    if REPORT_FILE.exists():
        REPORT_FILE.unlink()
    print("update-skills: no untrusted drift")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

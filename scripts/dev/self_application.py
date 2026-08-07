#!/usr/bin/env python3
"""The self-application route, enforced at the commit boundary (#130).

This repo is the template AND uses itself as a template, so a root file
with a `template/` counterpart is render OUTPUT. The route is: edit the
source, commit it, render, then adopt the render as a separate restamp
commit (docs/conventions.md - Template-First Changes).

`tests/test_self_application.py` compares the root against the render,
which is a statement about STATE. The route is about PROVENANCE, and no
content comparison can check it: when a hand-edit happens to produce
exactly what the render would have produced, the state is valid and
there is nothing to detect. The commit is the only place where the
information still exists, so that is where this looks. Under the
documented route a commit touches sources or stamps, never both -- one
touching both is a hand-edit or a mixed commit, and both are already
forbidden.

Repo-local by construction: the rule exists only where `template/`
does, and a generated repo has no template directory to violate.

With no arguments it judges the staged diff, which is the prek hook.
With `--range BASE..HEAD` it judges every commit in that range, which
is CI -- hooks only run in clones that installed them.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

TEMPLATE = "template"
CONVENTIONS = "docs/conventions.md - Template-First Changes"

# Root paths that deliberately diverge from the render. Everything NOT
# listed here must match, so adding a template file forces a decision:
# adopt it at root, or list it with a reason.
#
# Lives here rather than in the test that reads it: the state test and
# this route guard need the same list, and a commit hook must not have
# to import a test module (and through it copier) to know it.
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

# `{% if agentic_forge == 'github' %}.github{% endif %}` renders to the
# literal between the tags for this repo's own answers.
CONDITIONAL = re.compile(r"\{%.*?%\}")

# One entry of copier's `_skip_if_exists` list, as written in copier.yml.
SKIP_ENTRY = re.compile(r"^\s*-\s*[\"']?(.+?)[\"']?\s*$")


def skip_if_exists(copier_yml: str) -> set[str]:
    """Paths copier seeds once and never overwrites.

    Read without a YAML parser on purpose: this runs inside a commit
    hook, on whatever `python3` the contributor has, and a dependency
    there would make the guard the reason a commit cannot be made. The
    block is a flat list of strings, which is exactly as much YAML as
    this needs to understand. `tests/test_self_application_route`
    pins the result against a real parse.

    Seeded files stop being render output the moment they exist, so the
    route does not apply to them — the state check excludes them for
    the same reason.
    """
    paths: set[str] = set()
    collecting = False
    for line in copier_yml.splitlines():
        if line.startswith("_skip_if_exists:"):
            collecting = True
            continue
        if collecting:
            if line and not line[0].isspace():
                break
            if line.lstrip().startswith("#"):
                continue
            match = SKIP_ENTRY.match(line)
            if not match:
                continue
            entry = match.group(1)
            literal = CONDITIONAL.sub("", entry).strip()
            if literal:
                paths.add(literal)
    return paths


def stamp_of(path: str) -> str | None:
    """The root file `path` stamps to, or None when there is no pair.

    None covers three cases, all of them "this is not a source with a
    knowable stamp": a path outside `template/`, a name interpolating an
    answer (`{{ agentic_project_slug }}.md`) that only a render can
    resolve, and a conditional segment that leaves nothing behind.
    """
    prefix = f"{TEMPLATE}/"
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix) :]
    if "{{" in rest:
        return None
    rest = CONDITIONAL.sub("", rest)
    if rest.endswith(".jinja"):
        rest = rest[: -len(".jinja")]
    parts = [part for part in rest.split("/") if part]
    return "/".join(parts) or None


def route_violations(
    paths: list[str], exempt: set[str] | None = None
) -> list[tuple[str, str]]:
    """(source, stamp) pairs this set of paths carries, in path order.

    Pure over plain data: the caller decides whether the paths came from
    a staged diff or a commit, and the same rule judges both. `exempt`
    defaults to the paths no route applies to — those that deliberately
    diverge, and those copier seeds once.
    """
    if exempt is None:
        exempt = exempt_paths()
    touched = set(paths)
    found = []
    for path in sorted(touched):
        stamp = stamp_of(path)
        if stamp is None or stamp in exempt:
            continue
        if stamp in touched:
            found.append((path, stamp))
    return found


def exempt_paths(root: str = ".") -> set[str]:
    """Root paths the route does not govern, from both reasons at once."""
    try:
        with open(f"{root}/copier.yml", encoding="utf-8") as handle:
            seeded = skip_if_exists(handle.read())
    except OSError:
        # Not the template repo (or not its root): nothing here stamps
        # anything, and the guard has no business inventing pairs.
        seeded = set()
    return set(DELIBERATE_DIVERGENCE) | seeded


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def staged_paths() -> list[str]:
    """Paths in the index — empty outside a commit, so `--all-files`
    runs of the hook are a silent no-op rather than a false alarm."""
    return [
        line for line in git("diff", "--cached", "--name-only").splitlines() if line
    ]


def commits_in(rev_range: str) -> list[str]:
    return [
        line for line in git("rev-list", "--reverse", rev_range).splitlines() if line
    ]


def commit_paths(sha: str) -> list[str]:
    """Paths one commit changed. A merge commit reports nothing here,
    which is right: it introduces no edit of its own to attribute."""
    changed = git(
        "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", "--first-parent", sha
    )
    return [line for line in changed.splitlines() if line]


def report(where: str, violations: list[tuple[str, str]]) -> None:
    print(f"{where} edits a template source and its own stamp:", file=sys.stderr)
    for source, stamp in violations:
        print(f"  {source}", file=sys.stderr)
        print(f"  {stamp}   <- render output of the line above", file=sys.stderr)
    print(
        f"\nThe stamp is render output, never hand-edited ({CONVENTIONS}).\n"
        "Split this: commit the template change alone, render the template "
        "from that commit, and adopt the render as a separate restamp commit.",
        file=sys.stderr,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--range",
        dest="rev_range",
        help="judge every commit in BASE..HEAD instead of the staged diff",
    )
    # prek passes filenames to hooks that ask for them; this one reads
    # the diff itself, so anything else on the line is accepted and
    # ignored rather than turned into a usage error mid-commit.
    parser.add_argument("paths", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if not args.rev_range:
        violations = route_violations(staged_paths())
        if violations:
            report("this commit", violations)
            return 1
        return 0

    failed = False
    for sha in commits_in(args.rev_range):
        violations = route_violations(commit_paths(sha))
        if violations:
            report(f"commit {sha[:9]}", violations)
            failed = True
    if failed:
        return 1
    print(f"Every commit in {args.rev_range} kept sources and stamps apart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

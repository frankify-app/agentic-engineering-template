"""The uniform CI gate's decision logic (#137, #143).

The scripts' pure functions are imported straight from the template
copy; API access is a thin layer these tests never touch. The copies
in the repo root and the store subtemplates are pinned byte-identical,
template-first, like every other multi-copy file here.
"""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_COPY = ROOT / "template" / "scripts" / "ci" / "check_gate.py"

spec = importlib.util.spec_from_file_location("check_gate", TEMPLATE_COPY)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

KEYWORDS = json.loads(
    (
        ROOT
        / "template"
        / "{% if agentic_forge == 'github' %}.github{% endif %}"
        / "reference-keywords.json"
    ).read_text()
)


# ------------------------------------------------------------- ticket


def ticket(body, branch="claude/7-thing", labels=(), author="pando-ramet"):
    return gate.ticket_violations(body, branch, list(labels), author, KEYWORDS)


def test_canonical_caps_reference_passes():
    problems, escaped = ticket("CLOSES #7.\n\nDetails follow.")
    assert problems == [] and not escaped


def test_cross_repo_and_advances_pass():
    problems, _ = ticket("FIXES pandoscope/skills#7 and ADVANCES #7")
    assert problems == []


def test_lowercase_native_keyword_fails_even_beside_a_canonical_one():
    problems, _ = ticket("CLOSES #7, and this also closes #9")
    assert any("closes #9" in p for p in problems)


def test_unlisted_native_keyword_fails_in_any_case():
    problems, _ = ticket("CLOSES #7. Resolves #9 too.")
    assert any("Resolves #9" in p for p in problems)


def test_wrong_case_of_our_own_keyword_fails():
    problems, _ = ticket("Advances #7")
    assert any("Advances #7" in p for p in problems)


def test_no_reference_at_all_fails():
    problems, _ = ticket("A change with no ticket named.")
    assert any("no canonical ticket reference" in p for p in problems)


def test_branch_numbers_must_appear_in_the_body():
    problems, _ = ticket("CLOSES #7", branch="claude/7-9-two-tickets")
    assert any("ticket 9" in p for p in problems)


def test_non_claude_branch_carries_no_branch_constraint():
    problems, _ = ticket("CLOSES #7", branch="chore/template-update-v9.9.9")
    assert problems == []


def test_branch_pattern_and_marker_come_from_the_central_file():
    custom = dict(KEYWORDS, branch_pattern=r"agent/(\d+)-")
    problems, _ = gate.ticket_violations("CLOSES #7", "agent/9-thing", [], "x", custom)
    assert any("ticket 9" in p for p in problems)
    threads = [thread("pando-genet", ("pando-ramet", "Kein Commit: doc-only."))]
    assert (
        gate.review_violations(
            threads, "pando-ramet", SHAS, "https://github.com", marker="Kein Commit:"
        )
        == []
    )


def test_automated_escape_is_bot_only():
    _, escaped = ticket("", labels=["automated"], author="pandoscope-release-bot[bot]")
    assert escaped
    problems, escaped = ticket("", labels=["automated"], author="pando-ramet")
    assert not escaped and problems


# ------------------------------------------------------------ reviews


def thread(opener, *replies, path="core.mjs"):
    comments = [{"id": 1, "user": {"login": opener}, "body": "concern", "path": path}]
    comments += [
        {"id": i + 2, "in_reply_to_id": 1, "user": {"login": login}, "body": body}
        for i, (login, body) in enumerate(replies)
    ]
    return comments


SHAS = ["5e1f03edb10baf9e7ad0dfa8d9c36dfdc055a13b"]


def test_verified_commit_url_answers_a_thread():
    threads = [
        thread(
            "pando-genet",
            (
                "pando-ramet",
                "Fixed in https://github.com/o/r/commit/5e1f03edb10baf9e7ad0dfa8d9c36dfdc055a13b",
            ),
        )
    ]
    assert (
        gate.review_violations(
            threads, "pando-ramet", SHAS, "https://github.com", "No commit:"
        )
        == []
    )


def test_bare_hash_or_wrong_sha_does_not_answer():
    hash_only = [thread("pando-genet", ("pando-ramet", "Fixed in 5e1f03e"))]
    wrong = [
        thread(
            "pando-genet",
            (
                "pando-ramet",
                "Fixed in https://github.com/o/r/commit/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            ),
        )
    ]
    assert gate.review_violations(
        hash_only, "pando-ramet", SHAS, "https://github.com", "No commit:"
    )
    assert gate.review_violations(
        wrong, "pando-ramet", SHAS, "https://github.com", "No commit:"
    )


def test_no_commit_marker_answers_but_loose_wording_does_not():
    marked = [thread("pando-genet", ("pando-ramet", "No commit: doc-only concern."))]
    loose = [thread("pando-genet", ("pando-ramet", "no commit was needed here"))]
    assert (
        gate.review_violations(
            marked, "pando-ramet", SHAS, "https://github.com", "No commit:"
        )
        == []
    )
    assert gate.review_violations(
        loose, "pando-ramet", SHAS, "https://github.com", "No commit:"
    )


def test_own_and_bot_threads_are_not_gated():
    threads = [thread("pando-ramet"), thread("some-scanner[bot]")]
    assert (
        gate.review_violations(
            threads, "pando-ramet", SHAS, "https://github.com", "No commit:"
        )
        == []
    )


def test_a_reply_from_someone_else_does_not_answer():
    threads = [
        thread(
            "pando-genet",
            (
                "pando-other",
                "https://github.com/o/r/commit/5e1f03edb10baf9e7ad0dfa8d9c36dfdc055a13b",
            ),
        )
    ]
    assert gate.review_violations(
        threads, "pando-ramet", SHAS, "https://github.com", "No commit:"
    )


def test_threads_group_by_root():
    comments = [
        {"id": 1, "user": {"login": "a"}, "body": "x", "path": "f"},
        {"id": 2, "in_reply_to_id": 1, "user": {"login": "b"}, "body": "y"},
        {"id": 3, "user": {"login": "a"}, "body": "z", "path": "g"},
    ]
    assert [len(t) for t in gate.thread_of(comments)] == [2, 1]


# ---------------------------------------------------------- aggregate


def test_pr_workflows_discovered_including_bare_on_and_yaml_1_1_on():
    assert gate.expects_pr_run("on: [pull_request, push]\njobs: {}\n")
    assert gate.expects_pr_run("on:\n  pull_request:\njobs: {}\n")
    assert gate.expects_pr_run(
        "on:\n  pull_request:\n    types: [opened, synchronize]\njobs: {}\n"
    )


def test_narrow_types_and_other_triggers_are_not_awaited():
    assert not gate.expects_pr_run(
        "on:\n  pull_request:\n    types: [opened]\njobs: {}\n"
    )
    assert not gate.expects_pr_run(
        "on:\n  schedule:\n    - cron: '0 0 * * 0'\njobs: {}\n"
    )


def test_red_dependency_makes_the_gate_red_and_skipped_is_not_passed():
    runs = {"wf/a.yml": {"id": 1, "status": "completed"}}
    jobs = {
        1: [
            {"name": "test", "conclusion": "failure"},
            {"name": "lint", "conclusion": "skipped"},
        ]
    }
    pending, failures = gate.aggregate_verdict(["wf/a.yml"], runs, lambda i: jobs[i])
    assert pending == [] and len(failures) == 2


def test_missing_or_running_workflows_are_pending_not_failed():
    runs = {"wf/a.yml": {"id": 1, "status": "in_progress"}}
    pending, failures = gate.aggregate_verdict(
        ["wf/a.yml", "wf/b.yml"], runs, lambda i: []
    )
    assert len(pending) == 2 and failures == []


def test_all_green_run_passes():
    runs = {"wf/a.yml": {"id": 1, "status": "completed"}}
    jobs = {1: [{"name": "test", "conclusion": "success"}]}
    assert gate.aggregate_verdict(["wf/a.yml"], runs, lambda i: jobs[i]) == ([], [])


def test_own_run_judged_by_siblings_and_never_waits_for_itself():
    jobs = [
        {"name": "ci-ok", "status": "in_progress", "conclusion": None},
        {"name": "ticket", "status": "completed", "conclusion": "success"},
        {"name": "review answers", "status": "in_progress", "conclusion": None},
    ]
    pending, failures = gate.own_verdict(jobs)
    assert len(pending) == 1 and failures == []
    jobs[2] = {"name": "review answers", "status": "completed", "conclusion": "failure"}
    pending, failures = gate.own_verdict(jobs)
    assert pending == [] and len(failures) == 1


# ------------------------------------------------- copies stay pinned


def test_gate_script_copies_are_byte_identical_template_first():
    source = TEMPLATE_COPY.read_bytes()
    for copy in (
        ROOT / "scripts" / "ci" / "check_gate.py",
        ROOT / "decision-memory" / "scripts" / "ci" / "check_gate.py",
        ROOT / "evidence-memory" / "scripts" / "ci" / "check_gate.py",
    ):
        assert copy.read_bytes() == source, f"{copy} drifted from the template copy"


def test_store_keyword_files_are_byte_identical_to_the_template():
    source = (
        ROOT
        / "template"
        / "{% if agentic_forge == 'github' %}.github{% endif %}"
        / "reference-keywords.json"
    ).read_bytes()
    for copy in (
        ROOT / ".github" / "reference-keywords.json",
        ROOT / "decision-memory" / ".github" / "reference-keywords.json",
        ROOT / "evidence-memory" / ".github" / "reference-keywords.json",
    ):
        assert copy.read_bytes() == source, f"{copy} drifted from the template copy"


def test_store_gate_workflows_are_identical_and_unticketed():
    dm = (
        ROOT / "decision-memory" / ".github" / "workflows" / "ci-ok.yml.jinja"
    ).read_text()
    em = (
        ROOT / "evidence-memory" / ".github" / "workflows" / "ci-ok.yml.jinja"
    ).read_text()
    assert dm == em
    assert "ticket" not in dm.split("jobs:")[1].split("review-answers")[0]
    template = (
        ROOT
        / "template"
        / "{% if agentic_forge == 'github' %}.github{% endif %}"
        / "workflows"
        / "ci-ok.yml.jinja"
    ).read_text()
    assert "check_gate.py ticket" in template
    # The comments carry the central file's ACTUAL values, injected at
    # render time — the rendered root copy shows the marker itself and
    # no jinja residue, so readers never chase an indirection.
    assert "reference_keywords()" in template
    root_copy = (ROOT / ".github" / "workflows" / "ci-ok.yml").read_text()
    assert KEYWORDS["no_commit_marker"] in root_copy
    assert "{%" not in root_copy and "reference_keywords" not in root_copy

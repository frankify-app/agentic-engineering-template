"""Session mechanics: what a recording session's PR ends up containing.

These behaviors live entirely in the IO shell and decide the blast
radius of a session, so they are exercised against a real git fixture
rather than mocked.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.conftest import load_module

PROJECT_ROOT = Path(__file__).parent.parent
RECORDER = PROJECT_ROOT / "guard" / "tools" / "record.py"


def git(cwd: Path, *args: str) -> str:
    """Run git in `cwd`, failing loudly with its stderr."""
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


@pytest.fixture
def parked_store(tmp_path: Path) -> Path:
    """A store checkout sitting on someone else's unmerged branch.

    The normal state of a reused checkout, and the #64 trap: anything
    committed on that branch rides along into the next session unless
    the session branch is based on the default branch instead.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--quiet", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
    )
    store = tmp_path / "decision-memory"
    subprocess.run(
        ["git", "clone", "--quiet", str(origin), str(store)],
        check=True,
        capture_output=True,
    )
    git(store, "config", "user.email", "recorder@example.com")
    git(store, "config", "user.name", "Recorder Test")

    (store / "preferences.md").write_text("# Active Preference Set\n")
    # The store's own .gitignore, so importing the recorder in-process
    # does not make the worktree look dirty.
    (store / ".gitignore").write_text(
        (PROJECT_ROOT / "guard" / ".gitignore").read_text()
    )
    (store / "tools").mkdir()
    (store / "tools" / "record.py").write_text(RECORDER.read_text())
    git(store, "add", "-A")
    git(store, "commit", "--quiet", "-m", "seed store")
    git(store, "push", "--quiet", "-u", "origin", "main")

    git(store, "checkout", "--quiet", "-b", "session/20260101T000000Z")
    (store / "decisions").mkdir()
    (store / "decisions" / "leftover.json").write_text("{}\n")
    git(store, "add", "-A")
    git(store, "commit", "--quiet", "-m", "another session's unmerged record")
    git(store, "push", "--quiet", "-u", "origin", "session/20260101T000000Z")
    return store


@pytest.mark.xfail(strict=True, reason="red: open branches off HEAD, not the default")
def test_open_bases_the_session_on_the_default_branch(
    parked_store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A session carries its own records and nothing else.

    Branching from whatever the checkout happens to be on drags every
    unmerged commit of a previous session into this session's PR.
    """
    origin_url = git(parked_store, "config", "--get", "remote.origin.url").strip()
    monkeypatch.setenv("DECISION_MEMORY_URL", origin_url)
    recorder = load_module("parked_recorder", parked_store / "tools" / "record.py")

    recorder.main(["open"])

    branch = git(parked_store, "rev-parse", "--abbrev-ref", "HEAD").strip()
    assert branch.startswith("session/")
    assert not (parked_store / "decisions" / "leftover.json").exists()
    main_tip = git(parked_store, "rev-parse", "origin/main").strip()
    merge_base = git(parked_store, "merge-base", "HEAD", "origin/main").strip()
    assert merge_base == main_tip

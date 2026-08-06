"""Behavior tests for scripts/ensure-prek.sh (#139).

The script is a SessionStart bootstrap. Its one measured failure mode
was the layout every remote agent session actually uses: a multi-repo
session whose project dir is the parent of the clones and is itself no
repository — the old guard was false there, and the script exited 0
having installed nothing, silently.

`prek` is stubbed with a script that records the directory it ran in,
so the assertions are about where installs happened, not about prek.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "ensure-prek.sh"


def _stub_prek(tmp_path: Path) -> tuple[Path, Path]:
    """A fake prek on PATH that logs its cwd per invocation."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    log = tmp_path / "prek-calls.log"
    stub = bindir / "prek"
    stub.write_text(f'#!/bin/sh\npwd >> "{log}"\nexit 0\n')
    stub.chmod(0o755)
    return bindir, log


def _run(cwd: Path, bindir: Path) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "HOME": str(cwd),
    }
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)


def test_multi_repo_layout_installs_into_every_clone(tmp_path: Path) -> None:
    bindir, log = _stub_prek(tmp_path)
    parent = tmp_path / "session"
    for name in ("alpha", "beta"):
        _git_repo(parent / name)
    (parent / "not-a-repo").mkdir()

    result = _run(parent, bindir)

    assert result.returncode == 0
    ran_in = sorted(
        Path(line).name for line in log.read_text().splitlines() if line.strip()
    )
    assert ran_in == ["alpha", "beta"]
    assert "NOT blocked" not in result.stderr


def test_single_repo_layout_behaves_as_before(tmp_path: Path) -> None:
    bindir, log = _stub_prek(tmp_path)
    repo = tmp_path / "solo"
    _git_repo(repo)

    result = _run(repo, bindir)

    assert result.returncode == 0
    ran_in = [Path(line).name for line in log.read_text().splitlines() if line.strip()]
    assert ran_in == ["solo"]


def test_installing_nowhere_warns_and_names_the_directory(tmp_path: Path) -> None:
    """The silent branch was the defect: exiting 0 having installed
    nothing, in the exact layout the script's own header names."""
    bindir, log = _stub_prek(tmp_path)
    parent = tmp_path / "empty-session"
    parent.mkdir()

    result = _run(parent, bindir)

    assert result.returncode == 0, "a broken bootstrap must never block a session"
    assert not log.exists() or not log.read_text().strip()
    assert "no repository found" in result.stderr
    assert str(parent) in result.stderr
    assert "NOT blocked" in result.stderr


def test_template_copy_matches_the_rendered_one() -> None:
    """Template-first: the self copy is stamped from template/, and a
    drift between them means one of the two audiences runs old code."""
    template = (
        PROJECT_ROOT
        / "template"
        / "scripts"
        / "{% if agentic_precommit == 'prek' %}ensure-prek.sh{% endif %}"
    )
    assert template.read_bytes() == SCRIPT.read_bytes()

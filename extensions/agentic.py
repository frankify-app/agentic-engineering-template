"""Copier Jinja extensions for agentic-template dynamic defaults."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jinja2.ext import Extension

# The literal template-side dirname: resolved by copier at render time,
# opaque to the filesystem, so the path is spelled as it sits on disk.
_GITHUB_DIR = "{% if agentic_forge == 'github' %}.github{% endif %}"


def reference_keywords() -> dict:
    """The central ticket-reference config, parsed from the template.

    One source of truth (AET#137/#144): the gate script reads this file
    from the rendered repo at run time, and AGENTS.md renders its rules
    from the same bytes at generation time — injected here so the two
    can never drift.
    """
    path = (
        Path(__file__).resolve().parent.parent
        / "template"
        / _GITHUB_DIR
        / "reference-keywords.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _git_remote_url() -> str | None:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def detect_forge() -> str | None:
    """Return ``github`` when ``origin`` points at github.com."""
    url = _git_remote_url()
    if url and "github.com" in url:
        return "github"
    return None


def resolve_repo_owner() -> str:
    """Resolve repo owner from ``gh api user`` or ``git config github.user``."""
    try:
        result = subprocess.run(
            ["gh", "api", "user", "-q", ".login"],
            capture_output=True,
            text=True,
            check=True,
        )
        owner = result.stdout.strip()
        if owner:
            return owner
    except (OSError, subprocess.CalledProcessError):
        pass

    try:
        result = subprocess.run(
            ["git", "config", "github.user"],
            capture_output=True,
            text=True,
            check=True,
        )
        owner = result.stdout.strip()
        if owner:
            return owner
    except (OSError, subprocess.CalledProcessError):
        pass

    return ""


class AgenticExtension(Extension):
    """Expose forge/owner helpers to Copier Jinja templates."""

    def __init__(self, environment) -> None:
        super().__init__(environment)
        environment.globals["detect_forge"] = detect_forge
        environment.globals["resolve_repo_owner"] = resolve_repo_owner
        environment.globals["reference_keywords"] = reference_keywords

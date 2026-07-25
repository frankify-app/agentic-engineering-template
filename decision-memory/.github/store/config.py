"""Repo-local store configuration (`store.config.json`).

Copier-vendored from the agentic-engineering-template guard
subtemplate — change it there, pull via `copier update`. The DATA it
reads (`store.config.json`) is the store-owned half: seeded once,
never overwritten on update, so a human tunes the knobs without
fighting the template. The vendored guard next door
(`.github/guards/`) stays untouched; this layer sits on top of it and
only ever imports it read-only.

The one place the two meet is the token budget:
`decision_validator.PREFERENCES_TOKEN_BUDGET` is a vendored hard
backstop that fails any PR over it, so a repo-local `budget_tokens`
above that value would be unreachable — configuring one is an error
with a pointer to the fix (raise it in the template, `copier update`).

Stdlib only, like the vendored guard.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "guards"),
)

import decision_validator  # noqa: E402  (path bootstrap above)

CONFIG_FILENAME = "store.config.json"

DEFAULTS: dict[str, object] = {
    "budget_tokens": decision_validator.PREFERENCES_TOKEN_BUDGET,
    "warn_at_percent": 80,
    "carve_out_label": "preferences-carve-out",
    "budget_issue_label": "preferences-budget",
    "replay_window": 20,
}

_POSITIVE_INTS = ("budget_tokens", "replay_window")
_LABELS = ("carve_out_label", "budget_issue_label")


class ConfigError(Exception):
    """Raised when `store.config.json` is unusable."""


def validate_config(config: dict) -> list[str]:
    """Return a list of human-readable errors (empty = valid).

    Unknown keys are tolerated, matching the record contract: new knobs
    need no migration, and `_comment` stays legal.
    """
    errors: list[str] = []
    for key in _POSITIVE_INTS:
        value = config.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"{key}: must be a positive integer, got {value!r}")
    for key in _LABELS:
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{key}: must be a non-empty string, got {value!r}")
    warn = config.get("warn_at_percent")
    if not isinstance(warn, int) or isinstance(warn, bool) or not 1 <= warn <= 100:
        errors.append(f"warn_at_percent: must be an integer in 1..100, got {warn!r}")

    budget = config.get("budget_tokens")
    backstop = decision_validator.PREFERENCES_TOKEN_BUDGET
    if isinstance(budget, int) and not isinstance(budget, bool) and budget > backstop:
        errors.append(
            f"budget_tokens: {budget} exceeds the vendored backstop {backstop} "
            "— the vendored guard would fail the PR first. Raise "
            "PREFERENCES_TOKEN_BUDGET in the template's decision-memory subtemplate and "
            "`copier update` before raising it here"
        )
    return errors


def load_config(root: str = ".") -> dict:
    """Load `store.config.json`, filling defaults; raise on invalid values.

    A missing file is fine — the defaults ARE the contract; the file
    exists so a human can adjust them in one obvious place.
    """
    config = dict(DEFAULTS)
    path = os.path.join(root, CONFIG_FILENAME)
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"{path}: unreadable or invalid JSON: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigError(f"{path}: must contain a JSON object")
        config.update(loaded)
    errors = validate_config(config)
    if errors:
        raise ConfigError(f"{path}: " + "; ".join(errors))
    return config

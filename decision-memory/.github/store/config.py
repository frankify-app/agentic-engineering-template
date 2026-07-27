"""Repo-local store configuration (`store.config.json`).

Copier-vendored from the agentic-engineering-template guard
subtemplate — change it there, pull via `copier update`. The DATA it
reads (`store.config.json`) is the store-owned half: seeded once,
never overwritten on update, so a human tunes the knobs without
fighting the template. The vendored guard next door
(`.github/guards/`) stays untouched; this layer sits on top of it and
only ever imports it read-only.

The one place the two meet is the token budget, and there is exactly
one of it: `decision_validator.PREFERENCES_TOKEN_BUDGET` is the
DEFAULT `budget_tokens`, not a ceiling over it. The vendored guard
reads this config and enforces whatever the store chose, so a store
raising its budget does not have to raise a template constant first.
The budget is per-principal — one number, adjustable in one obvious
place, checked once.

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
    "replay_waiver_label": "preferences-replay-waiver",
    "replay_window": 20,
    # Below this many PREFERENCE-DRIVEN cases the replay gate reports
    # `insufficient-evidence` instead of `pass`. Measured, not guessed:
    # on a null test (same rule set, two blind runs) the gated
    # denominator moved 3 -> 5 purely on whether each run claimed a rule
    # drove its pick, and at that size one case flipping swings the hit
    # rate 20-33 points. Eight keeps a single flip inside ~12 points,
    # which is small enough for a degradation to mean something.
    "min_gated_cases": 8,
    # --- Ingestion-gate thresholds -------------------------------------
    #
    # These live here rather than in `similarity.py` because they are
    # CALIBRATION, not logic: the right value is a property of a
    # store's own corpus, and two stores with different corpora should
    # legitimately hold different numbers. A store that had to edit the
    # vendored module to act on a recalibration would be choosing
    # between a stale threshold and a merge conflict on every
    # `copier update`.
    #
    # Each carries its evidence in `calibration` below. The honest
    # state of that evidence today is uneven, so it is recorded rather
    # than smoothed over — see `recalibrate-thresholds`.
    #
    # Similarity below this is not worth a human's attention.
    # Deliberately generous: a false cluster costs one glance, a missed
    # duplicate costs an immutable record that can never be withdrawn.
    "similarity_threshold": 0.35,
    # Containment catches what jaccard is structurally blind to: one
    # draft re-extracted as TWO. Jaccard divides by the union, so a
    # bundle split in half scores low against each half even when the
    # half is entirely inside the bundle.
    "containment_threshold": 0.5,
    # An artifact_ref agreeing on repo+path is strong corroboration
    # that two records are about the same thing, so it lifts an
    # otherwise borderline text score over the line rather than
    # deciding alone.
    "artifact_boost": 0.15,
    # Two extractions of one ruling reword the answer freely, so exact
    # equality would call every reworded duplicate "a different
    # answer".
    "answer_agreement": 0.5,
    # Share of a RULE's terms that appear in a record. Not jaccard:
    # rules run ~8 tokens and records ~20-40, and dividing by the union
    # caps the score below any useful threshold regardless of content.
    "false_cold_threshold": 0.4,
    # How much the corpus may grow past a calibration stamp before the
    # stamp is treated as stale. 2.0 = "the corpus has doubled", which
    # is late enough not to nag and early enough that a threshold has
    # not been wrong for the majority of the corpus's life.
    "calibration_growth_factor": 2.0,
    # Evidence behind each calibrated constant. Empty by default: a
    # store that has never measured should SAY so rather than inherit a
    # stamp earned on somebody else's corpus. See `stale_calibrations`.
    "calibration": {},
}

_POSITIVE_INTS = ("budget_tokens", "replay_window", "min_gated_cases")
_LABELS = ("carve_out_label", "budget_issue_label", "replay_waiver_label")

# Constants whose value is a claim about where a real distribution
# separates — as opposed to `budget_tokens`, which is a policy choice
# that no corpus can contradict. Only these are worth recalibrating.
CALIBRATED = (
    "similarity_threshold",
    "containment_threshold",
    "artifact_boost",
    "answer_agreement",
    "false_cold_threshold",
)


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
    for key in CALIBRATED:
        value = config.get(key)
        if not _is_number(value) or not 0.0 <= value <= 1.0:
            errors.append(f"{key}: must be a number in 0..1, got {value!r}")
    factor = config.get("calibration_growth_factor")
    if not _is_number(factor) or factor < 1.0:
        errors.append(
            f"calibration_growth_factor: must be a number >= 1.0, got {factor!r}"
        )
    errors.extend(_calibration_errors(config.get("calibration")))
    return errors


def _is_number(value: object) -> bool:
    """True for int/float but not bool — `True` is not a threshold."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _calibration_errors(calibration: object) -> list[str]:
    """Validate the evidence block, which is optional but not freeform.

    A stamp that cannot be read is worse than no stamp: it looks like
    evidence while proving nothing, which is the exact failure this
    block exists to prevent.
    """
    if calibration is None:
        return []
    if not isinstance(calibration, dict):
        return [f"calibration: must be a JSON object, got {calibration!r}"]
    errors: list[str] = []
    for name, stamp in calibration.items():
        if name not in CALIBRATED:
            errors.append(
                f"calibration.{name}: not a calibrated constant "
                f"(expected one of {', '.join(CALIBRATED)})"
            )
            continue
        if not isinstance(stamp, dict):
            errors.append(f"calibration.{name}: must be a JSON object, got {stamp!r}")
            continue
        size = stamp.get("corpus_size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 1:
            errors.append(
                f"calibration.{name}.corpus_size: must be a positive integer, "
                f"got {size!r}"
            )
        separation = stamp.get("separation")
        if separation is not None and not _is_number(separation):
            errors.append(
                f"calibration.{name}.separation: must be a number, got {separation!r}"
            )
    return errors


def stale_calibrations(config: dict, corpus_size: int) -> list[dict]:
    """Which calibrated constants are due a re-measurement, and why.

    Two ways to be stale, and the distinction matters to whoever picks
    this up:

    - **never measured** — no stamp at all. The value is inherited from
      the template's default, which was calibrated (if at all) against
      a different corpus. This is not a mild version of the other case;
      it means nobody has ever checked.
    - **outgrown** — the corpus has grown past the stamp by the
      configured factor. The number may still be right; what expired is
      the evidence, not necessarily the value.

    Deliberately not a pass/fail gate. A stale threshold is a prompt to
    go and measure, and failing CI over it would only teach people to
    silence it.
    """
    calibration = config.get("calibration") or {}
    factor = config.get("calibration_growth_factor", 2.0)
    stale: list[dict] = []
    for name in CALIBRATED:
        stamp = calibration.get(name)
        if not isinstance(stamp, dict):
            stale.append(
                {
                    "constant": name,
                    "value": config.get(name),
                    "reason": "never measured",
                    "calibrated_at": None,
                    "corpus_size": corpus_size,
                }
            )
            continue
        at = stamp.get("corpus_size")
        if isinstance(at, int) and corpus_size >= at * factor:
            stale.append(
                {
                    "constant": name,
                    "value": config.get(name),
                    "reason": (
                        f"corpus grew {at} -> {corpus_size}, past the "
                        f"{factor}x re-measurement mark"
                    ),
                    "calibrated_at": at,
                    "corpus_size": corpus_size,
                }
            )
    return stale


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

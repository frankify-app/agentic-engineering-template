"""The vendored store layer's self-test runs in this repo's suite too.

The same file runs inside a store, driven by preferences-guard.yml.
Running it here as well means a template-side edit cannot ship a
broken preference-set lifecycle to every store that updates.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
STORE_SELF_TEST = (
    PROJECT_ROOT / "guard" / ".github" / "store" / "tests" / "test_store.py"
)


def test_vendored_store_layer_self_test_passes() -> None:
    """The store layer's own unittest suite must pass in the template.

    Runs as a subprocess because the file bootstraps sys.path relative
    to its own location, exactly as it does in a store checkout.
    """
    result = subprocess.run(
        [sys.executable, str(STORE_SELF_TEST)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

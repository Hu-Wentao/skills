#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Run the complete Skillcraft test suite."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent


def main() -> int:
    node = subprocess.run(
        ["node", "--test", str(TEST_ROOT / "quick_validate.test.mjs")],
        check=False,
    )
    if node.returncode != 0:
        return node.returncode
    suite = unittest.defaultTestLoader.discover(str(TEST_ROOT), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())

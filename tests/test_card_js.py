"""The card's guided-check logic, tested with node (skipped where node is missing)."""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

JS_TESTS = sorted((pathlib.Path(__file__).parent / "js").glob("*.test.mjs"))


NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_check_engine() -> None:
    assert NODE is not None
    result = subprocess.run(  # noqa: S603  (our own test files)
        [NODE, "--test", *map(str, JS_TESTS)],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]

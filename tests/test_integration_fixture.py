"""Run the legacy end-to-end fixture suite under pytest, without touching it.

`tests/test_pipeline.py` predates pytest here: it is a `main()` with its own
`check(name, got, want)` and roughly sixty assertions, and it drives twelve
scripts by subprocess over a synthetic ClinVar snapshot. It is the only
integration coverage that exists, and CLAUDE.md rules 1 and 2 forbid rewriting
it without permission. So it is invoked, not converted.
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.integration
def test_suite_de_fixture_ponta_a_ponta_passa_inteira():
    result = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tests", "test_pipeline.py")],
        cwd=ROOT, capture_output=True, text=True)

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("All fixture assertions passed.")
    assert "FAILURES:" not in result.stdout

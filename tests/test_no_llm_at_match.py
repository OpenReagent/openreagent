"""Guard: the scan path imports no LLM client.

Run in a fresh subprocess so the assertion is not contaminated by other tests
that may legitimately import the extract path.
"""
from __future__ import annotations

import subprocess
import sys


def test_scan_imports_no_llm_client(fixtures_dir):
    code = (
        "import sys\n"
        "from openreagent.scan import scan\n"
        f"scan({fixtures_dir!r})\n"
        "bad = [m for m in sys.modules if m == 'anthropic' or m == 'openreagent.llm']\n"
        "assert not bad, bad\n"
        "print('NO_LLM_OK')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "NO_LLM_OK" in result.stdout

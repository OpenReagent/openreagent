"""Full-stack E2E: a real ``openreagent serve`` process over a real PostgreSQL.

Gated on ``OPENREAGENT_TEST_DB_URL`` (a reachable PostgreSQL) **and** the
``server`` extra. This is the only test that runs the whole stack as separate
OS processes — the CLI (``openreagent serve``, ``openreagent sig add/list``) ->
uvicorn -> FastAPI -> pg8000 -> PostgreSQL — plus the client and ``scan --store``
over real HTTP. Skipped when the database or the extra is absent.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from openreagent import loader

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")

_TEST_DB = os.environ.get("OPENREAGENT_TEST_DB_URL")
requires_db = pytest.mark.skipif(
    not _TEST_DB, reason="set OPENREAGENT_TEST_DB_URL (PostgreSQL) to run the full-stack E2E")


def setup_module(_):
    loader.load_builtins()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_healthy(client, proc, timeout: float = 20.0) -> None:
    from openreagent.client import ServerError

    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
            raise AssertionError(f"`serve` exited early (code {proc.returncode}):\n{out}")
        try:
            if client.health().get("status") == "ok":
                return
        except ServerError:
            time.sleep(0.2)
    raise AssertionError("server did not become healthy in time")


def _cli(env, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "openreagent", *args],
                          env=env, capture_output=True, text=True)


@requires_db
def test_fullstack_serve_cli_and_scan(tmp_path):
    from openreagent.client import OpenReagentClient
    from openreagent.recipes import get_recipe
    from openreagent.scan import scan

    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    env = dict(os.environ)
    env["OPENREAGENT_DB_URL"] = _TEST_DB           # read by the server process only
    env["OPENREAGENT_SERVER_URL"] = url            # used by the CLI client subprocesses
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        [sys.executable, "-m", "openreagent", "serve", "--host", "127.0.0.1", "--port", str(port)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    client = OpenReagentClient(url)
    try:
        _wait_healthy(client, proc)
        client.clear()

        # a target on disk + its source-text signature
        code = ("// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\n"
                "contract C { uint256 x; function f() public { x = 1; } }\n")
        contracts = tmp_path / "contracts"
        contracts.mkdir()
        (contracts / "C.sol").write_text(code)

        value = get_recipe("bytecode-hash").extractor.extract({"source": code})
        sig = {"id": "fs-clone",
               "recipe": {"name": "bytecode-hash", "version": "1.0.0"},
               "value": value,
               "provenance": [{"source_kind": "audit_report", "source_ref": "x",
                               "extracted_by": {"recipe": "bytecode-hash", "version": "1.0.0",
                                                "timestamp": "2026-06-01T00:00:00Z"}}]}
        sig_file = tmp_path / "sig.json"
        sig_file.write_text(json.dumps(sig))

        # seed via the real CLI: client -> HTTP -> server -> pg8000 -> PostgreSQL
        added = _cli(env, "sig", "add", str(sig_file))
        assert added.returncode == 0, added.stderr or added.stdout

        # read it back via the CLI (separate process, real round trip)
        listed = _cli(env, "sig", "list", "--json")
        assert listed.returncode == 0, listed.stderr
        assert "fs-clone" in [s["id"] for s in json.loads(listed.stdout)]

        # scan against the live server: real HTTP /match against the real DB
        report = scan(str(contracts), store=url, enable=["bytecode-hash"], do_build=False)
        assert any(f.signature_id == "fs-clone" and f.recipe == "bytecode-hash"
                   for f in report.findings)

        # removal round trip, also via the CLI
        removed = _cli(env, "sig", "remove", "fs-clone")
        assert removed.returncode == 0, removed.stderr
        assert client.list() == []
    finally:
        try:
            client.clear()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()

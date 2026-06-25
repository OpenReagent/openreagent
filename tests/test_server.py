"""The server + client, end-to-end over real HTTP, with an in-memory stub store.

These tests need the ``server`` extra (fastapi + uvicorn); they are skipped if
it is not installed. No database is required — the store dependency is overridden
with an in-memory stub, so what is exercised is the full client -> HTTP -> server
-> /match chain (the seam where PSI will later slot in), plus ``scan --store``.
"""
from __future__ import annotations

import socket
import threading
import time
import types

import pytest

from openreagent import loader
from openreagent.models import Signature

pytest.importorskip("fastapi")
uvicorn = pytest.importorskip("uvicorn")


def setup_module(_):
    loader.load_builtins()


class _StubStore:
    """Minimal in-memory stand-in for SignatureStore (server-side)."""

    def __init__(self):
        self._sigs: dict[str, Signature] = {}

    def add_many(self, sigs):
        for s in sigs:
            self._sigs[s.id] = s
        return len(sigs)

    def list(self, recipe=None):
        rows = [types.SimpleNamespace(signature=s) for s in self._sigs.values()
                if recipe is None or s.recipe.name == recipe]
        return sorted(rows, key=lambda r: r.signature.id)

    def get(self, sig_id):
        return self._sigs.get(sig_id)

    def remove(self, sig_id):
        return self._sigs.pop(sig_id, None) is not None

    def clear(self):
        n = len(self._sigs)
        self._sigs.clear()
        return n

    def count(self):
        return len(self._sigs)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def live_server():
    from openreagent.server import create_app, get_store

    stub = _StubStore()
    app = create_app()
    app.dependency_overrides[get_store] = lambda: stub

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started, "uvicorn did not start"
    try:
        yield f"http://127.0.0.1:{port}", stub
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _sig_dict(sid, recipe, value):
    return {
        "id": sid,
        "recipe": {"name": recipe, "version": "1.0.0"},
        "value": value,
        "provenance": [{"source_kind": "audit_report", "source_ref": "x",
                        "extracted_by": {"recipe": recipe, "version": "1.0.0",
                                         "timestamp": "2026-06-01T00:00:00Z"}}],
    }


def test_health_crud_and_match(live_server):
    from openreagent.client import OpenReagentClient

    url, _ = live_server
    client = OpenReagentClient(url)
    assert client.health()["status"] == "ok"

    value = {"digest": "ab" * 32, "normalization": "source-text"}
    assert client.add([Signature.from_dict(_sig_dict("s1", "bytecode-hash", value))]) == 1
    assert [s.id for s in client.list()] == ["s1"]
    assert client.get("s1") is not None
    assert client.get("missing") is None

    # a candidate with the same digest -> match; a different digest -> none
    hits = client.match({"bytecode-hash": [value]})
    assert hits and hits[0]["signature_id"] == "s1" and hits[0]["candidate"] == 0
    assert client.match({"bytecode-hash": [{"digest": "cd" * 32, "normalization": "source-text"}]}) == []

    assert client.remove("s1") is True
    assert client.list() == []


def test_scan_via_server(live_server, tmp_path):
    from openreagent.recipes import get_recipe
    from openreagent.scan import scan

    url, stub = live_server
    code_text = ("// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\n"
                 "contract C { uint256 x; function f() public { x = 1; } }\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "C.sol").write_text(code_text)

    # Seed the (server-side) store with the source-text signature of the same file.
    value = get_recipe("bytecode-hash").extractor.extract({"source": code_text})
    stub.add_many([Signature.from_dict(_sig_dict("sig-clone", "bytecode-hash", value))])

    report = scan(str(src), store=url, enable=["bytecode-hash"], do_build=False)
    assert any(f.signature_id == "sig-clone" and f.recipe == "bytecode-hash"
               for f in report.findings)
    # pool_size reflects candidate fingerprints queried, not the server's set size
    assert report.pool_size >= 1

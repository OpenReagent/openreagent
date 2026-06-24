"""Scan-path guards: determinism, recipe isolation, shape conformance at load,
and end-to-end behavior on the Solidity fixtures."""
from __future__ import annotations

import json

from openreagent import loader
from openreagent.formatters import to_json
from openreagent.pool import load_pool
from openreagent.recipes import get_recipe
from openreagent.scan import scan


def _bytecode_hash_pool(tmp_path, fixtures_path):
    """A source-text bytecode-hash signature that self-matches Token.sol."""
    loader.load_builtins()
    rec = get_recipe("bytecode-hash")
    value = rec.extractor.extract({"source_path": str(fixtures_path / "Token.sol")})
    sig = {
        "id": "sig-token-clone",
        "recipe": {"name": "bytecode-hash", "version": "1.0.0"},
        "value": value,
        "provenance": [{
            "source_kind": "build", "source_ref": "token",
            "extracted_by": {"recipe": "bytecode-hash", "version": "1.0.0",
                             "timestamp": "2026-06-01T00:00:00Z"},
        }],
    }
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "sig.json").write_text(json.dumps(sig))
    return str(pool)


def test_determinism_same_input_same_output(fixtures_dir):
    a = to_json(scan(fixtures_dir, do_build=False))
    b = to_json(scan(fixtures_dir, do_build=False))
    assert a == b


def test_load_pool_ok():
    # The shipped pool loads without error (may be empty).
    assert isinstance(load_pool(), list)


def test_empty_pool_no_error(fixtures_dir, tmp_path):
    empty = tmp_path / "empty_pool"
    empty.mkdir()
    report = scan(fixtures_dir, pool=str(empty), do_build=False)
    assert report.findings == []
    assert report.pool_size == 0


def test_bytecode_hash_fires_and_is_isolated(fixtures_dir, fixtures_path, tmp_path):
    pool = _bytecode_hash_pool(tmp_path, fixtures_path)
    base = scan(fixtures_dir, pool=pool, enable=["bytecode-hash"], do_build=False)
    bh = [f for f in base.findings if f.recipe == "bytecode-hash"]
    assert bh  # Token.sol self-clone matches
    # Enabling every recipe must not change bytecode-hash findings.
    every = scan(fixtures_dir, pool=pool, enable=["*"], do_build=False)
    assert [f for f in every.findings if f.recipe == "bytecode-hash"] == bh


def test_end_to_end_three_contracts(fixtures_dir):
    report = scan(fixtures_dir, do_build=False)
    assert report.files_scanned == 3


def test_findings_sorted(fixtures_dir, fixtures_path, tmp_path):
    pool = _bytecode_hash_pool(tmp_path, fixtures_path)
    report = scan(fixtures_dir, pool=pool, enable=["*"], do_build=False)
    keys = [(f.file, f.line, f.recipe, f.function, f.signature_id) for f in report.findings]
    assert keys == sorted(keys)

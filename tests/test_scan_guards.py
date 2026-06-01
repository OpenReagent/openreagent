"""Scan-path guards: determinism, recipe isolation, shape conformance at load,
and end-to-end behavior on the Solidity fixtures."""
from __future__ import annotations

from openreagent.formatters import to_json
from openreagent.pool import load_pool
from openreagent.scan import scan


def _absence(report):
    return [f for f in report.findings if f.recipe == "internal-absence"]


def test_determinism_same_input_same_output(fixtures_dir):
    a = to_json(scan(fixtures_dir))
    b = to_json(scan(fixtures_dir))
    assert a == b


def test_pool_shape_conformance_at_load():
    # The shipped pool must validate against shapes with no exception (strict).
    entries = load_pool()
    assert len(entries) >= 2
    ids = {e.signature.id for e in entries}
    assert "sig-missing-access-control" in ids
    assert "sig-amm-spot-price" in ids


def test_recipe_isolation_disable(fixtures_dir):
    base = scan(fixtures_dir)
    without_div = scan(fixtures_dir, disable=["canonical-divergence"])
    # Disabling canonical-divergence must not change internal-absence findings.
    assert _absence(base) == _absence(without_div)


def test_recipe_isolation_enable_all(fixtures_dir):
    base = scan(fixtures_dir)
    enable_all = scan(fixtures_dir, enable=["*"])
    # Enabling every recipe must not change internal-absence findings.
    assert _absence(base) == _absence(enable_all)


def test_end_to_end_three_contracts(fixtures_dir):
    report = scan(fixtures_dir)
    assert report.files_scanned == 3
    hit = {(f.recipe, f.function) for f in report.findings}
    assert ("internal-absence", "setFeeRecipient") in hit
    assert ("canonical-divergence", "getPrice") in hit
    # The clean Token.sol must not produce a production finding.
    assert not any(f.file.endswith("Token.sol") for f in report.findings)


def test_empty_pool_no_error(fixtures_dir, tmp_path):
    empty = tmp_path / "empty_pool"
    empty.mkdir()
    report = scan(fixtures_dir, pool=str(empty))
    assert report.findings == []
    assert report.pool_size == 0


def test_findings_sorted(fixtures_dir):
    report = scan(fixtures_dir, enable=["*"])
    keys = [(f.file, f.line, f.recipe, f.function, f.signature_id) for f in report.findings]
    assert keys == sorted(keys)

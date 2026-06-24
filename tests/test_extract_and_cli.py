"""The extract path (offline, deterministic) and the CLI surface."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from openreagent.cli import app
from openreagent.extract import extract_signature
from openreagent.shapes import conforms

runner = CliRunner()


def test_extract_offline_bytecode_hash():
    finding = {
        "bytecode": "60806040" * 4,
        "source_kind": "build",
        "source_ref": "sample/clone-1",
    }
    sig = extract_signature(finding, "bytecode-hash")
    assert sig.recipe.name == "bytecode-hash"
    assert conforms(sig.value, "bytecode-hash")
    assert sig.value["normalization"].startswith("bytecode")
    assert sig.provenance[0].source_ref == "sample/clone-1"
    assert sig.provenance[0].extracted_by.recipe == "bytecode-hash"


def test_cli_recipes_json():
    result = runner.invoke(app, ["recipes", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    names = {r["name"] for r in data}
    assert "bytecode-hash" in names
    assert "ast-sketch" in names
    # No measurement numbers in the recipe listing.
    assert "precision" not in result.stdout.lower()


def test_cli_scan_runs(fixtures_dir):
    # Default scan is deterministic and emits a well-formed report (no findings
    # is fine — the journey recipes are off by default).
    result = runner.invoke(app, ["scan", fixtures_dir, "--no-build", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["tool"]["name"] == "openreagent"
    assert "summary" in data and "findings" in data


def test_cli_scan_sarif(fixtures_dir):
    result = runner.invoke(app, ["scan", fixtures_dir, "--no-build", "--format", "sarif"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "OpenReagent"


def test_cli_validate_sample(tmp_path):
    sig = {
        "id": "sig-x",
        "recipe": {"name": "bytecode-hash", "version": "1.0.0"},
        "value": {"digest": "ab" * 32, "normalization": "source-text"},
        "provenance": [{
            "source_kind": "audit_report", "source_ref": "x",
            "extracted_by": {"recipe": "bytecode-hash", "version": "1.0.0",
                             "timestamp": "2026-06-01T00:00:00Z"},
        }],
    }
    p = tmp_path / "sig.json"
    p.write_text(json.dumps(sig))
    result = runner.invoke(app, ["validate", str(p)])
    assert result.exit_code == 0
    assert "OK" in result.stdout

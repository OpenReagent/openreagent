"""The extract path (offline) and the CLI surface."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from openreagent.cli import app
from openreagent.extract import extract_signature
from openreagent.shapes import conforms

runner = CliRunner()


def test_extract_offline_passthrough_slots():
    finding = {
        "slots": {"operation": "access_control",
                  "site": {"function": "setFeeRecipient", "file": "Vault.sol"}},
        "source_kind": "audit_report",
        "source_ref": "sample/AC-99",
    }
    sig = extract_signature(finding, "internal-absence")
    assert sig.recipe.name == "internal-absence"
    assert conforms(sig.value, "slot-spec")
    assert sig.provenance[0].source_ref == "sample/AC-99"
    assert sig.provenance[0].extracted_by.recipe == "internal-absence"


def test_cli_recipes_json():
    result = runner.invoke(app, ["recipes", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    names = {r["name"] for r in data}
    assert "internal-absence" in names
    # No measurement numbers in the recipe listing.
    assert "precision" not in result.stdout.lower()
    # No recipe is named with the old M-number taxonomy (e.g. "M1-…", "M6-…").
    assert not any(len(n) >= 2 and n[0] in "Mm" and n[1].isdigit() for n in names)


def test_cli_scan_json(fixtures_dir):
    result = runner.invoke(app, ["scan", fixtures_dir, "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    recipes_hit = {f["recipe"] for f in data["findings"]}
    assert "internal-absence" in recipes_hit
    assert "canonical-divergence" in recipes_hit


def test_cli_scan_sarif(fixtures_dir):
    result = runner.invoke(app, ["scan", fixtures_dir, "--format", "sarif"])
    assert result.exit_code == 0
    doc = json.loads(result.stdout)
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "OpenReagent"


def test_cli_validate_sample(tmp_path):
    sig = {
        "id": "sig-x",
        "recipe": {"name": "internal-absence", "version": "1.0.0"},
        "value": {"slots": {"operation": "access_control"}},
        "provenance": [{
            "source_kind": "audit_report", "source_ref": "x",
            "extracted_by": {"recipe": "internal-absence", "version": "1.0.0",
                             "timestamp": "2026-06-01T00:00:00Z"},
        }],
    }
    p = tmp_path / "sig.json"
    p.write_text(json.dumps(sig))
    result = runner.invoke(app, ["validate", str(p)])
    assert result.exit_code == 0
    assert "OK" in result.stdout

"""Build-framework detection: Foundry / Hardhat / Vanilla.

Distinct from ``test_framework.py`` (which guards the recipe/shape registry).
Detection is deterministic and performs no build.
"""
from __future__ import annotations

import json
import pathlib

import pytest
from typer.testing import CliRunner

from openreagent.cli import app
from openreagent.frameworks import (
    AmbiguousFrameworkError,
    Framework,
    detect,
    resolve_framework,
)

runner = CliRunner()

HERE = pathlib.Path(__file__).resolve().parent
PROJECTS = HERE / "fixtures" / "projects"
FOUNDRY = PROJECTS / "foundry_app"
HARDHAT = PROJECTS / "hardhat_app"
BOTH = PROJECTS / "both_app"
VANILLA = HERE / "fixtures" / "contracts"


# ---- detect() ----

def test_detect_foundry():
    det = detect(FOUNDRY)
    assert det.framework is Framework.FOUNDRY
    assert det.ambiguous is False
    assert det.project_root == str(FOUNDRY)
    assert det.frameworks == (Framework.FOUNDRY,)


def test_detect_hardhat():
    det = detect(HARDHAT)
    assert det.framework is Framework.HARDHAT
    assert det.ambiguous is False
    assert det.project_root == str(HARDHAT)


def test_detect_vanilla_when_no_manifest():
    det = detect(VANILLA)
    assert det.framework is Framework.VANILLA
    assert det.ambiguous is False
    assert det.manifests == ()
    # Vanilla is rooted at the scanned directory, not some ancestor.
    assert det.project_root == str(VANILLA)


def test_detect_both_is_ambiguous():
    det = detect(BOTH)
    assert det.ambiguous is True
    assert det.framework is None  # no guess
    assert det.frameworks == (Framework.FOUNDRY, Framework.HARDHAT)
    assert det.project_root == str(BOTH)


def test_detect_walks_up_to_nearest_root():
    # Scanning a subdirectory resolves to the enclosing project root.
    det = detect(FOUNDRY / "src")
    assert det.framework is Framework.FOUNDRY
    assert det.project_root == str(FOUNDRY)


def test_detect_single_file_uses_enclosing_project():
    det = detect(FOUNDRY / "src" / "Counter.sol")
    assert det.framework is Framework.FOUNDRY
    assert det.project_root == str(FOUNDRY)


def test_detect_is_deterministic():
    assert detect(FOUNDRY).to_dict() == detect(FOUNDRY).to_dict()
    assert detect(BOTH).to_dict() == detect(BOTH).to_dict()


def test_detection_to_dict_shape():
    d = detect(FOUNDRY).to_dict()
    assert d["framework"] == "foundry"
    assert d["ambiguous"] is False
    assert d["detected"] == ["foundry"]
    assert d["manifests"][0]["framework"] == "foundry"
    assert d["manifests"][0]["path"].endswith("foundry.toml")


# ---- resolve_framework() ----

def test_resolve_single():
    assert resolve_framework(detect(FOUNDRY)) is Framework.FOUNDRY


def test_resolve_ambiguous_raises():
    with pytest.raises(AmbiguousFrameworkError):
        resolve_framework(detect(BOTH))


def test_resolve_override_wins():
    # Override forces a framework even on an ambiguous layout.
    assert resolve_framework(detect(BOTH), override="hardhat") is Framework.HARDHAT
    assert resolve_framework(detect(FOUNDRY), override="vanilla") is Framework.VANILLA


def test_resolve_override_unknown_raises():
    with pytest.raises(ValueError):
        resolve_framework(detect(FOUNDRY), override="truffle")


# ---- CLI: detect ----

def test_cli_detect_json_foundry():
    result = runner.invoke(app, ["detect", str(FOUNDRY), "--json"])
    assert result.exit_code == 0
    info = json.loads(result.stdout)
    assert info["framework"] == "foundry"
    assert info["resolved"] == "foundry"
    assert info["ambiguous"] is False


def test_cli_detect_json_ambiguous_is_unresolved_not_error():
    result = runner.invoke(app, ["detect", str(BOTH), "--json"])
    assert result.exit_code == 0  # JSON output never prompts or errors
    info = json.loads(result.stdout)
    assert info["ambiguous"] is True
    assert info["framework"] is None
    assert info["resolved"] is None
    assert info["detected"] == ["foundry", "hardhat"]


def test_cli_detect_ambiguous_override():
    result = runner.invoke(app, ["detect", str(BOTH), "--framework", "foundry", "--json"])
    assert result.exit_code == 0
    info = json.loads(result.stdout)
    assert info["resolved"] == "foundry"


def test_cli_detect_human_ambiguous_exits_nonzero():
    # Non-interactive (no TTY), no override: surface the ambiguity as an error.
    result = runner.invoke(app, ["detect", str(BOTH)])
    assert result.exit_code == 1


def test_cli_detect_bad_framework():
    result = runner.invoke(app, ["detect", str(FOUNDRY), "--framework", "brownie", "--json"])
    assert result.exit_code == 1


# ---- CLI: scan surfaces detection ----

def test_cli_scan_json_reports_framework():
    result = runner.invoke(app, ["scan", str(FOUNDRY), "--no-build", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["target"]["framework"] == "foundry"
    assert data["target"]["resolved_by"] == "detected"


def test_cli_scan_ambiguous_reports_unresolved():
    result = runner.invoke(app, ["scan", str(BOTH), "--no-build", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["target"]["ambiguous"] is True
    assert data["target"]["framework"] is None
    assert data["target"]["resolved_by"] == "ambiguous"


def test_cli_scan_framework_override():
    result = runner.invoke(app, ["scan", str(BOTH), "--framework", "hardhat", "--no-build", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["target"]["framework"] == "hardhat"
    assert data["target"]["resolved_by"] == "override"


def test_cli_scan_bad_framework():
    result = runner.invoke(app, ["scan", str(FOUNDRY), "--framework", "nope"])
    assert result.exit_code == 1

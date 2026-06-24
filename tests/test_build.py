"""Automatic build: graceful-degradation guards (always run) and E2E builds
(run only when the relevant toolchain is available).

The build is best-effort and must never abort a scan, so the unit guards assert
behavior with or without a toolchain. The E2E tests are skipped unless the real
``forge`` / ``solc`` / Hardhat install is present.
"""
from __future__ import annotations

import json
import pathlib
import shutil

import pytest
from typer.testing import CliRunner

from openreagent.building import (
    BuildStatus,
    _artifacts_from_standard_json,
    _read_foundry_out,
    _select_installed_solc,
    _solc_pragmas,
    build,
)
from openreagent.cli import app
from openreagent.frameworks import Framework, detect

runner = CliRunner()

HERE = pathlib.Path(__file__).resolve().parent
PROJECTS = HERE / "fixtures" / "projects"
FOUNDRY = PROJECTS / "foundry_app"
HARDHAT = PROJECTS / "hardhat_app"          # detection-only (TS config, no package.json)
HARDHAT_BUILD = PROJECTS / "hardhat_build_app"  # buildable (JS config + package.json)
BOTH = PROJECTS / "both_app"
VANILLA = PROJECTS / "vanilla_app"

_VALID_STATUS = {s.value for s in BuildStatus}


def _has_solc() -> bool:
    try:
        import solcx
    except ImportError:
        return False
    return bool(solcx.get_installed_solc_versions())


# ---- graceful-degradation guards (no toolchain required) ----

def test_build_disabled():
    res = build(detect(FOUNDRY), Framework.FOUNDRY, enabled=False)
    assert res.status is BuildStatus.DISABLED


def test_build_ambiguous_is_skipped_not_guessed():
    det = detect(BOTH)
    res = build(det, det.framework)  # det.framework is None when ambiguous
    assert res.status is BuildStatus.SKIPPED
    assert res.reason == "framework-ambiguous"


def test_build_never_raises_and_summary_is_well_formed():
    for path, fw in [(FOUNDRY, Framework.FOUNDRY),
                     (HARDHAT, Framework.HARDHAT),
                     (VANILLA, Framework.VANILLA)]:
        res = build(detect(path), fw)
        s = res.summary()
        assert s["status"] in _VALID_STATUS
        assert set(s) == {"status", "framework", "compiler", "artifacts", "reason"}


def test_foundry_skips_cleanly_without_forge():
    if shutil.which("forge") is not None:
        pytest.skip("forge is installed; covered by the E2E test")
    res = build(detect(FOUNDRY), Framework.FOUNDRY)
    assert res.status is BuildStatus.SKIPPED
    assert res.reason == "forge-not-found"


def test_hardhat_skips_cleanly_without_install():
    if (HARDHAT / "node_modules" / "hardhat").exists():
        pytest.skip("hardhat is installed; covered by the E2E test")
    res = build(detect(HARDHAT), Framework.HARDHAT)
    assert res.status is BuildStatus.SKIPPED
    assert res.reason == "hardhat-not-installed"


def test_npm_install_bootstraps_without_package_json(monkeypatch, tmp_path):
    # No package.json: npm can still bootstrap Hardhat (`npm install hardhat`).
    import openreagent.building as b

    class _Fake:
        returncode = 0
        stdout = stderr = ""

    calls = []
    monkeypatch.setattr(b, "_run", lambda cmd, cwd: calls.append(cmd) or _Fake())

    (tmp_path / "hardhat.config.js").write_text("module.exports = {};")
    b._npm_install(tmp_path)
    assert calls[-1][:3] == ["npm", "install", "hardhat@^2"]


def test_npm_install_bootstraps_typescript_for_ts_config(monkeypatch, tmp_path):
    import openreagent.building as b

    class _Fake:
        returncode = 0
        stdout = stderr = ""

    calls = []
    monkeypatch.setattr(b, "_run", lambda cmd, cwd: calls.append(cmd) or _Fake())

    (tmp_path / "hardhat.config.ts").write_text("export default {};")
    b._npm_install(tmp_path)
    cmd = calls[-1]
    assert cmd[:2] == ["npm", "install"]
    assert "ts-node" in cmd and any(p.startswith("typescript") for p in cmd)


def test_hardhat_compile_env_forces_commonjs_for_ts_config(tmp_path, monkeypatch):
    # A .ts config builds with no tsconfig.json: ts-node is pinned to CommonJS.
    import openreagent.building as b

    monkeypatch.delenv("TS_NODE_COMPILER_OPTIONS", raising=False)
    (tmp_path / "hardhat.config.ts").write_text("export default {};")
    env = b._hardhat_compile_env(tmp_path)
    assert env is not None
    assert "commonjs" in env["TS_NODE_COMPILER_OPTIONS"]


def test_hardhat_compile_env_none_for_js_config(tmp_path, monkeypatch):
    import openreagent.building as b

    monkeypatch.delenv("TS_NODE_COMPILER_OPTIONS", raising=False)
    (tmp_path / "hardhat.config.js").write_text("module.exports = {};")
    assert b._hardhat_compile_env(tmp_path) is None


def test_npm_install_uses_project_deps_when_package_json_present(monkeypatch, tmp_path):
    import openreagent.building as b

    class _Fake:
        returncode = 0
        stdout = stderr = ""

    calls = []
    monkeypatch.setattr(b, "_run", lambda cmd, cwd: calls.append(cmd) or _Fake())

    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "package-lock.json").write_text("{}")
    b._npm_install(tmp_path)
    assert calls[-1] == ["npm", "ci"]  # lockfile present => reproducible install


def test_build_falls_back_to_solc_when_framework_unavailable(monkeypatch):
    # When the framework toolchain is unavailable (skipped), build() should try a
    # plain solc compile of the discovered sources. Mock the vanilla builder so
    # the wiring is verified deterministically, offline.
    import openreagent.building as b

    if (HARDHAT / "node_modules" / "hardhat").exists():
        pytest.skip("hardhat installed in the detection fixture")
    fake = b.BuildResult(
        "vanilla", b.BuildStatus.OK, compiler="0.8.19",
        artifacts=[b.Artifact("contracts/C.sol", "C", "6080", {"nodeType": "SourceUnit"})],
    )
    monkeypatch.setattr(b, "_build_vanilla", lambda detection, install=False: fake)
    res = b.build(detect(HARDHAT), Framework.HARDHAT, install=False)
    assert res.status is BuildStatus.OK
    assert "toolchain-unavailable" in res.reason
    assert res.artifacts[0].contract == "C"


# ---- artifact parsers (deterministic; no toolchain) ----

def test_parse_standard_json_extracts_bytecode_and_ast():
    # The shape solc --standard-json emits, and what a Hardhat build-info embeds.
    output = {
        "sources": {
            "contracts/Counter.sol": {
                "id": 0,
                "ast": {"nodeType": "SourceUnit", "absolutePath": "contracts/Counter.sol"},
            }
        },
        "contracts": {
            "contracts/Counter.sol": {
                "Counter": {"evm": {"bytecode": {"object": "608060405234801561"}}},
            }
        },
    }
    output["contracts"]["contracts/Counter.sol"]["Counter"]["abi"] = [{"type": "function", "name": "f"}]
    arts = _artifacts_from_standard_json(output)
    assert len(arts) == 1
    a = arts[0]
    assert a.source == "contracts/Counter.sol"
    assert a.contract == "Counter"
    assert a.bytecode == "608060405234801561"
    assert a.ast["nodeType"] == "SourceUnit"
    assert a.abi == [{"type": "function", "name": "f"}]


def test_parse_standard_json_handles_empty():
    assert _artifacts_from_standard_json({}) == []


def test_read_foundry_out_parses_artifacts(tmp_path):
    out = tmp_path / "out" / "Counter.sol"
    out.mkdir(parents=True)
    (out / "Counter.json").write_text(json.dumps({
        "abi": [{"type": "function", "name": "increment"}],
        "bytecode": {"object": "0x6080604052"},
        "metadata": json.dumps({"compiler": {"version": "0.8.19+commit.7dd6d404"}}),
        "ast": {"nodeType": "SourceUnit", "absolutePath": "src/Counter.sol"},
    }))
    artifacts, compiler = _read_foundry_out(tmp_path / "out")
    assert compiler == "0.8.19"
    assert len(artifacts) == 1
    a = artifacts[0]
    assert a.contract == "Counter"
    assert a.source == "src/Counter.sol"   # taken from ast.absolutePath
    assert a.bytecode == "0x6080604052"
    assert a.ast is not None
    assert a.abi == [{"type": "function", "name": "increment"}]


def test_solc_pragmas_extracted():
    class _S:
        def __init__(self, text):
            self.text = text

    srcs = [_S("// SPDX\npragma solidity ^0.8.19;\ncontract A {}"),
            _S("pragma solidity >=0.7.0 <0.9.0;"),
            _S("// no pragma here")]
    assert _solc_pragmas(srcs) == ["^0.8.19", ">=0.7.0 <0.9.0"]


def _has_solcx() -> bool:
    try:
        from solcx.install import select_pragma_version  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.mark.skipif(not _has_solcx(), reason="py-solc-x (bytecode extra) not installed")
def test_select_installed_solc_respects_pragma():
    from packaging.version import Version

    installed = [Version("0.8.17"), Version("0.8.19"), Version("0.8.26")]
    # ^0.8.19 => >=0.8.19 <0.9.0 ; highest satisfying is 0.8.26.
    assert str(_select_installed_solc(["^0.8.19"], installed)) == "0.8.26"
    # Only 0.8.17 installed but ^0.8.19 required => nothing compatible.
    assert _select_installed_solc(["^0.8.19"], [Version("0.8.17")]) is None
    # No pragma => newest installed.
    assert str(_select_installed_solc([], installed)) == "0.8.26"
    # Intersection of two pragmas across files.
    assert str(_select_installed_solc([">=0.8.0", "<0.8.26"], installed)) == "0.8.19"


def test_read_foundry_out_ignores_non_artifacts(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "build-info.json").write_text(json.dumps({"id": "x", "input": {}}))  # not a contract
    artifacts, _ = _read_foundry_out(out)
    assert artifacts == []


# ---- scan integration ----

def test_vanilla_no_install_stays_offline():
    # With --no-install and no compatible solc, the build degrades cleanly.
    res = build(detect(VANILLA), Framework.VANILLA, install=False)
    if res.status is BuildStatus.SKIPPED:
        assert res.reason in ("no-solc-installed", "no-compatible-solc",
                              "bytecode-extra-not-installed")
    else:
        assert res.status is BuildStatus.OK  # a compatible solc happened to be installed


def test_scan_no_build_marks_disabled():
    from openreagent.scan import scan

    report = scan(str(VANILLA), do_build=False)
    assert report.target["build"]["status"] == "disabled"
    assert report.build.status is BuildStatus.DISABLED


def test_cli_scan_no_build():
    result = runner.invoke(app, ["scan", str(VANILLA), "--no-build", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["target"]["build"]["status"] == "disabled"


def test_cli_build_ambiguous_requires_choice():
    # An ambiguous layout with no --framework is skipped, not guessed.
    result = runner.invoke(app, ["build", str(BOTH), "--json"])
    assert result.exit_code == 0
    info = json.loads(result.stdout)
    assert info["status"] == "skipped"
    assert info["reason"] == "framework-ambiguous"


def test_cli_build_debug_exposes_log_field():
    # --debug surfaces the raw toolchain output / error in the JSON payload.
    # --no-install keeps the test offline.
    result = runner.invoke(app, ["build", str(VANILLA), "--no-install", "--json", "--debug"])
    info = json.loads(result.stdout)
    assert "log" in info  # present even when empty (e.g. skipped without solc)


# ---- E2E (real toolchains) ----

@pytest.mark.skipif(not _has_solc(), reason="no installed solc (bytecode extra)")
def test_e2e_vanilla_build_produces_bytecode_and_ast():
    res = build(detect(VANILLA), Framework.VANILLA)
    assert res.status is BuildStatus.OK, res.reason
    assert res.compiler  # a concrete solc version
    counter = [a for a in res.artifacts if a.contract == "Counter"]
    assert counter, "expected a Counter artifact"
    a = counter[0]
    assert a.bytecode and all(c in "0123456789abcdefABCDEF" for c in a.bytecode)
    assert isinstance(a.ast, dict) and a.ast  # AST present


@pytest.mark.skipif(not _has_solc(), reason="no installed solc (bytecode extra)")
def test_e2e_vanilla_build_is_deterministic():
    a = build(detect(VANILLA), Framework.VANILLA)
    b = build(detect(VANILLA), Framework.VANILLA)
    assert a.summary() == b.summary()
    assert [x.bytecode for x in a.artifacts] == [x.bytecode for x in b.artifacts]


@pytest.mark.skipif(shutil.which("forge") is None, reason="forge not installed")
def test_e2e_foundry_build_produces_bytecode():
    res = build(detect(FOUNDRY), Framework.FOUNDRY)
    assert res.status is BuildStatus.OK, res.reason
    assert any(a.bytecode for a in res.artifacts)


@pytest.mark.skipif(not (HARDHAT_BUILD / "node_modules" / "hardhat").exists(),
                    reason="hardhat deps not installed (run `openreagent build … --install` once)")
def test_e2e_hardhat_build_produces_bytecode_and_ast():
    res = build(detect(HARDHAT_BUILD), Framework.HARDHAT)
    assert res.status is BuildStatus.OK, res.reason
    assert any(a.bytecode for a in res.artifacts)
    assert any(a.ast for a in res.artifacts)

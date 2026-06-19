"""Automatic build of a scan target, at arm's length.

Given a :class:`~openreagent.frameworks.Detection`, this module produces build
artifacts — compiled **bytecode** and, where the toolchain provides it, the
**AST** — by running the project's real toolchain:

- **Foundry**  — ``forge build`` (artifacts read from ``out/``).
- **Hardhat**  — ``npx hardhat compile`` (artifacts read from ``artifacts/build-info``).
- **Vanilla**  — ``solc`` via the optional ``bytecode`` extra (``py-solc-x``).

Every builder runs the toolchain as a **separate process** (``py-solc-x`` shells
out to a ``solc`` binary), so the scan process never imports a heavy compiler
framework — the core stays dependency-light and the ``bytecode`` extra is
imported lazily, only on the vanilla path. See ``docs/architecture.md``.

Building is **best-effort and never fatal**: if a toolchain or the ``bytecode``
extra is absent, or a build fails, the result records a stable status/reason and
the caller continues on the lexical source view.

By default no network is used — the vanilla path compiles only with an
already-installed ``solc``. With ``install=True`` (the ``build`` CLI default;
opt-in for ``scan`` via ``--install``) a missing toolchain piece is fetched
automatically: a pragma-matching ``solc`` for vanilla, and the project's
``npm install`` for Hardhat. A plain ``scan`` therefore stays offline and
deterministic unless ``--install`` is given.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from openreagent.frameworks import Detection, Framework

# A generous ceiling; the fixtures build in well under a second.
_BUILD_TIMEOUT_S = 300


class BuildStatus(str, Enum):
    OK = "ok"
    SKIPPED = "skipped"   # toolchain / extra unavailable, or nothing to build
    FAILED = "failed"     # the toolchain ran but did not succeed
    DISABLED = "disabled"  # building was turned off by the caller


@dataclass(frozen=True)
class Artifact:
    """One compiled contract."""

    source: str           # source file (path or name as the toolchain reports it)
    contract: str         # contract name
    bytecode: str = ""    # creation bytecode, hex ("" when unavailable)
    ast: dict | None = None  # solc AST for the source, when the toolchain emits it

    def to_summary(self) -> dict:
        return {
            "source": self.source,
            "contract": self.contract,
            "bytecode_len": len(self.bytecode),
            "has_ast": self.ast is not None,
        }


@dataclass
class BuildResult:
    framework: str
    status: BuildStatus
    reason: str = ""               # stable category when skipped/failed (no raw logs)
    compiler: str = ""             # e.g. "0.8.19"
    artifacts: list[Artifact] = field(default_factory=list)
    log: str = field(default="", repr=False)  # raw toolchain output (never serialized)

    @property
    def ok(self) -> bool:
        return self.status is BuildStatus.OK

    def summary(self) -> dict:
        """A compact, deterministic description for the scan report."""
        return {
            "status": self.status.value,
            "framework": self.framework,
            "compiler": self.compiler,
            "artifacts": len(self.artifacts),
            "reason": self.reason,
        }


def _run(cmd: list[str], cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=str(cwd), capture_output=True, text=True, timeout=_BUILD_TIMEOUT_S, env=env
    )


# ts-node, on a TypeScript config, otherwise defaults `module` to NodeNext and
# errors (TS5109) unless a tsconfig says otherwise. Forcing CommonJS via the
# environment makes a `.ts` Hardhat config build with **no tsconfig.json**, and
# takes precedence over any project tsconfig (ts-node reads this first).
_TS_NODE_CJS = '{"module":"commonjs","moduleResolution":"node"}'


def _hardhat_compile_env(root: Path) -> dict | None:
    """Env for `hardhat compile`: pin ts-node to CommonJS for a TypeScript config.

    Returns ``None`` when not needed (JS config) or when the caller already set
    ``TS_NODE_COMPILER_OPTIONS`` (we never clobber an explicit choice).
    """
    is_ts = any((root / f"hardhat.config.{e}").exists() for e in ("ts", "mts", "cts"))
    if not is_ts or "TS_NODE_COMPILER_OPTIONS" in os.environ:
        return None
    return {**os.environ, "TS_NODE_COMPILER_OPTIONS": _TS_NODE_CJS}


def _artifacts_from_standard_json(output: dict) -> list[Artifact]:
    """Parse a solc **Standard-JSON** ``output`` object into artifacts.

    This is the shape produced by ``solc --standard-json`` (used directly on the
    vanilla path) and embedded as the ``output`` of a Hardhat build-info file, so
    both paths share one parser. Deterministic: contracts and sources are walked
    in sorted order.
    """
    asts = {
        src: info.get("ast")
        for src, info in (output.get("sources") or {}).items()
        if isinstance(info, dict)
    }
    artifacts: list[Artifact] = []
    for src, contracts in sorted((output.get("contracts") or {}).items()):
        for name, c in sorted((contracts or {}).items()):
            bytecode = str(((c or {}).get("evm", {}).get("bytecode") or {}).get("object", "") or "")
            artifacts.append(Artifact(source=src, contract=name,
                                      bytecode=bytecode, ast=asts.get(src)))
    return artifacts


# ---------------------------------------------------------------------------
# Foundry
# ---------------------------------------------------------------------------

def _build_foundry(root: Path) -> BuildResult:
    if shutil.which("forge") is None:
        return BuildResult("foundry", BuildStatus.SKIPPED, reason="forge-not-found")
    # Prefer building with the AST so the artifacts are useful downstream; fall
    # back to a plain build if this forge does not understand --ast.
    proc = _run(["forge", "build", "--ast", "--force"], root)
    if proc.returncode != 0 and "--ast" in (proc.stderr or ""):
        proc = _run(["forge", "build", "--force"], root)
    if proc.returncode != 0:
        return BuildResult("foundry", BuildStatus.FAILED, reason="build-error",
                           log=(proc.stderr or proc.stdout))
    out_dir = root / "out"
    artifacts, compiler = _read_foundry_out(out_dir)
    if not artifacts:
        return BuildResult("foundry", BuildStatus.FAILED, reason="no-artifacts",
                           log=(proc.stdout or ""))
    return BuildResult("foundry", BuildStatus.OK, compiler=compiler, artifacts=artifacts,
                       log=proc.stdout)


def _read_foundry_out(out_dir: Path) -> tuple[list[Artifact], str]:
    artifacts: list[Artifact] = []
    compiler = ""
    if not out_dir.is_dir():
        return artifacts, compiler
    for jf in sorted(out_dir.rglob("*.json"), key=lambda p: str(p)):
        try:
            obj = json.loads(jf.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if not isinstance(obj, dict) or "bytecode" not in obj:
            continue  # not a contract artifact (e.g. build-info)
        bytecode = ""
        bc = obj.get("bytecode")
        if isinstance(bc, dict):
            bytecode = str(bc.get("object", "") or "")
        ast = obj.get("ast") if isinstance(obj.get("ast"), dict) else None
        source = jf.parent.name           # out/<File.sol>/<Contract>.json
        contract = jf.stem
        if isinstance(ast, dict) and ast.get("absolutePath"):
            source = str(ast["absolutePath"])
        if not compiler:
            compiler = _foundry_compiler(obj)
        artifacts.append(Artifact(source=source, contract=contract,
                                  bytecode=bytecode, ast=ast))
    return artifacts, compiler


def _foundry_compiler(obj: dict) -> str:
    meta = obj.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = None
    if isinstance(meta, dict):
        comp = meta.get("compiler")
        if isinstance(comp, dict) and comp.get("version"):
            return str(comp["version"]).split("+")[0]
    return ""


# ---------------------------------------------------------------------------
# Hardhat
# ---------------------------------------------------------------------------

def _npm_install(root: Path) -> subprocess.CompletedProcess:
    """Make a local Hardhat available.

    With a ``package.json`` we install the project's declared dependencies
    (``npm ci`` when a lockfile exists, else ``npm install``). Without one — a
    bare project that just has a ``hardhat.config.*`` and contracts — npm can
    still bootstrap Hardhat directly: ``npm install hardhat`` creates the
    ``package.json``/``node_modules`` for us. A TypeScript config additionally
    needs ``ts-node``/``typescript`` (pinned to the v5 line to avoid the v7
    ``moduleResolution`` breakage).
    """
    if (root / "package.json").exists():
        locked = (root / "package-lock.json").exists() or (root / "npm-shrinkwrap.json").exists()
        return _run(["npm", "ci"] if locked else ["npm", "install"], root)
    pkgs = ["hardhat@^2"]  # pin the stable line for an undeclared (bare) project
    if any((root / f"hardhat.config.{e}").exists() for e in ("ts", "mts", "cts")):
        pkgs += ["ts-node", "typescript@^5", "@types/node"]
    return _run(["npm", "install", *pkgs], root)


def _build_hardhat(root: Path, install: bool = False) -> BuildResult:
    if not (root / "node_modules" / "hardhat").exists():
        # Hardhat must be installed locally (it refuses to run from an npx cache).
        # Installing runs the project's `npm install`, which can execute arbitrary
        # scripts, so it happens only with --install. No package.json is required:
        # npm bootstraps Hardhat for a bare config-only project.
        if install:
            if shutil.which("npm") is None:
                return BuildResult("hardhat", BuildStatus.SKIPPED, reason="npm-not-found")
            ni = _npm_install(root)
            if ni.returncode != 0:
                return BuildResult("hardhat", BuildStatus.FAILED, reason="npm-install-error",
                                   log=(ni.stderr or ni.stdout))
        if not (root / "node_modules" / "hardhat").exists():
            return BuildResult("hardhat", BuildStatus.SKIPPED, reason="hardhat-not-installed")
    if shutil.which("npx") is None:
        return BuildResult("hardhat", BuildStatus.SKIPPED, reason="npx-not-found")
    proc = _run(["npx", "--no-install", "hardhat", "compile"], root, env=_hardhat_compile_env(root))
    if proc.returncode != 0:
        return BuildResult("hardhat", BuildStatus.FAILED, reason="build-error",
                           log=(proc.stderr or proc.stdout))
    artifacts, compiler = _read_hardhat_build_info(root / "artifacts" / "build-info")
    if not artifacts:
        return BuildResult("hardhat", BuildStatus.FAILED, reason="no-artifacts",
                           log=(proc.stdout or ""))
    return BuildResult("hardhat", BuildStatus.OK, compiler=compiler, artifacts=artifacts,
                       log=proc.stdout)


def _read_hardhat_build_info(bi_dir: Path) -> tuple[list[Artifact], str]:
    artifacts: list[Artifact] = []
    compiler = ""
    if not bi_dir.is_dir():
        return artifacts, compiler
    for bi in sorted(bi_dir.glob("*.json"), key=lambda p: str(p)):
        try:
            obj = json.loads(bi.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        compiler = compiler or str(obj.get("solcVersion", "")).split("+")[0]
        artifacts.extend(_artifacts_from_standard_json(obj.get("output", {})))
    return artifacts, compiler


# ---------------------------------------------------------------------------
# Vanilla (solc via the optional `bytecode` extra)
# ---------------------------------------------------------------------------

_PRAGMA_RE = re.compile(r"pragma\s+solidity\s+([^;]+);")


def _solc_pragmas(sources) -> list[str]:
    """Every ``pragma solidity <spec>;`` constraint across the sources."""
    out: list[str] = []
    for s in sources:
        for m in _PRAGMA_RE.finditer(s.text):
            out.append(m.group(1).strip())
    return out


def _select_installed_solc(pragmas: list[str], installed: list):
    """Pick the highest installed solc that satisfies every pragma.

    Uses solc's own npm-style pragma resolver (``solcx.install.select_pragma_version``,
    which relies on ``packaging``), so the choice matches what forge/hardhat would
    make. Returns the chosen version or ``None`` when nothing installed satisfies
    the constraints. With no pragmas, the newest installed version is used.
    """
    if not installed:
        return None
    if not pragmas:
        return sorted(installed)[-1]
    try:
        from solcx.install import select_pragma_version
    except Exception:
        return sorted(installed)[-1]
    survivors = list(installed)
    for spec in pragmas:
        full = f"pragma solidity {spec};"
        try:
            survivors = [v for v in survivors if select_pragma_version(full, [v]) is not None]
        except Exception:
            continue  # ignore a constraint we cannot parse rather than failing hard
        if not survivors:
            return None
    return max(survivors) if survivors else None


def _install_matching_solc(solcx, pragmas: list[str]):
    """Download a solc satisfying the pragmas (network). Returns the chosen version."""
    if not pragmas:
        solcx.install_solc()  # latest
    else:
        for spec in pragmas:
            solcx.install_solc_pragma(f"pragma solidity {spec};")
    return _select_installed_solc(pragmas, solcx.get_installed_solc_versions())


def _build_vanilla(detection: Detection, install: bool = False) -> BuildResult:
    try:
        import solcx  # type: ignore
    except ImportError:
        return BuildResult("vanilla", BuildStatus.SKIPPED, reason="bytecode-extra-not-installed")

    from openreagent.solidity import load_target

    sources = load_target(detection.target)
    if not sources:
        return BuildResult("vanilla", BuildStatus.SKIPPED, reason="no-sources")

    pragmas = _solc_pragmas(sources)
    installed = solcx.get_installed_solc_versions()
    chosen = _select_installed_solc(pragmas, installed) if installed else None

    if chosen is None and install:
        # Fetch a pragma-matching solc. Off by default (offline-safe); turned on
        # explicitly via --install so a plain scan never reaches the network.
        try:
            chosen = _install_matching_solc(solcx, pragmas)
        except Exception:
            return BuildResult("vanilla", BuildStatus.FAILED, reason="solc-install-failed",
                               log=traceback.format_exc())

    if chosen is None:
        have = ", ".join(str(v) for v in sorted(installed)) or "(none)"
        want = ", ".join(pragmas) or "(none)"
        reason = "no-solc-installed" if not installed else "no-compatible-solc"
        return BuildResult(
            "vanilla", BuildStatus.SKIPPED, reason=reason,
            log=f"no installed solc satisfies pragma {want}; installed: {have}. "
                f"Re-run with --install to fetch a matching solc automatically.",
        )
    version = str(chosen)

    std_input = {
        "language": "Solidity",
        "sources": {src.path: {"content": src.text} for src in sources},
        "settings": {
            "outputSelection": {"*": {"*": ["evm.bytecode.object"], "": ["ast"]}}
        },
    }
    try:
        out = solcx.compile_standard(std_input, solc_version=version, allow_paths=".")
    except Exception:  # solcx raises on compiler errors; degrade, never abort
        return BuildResult("vanilla", BuildStatus.FAILED, reason="build-error",
                           compiler=version, log=traceback.format_exc())

    artifacts = _artifacts_from_standard_json(out)
    if not artifacts:
        return BuildResult("vanilla", BuildStatus.FAILED, reason="no-artifacts")
    return BuildResult("vanilla", BuildStatus.OK, compiler=version, artifacts=artifacts)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def build(detection: Detection, framework: Framework | None, *, enabled: bool = True,
          install: bool = False) -> BuildResult:
    """Build a detected target.

    ``framework`` is the resolved framework (an override or the single detected
    one). ``None`` means the layout is ambiguous and no choice was made — building
    is skipped rather than guessed. With ``install=True`` a missing toolchain
    piece is fetched automatically (a pragma-matching ``solc`` for vanilla; the
    project's ``npm install`` for Hardhat) — off by default so a plain scan stays
    offline.

    When a framework toolchain is **unavailable** (skipped: no ``forge``, no
    Hardhat install, no ``package.json``, …), the build falls back to compiling
    the discovered ``.sol`` directly with ``solc``. The goal is artifacts, so a
    self-contained project still yields bytecode/AST even without its framework
    set up; a project that needs the framework's import resolution simply fails
    the fallback gracefully. Building is best-effort: any missing toolchain or
    failure yields a non-OK :class:`BuildResult`, never an exception.
    """
    if not enabled:
        return BuildResult(framework.value if framework else "unknown", BuildStatus.DISABLED,
                           reason="build-disabled")
    if framework is None:
        return BuildResult("ambiguous", BuildStatus.SKIPPED, reason="framework-ambiguous")

    root = Path(detection.project_root)
    try:
        if framework is Framework.VANILLA:
            return _build_vanilla(detection, install=install)
        if framework is Framework.FOUNDRY:
            primary = _build_foundry(root)  # forge fetches its own solc via svm
        else:
            primary = _build_hardhat(root, install=install)
        if primary.status is not BuildStatus.SKIPPED:
            return primary  # OK or a real FAILED — don't mask it
        # Framework toolchain unavailable: best-effort solc compile of the sources.
        fallback = _build_vanilla(detection, install=install)
        if fallback.status is BuildStatus.OK:
            fallback.reason = f"{framework.value}-toolchain-unavailable; built via solc"
            return fallback
        return primary  # keep the more informative framework skip
    except subprocess.TimeoutExpired as exc:
        return BuildResult(framework.value, BuildStatus.FAILED, reason="timeout", log=str(exc))
    except Exception:  # a builder must never abort the scan
        return BuildResult(framework.value, BuildStatus.FAILED, reason="builder-error",
                           log=traceback.format_exc())

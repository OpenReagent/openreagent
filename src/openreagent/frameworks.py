"""Deterministic, dependency-free detection of a target's build framework.

Given a scan target, this module decides how the target is *meant to be built*:

- **Foundry**  — a ``foundry.toml`` manifest.
- **Hardhat**  — a ``hardhat.config.{js,ts,cjs,mjs}`` manifest.
- **Vanilla**  — loose ``.sol`` with no recognized manifest.

No build is performed and nothing is shelled out, so this is safe to run on every
scan. Detection walks upward from the scan target to the **nearest enclosing**
project root, stopping at a ``.git`` boundary so it never escapes into an
unrelated parent directory. The result is a pure function of the filesystem
layout, so it is deterministic for a fixed input.

When more than one manifest is present in the same root (e.g. a project that
carries both ``foundry.toml`` and ``hardhat.config.ts``), detection records
*both* and reports the result as **ambiguous**; choosing a single framework is
left to the caller (an explicit override or an interactive prompt), never guessed
here.

TODO(roadmap): Truffle (``truffle-config.js``) and Brownie
(``brownie-config.yaml``) are not yet recognized and currently fall back to
Vanilla. See docs/roadmap.md and docs/frameworks.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class Framework(str, Enum):
    FOUNDRY = "foundry"
    HARDHAT = "hardhat"
    VANILLA = "vanilla"


_FOUNDRY_MANIFEST = "foundry.toml"
_HARDHAT_MANIFESTS = (
    "hardhat.config.js",
    "hardhat.config.ts",
    "hardhat.config.cjs",
    "hardhat.config.mjs",
)


@dataclass(frozen=True)
class Manifest:
    framework: Framework
    path: str  # absolute path to the manifest file


@dataclass(frozen=True)
class Detection:
    """The outcome of inspecting a scan target's project layout."""

    target: str  # the scan target, resolved to an absolute path
    project_root: str  # dir holding the manifest(s), or the target dir if vanilla
    manifests: tuple[Manifest, ...]  # detected manifests, sorted; empty => vanilla

    @property
    def frameworks(self) -> tuple[Framework, ...]:
        """Distinct frameworks detected, sorted; ``(VANILLA,)`` when none."""
        kinds = sorted({m.framework for m in self.manifests}, key=lambda f: f.value)
        return tuple(kinds) or (Framework.VANILLA,)

    @property
    def ambiguous(self) -> bool:
        """True when more than one distinct framework was detected."""
        return len({m.framework for m in self.manifests}) > 1

    @property
    def framework(self) -> Framework | None:
        """The single resolved framework, or ``None`` when ambiguous.

        ``VANILLA`` when no manifest was found.
        """
        kinds = {m.framework for m in self.manifests}
        if not kinds:
            return Framework.VANILLA
        if len(kinds) == 1:
            return next(iter(kinds))
        return None

    def to_dict(self) -> dict:
        return {
            "framework": self.framework.value if self.framework else None,
            "ambiguous": self.ambiguous,
            "project_root": self.project_root,
            "detected": [f.value for f in self.frameworks],
            "manifests": [
                {"framework": m.framework.value, "path": m.path} for m in self.manifests
            ],
        }


class AmbiguousFrameworkError(Exception):
    """Raised when a single framework is required but several were detected."""

    def __init__(self, detection: Detection):
        self.detection = detection
        names = ", ".join(f.value for f in detection.frameworks)
        super().__init__(
            f"multiple build frameworks detected ({names}); choose one explicitly"
        )


def _manifests_in(d: Path) -> tuple[Manifest, ...]:
    """The recognized manifests directly inside directory ``d`` (sorted)."""
    out: list[Manifest] = []
    if (d / _FOUNDRY_MANIFEST).is_file():
        out.append(Manifest(Framework.FOUNDRY, str(d / _FOUNDRY_MANIFEST)))
    for name in _HARDHAT_MANIFESTS:
        if (d / name).is_file():
            out.append(Manifest(Framework.HARDHAT, str(d / name)))
            break  # a single Hardhat config is enough to identify the framework
    return tuple(sorted(out, key=lambda m: (m.framework.value, m.path)))


def detect(path: str | Path) -> Detection:
    """Detect the build framework for a scan target.

    Walks upward from ``path`` (or its parent, if ``path`` is a file) to the
    nearest directory containing a recognized manifest, stopping at a ``.git``
    boundary. Returns a vanilla :class:`Detection` rooted at the target when no
    manifest is found.
    """
    p = Path(path).resolve()
    start = p if p.is_dir() else p.parent
    for d in (start, *start.parents):
        found = _manifests_in(d)
        if found:
            return Detection(target=str(p), project_root=str(d), manifests=found)
        if (d / ".git").exists():
            break  # do not cross the repository boundary
    return Detection(target=str(p), project_root=str(start), manifests=())


def resolve_framework(detection: Detection, override: str | None = None) -> Framework:
    """Resolve a detection to a single framework.

    An explicit ``override`` (``"foundry"`` | ``"hardhat"`` | ``"vanilla"``) wins
    unconditionally. Otherwise the single detected framework is returned, or
    :class:`AmbiguousFrameworkError` is raised when the detection is ambiguous.
    """
    if override is not None:
        return Framework(override.lower().strip())  # ValueError on an unknown value
    fw = detection.framework
    if fw is None:
        raise AmbiguousFrameworkError(detection)
    return fw

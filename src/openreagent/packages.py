"""The package system — a small registry of installable detectors and shapes.

A *package* is a self-contained bundle: a directory with an ``openreagent.json``
manifest, an entry module that registers shapes and/or recipes, and any assets
the recipe needs (for example a recipe's canonical references live *inside* the
package, never in a global directory). Packages can be installed from a local
directory, a zip, an http(s) zip, or a GitHub repository — think "npm for
detectors and shapes."

Manifest (``openreagent.json``):

```json
{
  "name": "bytecode-hash",
  "version": "1.0.0",
  "kind": "recipe",                 // "recipe" | "shape" | "bundle"
  "entry": "detector.py",           // module that registers on import
  "requires": [],                   // other packages that must load first
  "description": "…",
  "provides": { "recipes": ["bytecode-hash"], "shapes": ["bytecode-hash"] }
}
```

Built-in packages ship inside the wheel. User-installed packages live under
``$OPENREAGENT_HOME`` (default ``~/.openreagent``) and override built-ins of the
same name. Loading imports packages in dependency order (shapes before the
recipes that require them).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from openreagent import sources

MANIFEST_NAME = "openreagent.json"


# ---------------------------------------------------------------------------
# Manifest + Package
# ---------------------------------------------------------------------------

@dataclass
class Package:
    name: str
    version: str
    kind: str
    entry: str
    directory: Path
    requires: list[str] = field(default_factory=list)
    description: str = ""
    provides: dict = field(default_factory=dict)
    origin: str = "builtin"  # "builtin" | "installed"

    @property
    def entry_path(self) -> Path:
        return self.directory / self.entry

    def describe(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "kind": self.kind,
            "requires": list(self.requires),
            "description": self.description,
            "provides": dict(self.provides),
            "origin": self.origin,
        }


def read_manifest(directory: Path, origin: str = "builtin") -> Package | None:
    mf = directory / MANIFEST_NAME
    if not mf.is_file():
        return None
    data = json.loads(mf.read_text(encoding="utf-8"))
    return Package(
        name=data["name"],
        version=data.get("version", "0.0.0"),
        kind=data.get("kind", "recipe"),
        entry=data.get("entry", "detector.py"),
        directory=directory,
        requires=list(data.get("requires", [])),
        description=data.get("description", ""),
        provides=dict(data.get("provides", {})),
        origin=origin,
    )


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------

def home_dir() -> Path:
    return Path(os.environ.get("OPENREAGENT_HOME", "~/.openreagent")).expanduser()


def installed_packages_dir() -> Path:
    return home_dir() / "packages"


def builtin_packages_dir() -> Path | None:
    here = Path(__file__).resolve()
    candidates = []
    if len(here.parents) >= 3:
        candidates.append(here.parents[2] / "packages")   # source checkout
    candidates.append(here.parent / "_data" / "packages")  # bundled wheel
    for c in candidates:
        if c.is_dir():
            return c
    return None


def builtin_pool_dir() -> Path | None:
    here = Path(__file__).resolve()
    for c in ([here.parents[2] / "pool"] if len(here.parents) >= 3 else []) + [
        here.parent / "_data" / "pool"
    ]:
        if c.is_dir():
            return c
    return None


# ---------------------------------------------------------------------------
# Discovery + dependency resolution
# ---------------------------------------------------------------------------

def _scan_dir(directory: Path | None, origin: str) -> dict[str, Package]:
    out: dict[str, Package] = {}
    if directory is None or not directory.is_dir():
        return out
    for sub in sorted(directory.iterdir()):
        if not sub.is_dir():
            continue
        pkg = read_manifest(sub, origin=origin)
        if pkg is not None:
            out[pkg.name] = pkg
    return out


def discover() -> dict[str, Package]:
    """All available packages. Installed packages override built-ins by name."""
    packages = _scan_dir(builtin_packages_dir(), "builtin")
    packages.update(_scan_dir(installed_packages_dir(), "installed"))
    return packages


def resolve_order(packages: dict[str, Package]) -> list[Package]:
    """Topologically sort packages so a package loads after its ``requires``.
    Raises on a missing dependency or a cycle. Deterministic (sorted)."""
    order: list[Package] = []
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(name: str, chain: tuple[str, ...]) -> None:
        if name in done:
            return
        if name in visiting:
            raise ValueError(f"dependency cycle: {' -> '.join(chain + (name,))}")
        pkg = packages.get(name)
        if pkg is None:
            raise ValueError(
                f"package {chain[-1] if chain else '?'} requires '{name}', "
                f"which is not installed"
            )
        visiting.add(name)
        for dep in sorted(pkg.requires):
            visit(dep, chain + (name,))
        visiting.discard(name)
        done.add(name)
        order.append(pkg)

    for name in sorted(packages):
        visit(name, ())
    return order


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

_LOADED = False
_LOADED_PACKAGES: list[Package] = []


def _import_entry(pkg: Package) -> None:
    path = pkg.entry_path
    if not path.is_file():
        raise FileNotFoundError(f"package {pkg.name}: entry {pkg.entry} not found")
    mod_name = f"openreagent._pkg.{pkg.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load package {pkg.name} from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    # Allow optional sibling imports within the package directory.
    pkg_dir = str(pkg.directory)
    sys.path.insert(0, pkg_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        try:
            sys.path.remove(pkg_dir)
        except ValueError:
            pass


def load(force: bool = False) -> list[Package]:
    """Discover, resolve, and import all packages in dependency order.
    Idempotent unless ``force``."""
    global _LOADED, _LOADED_PACKAGES
    if _LOADED and not force:
        return _LOADED_PACKAGES
    packages = discover()
    order = resolve_order(packages)
    for pkg in order:
        _import_entry(pkg)
    _LOADED = True
    _LOADED_PACKAGES = order
    return order


def load_path(directory: str | Path) -> list[Package]:
    """Load every package found under ``directory`` (recursively) without
    installing it — used by ``--recipe-dir`` style ad-hoc loading."""
    root = Path(directory).expanduser().resolve()
    found: dict[str, Package] = {}
    for mf in sorted(root.rglob(MANIFEST_NAME)):
        pkg = read_manifest(mf.parent, origin="installed")
        if pkg is not None:
            found[pkg.name] = pkg
    # Merge with already-available packages so dependencies resolve.
    merged = discover()
    merged.update(found)
    order = resolve_order(merged)
    loaded = [p for p in order if p.name in found]
    for pkg in loaded:
        _import_entry(pkg)
    return loaded


# ---------------------------------------------------------------------------
# Install / uninstall
# ---------------------------------------------------------------------------

def install(source: str) -> list[Package]:
    """Install one or more packages from a source (local dir/zip, http(s) zip,
    or ``github:owner/repo``). Returns the installed package descriptors."""
    materialized = sources.materialize(source)
    installed: list[Package] = []
    try:
        manifests = sorted(materialized.path.rglob(MANIFEST_NAME))
        if not manifests:
            raise ValueError(
                f"no {MANIFEST_NAME} found in source {source!r}; not an OpenReagent package"
            )
        dest_root = installed_packages_dir()
        dest_root.mkdir(parents=True, exist_ok=True)
        for mf in manifests:
            pkg = read_manifest(mf.parent, origin="installed")
            if pkg is None:
                continue
            dest = dest_root / pkg.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(mf.parent, dest)
            installed.append(read_manifest(dest, origin="installed"))
    finally:
        materialized.cleanup()
    if not installed:
        raise ValueError(f"no installable packages found in {source!r}")
    return installed


def uninstall(name: str) -> bool:
    dest = installed_packages_dir() / name
    if dest.is_dir():
        shutil.rmtree(dest)
        return True
    return False

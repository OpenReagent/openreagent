"""The package system: discovery, dependency order, install (dir + zip),
and ad-hoc loading."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from openreagent import packages
from openreagent.recipes import get_recipe

# A demo recipe package that reuses the built-in ``bytecode-hash`` shape, so it
# declares a real ``requires`` edge (shape provider must load first).
_DEMO_DETECTOR = '''
from openreagent.recipes import Extractor, Matcher, Recipe, Status, register_recipe
from openreagent.shapes import ShapeRef


class DemoExtractor(Extractor):
    impl = "demo"
    version = "1.0.0"

    def extract(self, source):
        return {"digest": "ab" * 32, "normalization": "demo"}


class DemoMatcher(Matcher):
    impl = "demo"
    version = "1.0.0"

    def match(self, value, sources, signature):
        return []


register_recipe(Recipe(
    name="demo-detector", version="1.0.0",
    shape=ShapeRef(name="bytecode-hash", version="1.0.0"),
    extractor=DemoExtractor(), matcher=DemoMatcher(),
    status=Status.EXPERIMENTAL, note="demo package",
))
'''


def _make_demo_pkg(directory: Path, name: str = "demo-detector") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "openreagent.json").write_text(json.dumps({
        "name": name, "version": "1.0.0", "kind": "recipe",
        "entry": "detector.py", "requires": ["bytecode-hash"],
        "description": "demo", "provides": {"recipes": [name]},
    }))
    (directory / "detector.py").write_text(_DEMO_DETECTOR.replace("demo-detector", name))
    return directory


def test_discover_builtin_packages():
    pkgs = packages.discover()
    for expected in ("bytecode-hash", "ast-sketch"):
        assert expected in pkgs, expected


def test_install_and_resolve_order(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("OPENREAGENT_HOME", str(home))
    pkg = _make_demo_pkg(tmp_path / "demo-detector")

    installed = packages.install(str(pkg))
    assert any(p.name == "demo-detector" for p in installed)
    assert (home / "packages" / "demo-detector" / "openreagent.json").is_file()

    pkgs = packages.discover()
    assert "demo-detector" in pkgs and pkgs["demo-detector"].origin == "installed"
    # A package's `requires` (its shape provider) loads before it.
    order = [p.name for p in packages.resolve_order(pkgs)]
    assert order.index("bytecode-hash") < order.index("demo-detector")

    packages.load(force=True)
    assert get_recipe("demo-detector") is not None


def test_install_from_zip(tmp_path, monkeypatch):
    home = tmp_path / "home2"
    monkeypatch.setenv("OPENREAGENT_HOME", str(home))
    pkg = _make_demo_pkg(tmp_path / "pkgsrc" / "demo-zip", name="demo-zip")
    archive = shutil.make_archive(str(tmp_path / "demo-zip"), "zip",
                                  root_dir=str(pkg.parent), base_dir="demo-zip")

    installed = packages.install(archive)
    assert any(p.name == "demo-zip" for p in installed)
    packages.load(force=True)
    assert get_recipe("demo-zip") is not None


def test_uninstall(tmp_path, monkeypatch):
    home = tmp_path / "home3"
    monkeypatch.setenv("OPENREAGENT_HOME", str(home))
    pkg = _make_demo_pkg(tmp_path / "demo-x", name="demo-x")
    packages.install(str(pkg))
    assert (home / "packages" / "demo-x").is_dir()
    assert packages.uninstall("demo-x") is True
    assert not (home / "packages" / "demo-x").exists()

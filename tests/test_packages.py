"""The package system: discovery, dependency order, install (dir + zip),
in-package references, and ad-hoc directory loading."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from openreagent import packages
from openreagent.recipes import get_recipe

_DEMO_DETECTOR = '''
from openreagent.matching import site_targets, slot
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor
from openreagent.shapes import ShapeRef


class DemoExtractor(SlotFillExtractor):
    impl = "demo-fill"
    version = "1.0.0"
    slot_keys = ("site",)


class DemoMatcher(Matcher):
    impl = "demo"
    version = "1.0.0"

    def match(self, value, sources, signature):
        return []


register_recipe(Recipe(
    name="demo-detector", version="1.0.0",
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=DemoExtractor(), matcher=DemoMatcher(),
    status=Status.EXPERIMENTAL, note="demo package",
))
'''


def _make_demo_pkg(directory: Path, name: str = "demo-detector") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "openreagent.json").write_text(json.dumps({
        "name": name, "version": "1.0.0", "kind": "recipe",
        "entry": "detector.py", "requires": ["slot-spec"],
        "description": "demo", "provides": {"recipes": [name]},
    }))
    (directory / "detector.py").write_text(_DEMO_DETECTOR.replace("demo-detector", name))
    return directory


def test_discover_builtin_packages():
    pkgs = packages.discover()
    for expected in ("slot-spec", "internal-absence", "canonical-divergence",
                     "bytecode-hash", "ast-sketch"):
        assert expected in pkgs, expected
    assert pkgs["slot-spec"].kind == "shape"


def test_resolve_order_shape_before_recipe():
    pkgs = packages.discover()
    order = [p.name for p in packages.resolve_order(pkgs)]
    assert order.index("slot-spec") < order.index("internal-absence")
    assert order.index("slot-spec") < order.index("canonical-divergence")


def test_references_bundled_in_package():
    pkgs = packages.discover()
    cd = pkgs["canonical-divergence"]
    assert (cd.directory / "references" / "uniswap_v2" / "twap_price.json").is_file()
    # There is no global references directory anymore.
    assert "references" not in pkgs


def test_install_from_local_dir(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("OPENREAGENT_HOME", str(home))
    pkg = _make_demo_pkg(tmp_path / "demo-detector")

    installed = packages.install(str(pkg))
    assert any(p.name == "demo-detector" for p in installed)
    assert (home / "packages" / "demo-detector" / "openreagent.json").is_file()

    disc = packages.discover()
    assert "demo-detector" in disc and disc["demo-detector"].origin == "installed"

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

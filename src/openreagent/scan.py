"""The scan path: pool of signatures + target code -> findings.

This module is deterministic and LLM-free *by construction*. It imports no LLM
client, directly or transitively (a test guard asserts this). The same pool and
the same input produce byte-identical findings across runs.

Flow:
  1. Load shapes and recipes (registration side effects).
  2. Load the target Solidity (sorted, deterministic).
  3. Load the pool of signatures, validating each against its recipe's shape.
  4. For each signature whose recipe is enabled, run that recipe's matcher.
  5. Return findings in a stable sort order.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from openreagent import loader
from openreagent.frameworks import Framework, detect as detect_framework
from openreagent.pool import PoolEntry, load_pool
from openreagent.recipes import Finding, Recipe, all_recipes, get_recipe
from openreagent.solidity import SourceFile, load_target


@dataclass
class ScanReport:
    findings: list[Finding]
    enabled_recipes: list[str]
    pool_size: int
    files_scanned: int
    skipped: list[dict] = field(default_factory=list)
    target: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tool": {"name": "openreagent", "rules": sorted(self.enabled_recipes)},
            "target": self.target,
            "summary": {
                "pool_size": self.pool_size,
                "files_scanned": self.files_scanned,
                "findings": len(self.findings),
            },
            "findings": [f.to_dict() for f in self.findings],
            "skipped": self.skipped,
        }


def enabled_recipe_set(enable: list[str] | None = None,
                       disable: list[str] | None = None) -> dict[str, Recipe]:
    """Resolve which recipes are active.

    Defaults follow each recipe's ``default_enabled`` (production on; everything
    else off). ``enable`` turns specific recipes on (by name); ``disable`` turns
    them off. ``enable=['*']`` turns every registered recipe on.
    """
    loader.load_builtins()
    enable = enable or []
    disable = disable or []
    active: dict[str, Recipe] = {}
    enable_all = "*" in enable
    for recipe in all_recipes():
        on = recipe.default_enabled or enable_all or recipe.name in enable
        if recipe.name in disable:
            on = False
        if on:
            active[recipe.name] = recipe
    return active


def _describe_target(target: str | Path, framework: str | None) -> dict:
    """Detect the target's build framework and describe it for the report.

    Detection is deterministic and performs no build (see ``frameworks.py``). An
    explicit ``framework`` override wins; otherwise the single detected framework
    is reported, and an ambiguous layout is reported as such with no guess.
    """
    detection = detect_framework(target)
    info = detection.to_dict()
    if framework:
        info["framework"] = Framework(framework.lower().strip()).value
        info["resolved_by"] = "override"
    elif detection.framework is not None:
        info["resolved_by"] = "detected"
    else:
        info["resolved_by"] = "ambiguous"  # framework stays null until a choice is made
    return info


def scan(
    target: str | Path,
    pool: str | Path | None = None,
    enable: list[str] | None = None,
    disable: list[str] | None = None,
    recipe_dirs: list[str] | None = None,
    store=None,
    framework: str | None = None,
) -> ScanReport:
    loader.load_builtins()
    for d in recipe_dirs or []:
        loader.load_extra_dir(d)

    target_info = _describe_target(target, framework)
    sources: list[SourceFile] = load_target(target)
    active = enabled_recipe_set(enable, disable)

    entries: list[PoolEntry] = load_pool(pool, store=store)
    # Deterministic processing order.
    entries = sorted(entries, key=lambda e: e.signature.id)

    findings: list[Finding] = []
    skipped: list[dict] = []

    for entry in entries:
        sig = entry.signature
        recipe = get_recipe(sig.recipe.name, sig.recipe.version)
        if recipe is None:
            skipped.append({"signature": sig.id, "reason": "recipe not registered",
                            "recipe": f"{sig.recipe.name}@{sig.recipe.version}"})
            continue
        if recipe.name not in active:
            skipped.append({"signature": sig.id, "reason": "recipe disabled",
                            "recipe": recipe.name})
            continue
        try:
            matched = recipe.matcher.match(sig.value, sources, sig)
        except Exception as exc:  # a single bad signature must not abort the scan
            skipped.append({"signature": sig.id, "reason": f"matcher error: {exc}",
                            "recipe": recipe.name})
            continue
        findings.extend(matched)

    findings.sort(key=lambda f: (f.file, f.line, f.recipe, f.function, f.signature_id))
    return ScanReport(
        findings=findings,
        enabled_recipes=[r.name for r in active.values()],
        pool_size=len(entries),
        files_scanned=len(sources),
        skipped=skipped,
        target=target_info,
    )

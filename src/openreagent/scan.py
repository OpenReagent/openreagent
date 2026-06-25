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
from openreagent.building import BuildResult, build as build_target
from openreagent.codeview import CodeView
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
    # The full build artifacts (bytecode / AST) for downstream recipe use. Held
    # on the report but not serialized by ``to_dict`` (only a compact summary,
    # under ``target['build']``, is). Consumed by the artifact-fed recipe path.
    build: BuildResult | None = field(default=None, repr=False)

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


def _describe_target(target: str | Path, framework: str | None, do_build: bool, install: bool):
    """Detect the target's framework, build it, and describe both for the report.

    Detection is deterministic and performs no build (see ``frameworks.py``). An
    explicit ``framework`` override wins; otherwise the single detected framework
    is used, and an ambiguous layout is left unresolved (no guess). The build runs
    at arm's length and is best-effort: a missing toolchain or a failure degrades
    gracefully (see ``building.py``). Returns ``(info_dict, build_result)``.
    """
    detection = detect_framework(target)
    resolved = Framework(framework.lower().strip()) if framework else detection.framework
    info = detection.to_dict()
    if framework:
        info["framework"] = resolved.value
        info["resolved_by"] = "override"
    elif detection.framework is not None:
        info["resolved_by"] = "detected"
    else:
        info["resolved_by"] = "ambiguous"  # framework stays null until a choice is made

    build_result = build_target(detection, resolved, enabled=do_build, install=install)
    info["build"] = build_result.summary()
    return info, build_result


def scan(
    target: str | Path,
    pool: str | Path | None = None,
    enable: list[str] | None = None,
    disable: list[str] | None = None,
    recipe_dirs: list[str] | None = None,
    store=None,
    framework: str | None = None,
    do_build: bool = True,
    install_toolchain: bool = False,
) -> ScanReport:
    loader.load_builtins()
    for d in recipe_dirs or []:
        loader.load_extra_dir(d)

    target_info, build_result = _describe_target(target, framework, do_build, install_toolchain)
    sources: list[SourceFile] = load_target(target)
    # The unified scan input: lexical Code + (when built) Bytecode/AST/ABI. Acts
    # as the source list for existing matchers; artifact-aware recipes read more.
    code = CodeView(sources, build_result)
    active = enabled_recipe_set(enable, disable)

    if store is not None and store is not False:
        # Remote store: match against the server (the PSI seam) — never download
        # the signature set, never send code; only candidate fingerprints.
        findings, skipped, pool_size = _scan_via_server(code, active, store)
    else:
        # Local pool: a directory/file of signature records, matched in-process.
        findings, skipped, pool_size = _scan_local_pool(pool, code, active)

    findings.sort(key=lambda f: (f.file, f.line, f.recipe, f.function, f.signature_id))
    return ScanReport(
        findings=findings,
        enabled_recipes=[r.name for r in active.values()],
        pool_size=pool_size,
        files_scanned=len(sources),
        skipped=skipped,
        target=target_info,
        build=build_result,
    )


def _scan_local_pool(pool, code, active) -> tuple[list[Finding], list[dict], int]:
    entries: list[PoolEntry] = sorted(load_pool(pool), key=lambda e: e.signature.id)
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
            skipped.append({"signature": sig.id, "reason": "recipe disabled", "recipe": recipe.name})
            continue
        try:
            findings.extend(recipe.matcher.match(sig.value, code, sig))
        except Exception as exc:  # a single bad signature must not abort the scan
            skipped.append({"signature": sig.id, "reason": f"matcher error: {exc}",
                            "recipe": recipe.name})
    return findings, skipped, len(entries)


def _scan_via_server(code, active, store) -> tuple[list[Finding], list[dict], int]:
    from openreagent import matchlib
    from openreagent.client import OpenReagentClient
    from openreagent.matching import tier_for

    client = OpenReagentClient(None if store is True else store)
    candidates: dict[str, list[dict]] = {}
    labels: dict[str, list[str]] = {}
    for recipe in active.values():
        cv = matchlib.candidate_values(recipe, code)
        if not cv:
            continue
        labels[recipe.name] = [label for label, _ in cv]
        candidates[recipe.name] = [value for _, value in cv]

    findings: list[Finding] = []
    matches = client.match(candidates) if candidates else []
    for m in matches:
        rn = m.get("recipe", "")
        idx = int(m.get("candidate", -1))
        label = labels.get(rn, [""])[idx] if 0 <= idx < len(labels.get(rn, [])) else ""
        file, _, function = label.partition("#")
        recipe = active.get(rn)
        score = float(m.get("score", 1.0))
        findings.append(Finding(
            recipe=rn, recipe_version=recipe.version if recipe else "?",
            signature_id=m.get("signature_id", "?"),
            file=file or "?", function=function, line=1,
            tier=tier_for(score) or "HIGH", score=round(score, 3),
            message=f"matched signature {m.get('signature_id', '?')} in the remote store "
                    f"(score {score:.2f})",
            details={"score": round(score, 3), "via": "server"},
        ))
    pool_size = sum(len(v) for v in candidates.values())  # candidate fingerprints queried
    return findings, [], pool_size

"""Recipe: canonical-divergence/1.0.0  (shape: slot-spec/v1)

Divergence from a canonical reference. The signature names a canonical pattern
via the ``canonical_reference`` slot (a reference id resolved against this
package's own ``references/`` directory) and, optionally, a ``site``.

The reference library is bundled *inside this package* and loaded relative to
this module — a recipe owns its references; there is no global reference
directory. Add a reference by dropping a JSON file under ``references/`` in this
package (see ``references/README.md``).

Matcher: at each candidate site, compare the implementation against the
reference. Divergence is flagged when the reference's required markers are
absent or its forbidden markers are present. Sites discovered from the named
``site`` slot are "primary"; sites discovered only via the reference's own name
hints are "fallback" and capped at MEDIUM tier (never HIGH).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from openreagent.matching import (
    function_in_scope,
    marker_present,
    name_match,
    site_targets,
    slot,
)
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor, make_finding
from openreagent.shapes import ShapeRef
from openreagent.solidity import iter_functions

NAME = "canonical-divergence"
VERSION = "1.0.0"

# References live inside this package, next to this module.
_REFERENCES_DIR = Path(__file__).resolve().parent / "references"


@lru_cache(maxsize=1)
def _references() -> dict:
    refs: dict[str, dict] = {}
    if not _REFERENCES_DIR.is_dir():
        return refs
    for path in sorted(_REFERENCES_DIR.rglob("*.json"), key=str):
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        rid = rec.get("reference_id")
        if rid:
            refs[rid] = rec
    return refs


def _resolve_ref_id(cr) -> str | None:
    if isinstance(cr, str):
        return cr.strip()
    if isinstance(cr, dict):
        return cr.get("reference_id") or cr.get("id")
    return None


class DivergenceExtractor(SlotFillExtractor):
    impl = "canonical-divergence-slot-fill"
    version = "1.0.0"
    slot_keys = ("operation", "site", "canonical_reference")


class DivergenceMatcher(Matcher):
    impl = "canonical-divergence-detector"
    version = "1.0.0"

    def match(self, value, sources, signature):
        ref_id = _resolve_ref_id(slot(value, "canonical_reference"))
        if not ref_id:
            return []
        ref = _references().get(ref_id)
        if ref is None:
            return []  # unresolved reference -> nothing to compare against

        required = ref.get("required_markers", [])
        forbidden = ref.get("forbidden_markers", [])
        funcs, files = site_targets(slot(value, "site"))
        primary_scope = bool(funcs or files)

        findings = []
        seen = set()
        for src, fn in iter_functions(sources):
            confidence = None
            if primary_scope and function_in_scope(src, fn, funcs, files):
                confidence = "primary"
            elif not primary_scope and self._matches_hints(fn, ref):
                confidence = "fallback"
            if confidence is None:
                continue

            missing = [m for m in required if not marker_present(fn, [m])]
            present_forbidden = [m for m in forbidden if marker_present(fn, [m])]
            if not missing and not present_forbidden:
                continue  # conforms to the canonical pattern

            key = (src.path, fn.name, fn.start_line)
            if key in seen:
                continue
            seen.add(key)

            score = 0.8 if confidence == "primary" else 0.6
            if confidence == "fallback":
                score = min(score, 0.65)  # one notch below HIGH
            findings.append(make_finding(
                NAME, VERSION, signature, src, fn, fn.start_line, score,
                message=(f"{fn.name} diverges from canonical reference '{ref_id}' "
                         f"({ref.get('name', '')}); missing={missing or '-'}, "
                         f"forbidden_present={present_forbidden or '-'} [{confidence}]"),
                details={"reference_id": ref_id, "confidence": confidence,
                         "missing_markers": missing,
                         "forbidden_present": present_forbidden},
            ))
        return findings

    @staticmethod
    def _matches_hints(fn, ref) -> bool:
        hints = ref.get("site_match", {})
        for p in hints.get("name_patterns", []):
            if name_match(fn.name, p):
                return True
        toks = [t.lower() for t in hints.get("body_match_tokens", [])]
        if toks and marker_present(fn, toks):
            return True
        return False


register_recipe(Recipe(
    name=NAME,
    version=VERSION,
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=DivergenceExtractor(),
    matcher=DivergenceMatcher(),
    status=Status.PRODUCTION,
    note="divergence from a canonical reference (references bundled in-package)",
))

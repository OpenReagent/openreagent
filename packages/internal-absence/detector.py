"""Recipe: internal-absence/1.0.0  (shape: slot-spec/v1)

A required element that should be present at a named site is missing. The
signature names the required element via ``operation`` (a key into the built-in
required-element vocabulary, or explicit markers in ``attribute``) and the
location via ``site``.

Matcher: for each in-scope function, if none of the element's markers are
present, the element is judged absent and a finding is emitted. A function named
explicitly by the site scores higher than a file-only match.
"""
from __future__ import annotations

from openreagent._markers import REQUIRED_ELEMENT_MARKERS, normalize
from openreagent.matching import (
    as_token_list,
    function_in_scope,
    marker_present,
    site_targets,
    slot,
)
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor, make_finding
from openreagent.shapes import ShapeRef
from openreagent.solidity import iter_functions

NAME = "internal-absence"
VERSION = "1.0.0"


class AbsenceExtractor(SlotFillExtractor):
    impl = "internal-absence-slot-fill"
    version = "1.0.0"
    slot_keys = ("operation", "attribute", "site")


class AbsenceMatcher(Matcher):
    impl = "internal-absence-detector"
    version = "1.0.0"

    def _markers(self, value) -> list[str]:
        op = normalize(slot(value, "operation"))
        markers = list(REQUIRED_ELEMENT_MARKERS.get(op, []))
        markers.extend(as_token_list(slot(value, "attribute")))
        return [m for m in markers if m]

    def match(self, value, sources, signature):
        markers = self._markers(value)
        if not markers:
            return []  # cannot decide presence/absence without a vocabulary
        funcs, files = site_targets(slot(value, "site"))
        if not funcs and not files:
            return []  # require a site to avoid scanning the whole codebase blindly
        findings = []
        for src, fn in iter_functions(sources):
            if not function_in_scope(src, fn, funcs, files):
                continue
            if marker_present(fn, markers):
                continue  # element present -> not absent
            named = bool(funcs and any(p == fn.name for p in funcs))
            score = 0.8 if named else 0.5
            findings.append(make_finding(
                NAME, VERSION, signature, src, fn, fn.start_line, score,
                message=(f"required element '{normalize(slot(value, 'operation')) or 'element'}' "
                         f"appears absent in {fn.name} (no markers: {markers})"),
                details={"markers": markers, "named_site": named,
                         "operation": normalize(slot(value, "operation"))},
            ))
        return findings


register_recipe(Recipe(
    name=NAME,
    version=VERSION,
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=AbsenceExtractor(),
    matcher=AbsenceMatcher(),
    status=Status.PRODUCTION,
    note="a required element is absent at a named site",
))

"""Recipe: generic-slot/1.0.0  (shape: slot-spec/v1)

The unclassified fallback. A finding that is expressible in the slot-spec
vocabulary but fits no specific recipe uses this one. It carries no specific
semantics, so its matcher is deliberately weak: it gathers the concrete tokens
mentioned across the value's slots and ``freeform``, and flags an in-scope
function in which several of them co-occur. Matches are capped at MEDIUM tier and
the recipe is off by default.
"""
from __future__ import annotations

from openreagent.matching import as_token_list, function_in_scope, marker_present, site_targets, slot
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor, make_finding
from openreagent.shapes import ShapeRef
from openreagent.solidity import iter_functions

NAME = "generic-slot"
VERSION = "1.0.0"
_MIN_COOCCUR = 3


class GenericSlotExtractor(SlotFillExtractor):
    impl = "generic-slot-fill"
    version = "1.0.0"
    slot_keys = ("operation", "attribute", "operator", "site", "intended_order", "canonical_reference")


class GenericSlotMatcher(Matcher):
    impl = "generic-slot-matcher"
    version = "1.0.0"

    @staticmethod
    def _tokens(value) -> list[str]:
        toks: list[str] = []
        for key in ("operation", "attribute", "intended_order"):
            toks.extend(as_token_list(slot(value, key)))
        free = value.get("freeform") if isinstance(value, dict) else None
        if isinstance(free, str):
            toks.extend(w.lower() for w in free.split() if len(w) > 3)
        return list(dict.fromkeys(t for t in toks if len(t) > 2))

    def match(self, value, sources, signature):
        tokens = self._tokens(value)
        if len(tokens) < _MIN_COOCCUR:
            return []
        funcs, files = site_targets(slot(value, "site"))
        findings = []
        for src, fn in iter_functions(sources):
            if (funcs or files) and not function_in_scope(src, fn, funcs, files):
                continue
            hits = [t for t in tokens if marker_present(fn, [t])]
            if len(hits) < _MIN_COOCCUR:
                continue
            score = min(0.4 + 0.05 * (len(hits) - _MIN_COOCCUR), 0.65)
            findings.append(make_finding(
                NAME, VERSION, signature, src, fn, fn.start_line, score,
                message=(f"{fn.name} mentions {len(hits)} signature tokens "
                         f"({hits}); unclassified candidate"),
                details={"matched_tokens": hits},
            ))
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=GenericSlotExtractor(), matcher=GenericSlotMatcher(),
    status=Status.EXPERIMENTAL,
    default_enabled=False,
    note="expressible but unclassified fallback",
))

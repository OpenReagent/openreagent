"""Recipe: aggregated-state/1.0.0  (shape: slot-spec/v1)

Aggregated (global) state is not maintained consistently with keyed (per-account)
state: a function updates the keyed quantity but not its aggregate (or vice
versa). The signature names the aggregate via ``operation`` and the keyed
quantity via ``attribute``, with a ``site``.

Matcher: in an in-scope function that touches the keyed state, flag the function
when the aggregate state is not also touched.
"""
from __future__ import annotations

from openreagent._markers import AGGREGATE_STATE_MARKERS, KEYED_STATE_MARKERS, normalize
from openreagent.matching import as_token_list, function_in_scope, marker_present, site_targets, slot
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor, make_finding
from openreagent.shapes import ShapeRef
from openreagent.solidity import iter_functions

NAME = "aggregated-state"
VERSION = "1.0.0"


class AggregateExtractor(SlotFillExtractor):
    impl = "aggregated-state-slot-fill"
    version = "1.0.0"
    slot_keys = ("operation", "attribute", "site")


class AggregateMatcher(Matcher):
    impl = "aggregated-state-detector"
    version = "1.0.0"

    def match(self, value, sources, signature):
        agg_key = normalize(slot(value, "operation"))
        keyed_key = normalize(slot(value, "attribute"))
        agg_markers = AGGREGATE_STATE_MARKERS.get(agg_key, []) + as_token_list(slot(value, "operation"))
        keyed_markers = KEYED_STATE_MARKERS.get(keyed_key, []) + as_token_list(slot(value, "attribute"))
        agg_markers = [m for m in agg_markers if m]
        keyed_markers = [m for m in keyed_markers if m]
        if not agg_markers or not keyed_markers:
            return []
        funcs, files = site_targets(slot(value, "site"))
        findings = []
        for src, fn in iter_functions(sources):
            if (funcs or files) and not function_in_scope(src, fn, funcs, files):
                continue
            if not marker_present(fn, keyed_markers):
                continue
            if marker_present(fn, agg_markers):
                continue  # both maintained -> consistent
            findings.append(make_finding(
                NAME, VERSION, signature, src, fn, fn.start_line, 0.55,
                message=(f"{fn.name} updates keyed state {keyed_markers} but not "
                         f"aggregate state {agg_markers}"),
                details={"aggregate": agg_markers, "keyed": keyed_markers},
            ))
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=AggregateExtractor(), matcher=AggregateMatcher(),
    status=Status.EXPERIMENTAL,
    note="aggregated state inconsistent with keyed state",
))

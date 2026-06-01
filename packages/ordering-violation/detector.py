"""Recipe: ordering-violation/1.0.0  (shape: slot-spec/v1)

Two operations occur in the wrong order (the classic case is an external call
before a state update — a checks-effects-interactions violation). The signature
carries ``intended_order`` as a list ``[earlier_marker, later_marker]`` and a
``site``.

Matcher: in an in-scope function where both markers occur, flag the function
when the marker that should come *later* actually appears before the marker that
should come *earlier*. The finding is emitted at the out-of-order line.
"""
from __future__ import annotations

from openreagent.matching import as_token_list, function_in_scope, site_targets, slot
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor, make_finding
from openreagent.shapes import ShapeRef
from openreagent.solidity import iter_functions

NAME = "ordering-violation"
VERSION = "1.0.0"


class OrderingExtractor(SlotFillExtractor):
    impl = "ordering-violation-slot-fill"
    version = "1.0.0"
    slot_keys = ("intended_order", "site")


class OrderingMatcher(Matcher):
    impl = "ordering-violation-detector"
    version = "1.0.0"

    def match(self, value, sources, signature):
        order = as_token_list(slot(value, "intended_order"))
        if len(order) < 2:
            return []
        earlier, later = order[0], order[1]
        funcs, files = site_targets(slot(value, "site"))
        findings = []
        for src, fn in iter_functions(sources):
            if (funcs or files) and not function_in_scope(src, fn, funcs, files):
                continue
            line_earlier = fn.first_line_matching([earlier])
            line_later = fn.first_line_matching([later])
            if line_earlier is None or line_later is None:
                continue
            if line_later < line_earlier:
                findings.append(make_finding(
                    NAME, VERSION, signature, src, fn, line_later, 0.7,
                    message=(f"in {fn.name}, '{later}' (line {line_later}) precedes "
                             f"'{earlier}' (line {line_earlier}); intended order is "
                             f"'{earlier}' then '{later}'"),
                    details={"intended_order": [earlier, later],
                             "earlier_line": line_earlier, "later_line": line_later},
                ))
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=OrderingExtractor(), matcher=OrderingMatcher(),
    status=Status.EXPERIMENTAL,
    note="two operations occur in the wrong order",
))

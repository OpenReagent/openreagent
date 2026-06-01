"""Recipe: unbound-caller-value/1.0.0  (shape: slot-spec/v1)

A caller-supplied value is used without being bound (validated or constrained).
The signature names the parameter(s) via ``attribute`` and the location via
``site``.

Matcher: in an in-scope function whose parameters include the named value, flag
the function when the value appears in the body but is never referenced by a
require/assert/if guard.
"""
from __future__ import annotations

from openreagent.matching import as_token_list, function_in_scope, site_targets, slot
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor, make_finding
from openreagent.shapes import ShapeRef
from openreagent.solidity import iter_functions

NAME = "unbound-caller-value"
VERSION = "1.0.0"


class UnboundExtractor(SlotFillExtractor):
    impl = "unbound-caller-value-slot-fill"
    version = "1.0.0"
    slot_keys = ("attribute", "site")


class UnboundMatcher(Matcher):
    impl = "unbound-caller-value-detector"
    version = "1.0.0"

    def match(self, value, sources, signature):
        params = as_token_list(slot(value, "attribute"))
        if not params:
            return []
        funcs, files = site_targets(slot(value, "site"))
        findings = []
        for src, fn in iter_functions(sources):
            if (funcs or files) and not function_in_scope(src, fn, funcs, files):
                continue
            fn_params = {p.lower() for p in fn.params}
            for param in params:
                pl = param.lower()
                if pl not in fn_params:
                    continue
                if self._is_bound(fn, param):
                    continue
                findings.append(make_finding(
                    NAME, VERSION, signature, src, fn, fn.start_line, 0.6,
                    message=(f"caller-supplied '{param}' is used in {fn.name} without a "
                             f"require/assert/if guard binding it"),
                    details={"parameter": param},
                ))
                break
        return findings

    @staticmethod
    def _is_bound(fn, param: str) -> bool:
        pl = param.lower()
        for line in fn.body_text.lower().splitlines():
            if pl in line and ("require(" in line or "assert(" in line or line.strip().startswith("if")):
                return True
        return False


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=UnboundExtractor(), matcher=UnboundMatcher(),
    status=Status.EXPERIMENTAL,
    note="caller-supplied value used without a binding check",
))

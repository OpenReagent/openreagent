"""Recipe: operator-direction/1.0.0  (shape: slot-spec/v1)

A comparison uses the wrong direction (for example ``<=`` where ``>=`` was
intended). The signature carries the ``operator`` slot, either a dict
``{"intended": ">=", "wrong": "<="}`` or just ``{"intended": ">="}`` (the wrong
operator is then inferred as the reverse).

Matcher: in an in-scope function, flag a comparison that uses the wrong
operator, emitting at the comparison's line. Operator direction is inherently
approximate without operand binding, so matches are capped at MEDIUM tier.
"""
from __future__ import annotations

from openreagent.matching import function_in_scope, site_targets, slot
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor, make_finding
from openreagent.shapes import ShapeRef
from openreagent.solidity import iter_functions

NAME = "operator-direction"
VERSION = "1.0.0"

_REVERSE = {">=": "<=", "<=": ">=", ">": "<", "<": ">", "==": "!=", "!=": "=="}


class OperatorExtractor(SlotFillExtractor):
    impl = "operator-direction-slot-fill"
    version = "1.0.0"
    slot_keys = ("operator", "site")


class OperatorMatcher(Matcher):
    impl = "operator-direction-detector"
    version = "1.0.0"

    @staticmethod
    def _ops(value):
        op = slot(value, "operator")
        intended = wrong = None
        if isinstance(op, dict):
            intended = op.get("intended")
            wrong = op.get("wrong") or op.get("observed") or op.get("actual")
        elif isinstance(op, str):
            intended = op.strip()
        if wrong is None and intended in _REVERSE:
            wrong = _REVERSE[intended]
        return intended, wrong

    def match(self, value, sources, signature):
        intended, wrong = self._ops(value)
        if not wrong:
            return []
        funcs, files = site_targets(slot(value, "site"))
        findings = []
        for src, fn in iter_functions(sources):
            if (funcs or files) and not function_in_scope(src, fn, funcs, files):
                continue
            for op, line in fn.comparisons():
                if op == wrong:
                    findings.append(make_finding(
                        NAME, VERSION, signature, src, fn, line, 0.6,
                        message=(f"{fn.name} uses '{wrong}' where '{intended}' was "
                                 f"intended (operator direction)"),
                        details={"intended": intended, "wrong": wrong},
                    ))
                    break  # one finding per function
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=OperatorExtractor(), matcher=OperatorMatcher(),
    status=Status.EXPERIMENTAL,
    note="comparison operator points the wrong way",
))

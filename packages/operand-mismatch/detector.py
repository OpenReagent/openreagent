"""Recipe: operand-mismatch/1.0.0  (shape: slot-spec/v1)

An operation is performed against the wrong operand attribute (for example, a
check that should read one quantity reads a sibling quantity instead). The
signature names the operation via ``operation`` and the expected/wrong operand
attributes via ``attribute``.

Matcher: in an in-scope function where the operation token appears, flag the
function when a "wrong" attribute marker is present and the "expected" attribute
marker is absent.
"""
from __future__ import annotations

from openreagent._markers import normalize
from openreagent.matching import as_token_list, function_in_scope, marker_present, site_targets, slot
from openreagent.recipes import Matcher, Recipe, Status, register_recipe
from openreagent.recipe_lib import SlotFillExtractor, make_finding
from openreagent.shapes import ShapeRef
from openreagent.solidity import iter_functions

NAME = "operand-mismatch"
VERSION = "1.0.0"


class OperandExtractor(SlotFillExtractor):
    impl = "operand-mismatch-slot-fill"
    version = "1.0.0"
    slot_keys = ("operation", "attribute", "site")


class OperandMatcher(Matcher):
    impl = "operand-mismatch-detector"
    version = "1.0.0"

    @staticmethod
    def _attrs(value):
        attr = slot(value, "attribute")
        if isinstance(attr, dict):
            expected = as_token_list(attr.get("expected"))
            wrong = as_token_list(attr.get("wrong") or attr.get("actual"))
        else:
            expected = []
            wrong = as_token_list(attr)
        return expected, wrong

    def match(self, value, sources, signature):
        op = normalize(slot(value, "operation"))
        expected, wrong = self._attrs(value)
        if not op or not wrong:
            return []
        funcs, files = site_targets(slot(value, "site"))
        findings = []
        for src, fn in iter_functions(sources):
            if (funcs or files) and not function_in_scope(src, fn, funcs, files):
                continue
            if not marker_present(fn, [op]):
                continue
            if not marker_present(fn, wrong):
                continue
            if expected and marker_present(fn, expected):
                continue  # expected operand is present -> no mismatch
            findings.append(make_finding(
                NAME, VERSION, signature, src, fn, fn.start_line, 0.7,
                message=(f"{fn.name} uses operand {wrong} with operation '{op}' "
                         f"where {expected or 'the canonical operand'} was expected"),
                details={"operation": op, "expected": expected, "wrong": wrong},
            ))
        return findings


register_recipe(Recipe(
    name=NAME, version=VERSION,
    shape=ShapeRef(name="slot-spec", version="1.0.0"),
    extractor=OperandExtractor(), matcher=OperandMatcher(),
    status=Status.EXPERIMENTAL,
    note="operation reads the wrong operand attribute",
))

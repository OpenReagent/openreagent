"""Server-side matching primitives — the seam where PSI will later slot in.

The remote store never receives a client's code. Instead the client derives, from
its own target, a set of **candidate values** per recipe (by re-running each
recipe's deterministic extractor over each unit — file, function, or contract),
and the server compares those against its stored signature values. Today the
comparison is plaintext (digest equality / MinHash Jaccard / hash containment);
the request/response of that comparison is the boundary a Private Set
Intersection protocol will later replace, so neither side reveals non-matching
elements.

Both functions are pure and deterministic.

Notes / v1 limitations:
- Parametric recipes (MinHash ``num_perm``/``ngram``, snippet ``ngram``) are
  compared assuming the **default** recipe parameters, which the built-in
  extractors use. Signatures stored with non-default parameters may not compare.
- Unit enumeration is known for the built-in recipes; third-party recipes are
  not server-matchable until they declare it (future work).
"""
from __future__ import annotations

from openreagent._hashing import jaccard
from openreagent.matching import ast_for, bytecode_for
from openreagent.solidity import iter_functions

# Default similarity thresholds per recipe (mirror each matcher's tau).
_TAU = {"bytecode-hash": 1.0, "function-skeleton": 1.0, "snippet-match": 0.8,
        "ast-sketch": 0.7, "bytecode-sketch": 0.7}


def candidate_values(recipe, code) -> list[tuple[str, dict]]:
    """``(unit_label, value)`` candidates derived from ``code`` for ``recipe``.

    ``unit_label`` lets the *client* map a match back to a file/function for the
    finding; it is never required to be sent to the server.
    """
    name, ex = recipe.name, recipe.extractor
    out: list[tuple[str, dict]] = []
    if name == "bytecode-hash":
        for src in code:
            out.append((src.path, ex.extract({"source": src.text})))
            for contract, bc in bytecode_for(code, src):
                out.append((f"{src.path}#{contract}", ex.extract({"bytecode": bc})))
    elif name == "function-skeleton":
        for src, fn in iter_functions(code):
            out.append((f"{src.path}#{fn.name}", ex.extract({"source": fn.body_text})))
    elif name == "ast-sketch":
        for src in code:
            ast = ast_for(code, src)
            out.append((src.path, ex.extract({"ast": ast} if ast is not None else {"source": src.text})))
    elif name == "bytecode-sketch":
        for src in code:
            for contract, bc in bytecode_for(code, src):
                out.append((f"{src.path}#{contract}", ex.extract({"bytecode": bc})))
    elif name == "snippet-match":
        for src in code:
            try:
                out.append((src.path, ex.extract({"source": src.text})))
            except ValueError:
                continue  # too short for the n-gram
    return out


def compare(stored_value: dict, candidate_value: dict) -> float:
    """Similarity in [0,1] between a stored signature value and a candidate.

    Shape-aware: exact digest (1.0/0.0, normalization family must agree), MinHash
    Jaccard, or hash-set containment (stored ⊆ candidate). Unknown shapes -> 0.
    """
    if "digest" in stored_value and "digest" in candidate_value:
        sd = stored_value["digest"].lower().removeprefix("0x")
        cd = candidate_value["digest"].lower().removeprefix("0x")
        sn = str(stored_value.get("normalization", "")).split(":")[0]
        cn = str(candidate_value.get("normalization", "")).split(":")[0]
        return 1.0 if (sd == cd and sn == cn) else 0.0
    if "minhash" in stored_value and "minhash" in candidate_value:
        a, b = stored_value["minhash"], candidate_value["minhash"]
        return jaccard(a, b) if len(a) == len(b) else 0.0
    if "hashes" in stored_value and "hashes" in candidate_value:
        s = set(stored_value["hashes"])
        c = set(candidate_value["hashes"])
        return (len(s & c) / len(s)) if s else 0.0
    return 0.0


def tau_for(recipe_name: str) -> float:
    return _TAU.get(recipe_name, 0.7)

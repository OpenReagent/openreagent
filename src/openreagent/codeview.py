"""The unified scan-input model: Code + Bytecode + AST + ABI.

A :class:`CodeView` is what the scan path hands to a matcher. It **behaves as the
list of** :class:`~openreagent.solidity.SourceFile` (the lexical *Code* view) for
full backward compatibility — existing matchers iterate it unchanged — while also
carrying, per source, the compiled **Bytecode / AST / ABI** recovered by the
build (``building.Artifact``).

The lexical view is the **fallback**: when a target did not build (no toolchain,
offline, partial / non-compiling code), a ``CodeView`` simply has no artifacts and
artifact-aware recipes degrade to the lexical Code view. Matchers reach the
artifacts through the helpers in ``matching.py`` (``artifacts_for`` / ``ast_for``
/ ``abi_for`` / ``bytecode_for``), so a plain ``list`` (e.g. in a unit test)
transparently yields "no artifacts".

Source↔artifact reconciliation lives here, in one place: a toolchain names a
source differently (Hardhat ``contracts/Foo.sol``, vanilla an absolute path,
Foundry the AST ``absolutePath``), so artifacts are indexed by path *suffixes*
and looked up most-specific-first.
"""
from __future__ import annotations


def _suffix_keys(path: str) -> list[str]:
    """Trailing path keys, most specific first: ``a/b/c.sol`` -> [a/b/c.sol, b/c.sol, c.sol]."""
    parts = str(path).replace("\\", "/").split("/")
    return ["/".join(parts[-n:]) for n in range(min(3, len(parts)), 0, -1)]


class CodeView(list):
    """``list[SourceFile]`` + per-source build artifacts (Code/Bytecode/AST/ABI)."""

    def __init__(self, sources, build=None):
        super().__init__(sources)
        self.build = build
        self._by_key: dict[str, list] = {}
        artifacts = getattr(build, "artifacts", None) or []
        for art in artifacts:
            for key in _suffix_keys(art.source):
                self._by_key.setdefault(key, []).append(art)

    def artifacts_for(self, src) -> list:
        """Artifacts whose source reconciles to ``src`` (one per contract)."""
        path = getattr(src, "path", src)
        for key in _suffix_keys(path):
            hit = self._by_key.get(key)
            if hit:
                return hit
        return []

    def ast_for(self, src):
        """The AST for ``src`` (first artifact that carries one), or ``None``."""
        for art in self.artifacts_for(src):
            if getattr(art, "ast", None) is not None:
                return art.ast
        return None

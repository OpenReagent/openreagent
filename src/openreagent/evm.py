"""Small EVM bytecode helpers for the bytecode recipes.

Disassembly is delegated to **pyevmasm** (Apache-2.0, maintained), imported
lazily so it only loads on the bytecode-recipe path and stays an optional extra
(``pip install 'openreagent[bytecode]'``). Disassembly is a pure function of the
bytecode, hence deterministic; pin the extra's version so the opcode table can't
silently shift a signature.

Two preprocessing steps matter for clone matching: strip the Solidity metadata
trailer (so a one-character source change does not change the hash) and reduce
each instruction to its opcode mnemonic with the ``PUSH`` immediate masked.
"""
from __future__ import annotations


def from_hex(s: str) -> bytes:
    """Decode a hex string (optional ``0x``) to bytes; tolerate a trailing nibble."""
    h = s[2:] if s.startswith(("0x", "0X")) else s
    h = "".join(c for c in h if c in "0123456789abcdefABCDEF")
    if len(h) % 2:
        h = h[:-1]
    return bytes.fromhex(h)


def strip_metadata(code: bytes) -> bytes:
    """Remove the Solidity CBOR metadata trailer (last 2 bytes = its length)."""
    if len(code) > 2:
        meta_len = int.from_bytes(code[-2:], "big")
        if 0 < meta_len + 2 <= len(code):
            return code[: -(meta_len + 2)]
    return code


def opcodes(code: bytes) -> list[str]:
    """Disassemble to opcode mnemonics with PUSH immediates masked.

    Every ``PUSHx`` collapses to ``PUSH`` (so a changed constant or push width
    does not change the token stream); all other opcodes keep their name. Raises
    ``ImportError`` if the ``bytecode`` extra (pyevmasm) is not installed.
    """
    from pyevmasm import disassemble_all  # lazy: bytecode extra

    out: list[str] = []
    for ins in disassemble_all(code):
        name = ins.name
        out.append("PUSH" if name.startswith("PUSH") else name)
    return out

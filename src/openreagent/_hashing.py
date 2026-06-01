"""Hashing primitives for the journey recipes.

``keccak256`` uses ``eth-hash`` (the ``bytecode`` extra) when available and a
small pure-Python Keccak-256 otherwise, so ``bytecode-hash`` works in any clean
environment. ``minhash`` uses ``datasketch`` (the ``sketch`` extra) when
available and a deterministic pure-Python MinHash otherwise. Both fall back to
implementations that produce identical results run-to-run.
"""
from __future__ import annotations

import hashlib

# ---------------------------------------------------------------------------
# keccak-256 (Ethereum variant: pad byte 0x01)
# ---------------------------------------------------------------------------

_RC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_ROT = [
    [0, 36, 3, 41, 18],
    [1, 44, 10, 45, 2],
    [62, 6, 43, 15, 61],
    [28, 55, 25, 21, 56],
    [27, 20, 39, 8, 14],
]
_MASK = (1 << 64) - 1


def _rotl(x: int, n: int) -> int:
    return ((x << n) | (x >> (64 - n))) & _MASK


def _keccak_f(state: list[list[int]]) -> None:
    for rnd in range(24):
        # theta
        c = [state[x][0] ^ state[x][1] ^ state[x][2] ^ state[x][3] ^ state[x][4] for x in range(5)]
        d = [c[(x - 1) % 5] ^ _rotl(c[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x][y] ^= d[x]
        # rho + pi
        b = [[0] * 5 for _ in range(5)]
        for x in range(5):
            for y in range(5):
                b[y][(2 * x + 3 * y) % 5] = _rotl(state[x][y], _ROT[x][y])
        # chi
        for x in range(5):
            for y in range(5):
                state[x][y] = b[x][y] ^ ((~b[(x + 1) % 5][y]) & b[(x + 2) % 5][y])
        # iota
        state[0][0] ^= _RC[rnd]


def _keccak256_pure(data: bytes) -> bytes:
    rate = 136  # 1088 bits for keccak-256
    # padding (Keccak/Ethereum: 0x01 ... 0x80)
    padded = bytearray(data)
    padded.append(0x01)
    while len(padded) % rate != 0:
        padded.append(0x00)
    padded[-1] ^= 0x80

    state = [[0] * 5 for _ in range(5)]
    for off in range(0, len(padded), rate):
        block = padded[off:off + rate]
        for i in range(rate // 8):
            lane = int.from_bytes(block[i * 8:i * 8 + 8], "little")
            state[i % 5][i // 5] ^= lane
        _keccak_f(state)

    out = bytearray()
    for i in range(4):  # 32 bytes = 4 lanes
        out += state[i % 5][i // 5].to_bytes(8, "little")
    return bytes(out)


def keccak256(data: bytes) -> str:
    """Return the lowercase hex (no 0x) keccak-256 of ``data``."""
    try:
        from eth_hash.auto import keccak  # type: ignore

        return keccak(data).hex()
    except Exception:
        return _keccak256_pure(data).hex()


# ---------------------------------------------------------------------------
# MinHash
# ---------------------------------------------------------------------------

_MERSENNE = (1 << 61) - 1
_UINT64 = (1 << 64) - 1


def _perms(num: int) -> list[tuple[int, int]]:
    """Deterministic (a, b) permutation coefficients seeded from a fixed value."""
    import random

    rng = random.Random(0xA17EA)
    return [(rng.randrange(1, _MERSENNE), rng.randrange(0, _MERSENNE)) for _ in range(num)]


def minhash(shingles: list[str], num_perm: int = 64) -> list[int]:
    """Return a length-``num_perm`` MinHash signature over ``shingles``.

    Uses ``datasketch`` if importable (so callers who installed the ``sketch``
    extra interoperate with its objects); otherwise a deterministic pure
    implementation with the same external contract (a list of uint64).
    """
    try:
        from datasketch import MinHash  # type: ignore

        m = MinHash(num_perm=num_perm)
        for s in shingles:
            m.update(s.encode("utf-8"))
        return [int(x) & _UINT64 for x in m.hashvalues]
    except Exception:
        perms = _perms(num_perm)
        sig = [_UINT64] * num_perm
        for s in shingles:
            h = int.from_bytes(hashlib.sha1(s.encode("utf-8")).digest()[:8], "little")
            for i, (a, b) in enumerate(perms):
                v = ((a * (h & _MERSENNE) + b) % _MERSENNE) & _UINT64
                if v < sig[i]:
                    sig[i] = v
        return sig


def jaccard(sig_a: list[int], sig_b: list[int]) -> float:
    """Estimated Jaccard similarity of two equal-length MinHash signatures."""
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    equal = sum(1 for x, y in zip(sig_a, sig_b) if x == y)
    return equal / len(sig_a)


def shingle(tokens: list[str], ngram: int) -> list[str]:
    if ngram <= 1:
        return list(tokens)
    return ["".join(tokens[i:i + ngram]) for i in range(len(tokens) - ngram + 1)]

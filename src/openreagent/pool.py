"""The pool: a collection of signature records on disk.

A pool is a directory of ``*.json`` signature files (the shipped default pool
is empty apart from a few hand-authored samples). Loading validates two things
for every signature, at load time:

  - the record itself parses against ``openreagent.models.Signature``;
  - the ``value`` conforms to the shape declared by the signature's recipe.

A pool that fails either check raises ``PoolError`` in strict mode (the
default). An empty or missing pool loads to an empty list without error.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from openreagent import loader
from openreagent.models import Signature
from openreagent.recipes import get_recipe
from openreagent.shapes import get_shape


class PoolError(Exception):
    pass


@dataclass
class PoolEntry:
    signature: Signature
    source_path: str


def _pool_files(pool: str | Path | None) -> list[Path]:
    if pool is None:
        d = loader.pool_dir()
        if d is None:
            return []
        return sorted(d.rglob("*.json"), key=str)
    p = Path(pool)
    if p.is_file():
        return [p]
    if p.is_dir():
        return sorted(p.rglob("*.json"), key=str)
    return []


def load_pool(pool: str | Path | None = None, strict: bool = True,
              store=None) -> list[PoolEntry]:
    """Load a pool of signatures.

    ``store`` takes precedence over ``pool``: pass ``True`` for the default
    SQLite store, a path/``SignatureStore`` for a specific one. Otherwise ``pool``
    is a directory or file of ``*.json`` signature records (default: the shipped
    sample pool).
    """
    loader.load_builtins()
    if store is not None and store is not False:
        return _load_from_store(store, strict)
    entries: list[PoolEntry] = []
    for path in _pool_files(pool):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            if strict:
                raise PoolError(f"{path}: cannot read JSON ({exc})") from exc
            continue
        try:
            sig = Signature.from_dict(raw)
        except Exception as exc:
            if strict:
                raise PoolError(f"{path}: invalid signature record ({exc})") from exc
            continue
        _check_shape(path, sig, strict)
        entries.append(PoolEntry(signature=sig, source_path=str(path)))
    return entries


def _load_from_store(store, strict: bool) -> list[PoolEntry]:
    from openreagent.store import SignatureStore

    own = False
    if isinstance(store, SignatureStore):
        st = store
    else:
        st = SignatureStore(None if store is True else store)
        own = True
    try:
        entries: list[PoolEntry] = []
        for sig in st.signatures():
            _check_shape(Path(f"store:{st.path}"), sig, strict)
            entries.append(PoolEntry(signature=sig, source_path=f"store:{st.path}#{sig.id}"))
        return entries
    finally:
        if own:
            st.close()


def _check_shape(path: Path, sig: Signature, strict: bool) -> None:
    recipe = get_recipe(sig.recipe.name, sig.recipe.version)
    if recipe is None:
        if strict:
            raise PoolError(
                f"{path}: signature {sig.id} names unregistered recipe "
                f"{sig.recipe.name}@{sig.recipe.version}"
            )
        return
    shape = get_shape(recipe.shape.name, recipe.shape.version)
    if shape is None:
        if strict:
            raise PoolError(
                f"{path}: recipe {recipe.name} references unregistered shape "
                f"{recipe.shape.name}@{recipe.shape.version}"
            )
        return
    if not shape.conforms(sig.value):
        if strict:
            raise PoolError(
                f"{path}: signature {sig.id} value does not conform to shape "
                f"{shape.key}"
            )

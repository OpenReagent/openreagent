"""A local SQLite store for signature records, plus remote pull.

The store keeps signatures locally so they can be scanned without a directory of
JSON files, and so signatures pulled from a remote source accumulate in one
place. The default database is ``$OPENREAGENT_HOME/signatures.db`` (default
``~/.openreagent/signatures.db``).

A signature is stored as its canonical record (id, recipe ref, value JSON,
provenance JSON). Values are validated against the recipe's shape on insert, the
same check the file pool performs at load time.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from openreagent import loader, packages, sources
from openreagent.models import Signature
from openreagent.recipes import get_recipe
from openreagent.shapes import get_shape

_SCHEMA = """
CREATE TABLE IF NOT EXISTS signatures (
    id            TEXT PRIMARY KEY,
    recipe_name   TEXT NOT NULL,
    recipe_version TEXT NOT NULL,
    value         TEXT NOT NULL,
    provenance    TEXT NOT NULL,
    record        TEXT NOT NULL,
    added_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_recipe ON signatures(recipe_name);
"""


def default_db_path() -> Path:
    return packages.home_dir() / "signatures.db"


@dataclass
class StoredSignature:
    signature: Signature
    added_at: str


class SignatureStore:
    """A SQLite-backed collection of signature records."""

    def __init__(self, db_path: str | Path | None = None):
        self.path = Path(db_path) if db_path else default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SignatureStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- writes --

    def add(self, sig: Signature, validate: bool = True) -> None:
        if validate:
            _validate_against_shape(sig)
        rec = sig.to_dict()
        self._conn.execute(
            "INSERT OR REPLACE INTO signatures "
            "(id, recipe_name, recipe_version, value, provenance, record) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                sig.id,
                sig.recipe.name,
                sig.recipe.version,
                json.dumps(rec["value"], sort_keys=True),
                json.dumps(rec["provenance"], sort_keys=True),
                json.dumps(rec, sort_keys=True),
            ),
        )
        self._conn.commit()

    def add_many(self, sigs: list[Signature], validate: bool = True) -> int:
        count = 0
        for sig in sigs:
            self.add(sig, validate=validate)
            count += 1
        return count

    def remove(self, sig_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM signatures WHERE id = ?", (sig_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def clear(self) -> int:
        cur = self._conn.execute("DELETE FROM signatures")
        self._conn.commit()
        return cur.rowcount

    # -- reads --

    def get(self, sig_id: str) -> Signature | None:
        row = self._conn.execute(
            "SELECT record FROM signatures WHERE id = ?", (sig_id,)
        ).fetchone()
        if row is None:
            return None
        return Signature.from_dict(json.loads(row["record"]))

    def list(self, recipe: str | None = None) -> list[StoredSignature]:
        if recipe:
            rows = self._conn.execute(
                "SELECT record, added_at FROM signatures WHERE recipe_name = ? ORDER BY id",
                (recipe,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT record, added_at FROM signatures ORDER BY id"
            ).fetchall()
        return [
            StoredSignature(Signature.from_dict(json.loads(r["record"])), r["added_at"])
            for r in rows
        ]

    def signatures(self, recipe: str | None = None) -> list[Signature]:
        return [s.signature for s in self.list(recipe)]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS c FROM signatures").fetchone()["c"]


def _validate_against_shape(sig: Signature) -> None:
    loader.load_builtins()
    recipe = get_recipe(sig.recipe.name, sig.recipe.version)
    if recipe is None:
        raise ValueError(
            f"signature {sig.id} names unregistered recipe "
            f"{sig.recipe.name}@{sig.recipe.version}"
        )
    shape = get_shape(recipe.shape.name, recipe.shape.version)
    if shape is None or not shape.conforms(sig.value):
        raise ValueError(
            f"signature {sig.id} value does not conform to shape "
            f"{recipe.shape.name}@{recipe.shape.version}"
        )


# ---------------------------------------------------------------------------
# Loading signatures from arbitrary content (files, JSON arrays, JSONL, zips)
# ---------------------------------------------------------------------------

def parse_signatures(data: bytes) -> list[Signature]:
    """Parse a JSON array, a JSON object, or JSONL of signature records."""
    text = data.decode("utf-8").strip()
    if not text:
        return []
    out: list[Signature] = []
    # JSON array or single object.
    if text[0] in "[{":
        try:
            obj = json.loads(text)
            items = obj if isinstance(obj, list) else [obj]
            return [Signature.from_dict(x) for x in items]
        except json.JSONDecodeError:
            pass
    # JSONL fallback.
    for line in text.splitlines():
        line = line.strip()
        if line:
            out.append(Signature.from_dict(json.loads(line)))
    return out


def signatures_from_source(source: str) -> list[Signature]:
    """Fetch and parse signatures from a remote or local source.

    Supports a single JSON/JSONL file (local path, ``file://``, or http(s) URL)
    and a zip / directory / GitHub repo containing ``*.json`` signature files.
    """
    # Directory / zip / github -> collect every *.json under it.
    p = Path(source)
    if (not sources.is_remote(source)) and p.is_dir():
        return _collect_json_dir(p)
    if source.endswith(".zip") or sources.is_remote(source) and not source.endswith((".json", ".jsonl")):
        try:
            mat = sources.materialize(source)
            try:
                return _collect_json_dir(mat.path)
            finally:
                mat.cleanup()
        except ValueError:
            pass
    # Single file / URL of JSON or JSONL.
    return parse_signatures(sources.fetch_bytes(source))


def _collect_json_dir(directory: Path) -> list[Signature]:
    out: list[Signature] = []
    for f in sorted(directory.rglob("*.json"), key=str):
        # Skip package manifests if a repo of detectors is pointed at by mistake.
        if f.name == packages.MANIFEST_NAME:
            continue
        try:
            out.extend(parse_signatures(f.read_bytes()))
        except Exception:
            continue
    return out

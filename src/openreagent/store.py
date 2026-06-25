"""The signature store — a **remote PostgreSQL** database.

OpenReagent keeps signatures in a remote, shared database; there is **no local
file-based store**. Configure it with a PostgreSQL connection URL via the
``OPENREAGENT_DB_URL`` environment variable (or pass one explicitly):

    postgresql://user:password@host:5432/openreagent

Run one locally for development with the bundled ``docker-compose.yml`` (see
``docs/storage.md``). The driver is **pg8000** (pure-Python, BSD), shipped as the
``store`` extra: ``pip install 'openreagent[store]'``.

A signature is stored as its canonical record (id, recipe ref, value, provenance)
and validated against the recipe's shape on insert — the same check the file pool
performs at load time. The ``parse_signatures`` / ``signatures_from_source``
helpers below are independent of the database (used by ``sig pull``).
"""
from __future__ import annotations

import json
import os
import ssl
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from openreagent import loader, packages, sources
from openreagent.models import Signature
from openreagent.recipes import get_recipe
from openreagent.shapes import get_shape

DB_URL_ENV = "OPENREAGENT_DB_URL"

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS signatures (
        id             text PRIMARY KEY,
        recipe_name    text NOT NULL,
        recipe_version text NOT NULL,
        value          text NOT NULL,
        provenance     text NOT NULL,
        record         text NOT NULL,
        added_at       timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_signatures_recipe ON signatures(recipe_name)",
)


class StoreConfigError(RuntimeError):
    """Raised when the remote signature database is not configured/available."""


def resolve_db_url(url: str | None = None) -> str:
    u = url or os.environ.get(DB_URL_ENV)
    if not u:
        raise StoreConfigError(
            "A remote signature database is required (there is no local store). "
            f"Set {DB_URL_ENV} to a PostgreSQL URL, e.g. "
            "postgresql://user:pass@host:5432/openreagent — or start the bundled "
            "docker-compose (see docs/storage.md)."
        )
    return u


@dataclass
class StoredSignature:
    signature: Signature
    added_at: str


def _connect(url: str):
    try:
        import pg8000.dbapi as dbapi
    except ImportError as exc:  # pragma: no cover - exercised when extra absent
        raise StoreConfigError(
            "The remote store needs the 'store' extra: pip install 'openreagent[store]'"
        ) from exc
    p = urlparse(url)
    if p.scheme not in ("postgresql", "postgres"):
        raise StoreConfigError(f"unsupported database URL scheme: {p.scheme!r} (use postgresql://)")
    kwargs: dict = {
        "host": p.hostname or "localhost",
        "port": p.port or 5432,
        "user": unquote(p.username) if p.username else "postgres",
        "database": (p.path or "/openreagent").lstrip("/") or "openreagent",
    }
    if p.password:
        kwargs["password"] = unquote(p.password)
    sslmode = (parse_qs(p.query).get("sslmode", [None])[0])
    if sslmode and sslmode not in ("disable", "allow", "prefer"):
        kwargs["ssl_context"] = ssl.create_default_context()
    return dbapi.connect(**kwargs)


class SignatureStore:
    """A remote PostgreSQL-backed collection of signature records."""

    def __init__(self, db_url: str | None = None):
        self.url = resolve_db_url(db_url)
        self._conn = _connect(self.url)
        cur = self._conn.cursor()
        for stmt in _SCHEMA:
            cur.execute(stmt)
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def __enter__(self) -> "SignatureStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- writes --

    def add(self, sig: Signature, validate: bool = True) -> None:
        if validate:
            _validate_against_shape(sig)
        rec = sig.to_dict()
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO signatures "
            "(id, recipe_name, recipe_version, value, provenance, record) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET "
            "recipe_name = EXCLUDED.recipe_name, recipe_version = EXCLUDED.recipe_version, "
            "value = EXCLUDED.value, provenance = EXCLUDED.provenance, record = EXCLUDED.record",
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
        cur = self._conn.cursor()
        cur.execute("DELETE FROM signatures WHERE id = %s", (sig_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def clear(self) -> int:
        cur = self._conn.cursor()
        cur.execute("DELETE FROM signatures")
        self._conn.commit()
        return cur.rowcount

    # -- reads --

    def get(self, sig_id: str) -> Signature | None:
        cur = self._conn.cursor()
        cur.execute("SELECT record FROM signatures WHERE id = %s", (sig_id,))
        row = cur.fetchone()
        return Signature.from_dict(json.loads(row[0])) if row else None

    def list(self, recipe: str | None = None) -> list[StoredSignature]:
        cur = self._conn.cursor()
        if recipe:
            cur.execute(
                "SELECT record, added_at FROM signatures WHERE recipe_name = %s ORDER BY id",
                (recipe,),
            )
        else:
            cur.execute("SELECT record, added_at FROM signatures ORDER BY id")
        out = []
        for record, added_at in cur.fetchall():
            added = added_at.isoformat() if hasattr(added_at, "isoformat") else str(added_at)
            out.append(StoredSignature(Signature.from_dict(json.loads(record)), added))
        return out

    def signatures(self, recipe: str | None = None) -> list[Signature]:
        return [s.signature for s in self.list(recipe)]

    def count(self) -> int:
        cur = self._conn.cursor()
        cur.execute("SELECT COUNT(*) FROM signatures")
        return int(cur.fetchone()[0])


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
# (independent of the database backend; used by `sig pull` / `sig add`)
# ---------------------------------------------------------------------------

def parse_signatures(data: bytes) -> list[Signature]:
    """Parse a JSON array, a JSON object, or JSONL of signature records."""
    text = data.decode("utf-8").strip()
    if not text:
        return []
    out: list[Signature] = []
    if text[0] in "[{":
        try:
            obj = json.loads(text)
            items = obj if isinstance(obj, list) else [obj]
            return [Signature.from_dict(x) for x in items]
        except json.JSONDecodeError:
            pass
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
    return parse_signatures(sources.fetch_bytes(source))


def _collect_json_dir(directory: Path) -> list[Signature]:
    out: list[Signature] = []
    for f in sorted(directory.rglob("*.json"), key=str):
        if f.name == packages.MANIFEST_NAME:
            continue
        try:
            out.extend(parse_signatures(f.read_bytes()))
        except Exception:
            continue
    return out

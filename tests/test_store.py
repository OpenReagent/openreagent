"""The PostgreSQL signature store (the server's backend) and pull parsing.

The store is server-internal now: clients talk to the server, not the database.
End-to-end matching through the server lives in ``test_server.py``. The CRUD
tests here require a reachable PostgreSQL: set ``OPENREAGENT_TEST_DB_URL``
(e.g. start the bundled docker-compose). They are skipped otherwise. The config
and parse/pull tests need no database and always run.
"""
from __future__ import annotations

import json
import os

import pytest

from openreagent import loader
from openreagent.models import Signature
from openreagent.store import (
    SignatureStore,
    StoreConfigError,
    parse_signatures,
    resolve_db_url,
    signatures_from_source,
)


def setup_module(_):
    loader.load_builtins()


_TEST_DB = os.environ.get("OPENREAGENT_TEST_DB_URL")
requires_db = pytest.mark.skipif(
    not _TEST_DB, reason="set OPENREAGENT_TEST_DB_URL (PostgreSQL) to run store CRUD tests")


S_BC = {
    "id": "sig-bc-1",
    "recipe": {"name": "bytecode-hash", "version": "1.0.0"},
    "value": {"digest": "ab" * 32, "normalization": "source-text"},
    "provenance": [{"source_kind": "audit_report", "source_ref": "x",
                    "extracted_by": {"recipe": "bytecode-hash", "version": "1.0.0",
                                     "timestamp": "2026-06-01T00:00:00Z"}}],
}
S_AST = {
    "id": "sig-ast-1",
    "recipe": {"name": "ast-sketch", "version": "1.0.0"},
    "value": {"ngram": 5, "minhash": [1, 2, 3]},
    "provenance": [{"source_kind": "audit_report", "source_ref": "y",
                    "extracted_by": {"recipe": "ast-sketch", "version": "1.0.0",
                                     "timestamp": "2026-05-10T00:00:00Z"}}],
}


@pytest.fixture
def store():
    st = SignatureStore(_TEST_DB)
    st.clear()
    try:
        yield st
    finally:
        st.clear()
        st.close()


# ---- configuration (no database; always runs) ----

def test_remote_store_is_required(monkeypatch):
    monkeypatch.delenv("OPENREAGENT_DB_URL", raising=False)
    with pytest.raises(StoreConfigError):
        resolve_db_url()
    with pytest.raises(StoreConfigError):
        SignatureStore()  # no URL and no env → there is no local fallback


def test_resolve_db_url_explicit():
    assert resolve_db_url("postgresql://u@h/db") == "postgresql://u@h/db"


# ---- CRUD (needs a live PostgreSQL) ----

@requires_db
def test_store_add_list_get_remove(store):
    store.add(Signature.from_dict(S_BC))
    assert store.count() == 1
    assert store.get("sig-bc-1") is not None
    assert [s.signature.id for s in store.list()] == ["sig-bc-1"]
    assert store.remove("sig-bc-1") is True
    assert store.count() == 0


@requires_db
def test_store_rejects_nonconforming(store):
    bad = dict(S_BC, id="bad", value={"nope": 1})
    with pytest.raises(Exception):
        store.add(Signature.from_dict(bad))


# ---- parse / pull (no database) ----

def test_parse_signatures_array_and_jsonl():
    arr = json.dumps([S_BC, S_AST]).encode()
    assert len(parse_signatures(arr)) == 2
    jsonl = (json.dumps(S_BC) + "\n" + json.dumps(S_AST)).encode()
    assert len(parse_signatures(jsonl)) == 2


def test_signatures_from_local_file(tmp_path):
    p = tmp_path / "sig.json"
    p.write_text(json.dumps(S_BC))
    sigs = signatures_from_source(str(p))
    assert len(sigs) == 1 and sigs[0].id == "sig-bc-1"


def test_signatures_from_dir(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(S_BC))
    (tmp_path / "b.json").write_text(json.dumps(S_AST))
    sigs = signatures_from_source(str(tmp_path))
    assert {s.id for s in sigs} == {"sig-bc-1", "sig-ast-1"}


def test_pull_from_file_url(tmp_path):
    p = tmp_path / "remote.json"
    p.write_text(json.dumps([S_BC, S_AST]))
    sigs = signatures_from_source(p.as_uri())
    assert len(sigs) == 2

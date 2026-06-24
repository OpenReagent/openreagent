"""The SQLite signature store, scanning from a store, and remote-style pull."""
from __future__ import annotations

import json

import pytest

from openreagent import loader
from openreagent.models import Signature
from openreagent.recipes import get_recipe
from openreagent.scan import scan
from openreagent.store import SignatureStore, parse_signatures, signatures_from_source


def setup_module(_):
    loader.load_builtins()


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


def test_store_add_list_get_remove(tmp_path):
    db = tmp_path / "s.db"
    with SignatureStore(db) as st:
        st.add(Signature.from_dict(S_BC))
        assert st.count() == 1
        assert st.get("sig-bc-1") is not None
        assert [s.signature.id for s in st.list()] == ["sig-bc-1"]
        assert st.remove("sig-bc-1") is True
        assert st.count() == 0


def test_store_rejects_nonconforming(tmp_path):
    db = tmp_path / "s.db"
    bad = dict(S_BC, id="bad", value={"nope": 1})
    with SignatureStore(db) as st:
        with pytest.raises(Exception):
            st.add(Signature.from_dict(bad))


def test_scan_from_store(tmp_path, fixtures_dir, fixtures_path):
    # A bytecode-hash signature that self-matches Token.sol, scanned from a store.
    rec = get_recipe("bytecode-hash")
    value = rec.extractor.extract({"source_path": str(fixtures_path / "Token.sol")})
    sig = {
        "id": "sig-token-clone",
        "recipe": {"name": "bytecode-hash", "version": "1.0.0"},
        "value": value,
        "provenance": [{"source_kind": "build", "source_ref": "token",
                        "extracted_by": {"recipe": "bytecode-hash", "version": "1.0.0",
                                         "timestamp": "2026-06-01T00:00:00Z"}}],
    }
    db = tmp_path / "s.db"
    with SignatureStore(db) as st:
        st.add(Signature.from_dict(sig))
    report = scan(fixtures_dir, store=str(db), enable=["bytecode-hash"], do_build=False)
    assert "bytecode-hash" in {f.recipe for f in report.findings}


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
    """Pull via a file:// URL exercises the same path as a remote pull, offline."""
    p = tmp_path / "remote.json"
    p.write_text(json.dumps([S_BC, S_AST]))
    sigs = signatures_from_source(p.as_uri())
    assert len(sigs) == 2

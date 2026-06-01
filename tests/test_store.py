"""The SQLite signature store, scanning from a store, and remote-style pull."""
from __future__ import annotations

import json

import pytest

from openreagent.models import Signature
from openreagent.scan import scan
from openreagent.store import SignatureStore, parse_signatures, signatures_from_source

S_ABSENCE = {
    "id": "sig-absence-1",
    "recipe": {"name": "internal-absence", "version": "1.0.0"},
    "value": {"slots": {"operation": "access_control",
                        "site": {"function": "setFeeRecipient", "file": "Vault.sol"}}},
    "provenance": [{"source_kind": "audit_report", "source_ref": "x",
                    "extracted_by": {"recipe": "internal-absence", "version": "1.0.0",
                                     "timestamp": "2026-06-01T00:00:00Z"}}],
}
S_DIVERGENCE = {
    "id": "sig-divergence-1",
    "recipe": {"name": "canonical-divergence", "version": "1.0.0"},
    "value": {"slots": {"operation": "amm_spot_price_read",
                        "site": {"function": "getPrice", "file": "PriceOracle.sol"},
                        "canonical_reference": "uniswap_v2/twap"}},
    "provenance": [{"source_kind": "audit_report", "source_ref": "y",
                    "extracted_by": {"recipe": "canonical-divergence", "version": "1.0.0",
                                     "timestamp": "2026-05-10T00:00:00Z"}}],
}


def test_store_add_list_get_remove(tmp_path):
    db = tmp_path / "s.db"
    with SignatureStore(db) as st:
        st.add(Signature.from_dict(S_ABSENCE))
        assert st.count() == 1
        assert st.get("sig-absence-1") is not None
        assert [s.signature.id for s in st.list()] == ["sig-absence-1"]
        assert st.remove("sig-absence-1") is True
        assert st.count() == 0


def test_store_rejects_nonconforming(tmp_path):
    db = tmp_path / "s.db"
    bad = dict(S_ABSENCE, id="bad", value={"not_slots": 1})
    with SignatureStore(db) as st:
        with pytest.raises(Exception):
            st.add(Signature.from_dict(bad))


def test_scan_from_store(tmp_path, fixtures_dir):
    db = tmp_path / "s.db"
    with SignatureStore(db) as st:
        st.add_many([Signature.from_dict(S_ABSENCE), Signature.from_dict(S_DIVERGENCE)])
    report = scan(fixtures_dir, store=str(db))
    hit = {f.recipe for f in report.findings}
    assert "internal-absence" in hit
    assert "canonical-divergence" in hit


def test_parse_signatures_array_and_jsonl():
    arr = json.dumps([S_ABSENCE, S_DIVERGENCE]).encode()
    assert len(parse_signatures(arr)) == 2
    jsonl = (json.dumps(S_ABSENCE) + "\n" + json.dumps(S_DIVERGENCE)).encode()
    assert len(parse_signatures(jsonl)) == 2


def test_signatures_from_local_file(tmp_path):
    p = tmp_path / "sig.json"
    p.write_text(json.dumps(S_ABSENCE))
    sigs = signatures_from_source(str(p))
    assert len(sigs) == 1 and sigs[0].id == "sig-absence-1"


def test_signatures_from_dir(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps(S_ABSENCE))
    (tmp_path / "b.json").write_text(json.dumps(S_DIVERGENCE))
    sigs = signatures_from_source(str(tmp_path))
    assert {s.id for s in sigs} == {"sig-absence-1", "sig-divergence-1"}


def test_pull_from_file_url(tmp_path):
    """Pull via a file:// URL exercises the same path as a remote pull, offline."""
    p = tmp_path / "remote.json"
    p.write_text(json.dumps([S_ABSENCE, S_DIVERGENCE]))
    sigs = signatures_from_source(p.as_uri())
    assert len(sigs) == 2

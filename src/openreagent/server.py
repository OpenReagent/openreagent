"""The OpenReagent server — a remote API in front of the signature store.

Clients never touch the database; they talk to this service (see
``openreagent.client``). The store (PostgreSQL via ``store.py``) is an internal
detail here. The ``POST /match`` endpoint is the boundary where a Private Set
Intersection protocol will later replace the plaintext comparison, so neither the
client's candidate set nor the server's full signature set need be revealed.

Run it with ``openreagent serve`` (needs the ``server`` and ``store`` extras:
``pip install 'openreagent[server,store]'``).

Note: this module intentionally does *not* use ``from __future__ import
annotations``. FastAPI resolves endpoint type hints via ``get_type_hints``; with
stringized annotations the request-body models (defined inside ``create_app``)
would not resolve and bodies would be misread as query params.
"""
import os

from openreagent import loader, matchlib
from openreagent.models import Signature
from openreagent.recipes import get_recipe


def get_store():
    """FastAPI dependency yielding a store. Overridden in tests with a fake."""
    from openreagent.store import SignatureStore

    st = SignatureStore()
    try:
        yield st
    finally:
        st.close()


def create_app():
    from fastapi import Depends, FastAPI, Header, HTTPException
    from pydantic import BaseModel

    loader.load_builtins()
    app = FastAPI(title="OpenReagent", version="0.1.0")
    token = os.environ.get("OPENREAGENT_SERVER_TOKEN")

    def auth(authorization: str | None = Header(default=None)) -> None:
        if token and authorization != f"Bearer {token}":
            raise HTTPException(status_code=401, detail="invalid or missing token")

    class SignaturesIn(BaseModel):
        signatures: list[dict]

    class MatchIn(BaseModel):
        candidates: dict[str, list[dict]]  # {recipe: [candidate value, ...]}

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.post("/signatures")
    def add_signatures(body: SignaturesIn, _: None = Depends(auth), store=Depends(get_store)):
        try:
            n = store.add_many([Signature.from_dict(r) for r in body.signatures])
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"added": n, "count": store.count()}

    @app.get("/signatures")
    def list_signatures(recipe: str | None = None, _: None = Depends(auth), store=Depends(get_store)):
        return {"signatures": [s.signature.to_dict() for s in store.list(recipe)]}

    @app.get("/signatures/{sig_id}")
    def get_signature(sig_id: str, _: None = Depends(auth), store=Depends(get_store)):
        sig = store.get(sig_id)
        if sig is None:
            raise HTTPException(status_code=404, detail="not found")
        return sig.to_dict()

    @app.delete("/signatures/{sig_id}")
    def remove_signature(sig_id: str, _: None = Depends(auth), store=Depends(get_store)):
        return {"removed": store.remove(sig_id)}

    @app.delete("/signatures")
    def clear_signatures(_: None = Depends(auth), store=Depends(get_store)):
        return {"cleared": store.clear()}

    @app.post("/match")
    def match(body: MatchIn, _: None = Depends(auth), store=Depends(get_store)):
        """Compare client candidate values against stored signatures (PSI seam).

        Returns only the matches — the server reveals nothing about non-matching
        signatures, and the client revealed only fingerprints, never its code.
        """
        matches = []
        for recipe_name, candidates in body.candidates.items():
            recipe = get_recipe(recipe_name)
            if recipe is None or not candidates:
                continue
            tau = matchlib.tau_for(recipe_name)
            for stored in store.list(recipe_name):
                sv = stored.signature.value
                for idx, cand in enumerate(candidates):
                    score = matchlib.compare(sv, cand)
                    if score >= tau:
                        matches.append({
                            "signature_id": stored.signature.id,
                            "recipe": recipe_name,
                            "candidate": idx,
                            "score": round(score, 3),
                        })
        return {"matches": matches}

    return app

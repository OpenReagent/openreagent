"""Thin HTTP client for the OpenReagent server.

Stdlib only (no extra) — the client ships with the core. Configure the server
with ``OPENREAGENT_SERVER_URL`` (and an optional ``OPENREAGENT_SERVER_TOKEN``).
The client never talks to the database; it talks to the server, whose ``/match``
endpoint is the seam where PSI will later be applied.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from openreagent.models import Signature

SERVER_URL_ENV = "OPENREAGENT_SERVER_URL"
TOKEN_ENV = "OPENREAGENT_SERVER_TOKEN"


class ServerConfigError(RuntimeError):
    """The remote server is not configured."""


class ServerError(RuntimeError):
    """The remote server returned an error or is unreachable."""


def resolve_server_url(url: str | None = None) -> str:
    u = url or os.environ.get(SERVER_URL_ENV)
    if not u:
        raise ServerConfigError(
            "A remote OpenReagent server is required (there is no local store). "
            f"Set {SERVER_URL_ENV} to the server, e.g. http://localhost:8000 — or "
            "run `openreagent serve` against your database (see docs/storage.md)."
        )
    return u.rstrip("/")


class OpenReagentClient:
    def __init__(self, url: str | None = None, token: str | None = None, timeout: float = 30.0):
        self.url = resolve_server_url(url)
        self.token = token or os.environ.get(TOKEN_ENV)
        self.timeout = timeout

    def _request(self, method: str, path: str, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise ServerError(f"server returned {exc.code}: {detail}")
        except urllib.error.URLError as exc:
            raise ServerError(f"cannot reach server at {self.url}: {exc.reason}")

    # -- signatures (admin) --

    def health(self) -> dict:
        return self._request("GET", "/healthz")

    def add(self, sigs) -> int:
        payload = [s.to_dict() if isinstance(s, Signature) else s for s in sigs]
        return int(self._request("POST", "/signatures", {"signatures": payload}).get("added", 0))

    def list(self, recipe: str | None = None) -> list[Signature]:
        q = "?recipe=" + urllib.parse.quote(recipe) if recipe else ""
        out = self._request("GET", "/signatures" + q)
        return [Signature.from_dict(x) for x in out.get("signatures", [])]

    def get(self, sig_id: str) -> Signature | None:
        try:
            return Signature.from_dict(self._request("GET", f"/signatures/{urllib.parse.quote(sig_id)}"))
        except ServerError:
            return None

    def remove(self, sig_id: str) -> bool:
        return bool(self._request("DELETE", f"/signatures/{urllib.parse.quote(sig_id)}").get("removed"))

    def clear(self) -> int:
        return int(self._request("DELETE", "/signatures").get("cleared", 0))

    # -- the match seam (PSI later) --

    def match(self, candidates: dict[str, list[dict]]) -> list[dict]:
        return self._request("POST", "/match", {"candidates": candidates}).get("matches", [])

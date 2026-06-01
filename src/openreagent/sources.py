"""Fetching package and signature sources from local paths, zips, URLs, and
GitHub — the transport layer behind ``openreagent install`` and
``openreagent sig pull``.

A *source* is a short string. Supported forms:

  - ``./path`` or ``/abs/path``        a local directory or file
  - ``./bundle.zip``                   a local zip archive
  - ``file:///abs/bundle.zip``         a file URL (dir or zip)
  - ``https://host/bundle.zip``        a remote zip archive
  - ``github:owner/repo``              a GitHub repository (default branch)
  - ``github:owner/repo@ref``          a GitHub repository at a branch/tag/sha
  - ``https://github.com/owner/repo``  the same, as a URL

Network access uses only the standard library (``urllib``). Nothing here is
imported by the scan path.
"""
from __future__ import annotations

import io
import re
import shutil
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

_USER_AGENT = "openreagent/0.1 (+https://github.com/openreagent/openreagent)"
_GITHUB_URL = re.compile(r"^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/tree/([^/]+))?/?$")
_GITHUB_SHORT = re.compile(r"^github:([^/]+)/([^/@]+)(?:@(.+))?$")


@dataclass
class Materialized:
    """A local directory containing the fetched content, plus a cleanup hook."""

    path: Path
    _tmp: Path | None = None

    def cleanup(self) -> None:
        if self._tmp is not None and self._tmp.exists():
            shutil.rmtree(self._tmp, ignore_errors=True)


def _download(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (intended)
        return resp.read()


def _github_zip_url(owner: str, repo: str, ref: str | None) -> str:
    # codeload serves a zip of any ref (branch, tag, or sha).
    ref = ref or "HEAD"
    return f"https://codeload.github.com/{owner}/{repo}/zip/{ref}"


def _extract_zip(data: bytes, dest: Path) -> Path:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)
    # GitHub (and many zips) wrap everything in a single top-level folder.
    entries = [p for p in dest.iterdir() if not p.name.startswith("__MACOSX")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return dest


def is_remote(source: str) -> bool:
    return bool(
        source.startswith(("http://", "https://", "github:"))
    )


def fetch_bytes(source: str, timeout: float = 30.0) -> bytes:
    """Read raw bytes from a local file, a ``file://`` URL, or an http(s) URL."""
    if source.startswith(("http://", "https://")):
        return _download(source, timeout)
    if source.startswith("file://"):
        return Path(urllib.request.url2pathname(source[len("file://"):])).read_bytes()
    return Path(source).read_bytes()


def materialize(source: str, timeout: float = 30.0) -> Materialized:
    """Resolve ``source`` to a local directory containing its content.

    The caller is responsible for calling ``.cleanup()`` when finished.
    """
    # GitHub shorthand / URL -> zip download.
    m = _GITHUB_SHORT.match(source)
    if m:
        owner, repo, ref = m.group(1), m.group(2), m.group(3)
        return _materialize_zip_bytes(_download(_github_zip_url(owner, repo, ref), timeout))
    m = _GITHUB_URL.match(source)
    if m:
        owner, repo, ref = m.group(1), m.group(2), m.group(3)
        return _materialize_zip_bytes(_download(_github_zip_url(owner, repo, ref), timeout))

    # Remote zip.
    if source.startswith(("http://", "https://")):
        return _materialize_zip_bytes(_download(source, timeout))

    # file:// URL (dir or zip).
    if source.startswith("file://"):
        local = Path(urllib.request.url2pathname(source[len("file://"):]))
        source = str(local)

    p = Path(source)
    if p.is_dir():
        return Materialized(path=p, _tmp=None)
    if p.is_file() and p.suffix == ".zip":
        return _materialize_zip_bytes(p.read_bytes())
    raise ValueError(f"cannot materialize source: {source!r}")


def _materialize_zip_bytes(data: bytes) -> Materialized:
    tmp = Path(tempfile.mkdtemp(prefix="openreagent-pkg-"))
    root = _extract_zip(data, tmp)
    return Materialized(path=root, _tmp=tmp)

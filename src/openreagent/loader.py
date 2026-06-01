"""Thin facade over the package system.

Kept as a stable import surface for the rest of the codebase. All discovery and
loading lives in :mod:`openreagent.packages`; this module just exposes the few
entry points the engines use.
"""
from __future__ import annotations

from pathlib import Path

from openreagent import packages


def load_builtins(force: bool = False):
    """Load every available package (built-in + installed) in dependency order.
    Idempotent. Named for historical reasons; it loads the whole registry."""
    return packages.load(force=force)


# Alias with a clearer name.
load_registry = load_builtins


def load_extra_dir(directory: str | Path):
    """Load packages found under an arbitrary directory without installing."""
    return packages.load_path(directory)


def pool_dir() -> Path | None:
    """The shipped sample-pool directory."""
    return packages.builtin_pool_dir()

"""A small, dependency-free Solidity reader for the matching path.

The matchers do not need a full compiler front end. They need to enumerate the
functions in a body of Solidity, know each function's name, parameters, line
span, the identifiers and call targets in its body, and the comparison
operators it uses. This module provides exactly that, deterministically and
with no native dependencies, so the scan path installs and runs anywhere.

Comments and string/hex literals are masked (replaced by spaces, newlines
preserved) before any structural scanning, so tokens and braces inside strings
or comments never leak into the analysis. Line numbers are 1-based.

This is deliberately a *reader*, not a parser: it recognises function and
contract boundaries by brace matching and reads tokens lexically. A recipe that
needs a real AST should declare a heavier dependency in its own extra and
document it (see ``docs/architecture.md``); the built-in slot recipes are
designed to work on this lexical view.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# A conservative set of Solidity keywords/types to exclude from "identifiers".
_KEYWORDS = {
    "abstract", "address", "anonymous", "as", "assembly", "bool", "break",
    "bytes", "calldata", "catch", "constant", "constructor", "continue",
    "contract", "delete", "do", "else", "emit", "enum", "event", "external",
    "fallback", "false", "for", "function", "if", "immutable", "import",
    "indexed", "interface", "internal", "is", "library", "mapping", "memory",
    "modifier", "new", "override", "payable", "pragma", "private", "public",
    "pure", "receive", "return", "returns", "revert", "storage", "string",
    "struct", "true", "try", "uint", "int", "unchecked", "using", "view",
    "virtual", "while", "wei", "ether", "gwei", "days", "hours", "weeks",
    "seconds", "minutes", "this", "super", "type",
}

_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_FN_DECL = re.compile(
    r"\b(function|modifier|constructor|receive|fallback)\b"
    r"(?:\s+([A-Za-z_$][A-Za-z0-9_$]*))?\s*\(",
)
_CONTRACT_DECL = re.compile(
    r"\b(contract|interface|library)\b\s+([A-Za-z_$][A-Za-z0-9_$]*)",
)
_COMPARATORS = ("<=", ">=", "==", "!=", "<", ">")


def _mask(text: str) -> str:
    """Replace the contents of comments and string/hex literals with spaces,
    preserving every newline so line numbers are unchanged."""
    out = list(text)
    i, n = 0, len(text)

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = text[i]
        two = text[i : i + 2]
        if two == "//":
            j = text.find("\n", i)
            j = n if j == -1 else j
            blank(i, j)
            i = j
        elif two == "/*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            blank(i, j)
            i = j
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c:
                if text[j] == "\\":
                    j += 2
                    continue
                j += 1
            j = min(j + 1, n)
            blank(i, j)
            i = j
        else:
            i += 1
    return "".join(out)


def _line_index(text: str) -> list[int]:
    """offsets of the start of each line; ``line_at`` uses bisect."""
    starts = [0]
    for m in re.finditer(r"\n", text):
        starts.append(m.end())
    return starts


def _line_at(starts: list[int], offset: int) -> int:
    import bisect

    return bisect.bisect_right(starts, offset)


def _match_brace(code: str, open_pos: int) -> int:
    """Given the index of an opening ``{``, return the index just past the
    matching ``}`` (or len(code) if unbalanced)."""
    depth = 0
    for i in range(open_pos, len(code)):
        ch = code[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(code)


def _skip_params(code: str, open_paren: int) -> int:
    """Index just past the matching ``)`` for a ``(`` at ``open_paren``."""
    depth = 0
    for i in range(open_paren, len(code)):
        ch = code[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(code)


@dataclass
class Function:
    name: str
    kind: str  # function | modifier | constructor | receive | fallback
    contract: str
    in_interface: bool
    params: list[str]
    start_line: int
    end_line: int
    body_text: str
    _code_body: str = field(repr=False, default="")

    def identifiers(self) -> set[str]:
        return {
            m.group(0)
            for m in _IDENT.finditer(self._code_body)
            if m.group(0) not in _KEYWORDS
        }

    def call_targets(self) -> set[str]:
        out: set[str] = set()
        for m in re.finditer(r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\(", self._code_body):
            name = m.group(1)
            if name not in _KEYWORDS:
                out.add(name)
        return out

    def comparisons(self) -> list[tuple[str, int]]:
        """List of (operator, line) for comparison operators in the body."""
        out: list[tuple[str, int]] = []
        starts = _line_index(self._code_body)
        i, n = 0, len(self._code_body)
        while i < n:
            matched = None
            for op in _COMPARATORS:
                if self._code_body.startswith(op, i):
                    matched = op
                    break
            if matched:
                # skip '=>' and '<<'/'>>' shift/arrow lookalikes handled by order
                out.append((matched, self.start_line + _line_at(starts, i) - 1))
                i += len(matched)
            else:
                i += 1
        return out

    def first_line_matching(self, needles: list[str]) -> int | None:
        """Line (1-based, file coordinates) of the first body line whose code
        contains any of ``needles``; None if none match."""
        lines = self._code_body.splitlines()
        for offset, ln in enumerate(lines):
            if any(nd in ln for nd in needles):
                return self.start_line + offset
        return None


@dataclass
class SourceFile:
    path: str
    text: str
    functions: list[Function]

    @property
    def basename(self) -> str:
        return Path(self.path).name


def parse_source(path: str, text: str) -> SourceFile:
    code = _mask(text)
    starts = _line_index(text)

    # Contract spans: (name, kind, start_offset, end_offset)
    spans: list[tuple[str, str, int, int]] = []
    for m in _CONTRACT_DECL.finditer(code):
        brace = code.find("{", m.end())
        if brace == -1:
            continue
        end = _match_brace(code, brace)
        spans.append((m.group(2), m.group(1), m.start(), end))

    def containing_contract(pos: int) -> tuple[str, str]:
        best = ("", "contract")
        best_start = -1
        for name, kind, s, e in spans:
            if s <= pos < e and s > best_start:
                best = (name, kind)
                best_start = s
        return best

    functions: list[Function] = []
    for m in _FN_DECL.finditer(code):
        kind = m.group(1)
        name = m.group(2) or kind  # constructor/receive/fallback have no name
        open_paren = code.index("(", m.start())
        after_params = _skip_params(code, open_paren)
        param_src = code[open_paren + 1 : after_params - 1]
        params = _param_names(param_src)

        # Find the body brace or a terminating semicolon (declaration only).
        j = after_params
        body_brace = -1
        while j < len(code):
            ch = code[j]
            if ch == "{":
                body_brace = j
                break
            if ch == ";":
                break
            j += 1
        if body_brace == -1:
            continue  # no body (interface / abstract declaration)

        body_end = _match_brace(code, body_brace)
        contract_name, contract_kind = containing_contract(m.start())
        start_line = _line_at(starts, m.start())
        end_line = _line_at(starts, body_end - 1)
        functions.append(
            Function(
                name=name,
                kind=kind,
                contract=contract_name,
                in_interface=(contract_kind == "interface"),
                params=params,
                start_line=start_line,
                end_line=end_line,
                body_text=text[body_brace:body_end],
                _code_body=code[body_brace:body_end],
            )
        )
    return SourceFile(path=path, text=text, functions=functions)


def _param_names(param_src: str) -> list[str]:
    names: list[str] = []
    for part in _split_top_level(param_src, ","):
        part = part.strip()
        if not part:
            continue
        toks = _IDENT.findall(part)
        # The parameter name is the last identifier that is not a keyword/type.
        for tok in reversed(toks):
            if tok not in _KEYWORDS:
                names.append(tok)
                break
    return names


def _split_top_level(s: str, sep: str) -> list[str]:
    out: list[str] = []
    depth = 0
    cur = []
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def load_source_file(path: str | Path) -> SourceFile | None:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None
    return parse_source(str(p), text)


# Directories never worth scanning (vendored libraries, tests, build output).
_SKIP_DIRS = {
    "node_modules", "lib", "test", "tests", "mock", "mocks",
    ".git", "out", "artifacts", "cache", "build", "dist",
}


def load_target(path: str | Path) -> list[SourceFile]:
    """Load a single ``.sol`` file or every ``.sol`` file under a directory.

    Results are returned in sorted path order so the scan is deterministic.
    """
    p = Path(path)
    files: list[Path] = []
    if p.is_file() and p.suffix == ".sol":
        files = [p]
    elif p.is_dir():
        for f in p.rglob("*.sol"):
            # Only skip on directories *below* the scan root, so a scan root
            # that itself lives under e.g. a "tests" path is not excluded.
            rel_dirs = f.relative_to(p).parts[:-1]
            if any(part in _SKIP_DIRS for part in rel_dirs):
                continue
            files.append(f)
    out: list[SourceFile] = []
    for f in sorted(files, key=lambda x: str(x)):
        sf = load_source_file(f)
        if sf is not None:
            out.append(sf)
    return out


_TOKEN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*|<=|>=|==|!=|[-+*/%<>=(){}\[\];,.]")


def code_tokens(text: str) -> list[str]:
    """A lexical token stream of ``text`` (comments/strings masked), used to
    build AST-sketch shingles. Deterministic."""
    return _TOKEN.findall(_mask(text))


def iter_functions(sources: list[SourceFile], include_interfaces: bool = False):
    """Yield (SourceFile, Function) for every function, in deterministic order."""
    for src in sources:
        for fn in src.functions:
            if fn.in_interface and not include_interfaces:
                continue
            yield src, fn

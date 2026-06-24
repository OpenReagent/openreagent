"""The ``openreagent`` command-line interface.

Paths:
  scan <path>        load pool, run matchers, emit findings (deterministic, no LLM)
  extract <finding>  offline; may use an LLM; writes a signature record

Registry (the package system — "npm for detectors and shapes"):
  install <source>   install a detector/shape package (dir, zip, url, github:owner/repo)
  uninstall <name>   remove an installed package
  packages           list built-in + installed packages
  recipes            list registered recipes with maturity status

Signature store (local SQLite + remote pull):
  sig add <file>     add signature(s) to the local store
  sig list           list stored signatures
  sig pull <source>  fetch signatures from a remote/local source into the store
  sig remove <id>    delete a stored signature
  sig clear          empty the store

  validate <file>    check a signature value against its recipe's shape

``scan`` and the registry/listing commands import no LLM client.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from openreagent import loader, packages
from openreagent.recipes import all_recipes, get_recipe
from openreagent.shapes import get_shape

app = typer.Typer(
    add_completion=False,
    help="OpenReagent — recipe-based matching of recurring smart-contract vulnerabilities.",
    no_args_is_help=True,
)
sig_app = typer.Typer(add_completion=False, help="Manage the local signature store.", no_args_is_help=True)
app.add_typer(sig_app, name="sig")
console = Console()
err = Console(stderr=True)


# ---------------------------------------------------------------------------
# scan / extract
# ---------------------------------------------------------------------------

@app.command()
def scan(
    path: str = typer.Argument(..., help="A .sol file or a directory of Solidity."),
    fmt: str = typer.Option("markdown", "--format", "-f", help="json | sarif | markdown"),
    pool: Optional[str] = typer.Option(None, "--pool", "-p", help="Pool dir/file (default: shipped pool)."),
    use_store: bool = typer.Option(False, "--store", help="Use the default SQLite signature store as the pool."),
    store_db: Optional[str] = typer.Option(None, "--store-db", help="Use a specific SQLite store file as the pool."),
    enable: List[str] = typer.Option([], "--enable", "-e", help="Enable a recipe by name ('*' for all)."),
    disable: List[str] = typer.Option([], "--disable", "-d", help="Disable a recipe by name."),
    recipe_dir: List[str] = typer.Option([], "--recipe-dir", help="Load extra packages from a directory."),
    framework: Optional[str] = typer.Option(None, "--framework", help="Override build-framework detection: foundry | hardhat | vanilla."),
    no_build: bool = typer.Option(False, "--no-build", help="Skip the automatic build; scan the lexical source view only."),
    install: bool = typer.Option(False, "--install/--no-install", help="Allow auto-installing solc / node deps during the build (off by default; keeps scans offline)."),
    debug: bool = typer.Option(False, "--debug", help="Print the build's raw toolchain output / error to stderr."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Write to a file instead of stdout."),
):
    """Scan code against the pool. Deterministic; never calls an LLM."""
    from openreagent.formatters import format_report
    from openreagent.frameworks import Framework
    from openreagent.scan import scan as run_scan

    if framework is not None:
        try:
            Framework(framework.lower().strip())
        except ValueError:
            err.print(f"[red]unknown framework[/red] {framework!r}; expected foundry | hardhat | vanilla")
            raise typer.Exit(code=1)

    store = store_db if store_db else (True if use_store else None)
    report = run_scan(path, pool=pool, enable=list(enable), disable=list(disable),
                      recipe_dirs=list(recipe_dir), store=store, framework=framework,
                      do_build=not no_build, install_toolchain=install)

    if debug and report.build is not None:
        b = report.build
        err.print(f"[dim]--- build: {b.status.value} ({b.reason or 'ok'}) ---[/dim]")
        if b.log:
            err.print(b.log)
    text = format_report(report, fmt)
    if output:
        Path(output).write_text(text + "\n", encoding="utf-8")
        err.print(f"[green]Wrote {len(report.findings)} finding(s) to {output}[/green]")
    else:
        print(text)


@app.command()
def extract(
    finding: str = typer.Argument(..., help="Path to an audit-finding JSON file."),
    recipe: str = typer.Option(..., "--recipe", "-r", help="Recipe name to extract under."),
    version: Optional[str] = typer.Option(None, "--recipe-version", help="Recipe version (default: latest)."),
    signature_id: Optional[str] = typer.Option(None, "--id", help="Signature id (default: derived)."),
    reviewer: Optional[str] = typer.Option(None, "--reviewer", help="Reviewer to record in provenance."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Write the signature here."),
    to_store: bool = typer.Option(False, "--to-store", help="Also add the signature to the local store."),
):
    """Turn an audit finding into a signature record. Offline and deterministic."""
    from openreagent.extract import extract_signature, write_signature

    try:
        sig = extract_signature(finding, recipe, version=version,
                                signature_id=signature_id, reviewer=reviewer)
    except Exception as exc:
        err.print(f"[red]extract failed:[/red] {exc}")
        raise typer.Exit(code=1)
    if output:
        write_signature(sig, output)
        err.print(f"[green]Wrote signature {sig.id} to {output}[/green]")
    if to_store:
        from openreagent.store import SignatureStore

        with SignatureStore() as st:
            st.add(sig)
        err.print(f"[green]Added {sig.id} to the store[/green]")
    if not output and not to_store:
        print(json.dumps(sig.to_dict(), indent=2, sort_keys=True))


# ---------------------------------------------------------------------------
# framework detection
# ---------------------------------------------------------------------------

@app.command()
def detect(
    path: str = typer.Argument(..., help="A .sol file or a project/Solidity directory."),
    framework: Optional[str] = typer.Option(None, "--framework", help="Override: foundry | hardhat | vanilla."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
):
    """Detect a target's build framework (Foundry / Hardhat / Vanilla).

    Deterministic and performs no build. If both Foundry and Hardhat manifests are
    present, the result is ambiguous: choose one with ``--framework``, or answer
    the prompt when running interactively.
    """
    import sys

    from openreagent.frameworks import Framework, detect as detect_fw

    det = detect_fw(path)
    info = det.to_dict()

    chosen: Optional[Framework] = None
    if framework is not None:
        try:
            chosen = Framework(framework.lower().strip())
        except ValueError:
            err.print(f"[red]unknown framework[/red] {framework!r}; expected foundry | hardhat | vanilla")
            raise typer.Exit(code=1)
    elif det.framework is not None:
        chosen = det.framework
    elif not as_json and sys.stdin.isatty():
        options = [f.value for f in det.frameworks]
        answer = typer.prompt(
            f"Multiple frameworks detected ({', '.join(options)}). Choose one",
            default=options[0],
        )
        try:
            chosen = Framework(answer.lower().strip())
        except ValueError:
            err.print(f"[red]unknown framework[/red] {answer!r}")
            raise typer.Exit(code=1)

    info["resolved"] = chosen.value if chosen else None

    if as_json:
        print(json.dumps(info, indent=2, sort_keys=True))
        return

    table = Table(title="OpenReagent framework detection")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("target", det.target)
    table.add_row("project root", det.project_root)
    table.add_row("detected", ", ".join(info["detected"]))
    table.add_row("ambiguous", "yes" if det.ambiguous else "no")
    table.add_row("resolved", info["resolved"] or "[unresolved]")
    console.print(table)
    for m in det.manifests:
        console.print(f"[dim]{m.framework.value}[/dim] {m.path}")
    if det.ambiguous and chosen is None:
        err.print("[yellow]ambiguous:[/yellow] pass --framework foundry|hardhat|vanilla to choose")
        raise typer.Exit(code=1)


@app.command()
def build(
    path: str = typer.Argument(..., help="A .sol file or a project/Solidity directory."),
    framework: Optional[str] = typer.Option(None, "--framework", help="Override: foundry | hardhat | vanilla."),
    install: bool = typer.Option(True, "--install/--no-install", help="Auto-install a missing solc (vanilla) or node deps (Hardhat)."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table."),
    debug: bool = typer.Option(False, "--debug", help="Show the raw toolchain output / error (the build log)."),
):
    """Build a target at arm's length (forge / hardhat / solc) and report artifacts.

    Best-effort: a missing toolchain or the absent ``bytecode`` extra is reported
    as a skip, not an error. An ambiguous layout must be resolved with
    ``--framework``. By default a missing solc (vanilla) or the project's node
    dependencies (Hardhat) are installed automatically; use ``--no-install`` to
    stay offline. Use ``--debug`` to see the underlying compiler output.
    """
    from openreagent.building import build as build_target
    from openreagent.frameworks import Framework, detect as detect_fw

    det = detect_fw(path)
    resolved: Optional[Framework] = det.framework
    if framework is not None:
        try:
            resolved = Framework(framework.lower().strip())
        except ValueError:
            err.print(f"[red]unknown framework[/red] {framework!r}; expected foundry | hardhat | vanilla")
            raise typer.Exit(code=1)

    result = build_target(det, resolved, enabled=True, install=install)
    summary = result.summary()

    if as_json:
        payload = {**summary, "project_root": det.project_root,
                   "artifacts_detail": [a.to_summary() for a in result.artifacts]}
        if debug:
            payload["log"] = result.log
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    table = Table(title="OpenReagent build")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("framework", summary["framework"])
    table.add_row("status", summary["status"])
    table.add_row("reason", summary["reason"] or "-")
    table.add_row("compiler", summary["compiler"] or "-")
    table.add_row("artifacts", str(summary["artifacts"]))
    table.add_row("project root", det.project_root)
    console.print(table)
    for a in result.artifacts:
        console.print(f"[dim]{a.contract}[/dim] {a.source} "
                      f"(bytecode {len(a.bytecode)} chars, ast {'yes' if a.ast else 'no'})")
    if debug and result.log:
        err.print("[dim]--- toolchain output ---[/dim]")
        err.print(result.log)
    _hints = {
        "bytecode-extra-not-installed": "install the extra: pip install 'openreagent[bytecode]'",
        "no-solc-installed": "re-run with --install to fetch a matching solc automatically",
        "no-compatible-solc": "re-run with --install to fetch a matching solc automatically",
        "solc-install-failed": "solc download failed — check your network, then retry",
        "hardhat-not-installed": "re-run with --install to bootstrap Hardhat (npm install)",
        "npm-not-found": "install Node.js/npm to build a Hardhat project",
        "npm-install-error": "npm install failed — check Node version and the project",
        "forge-not-found": "install Foundry (https://getfoundry.sh) to build this project",
    }
    if summary["reason"] in _hints:
        err.print(f"[yellow]hint:[/yellow] {_hints[summary['reason']]}")
    if result.status.value in ("failed",):
        if not debug:
            err.print("[yellow]hint:[/yellow] re-run with --debug to see the compiler output")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# package registry
# ---------------------------------------------------------------------------

@app.command()
def install(source: str = typer.Argument(..., help="Local dir/zip, http(s) zip, or github:owner/repo[@ref].")):
    """Install detector/shape package(s) from a source."""
    try:
        installed = packages.install(source)
    except Exception as exc:
        err.print(f"[red]install failed:[/red] {exc}")
        raise typer.Exit(code=1)
    for pkg in installed:
        console.print(f"[green]installed[/green] {pkg.name}@{pkg.version} ({pkg.kind})")


@app.command()
def uninstall(name: str = typer.Argument(..., help="Installed package name.")):
    """Remove an installed package."""
    if packages.uninstall(name):
        console.print(f"[green]uninstalled[/green] {name}")
    else:
        err.print(f"[yellow]not installed:[/yellow] {name}")
        raise typer.Exit(code=1)


@app.command(name="packages")
def list_packages(as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table.")):
    """List built-in and installed packages."""
    pkgs = packages.discover()
    items = [pkgs[k] for k in sorted(pkgs)]
    if as_json:
        print(json.dumps([p.describe() for p in items], indent=2, sort_keys=True))
        return
    table = Table(title="OpenReagent packages")
    table.add_column("Package", style="bold")
    table.add_column("Version")
    table.add_column("Kind")
    table.add_column("Requires")
    table.add_column("Origin")
    table.add_column("Description")
    for p in items:
        table.add_row(p.name, p.version, p.kind, ", ".join(p.requires) or "-", p.origin, p.description)
    console.print(table)


@app.command()
def recipes(as_json: bool = typer.Option(False, "--json", help="Emit JSON instead of a table.")):
    """List registered recipes with their maturity status (no numbers)."""
    loader.load_builtins()
    items = all_recipes()
    if as_json:
        print(json.dumps([r.describe() for r in items], indent=2, sort_keys=True))
        return
    table = Table(title="OpenReagent recipes")
    table.add_column("Recipe", style="bold")
    table.add_column("Version")
    table.add_column("Shape")
    table.add_column("Status")
    table.add_column("Default")
    table.add_column("LLM @ extract")
    table.add_column("Note")
    for r in items:
        table.add_row(r.name, r.version, f"{r.shape.name}@{r.shape.version}", r.status.value,
                      "on" if r.default_enabled else "off",
                      "yes" if r.extractor.uses_llm else "no", r.note or "")
    console.print(table)


# ---------------------------------------------------------------------------
# signature store
# ---------------------------------------------------------------------------

@sig_app.command("add")
def sig_add(
    source: str = typer.Argument(..., help="A signature JSON/JSONL file (or a dir of them)."),
    db: Optional[str] = typer.Option(None, "--db", help="Store path (default: ~/.openreagent/signatures.db)."),
):
    """Add signature(s) to the local store."""
    from openreagent.store import SignatureStore, signatures_from_source

    sigs = signatures_from_source(source)
    if not sigs:
        err.print(f"[yellow]no signatures found in[/yellow] {source}")
        raise typer.Exit(code=1)
    with SignatureStore(db) as st:
        try:
            n = st.add_many(sigs)
        except Exception as exc:
            err.print(f"[red]add failed:[/red] {exc}")
            raise typer.Exit(code=1)
    console.print(f"[green]added {n} signature(s) to the store[/green]")


@sig_app.command("pull")
def sig_pull(
    source: str = typer.Argument(..., help="Remote/local source: URL to JSON/JSONL/zip, github:owner/repo, dir, file."),
    db: Optional[str] = typer.Option(None, "--db", help="Store path."),
):
    """Fetch signatures from a remote or local source into the store."""
    from openreagent.store import SignatureStore, signatures_from_source

    try:
        sigs = signatures_from_source(source)
    except Exception as exc:
        err.print(f"[red]pull failed:[/red] {exc}")
        raise typer.Exit(code=1)
    if not sigs:
        err.print(f"[yellow]no signatures found at[/yellow] {source}")
        raise typer.Exit(code=1)
    with SignatureStore(db) as st:
        n = st.add_many(sigs)
        total = st.count()
    console.print(f"[green]pulled {n} signature(s)[/green]; store now holds {total}")


@sig_app.command("list")
def sig_list(
    recipe: Optional[str] = typer.Option(None, "--recipe", help="Filter by recipe name."),
    db: Optional[str] = typer.Option(None, "--db", help="Store path."),
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
):
    """List signatures in the store."""
    from openreagent.store import SignatureStore

    with SignatureStore(db) as st:
        items = st.list(recipe)
    if as_json:
        print(json.dumps([s.signature.to_dict() for s in items], indent=2, sort_keys=True))
        return
    if not items:
        console.print("[dim]store is empty[/dim]")
        return
    table = Table(title="Stored signatures")
    table.add_column("Id", style="bold")
    table.add_column("Recipe")
    table.add_column("Version")
    table.add_column("Added")
    for s in items:
        table.add_row(s.signature.id, s.signature.recipe.name, s.signature.recipe.version, s.added_at)
    console.print(table)


@sig_app.command("remove")
def sig_remove(
    signature_id: str = typer.Argument(..., help="Signature id to remove."),
    db: Optional[str] = typer.Option(None, "--db", help="Store path."),
):
    """Remove a signature from the store."""
    from openreagent.store import SignatureStore

    with SignatureStore(db) as st:
        ok = st.remove(signature_id)
    if ok:
        console.print(f"[green]removed[/green] {signature_id}")
    else:
        err.print(f"[yellow]not found:[/yellow] {signature_id}")
        raise typer.Exit(code=1)


@sig_app.command("clear")
def sig_clear(
    db: Optional[str] = typer.Option(None, "--db", help="Store path."),
    yes: bool = typer.Option(False, "--yes", help="Do not prompt."),
):
    """Empty the store."""
    from openreagent.store import SignatureStore

    if not yes:
        typer.confirm("Delete every signature in the store?", abort=True)
    with SignatureStore(db) as st:
        n = st.clear()
    console.print(f"[green]cleared {n} signature(s)[/green]")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@app.command()
def validate(signature_file: str = typer.Argument(..., help="A signature JSON file to validate.")):
    """Check that a signature parses and its value conforms to its shape."""
    from openreagent.models import Signature

    loader.load_builtins()
    try:
        raw = json.loads(Path(signature_file).read_text(encoding="utf-8"))
        sig = Signature.from_dict(raw)
    except Exception as exc:
        err.print(f"[red]invalid record:[/red] {exc}")
        raise typer.Exit(code=1)
    recipe = get_recipe(sig.recipe.name, sig.recipe.version)
    if recipe is None:
        err.print(f"[red]unknown recipe[/red] {sig.recipe.name}@{sig.recipe.version}")
        raise typer.Exit(code=1)
    shape = get_shape(recipe.shape.name, recipe.shape.version)
    if shape is None or not shape.conforms(sig.value):
        err.print(f"[red]value does not conform to shape[/red] {recipe.shape.name}@{recipe.shape.version}")
        raise typer.Exit(code=1)
    console.print(f"[green]OK[/green] {sig.id}: conforms to {recipe.shape.name}@{recipe.shape.version} "
                  f"(recipe {recipe.name}@{recipe.version})")


if __name__ == "__main__":  # pragma: no cover
    app()

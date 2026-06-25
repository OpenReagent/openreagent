"""The ``openreagent`` command-line interface.

Paths:
  scan <path>        load pool/store, run matchers, emit findings (deterministic, no LLM)
  extract <finding>  offline, deterministic; writes a signature record

Registry (the package system — "npm for detectors and shapes"):
  install <source>   install a detector/shape package (dir, zip, url, github:owner/repo)
  uninstall <name>   remove an installed package
  packages           list built-in + installed packages
  recipes            list registered recipes with maturity status

Remote store (a server in front of the database — set OPENREAGENT_SERVER_URL):
  serve              run the OpenReagent server (the store API; needs server+store extras)
  sig add <file>     add signature(s) to the remote server
  sig list           list stored signatures
  sig pull <source>  fetch signatures from a remote/local source into the server
  sig remove <id>    delete a stored signature
  sig clear          empty the store

  validate <file>    check a signature value against its recipe's shape

Clients talk to the server, not the database; ``scan --store`` matches via the
server's ``/match`` endpoint (the seam for future PSI). ``scan`` and the
registry/listing commands use no LLM.
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
sig_app = typer.Typer(add_completion=False, help="Manage signatures on the remote server (the store API).", no_args_is_help=True)
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
    use_store: bool = typer.Option(False, "--store", help="Match against the remote server (OPENREAGENT_SERVER_URL)."),
    server_url: Optional[str] = typer.Option(None, "--server-url", help="OpenReagent server URL override (http://...); implies --store."),
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
    from openreagent.client import ServerConfigError, ServerError
    from openreagent.formatters import format_report
    from openreagent.frameworks import Framework
    from openreagent.scan import scan as run_scan

    if framework is not None:
        try:
            Framework(framework.lower().strip())
        except ValueError:
            err.print(f"[red]unknown framework[/red] {framework!r}; expected foundry | hardhat | vanilla")
            raise typer.Exit(code=1)

    store = server_url if server_url else (True if use_store else None)
    try:
        report = run_scan(path, pool=pool, enable=list(enable), disable=list(disable),
                          recipe_dirs=list(recipe_dir), store=store, framework=framework,
                          do_build=not no_build, install_toolchain=install)
    except (ServerConfigError, ServerError) as exc:
        err.print(f"[red]server:[/red] {exc}")
        raise typer.Exit(code=1)

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
    to_store: bool = typer.Option(False, "--to-store", help="Also send the signature to the remote server (OPENREAGENT_SERVER_URL)."),
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
        from openreagent.client import OpenReagentClient, ServerConfigError, ServerError

        try:
            OpenReagentClient().add([sig])
        except (ServerConfigError, ServerError) as exc:
            err.print(f"[red]server:[/red] {exc}")
            raise typer.Exit(code=1)
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

_SERVER_OPT = typer.Option(None, "--server-url", help="Server URL (default: $OPENREAGENT_SERVER_URL).")


def _client(server_url):
    """Build a server client, turning a missing-config into a clean exit."""
    from openreagent.client import OpenReagentClient, ServerConfigError

    try:
        return OpenReagentClient(server_url)
    except ServerConfigError as exc:
        err.print(f"[red]server:[/red] {exc}")
        raise typer.Exit(code=1)


def _push(source, server_url, *, verb):
    from openreagent.client import ServerError
    from openreagent.store import signatures_from_source

    try:
        sigs = signatures_from_source(source)
    except Exception as exc:
        err.print(f"[red]{verb} failed:[/red] {exc}")
        raise typer.Exit(code=1)
    if not sigs:
        err.print(f"[yellow]no signatures found in[/yellow] {source}")
        raise typer.Exit(code=1)
    client = _client(server_url)
    try:
        n = client.add(sigs)
    except ServerError as exc:
        err.print(f"[red]server:[/red] {exc}")
        raise typer.Exit(code=1)
    console.print(f"[green]{verb}ed {n} signature(s) to the server[/green]")


@sig_app.command("add")
def sig_add(
    source: str = typer.Argument(..., help="A signature JSON/JSONL file (or a dir of them)."),
    server_url: Optional[str] = _SERVER_OPT,
):
    """Add signature(s) to the remote server."""
    _push(source, server_url, verb="add")


@sig_app.command("pull")
def sig_pull(
    source: str = typer.Argument(..., help="Remote/local source: URL to JSON/JSONL/zip, github:owner/repo, dir, file."),
    server_url: Optional[str] = _SERVER_OPT,
):
    """Fetch signatures from a remote or local source into the server."""
    _push(source, server_url, verb="pull")


@sig_app.command("list")
def sig_list(
    recipe: Optional[str] = typer.Option(None, "--recipe", help="Filter by recipe name."),
    server_url: Optional[str] = _SERVER_OPT,
    as_json: bool = typer.Option(False, "--json", help="Emit JSON."),
):
    """List signatures in the server."""
    from openreagent.client import ServerError

    client = _client(server_url)
    try:
        items = client.list(recipe)
    except ServerError as exc:
        err.print(f"[red]server:[/red] {exc}")
        raise typer.Exit(code=1)
    if as_json:
        print(json.dumps([s.to_dict() for s in items], indent=2, sort_keys=True))
        return
    if not items:
        console.print("[dim]store is empty[/dim]")
        return
    table = Table(title="Stored signatures")
    table.add_column("Id", style="bold")
    table.add_column("Recipe")
    table.add_column("Version")
    for s in items:
        table.add_row(s.id, s.recipe.name, s.recipe.version)
    console.print(table)


@sig_app.command("remove")
def sig_remove(
    signature_id: str = typer.Argument(..., help="Signature id to remove."),
    server_url: Optional[str] = _SERVER_OPT,
):
    """Remove a signature from the server."""
    from openreagent.client import ServerError

    client = _client(server_url)
    try:
        ok = client.remove(signature_id)
    except ServerError as exc:
        err.print(f"[red]server:[/red] {exc}")
        raise typer.Exit(code=1)
    if ok:
        console.print(f"[green]removed[/green] {signature_id}")
    else:
        err.print(f"[yellow]not found:[/yellow] {signature_id}")
        raise typer.Exit(code=1)


@sig_app.command("clear")
def sig_clear(
    server_url: Optional[str] = _SERVER_OPT,
    yes: bool = typer.Option(False, "--yes", help="Do not prompt."),
):
    """Empty the store."""
    from openreagent.client import ServerError

    if not yes:
        typer.confirm("Delete every signature in the store?", abort=True)
    client = _client(server_url)
    try:
        n = client.clear()
    except ServerError as exc:
        err.print(f"[red]server:[/red] {exc}")
        raise typer.Exit(code=1)
    console.print(f"[green]cleared {n} signature(s)[/green]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address."),
    port: int = typer.Option(8000, "--port", help="Port."),
):
    """Run the OpenReagent server (the remote store API).

    Needs the ``server`` and ``store`` extras and a configured database
    (``OPENREAGENT_DB_URL``): pip install 'openreagent[server,store]'.
    """
    try:
        import uvicorn

        from openreagent.server import create_app
    except ImportError:
        err.print("[red]serve needs the server extra:[/red] pip install 'openreagent[server,store]'")
        raise typer.Exit(code=1)
    uvicorn.run(create_app(), host=host, port=port)


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

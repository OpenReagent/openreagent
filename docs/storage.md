# Signature storage

Signatures can live in a local **SQLite store** instead of (or alongside) a
directory of JSON files. The store makes it easy to accumulate signatures over
time, sync a shared set from a remote source, and scan against them directly.

## Where the store lives

The default database is `$OPENREAGENT_HOME/signatures.db` (default
`~/.openreagent/signatures.db`). Use a different file with `--db <path>` on any
`sig` command, or `--store-db <path>` on `scan`.

## Schema

One row per signature:

| column | meaning |
|--------|---------|
| `id` | signature id (primary key) |
| `recipe_name`, `recipe_version` | the recipe reference |
| `value` | the value, as JSON |
| `provenance` | the provenance list, as JSON |
| `record` | the full canonical record, as JSON |
| `added_at` | insert timestamp |

On insert, the value is validated against its recipe's shape — the same check the
file pool performs at load time. A non-conforming or recipe-less signature is
rejected.

## Adding signatures

```bash
openreagent sig add sig.json                # a single record, an array, or JSONL
openreagent sig add ./signatures/           # every *.json under a directory
openreagent extract finding.json -r internal-absence --to-store
```

## Pulling from a remote source

`sig pull` fetches signatures from a remote or local source and inserts them:

```bash
openreagent sig pull https://host/signatures.json   # a JSON array or JSONL
openreagent sig pull https://host/signatures.zip     # a zip of *.json records
openreagent sig pull github:owner/sig-repo           # a GitHub repo of records
openreagent sig pull ./local/dir                     # a local directory
```

The accepted content is a JSON array of records, a single record, JSONL, or a
directory/zip/repo of `*.json` records (package manifests are skipped). Every
pulled record is shape-validated on insert.

## Listing and removing

```bash
openreagent sig list                 # table of id / recipe / version / added
openreagent sig list --recipe canonical-divergence
openreagent sig list --json
openreagent sig remove <id>
openreagent sig clear                # empty the store (prompts unless --yes)
```

## Scanning against the store

```bash
openreagent scan ./contracts --store               # default store as the pool
openreagent scan ./contracts --store-db ./team.db  # a specific store file
```

Scanning from the store is identical to scanning from a file pool: signatures are
shape-validated, recipes run deterministically, and no LLM is involved.

## Provenance and sharing

Each record keeps its own provenance (source kind, source ref, and the recipe
version and timestamp of each extraction), so a store assembled from several
pulls remains auditable. Note the open question in
[open-questions.md](open-questions.md) about distributing pools without
redistributing the underlying audit material: a `source_ref` points at material
a recipient may or may not be able to access.

# Open questions

OpenReagent is deliberately narrow: it surfaces code consistent with a signature,
deterministically and with no LLM at match time. That narrowness leaves real
questions unresolved — questions the maintainers have hit in practice and want to
work through with the community rather than decide unilaterally in a pull request.
This document records them so contributors and reviewers share the same picture
of what the project does **not** yet answer. None is settled; each is an
invitation to a working-group discussion (see [CONTRIBUTING.md](../CONTRIBUTING.md)).

## Recipe registry and integrity

**Who validates and registers a recipe?** Recipes are the unit of method, and the
framework runs whatever recipe it is given. If recipes are distributed as packages
("npm for detectors and shapes"), some party has to decide which recipes are sound
enough to publish, and on what basis. There is no review authority or acceptance
bar defined yet beyond a maintainer's judgement on this repository.

**Recipe signing.** A package that ships executable matcher/extractor code is a
supply-chain surface: a malicious or tampered recipe could mislead a scan or run
unwanted code at extract time. Do we need integrity and authenticity guarantees
for recipes — signed packages, a verifiable publisher identity, a trust policy a
consumer can enforce — analogous to app signing?

**Backward compatibility across recipe versions.** Comparison is only meaningful
between signatures extracted under the same recipe version. When a recipe is
bumped, must it preserve backward compatibility with signatures already in the
wild, or is a clean break acceptable if the version is part of the record? What
is the contract authors owe consumers across a version change?

## What a signature is

**Signature granularity.** A signature carries a "vulnerable location," but how
fine should that be — a line, a statement, a function, a contract, a slice of a
control-/data-flow path? Too coarse and matches are noisy; too fine and the
signature fails to generalize. There is no agreed definition of the unit a
vulnerable location should name.

**Partial-code vs. full-code recipes.** Audit reports often present a fragment
rather than a complete, buildable contract with full context. Can a recipe be
designed to extract and match against *partial* code, and how does its behavior
differ from a recipe that assumes a full codebase? This depends on a question we
have not pinned down: **what precisely distinguishes "full code" from "partial
code"** for the purposes of extraction and matching?

## Evaluating and benchmarking a recipe

**How do you show a recipe is effective?** The usual vulnerability-detection
metric is an F1 score against labelled data, but the vulnerabilities that matter
most are frequently the ones that are hard to capture mechanically, which makes
constructing a fair benchmark very hard. Pool-level evaluation can characterize
**precision** on a fixed pool and code, but it says nothing about what a recipe
*misses* — there is no labelled universe of real vulnerabilities to measure
recall against, and building a versioned ground-truth corpus is itself an open
problem (see [evaluation.md](evaluation.md)). Until this is resolved, recipes
report **maturity only**, and any private evaluation must be stated as "precision
on this pool and this code," never as a detection rate.

**Build-artifact reproducibility.** Recipes that consume compiled bytecode or an
AST inherit the compiler's nondeterminism: output varies by solc version,
optimizer settings, and metadata, and AST schemas change across versions (see the
build-integration direction in [roadmap.md](roadmap.md) and the dependency note
in [architecture.md](architecture.md)). What is the minimal, honest set of build
inputs to pin and record in provenance so a finding over an artifact stays
reproducible?

## Sharing, privacy, and standardization

**Privacy-preserving sharing.** If recipe authors have wide latitude over how a
recipe is composed, how can an organization share that a vulnerability matched —
or contribute a signature — without exposing its codebase, execution traces, or
proprietary artifacts? Does enabling confidential validation require placing
constraints on how recipes may be composed, so that shareable representations are
cleanly separated from internal analysis context?

**Distributing pools without redistributing audit material.** A signature's
provenance points at the material it was extracted from via a `source_ref` (see
[storage.md](storage.md) and [schema.md](schema.md)). That reference may name
audit text a recipient is not licensed to receive. We want a shared pool to stay
**auditable** — a reviewer can trace a signature back to its evidence — without
the pool itself becoming a way to redistribute confidential audit material. Can a
`source_ref` be a stable, resolvable identifier (content hash, DOI, access-gated
URL) so the reference travels while the material does not, and what is the minimum
provenance a recipient needs to trust a signature they cannot fully dereference?

**Standardizing audit-knowledge sharing.** Today, signatures are produced by
hand-collecting audit reports and converting them into this project's format. A
broadcast standard for publishing audit findings in a shareable form — aligned
with ecosystem formats such as OSV/VEX, and considering a mapping onto an
ATT&CK-style model — would remove that manual step. What should such a standard
contain, and who maintains it?

## Governance

Who operates and reviews the **signature database** and the **recipe registry**?
As signatures accumulate, someone must be accountable for their quality, for the
trust placed in them, and for preventing abuse (e.g. poisoned signatures or
recipes). A registry of executable recipes needs a comparable accountability
model. The operating and review structures, and how they relate to the LFDT
working group, are not yet defined.

## Catalog completeness

The set of recipes is a catalog of *expressible* recurring shapes, not a taxonomy
of vulnerabilities, and we have no principled measure of how complete it is: many
known classes have no recipe, some have a recipe only over the lexical Solidity
view, recipes may overlap (see the detector-adjacency note in
[conventions.md](conventions.md)), and there is no agreed signal for "this shape
is common enough to warrant a recipe." The catalog grows by contribution rather
than by plan.

## How to engage

These questions are best moved forward in the LFDT working group rather than
decided in a single pull request. If your contribution bears on one of them, say
so in the pull request and link back to the relevant section here.

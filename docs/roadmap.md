# Roadmap

This roadmap is direction, not a schedule: a target date appears only where one is
committed; no date means planned but not yet scheduled. The scan path always stays
**deterministic** and **LLM-free at match time**. Open design questions behind
these items live in [open-questions.md](open-questions.md).

## Release plan

| version | theme | target |
|---------|-------|--------|
| **v0.1.0** | Current baseline: recipe framework, deterministic scan / offline extract, signature store, package system, lexical Solidity view | released |
| **v0.2.0** | Toolchain integration: framework detection, automatic build, artifact-fed recipes (bytecode / AST); clone-detection recipes; large-scale benchmarking | end of June 2026 |
| **v0.3.0** | More signature sources: security-incident–based and IR-based extraction | planned |
| **v0.4.0** | Privacy-preserving validation | planned |
| **v0.5.0** | Draft end-to-end vulnerability-sharing protocol | planned |
| **v0.6.0** | Auxiliary features (e.g. a dashboard) | planned |
| **v1.0.0** | First stable release after bug-fix hardening | planned |

## v0.2.0 — current milestone

Build the path from a target's project layout to real build artifacts, then feed
those artifacts to matchers. Heavier toolchains run **at arm's length**, behind
optional extras, so a plain source scan still runs anywhere.

- **Framework detection** — Foundry (`foundry.toml`), Hardhat (`hardhat.config.*`),
  or vanilla `.sol`; deterministic, no build (see [frameworks.md](frameworks.md)).
  *TODO: Truffle / Brownie fall back to vanilla for now.*
- **Automatic build** — `forge build` / `hardhat compile` / `solc` (vanilla);
  degrades gracefully when a tool or extra is absent.
- **Artifact-fed recipes** — carry bytecode and AST alongside the source view so
  `bytecode-hash` and `ast-sketch` can use them (see [recipes.md](recipes.md)).
- **More recipes & benchmarking** — BAP-/Vuddy-style clone recipes; large-scale
  Ethereum benchmark (methodology only; no numbers published, see
  [evaluation.md](evaluation.md)).

## Long-term (after v1.0.0)

Beyond the first stable release, the direction follows the
[LFDT Lab proposal](https://lf-decentralized-trust-labs.github.io/labs/approved/openreagent.html):
evolving OpenReagent into an industry-grade platform for structured, secure
sharing of smart-contract vulnerability intelligence.

- **Standardization.** Mature the v0.5.0 sharing protocol into an adopted standard,
  aligned with ecosystem formats (OSV/VEX) and integrated into CI/CD and
  DevSecOps pipelines.
- **Confidential validation at scale.** Generalize privacy-preserving validation
  to arbitrarily structured signatures, so organizations verify results without
  exposing source, traces, or proprietary artifacts.
- **Multi-chain and IR expansion.** Extend beyond Solidity/EVM to additional
  blockchains and intermediate representations, with richer behavioral signatures.
- **Cross-organization consensus.** Establish shared validation practices and
  **governance** for the signature database and recipe registry (see the
  governance question in [open-questions.md](open-questions.md)).

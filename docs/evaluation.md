# Evaluating a recipe

This document describes *how* to evaluate a recipe. It deliberately contains no
precision, recall, or CI numbers: this repository publishes maturity status
only. If you run an evaluation, keep your numbers in your own notes, not in the
public artifacts here.

## What a pool-level evaluation can and cannot tell you

Running a recipe against a pool of signatures over a body of code measures
**precision-style** behavior: of the candidates a matcher surfaces, how many a
reviewer judges to be true positives. It does **not** measure recall against the
universe of real vulnerabilities, because the pool is not that universe (see
[open-questions.md](open-questions.md) on false negatives). State results as
"precision on this pool and this code," never as a detection rate.

## Manual precision sampling — the field standard

The honest way to characterize a recipe's output is manual review of a sample:

1. **Fix the inputs.** Pin the recipe version, the pool, and the exact target
   code (commit hashes). Record them. Scanning is deterministic, so a fixed
   triple reproduces exactly.
2. **Draw a sample.** From the findings, draw a random sample (record the seed).
   For rare recipes, review the full set.
3. **Label against a written rubric.** For each sampled finding, a reviewer
   decides true positive / false positive / unclear against a rubric written
   *before* labelling. A true positive means the surfaced code is genuinely
   consistent with the signature — not that it is necessarily exploitable
   (exploitability is out of scope; see the scope note in
   [schema.md](schema.md)).
4. **Adjudicate.** Have a second reviewer label a subset and reconcile
   disagreements; keep the rubric and the disagreements with your notes.
5. **Report with caveats, privately.** Report the sampled precision with its
   sample size and confidence interval, the inputs, and the rubric. Do not
   publish these numbers in this repository.

## The false-negative limitation

Pool-level evaluation surfaces precision but says nothing about the
vulnerabilities a recipe *misses*. There is no labelled universe of real
vulnerabilities to measure recall against, and constructing one is an open
problem ([open-questions.md](open-questions.md)). Be explicit about this whenever
you describe a recipe's behavior: "we characterized precision on a sample; recall
is not established."

## Determinism makes evaluation cheap to reproduce

Because scan output is byte-identical for fixed inputs, an evaluation is fully
reproducible from the recorded triple (recipe version, pool, target commit). A
reviewer can re-run your scan and get exactly your findings before re-labelling.

## What to put in public docs

Maturity status (`production`, `experimental`, `journey`) and the methodology
above — not numbers. The status of a recipe reflects how much review it has had,
which is a judgement, not a measurement.

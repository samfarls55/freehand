# Small-model cleanup quality and performance protocol

This protocol was prepared before viewing any new small-model output. The fresh
finalist holdout is `work/cleanup-small-models-2026-11-03/frozen-holdout.json`,
SHA-256 `3529e74da64616e5b08f2c9c189706f03c68e6247c924eb8b9137743c4881e5d`.
Its freeze manifest is beside it. It contains 40 newly authored synthetic cases,
including 6 actual dictionary cases, 38 short inputs under 50 words, one medium
input and one input of at least 150 words. Twenty-nine inputs need an edit.
There is no exact input overlap with the previous 90 general and 10 dictionary
fixtures. Shared categories are intentional; this is not an independent sample
of real user dictation or a population accuracy estimate.

Use previous development examples to choose candidate model, quantization,
trained prompt, sampler, context and worker settings. Before running the new
holdout, save the exact finalist model/runtime/artifact hashes, managed source
hashes, fully rendered prompts, configuration, and any guards. Do not tune on
holdout outputs. A later change makes this set development evidence for that
candidate and requires a fresh holdout for a new generalization claim. Running
cleanup-disabled Core normalization to verify the fixture contract does not
consume a model holdout; preserve that output and do not alter frozen cases.

## Meaning and clean text

Every completed model return and final application output needs a manual meaning
review, including outputs that match automatic assertions. The reference strings
are examples, not an exhaustive set of valid wording. Report these separately:

- `candidate_faithful`: the provider return retains intended facts, conditions,
  negation, speech act, uncertainty, deliberate emphasis, quoted words and exact
  protected replacement bytes. Do not credit bytes restored by code as model
  copying quality. Record the raw model text separately when the adapter changes
  it. Missing or unreturned candidate text is unassessed, not a fidelity pass.
- `final_faithful`: the text actually selected by Core retains that meaning.
  Original-text fallback can preserve meaning while providing no cleanup benefit.
- `useful`: a faithful edit addresses a real cleanup defect. Punctuation alone
  does not count when a substantive correction or restart remains unresolved.
  A partial beneficial edit can be useful without being complete.
- `cleanup_complete`: all material cleanup defects are resolved. Explicit spoken
  correction cues should collapse to the final intended phrase, without obsolete
  values or clauses. A meaningful contrast such as “0.25, not 2.5” is retained.
- `plain_text_usable`: the output can be inserted directly, without assistant
  commentary, answers to dictated questions, invented facts, Markdown fences,
  extra backticks or other unrequested wrappers. Existing literal code is kept.
- `acceptable`: final text is faithful, plain text is usable, and cleanup is
  complete when needed. A no-edit input qualifies when faithfully preserved.

Uncertainty and emphasis are meaning. “I think,” “might,” and intentional repeated
words must survive. Filling an unfinished thought, summarizing a long utterance,
executing an instruction in the dictation, or answering a dictated question is a
semantic failure. Harmless punctuation and quote typography can differ. Preserve
explicitly required literal bytes, including whitespace, tabs, paths and Unicode.
Core dictionary acceptance is a structural contract, not semantic certification.

Classify semantic failures by severity: `critical` for changed negation, action,
recipient, quantity, condition, invented content or an answered/executed command;
`major` for lost substantive detail, uncertainty, intentional emphasis or quoted
wording; `minor` for a harmless presentation defect with meaning intact; `none`
when no defect is observed. Record evidence in a short per-case note rather than
inferring correctness from target similarity or a model's own self-assessment.

Rank defaults by fidelity and complete useful coverage among profiles that meet
the measured resource gate. An accepted critical semantic failure disqualifies a
profile from being called an established production choice on this evaluation.
A model that frequently falls back is not a cleanup success even when fallback
keeps original meaning. Report accepted coverage, fallback causes, complete
cleanup rate among edit-needed cases, and no-edit preservation separately. Do not
average facts changed and improvements together into one flattering score.

## The 15% resource gate

The user's limits are **747,500,000 bytes of whole-app host memory** and **805 ms
from release to complete text**, calculated from 650,000,000 bytes and 700 ms.
These replace the earlier descriptive-only or extra-cleanup-budget targets.
Model download size is not loaded memory. A model-server RSS peak or Core probe
peak is not the whole-application measurement.

For target Windows acceptance, sample simultaneous desktop, speech-worker and
cleanup-worker resident memory throughout ready state, recording, inference,
worker load, recovery and teardown. Include external servers if used. Align the
resident metric with the historical measurement and report private commit too;
summed working sets can double-count shared pages. Keep dedicated GPU memory
separate and count shared GPU host allocations in host RAM. Do not sum unrelated
historical maxima or call independent p95 sums a measured end-to-end p95.

Measure release through actual completed insertion in the owned foreground
Windows control, after ASR, preprocessing, cleanup, validation and delivery. Keep
first character, complete text and model first token separate. The historical
short baseline used 50 warm 10-second fixtures yielding 107 characters. Require
at least the same warm-trial count and report p50, p95 and maximum, plus cold,
first-after-idle, restart and longer-duration observations. Cold and longer
measurements must not silently disappear from the report when they exceed 805 ms.
The existing physical delivery path can itself take about one second for 500
characters, so a short-fixture pass does not establish an all-length deadline.
Report latency by input and output length classes.

Run candidates one at a time on otherwise idle hardware. Save CPU, memory limit,
thread count, runtime build, GPU/backend and settings. Repeat a timed series only
when resolving a specific comparison or unstable observation. Linux cloud CPU
measurements can screen options and expose failures; they cannot certify the
Windows laptop, its microphone, physical key, foreground delivery or whole app.
If only partial-path measurements exist, state that the gate remains unproven.

## Review records and freeze evidence

`human-review-template.json` defines a compact per-case review. Keep unassessed
judgments null. Use a candidate label during initial review and reveal its
identity afterward where practical. An assistant review is an agent judgment,
not a claim of human sign-off. Preserve review provenance and disagreements.

Save the corpus, freeze metadata, raw HTTP output, provider return, final Core
text, status, timing scope, insertion count, errors and source/config hashes.
Test actual dictionary integration separately from raw native cleanup; deterministic
restoration and fallback must remain visible in those records. Existing strict
protection can reject deleting an intentionally superseded protected phrase;
report that as limited cleanup coverage rather than relaxing dictionary semantics
without a separate contract change.

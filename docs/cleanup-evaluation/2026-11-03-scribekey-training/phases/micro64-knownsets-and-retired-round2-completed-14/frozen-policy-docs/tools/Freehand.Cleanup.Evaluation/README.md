# Cleanup model evaluation

This Python standard-library tool compares complete cleanup outputs on public
synthetic transcript fixtures. Output quality is the first selection criterion.
Latency and memory are descriptive measurements in this first pass, not the
historical Wispr Flow acceptance gates.

The corpus contains 60 development and 30 held-out examples. It includes good
text that should remain unchanged, meaningful uses of filler words, deliberate
emphasis, spoken corrections, hedges, negation, unfinished thoughts, quoted
instructions, lists, literal spans and technical text. The examples were authored
for this diagnostic; they are not private dictations or a representative speech
benchmark. Tune on the development split and freeze artifacts, prompt and
configuration before opening held-out outputs.

## Run

The no-cleanup control requires no model, runtime or network access:

```sh
python tools/Freehand.Cleanup.Evaluation/benchmark.py --output work/cleanup-baseline
```

Copy `config.example.json` into an ignored work directory. Supply local model
and runtime paths, SHA256 hashes and immutable artifact provenance. This tool
does not download models or runtimes. The example is a configuration template,
not evidence that those model files are available or have been benchmarked.

```sh
python tools/Freehand.Cleanup.Evaluation/benchmark.py --config work/cleanup-config.json --output work/cleanup-development
python tools/Freehand.Cleanup.Evaluation/benchmark.py --config work/cleanup-config.json --output work/cleanup-heldout --split heldout
```

`--ids dev-001,dev-013`, `--limit 5`, `--repetitions 3`, `--request-timeout 120`
and `--startup-timeout 180` support bounded experiments. An existing output
directory is rejected to preserve previous results. A failing request, startup,
artifact check or incomplete completion is reported explicitly; a deadline stops
the owned server and aborts its remaining jobs. Never interpret unrun fixtures as
quality passes.

The harness owns one `llama-server` at a time, binds it to loopback, authenticates
requests with a generated key in `LLAMA_API_KEY`, and shuts it down after each
candidate. CPU-only arguments are the default. Use a pinned runtime supporting
the configured options. Quill uses its published minimal system prompt and raw
ChatML with an empty think block; other candidates use the exact policy in
`shared/transcript-cleanup-prompt.txt` with the model's Jinja template and thinking disabled.
Their user message contains one compact JSON `transcript` field so questions and
commands are presented as dictation data. This is an empirical editing cue, not
a guarantee of fidelity. Known raw model control tokens are rejected; ordinary
angle-bracket text remains supported. Quill retains its trained raw input contract.
For general models, complete protected literal blocks are replaced by deterministic
opaque identifiers. The adapter restores their original bytes only if every
identifier survives exactly once and in order. Reports retain raw model output
separately from restored provider output; restored literal bytes are not model
copying successes. The Python adapter mirrors the managed provider.
That policy matches Freehand's local cleanup provider. The prompt difference is
recorded and is an intentional model-specific condition of the experiment.

## Read the results

- `report.json` records model/runtime/configuration/prompt/fixture hashes, selected
  IDs, failures, category summaries, complete-response times and memory scope.
- `outputs.jsonl` retains every actual output, raw response and automatic checks.
- `review.md` presents candidate labels for human comparison; `review-key.json`
  maps labels back to identities. Keep the key closed during initial review.
- Each candidate's server log is retained separately.
- Input corpus, evaluator source, prompt, configuration and normalization/probe report snapshots
  preserve the exact source evidence when later runs replace external files.

The grader tests explicit expected facts, final corrected alternatives, exact
literal bytes and output-contract violations. It records similarity to one or
more example targets separately. A different faithful wording can require human
review without being an automatic failure. Passing content checks also requires
human review: those checks cannot establish equivalent meaning. Compare final
intended facts and readable wording, not verbatim recognition WER or unchanged
counts of every date/number; Backtrack deliberately removes superseded facts.

The no-cleanup output is the provided pre-cleanup transcript. For a production
pipeline comparison, use `tools/Freehand.Cleanup.Probe` without a cleanup manifest
to obtain the existing dictionary and number-normalized transcript first. Supply
its baseline JSON through `--normalization-report`; the harness verifies source
inputs and uses its normalized targets and semantic checks too. Do not credit
cleanup with improvements the existing normalizer already makes. The synthetic
corpus alone does not establish production-normalized inputs.

Grade the integrated Core probe separately:

```sh
python tools/Freehand.Cleanup.Evaluation/score_probe.py --input work/cleanup-probe-results.json --candidate-id selected-model --output work/cleanup-probe-scores
```

That report separates raw text returned by the processor, accepted application
results, fallback results and accepted coverage. A model returning bad edits must
not receive credit because Core fell back to a good original transcript. Raw
responses rejected by the provider's parser may have no `candidate_text`; native
HTTP replay preserves those responses separately. Both native completion parsing
and Quill stop tokens match `LlamaTranscriptPostProcessor`.

Memory is the sampled simultaneous sum for the owned cleanup server process tree.
Linux reports RSS and private resident pages; Windows reports working set and
private commit separately. Shared pages can be counted twice. GPU allocations,
the Python observer, the Freehand desktop and the speech worker are excluded.
This is not a full-application or Windows microphone/hotkey/delivery benchmark.
Report CPU/GPU configuration, trial counts and cold readiness time with results;
the nearest-rank p95 of a handful of trials is not a stable tail guarantee.

## Verify the evaluator

```sh
python -m unittest discover -s tools/Freehand.Cleanup.Evaluation -p 'test_*.py' -v
```

The tests exercise semantic diagnostics, legitimate correction deletions, exact
literal preservation, incomplete output, authenticated loopback lifecycle,
deadline termination, artifact mismatch and Linux process-tree memory reporting.
The fake runtime used by lifecycle tests performs no model inference and its
results must never be presented as model performance. The Windows ctypes memory
path requires validation on Windows.

## Small-model contracts

`small_models.py` consumes exact prompts exported by the managed implementation,
so specialist formats do not need a second Python implementation. Exporting
normalizes inputs and references through the existing Core pipeline first:

```sh
dotnet run --project tools/Freehand.Cleanup.Probe -c Release -- --export-prompts --input tools/Freehand.Cleanup.Evaluation/fixtures.json --output work/s1-prompts.json --prompt-style S1Mini --split development
python tools/Freehand.Cleanup.Evaluation/small_models.py --asset-index work/cleanup-small-models-2026-11-03/asset-index.json --candidate superwhisper/s1-mini-GGUF --prompts work/s1-prompts.json --output work/s1-native-screen --ids dev-001,dev-013
```

The acquisition index must contain independently verified complete model and
runtime files; the runner rechecks their exact hashes and sizes. Each run owns
one server and refuses an existing output directory. Linux runs also reject an
already running `llama-server`. The default profile uses four CPU threads,
2048 context tokens, a 512-token complete-output reservation, 128-token batch
and micro-batch sizes, no host prompt cache and no context checkpoints.
`--threads`, `--context`, `--max-output`, `--batch`, `--micro-batch`, `--cache-ram`
and `--repeats` support explicit profiles. Additional native options can be
supplied with repeated `--extra-server-arg`, for example
`--extra-server-arg=--spec-type --extra-server-arg=ngram-simple`.

When `runtime-file-index.json` exists beside the asset index, the runner also
verifies every listed runtime file and symlink target and records the inventory
hash. `--runtime-file-index PATH` requires an explicit inventory. A small server
launcher hash alone does not freeze its dynamically loaded libraries.

Specialist generation submits the integer token array returned by `/tokenize`.
In the pinned b12015 runtime, the `/completion` string-prompt path always adds
special tokens; an `add_special: false` JSON field does not suppress that step.
Sending the validated array preserves each model's exact BOS contract. General
controls use their embedded chat template, shared JSON policy and literal mask.
Oversized prompts and incomplete responses are recorded as failures, with no
input truncation or credit for partial output. Raw responses remain available.

The native report separates server readiness, complete request time including
budget validation, generation time, first request and later requests. Its
`warm_summary` excludes the first request. Hash verification warms OS file pages
before server startup; this is not a filesystem-cold loading measurement.
Memory includes only the cleanup worker process tree. Native exports omit Core
dictionary-protection wrappers, so dictionary behavior must additionally pass
the integrated managed probe. Neither native timing nor worker memory alone
establishes the whole-application SLA.

Specialist literal masking is a separately labeled adapter experiment. Add
`--mask-specialist-literals true` to prompt export, and set
`"maskSpecialistLiterals": true` in an integrated model manifest to apply the
same opaque-token adapter while retaining the specialist's prompt format.
It defaults to false for specialists and is always active for general models.
General models retain the original `literal-token-v1` dictionary mask. The
specialist experiment uses `specialist-compact-v3`: first validate and hide Core
dictionary blocks, then replace each resulting literal token or paired
double-quoted span with a distinct 12-character identifier. A quote containing a
dictionary block is protected as one span. Straight double quotes and curly
double quotes are paired; an odd number of immediately preceding backslashes
escapes a quote. Unbalanced quotes and apostrophes remain ordinary text.

Identifiers are `FHX_` plus the first eight lowercase SHA-256 hex digits of the
UTF-8 string `ordinal:nonce:payload`. The zero-based encounter ordinal keeps
repeated equal phrases distinct; nonce starts at zero and increases only to
avoid a collision within the request. Both implementations reject the reserved
`FHX_` family in source text and require every returned identifier exactly once,
in source order, before restoring the original spans and Core dictionary blocks.
This reduces the shared prefix that a repetition-removing model could collapse
and protects verbatim quoted wording without teaching fixture-specific rules.

V3 adds one narrow restoration rule. If the original transcript ends, apart from
whitespace, with a paired protected quote whose last inner character is `.`, `?`
or `!`, a model-added single period immediately after the final opaque token is
removed when only whitespace follows it. Protected payload bytes are unchanged.
Original outside punctuation, inner or outside ellipses, added words, mid-sentence
quotes and unpunctuated quotes do not trigger the rule. This avoids rendering
`She said "Go.".` after restoring a terminal quote that already had its period.

Exports and native reports record `mask_literals` and `literal_mask_protocol`.
Each new exported case also records `model_input_sha256`; Python verifies that
its mask matches the managed export before sending any inference request. Frozen
initial specialist-mask exports without a protocol field retain the legacy v1
adapter on replay. Explicit `specialist-compact-v2` exports retain the compact
identifiers and verbatim quotes without V3's period rule; token IDs are identical
between V2 and V3. All three stages keep their own evidence. Restored bytes are
adapter preservation, rather than evidence that a model copied the original
literal correctly. Quotes are protected verbatim, so cleanup inside them is
deliberately unavailable in this experiment.

Sotto and ScribeKey prescribe `###` as a completion delimiter. Literal Markdown
or code containing that sequence can collide with the format or stop generation
early. Their native `word` stop status confirms a configured stop, rather than
semantic completeness. Such cases need separate literal coverage and integrated
fallback review before either model can be selected for unrestricted dictation.

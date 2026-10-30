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
That policy matches Freehand's local cleanup provider. The prompt difference is
recorded and is an intentional model-specific condition of the experiment.

## Read the results

- `report.json` records model/runtime/configuration/prompt/fixture hashes, selected
  IDs, failures, category summaries, complete-response times and memory scope.
- `outputs.jsonl` retains every actual output, raw response and automatic checks.
- `review.md` presents candidate labels for human comparison; `review-key.json`
  maps labels back to identities. Keep the key closed during initial review.
- Each candidate's server log is retained separately.
- Input corpus, prompt, configuration and normalization/probe report snapshots
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

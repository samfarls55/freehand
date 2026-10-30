# Transcript cleanup evaluation — October 30, 2026

Subsequent [small-model research](TRANSCRIPT-CLEANUP-SMALL-MODELS.md) reopens
production selection. References below to the selected Qwen model describe this
historical experiment and its pinned prototype; they do not establish the best
production candidate across the newly researched specialists.

This continuation started from checkpoint `6266be5` on `codex/transcript-cleanup`.
The [handoff](TRANSCRIPT-CLEANUP-HANDOFF.md) makes output quality the first
selection criterion. Earlier additional-memory and additional-delay limits do
not determine this experiment's winner.

## Method

Four complete GGUF artifacts were downloaded through the configured HTTPS proxy,
independently hashed, and run using the pinned llama.cpp b12015 CPU runtime.
The existing Core dictionary/English-number pipeline supplied the inputs,
reference targets and diagnostic assertions. The no-cleanup baseline contains
90 synthetic cases, each with exactly one recorded insertion. It has 47 normalized
example-target matches, 41 diagnostic failures and two review-required nonmatches.
Those counts describe cleanup opportunities, not speech recognition accuracy.

Initial development replay uses all 60 public synthetic cases for Quill and Qwen.
Observed question-answer failures motivated a shared JSON transcript envelope and
an explicit data-boundary instruction for general models. The revised protocol
uses the same frozen 24-case risk screen for Qwen, Ministral and Gemma; quality
finalists then receive the full development replay. Thirty additional cases remain
held out until model, precision, template, prompt and inference settings are frozen.
Targets are examples rather than the only faithful wording; all real outputs
receive separate agent review for meaning and readability. Automated assertions
can reject an equivalent number rendering or miss an invented continuation.
Review counts are agent judgments, not independent human-approved conversational
gold or a population quality estimate.

Each model runs alone with four CPU threads, zero GPU layers, 8,192 context
tokens, a 2,048-token output cap, greedy decoding, seed zero and prompt caching
disabled. Quill receives its publisher's minimal ChatML/empty-think contract;
the general models receive the canonical Freehand cleanup prompt and their
embedded chat templates with thinking disabled. In the revised protocol their
user message contains one compact JSON `transcript` field; the original
raw-message runs retain their original prompt and evaluator source snapshots. No prompt is tuned on held-out
outputs. Raw model returns, accepted Core results and fallbacks are scored
separately. Dictionary integration cases create actual per-job literal markers.

The cloud host reports AMD EPYC 9V74, five visible CPUs with a four-CPU cgroup
quota and a 16 GiB cgroup memory ceiling. There is no GPU. Native latency is
complete-response time, not first-token speed or key-release-to-Windows delivery.
Native memory samples cover the owned server process tree and exclude the UI,
ASR and observer. Linux private resident pages are not Windows private commit.
Development timings include concurrent acquisition and source validation;
final integrated measurements run without competing builds or model downloads.
Sampling itself adds overhead and can miss short peaks. No figure here establishes
Windows laptop memory, microphone accuracy, physical hotkey behavior or real
foreground text delivery.

## Artifact pins

| Candidate | Quantization | Weight bytes | Publisher revision | SHA-256 |
|---|---|---:|---|---|
| [quill-4b](https://huggingface.co/Quobi/Quill/resolve/4cc2cc3c8e7ea9ee69126becd55be23a3a949899/quill-4b-Q4_K_M.gguf) | Q4_K_M | 2,708,803,936 | `4cc2cc3c8e7ea9ee69126becd55be23a3a949899` | `e5e6bd7e92690c6f954399c473e740561d9deff0862e1bfe42c1f6055535b987` |
| [qwen35-9b](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/3885219b6810b007914f3a7950a8d1b469d598a5/Qwen3.5-9B-Q8_0.gguf) | Q8_0 | 9,527,502,048 | `3885219b6810b007914f3a7950a8d1b469d598a5` | `809626574d0cb43d4becfa56169980da2bb448f2299270f7be443cb89d0a6ae4` |
| [ministral3-8b](https://huggingface.co/mistralai/Ministral-3-8B-Instruct-2512-GGUF/resolve/0102285ad796bd99af90f58de616092e5630e970/Ministral-3-8B-Instruct-2512-Q8_0.gguf) | Q8_0 | 9,029,392,800 | `0102285ad796bd99af90f58de616092e5630e970` | `bd0ca58473b64618df4d08c1410cc25c910ca84e647833ebaf099e0fc0523b45` |
| [gemma4-e4b](https://huggingface.co/unsloth/gemma-4-E4B-it-GGUF/resolve/bfc15c382204943c3a8fff0c750b94ae2364d7a3/gemma-4-E4B-it-Q8_0.gguf) | Q8_0 | 8,192,953,472 | `bfc15c382204943c3a8fff0c750b94ae2364d7a3` | `f8854aa4480df62585a279e7ca0a881554fc18a41c59c4f62642d16a2ae47012` |

The GGUF files are not committed. Model cards and base license evidence were
retrieved at immutable revisions. Quill's Apache 2.0 declaration is in its card;
its repository has no standalone license, so its base Qwen license and publisher
card would be required when bundling it. Qwen's original Apache license is
available. The Mistral and Gemma 4 publisher cards declare Apache 2.0; this is
Gemma 4, not an assumption about earlier Gemma licensing. The selected acquisition
manifest retains required license texts and publisher attribution.

## Integration and distribution

The selected model remains a local, explicitly set up feature. A multi-gigabyte
GGUF cannot be assumed to fit the existing updater/GitHub installer limit of
2 GiB. Default packages therefore carry pinned acquisition metadata, and Settings
initiates a verified model/runtime download into the current profile. Dictated
text is never part of acquisition requests. Dictation remains usable while setup
runs; model selection takes effect through the idle preference gate. Existing
bundles survive failed or cancelled setup.

Core still applies dictionary corrections once, preserves replacement bytes and
order, and performs only the original single insertion. Incomplete responses,
worker failures, timeouts and literal corruption retain the normalized original.
The latest original remains copyable even when history is off. Structural checks
cannot prove semantic equivalence; a fluent wrong edit can still pass them.

Strict dictionary preservation rejects an edit that removes a superseded
clause containing a protected replacement. A model can instead retain the whole
correction narrative and pass validation. Both outcomes limit useful cleanup;
accepted unchanged intent is not evidence that Backtrack cleanup succeeded.

## Results

Initial raw-message development results (60 cases each):

| Candidate | Faithful | Fully acceptable | Median completion | Sample p95 | Peak server RSS |
|---|---:|---:|---:|---:|---:|
| Quill 4B Q4 | 47/60 | 45/60 | 3.79 s | 13.31 s | 8,482 MiB |
| Qwen3.5 9B Q8, original protocol | 55/60 | 52/60 | 12.97 s | 29.71 s | 10,117 MiB |

These development timings include competing acquisition/source validation and
memory sampling; they are descriptive, not controlled Windows benchmarks.

Quill answered the museum-hours question with an invented 5 PM closing time,
obeyed a quoted instruction by returning `Banana.`, and completed an unfinished
thought with invented troubleshooting steps. Qwen's original protocol also
invented museum hours and returned an assistant explanation to another dictated
question. It preserved unfinished thoughts better, but it was not safe to select
on target-match count alone. These observed failures motivated the revised data
boundary before any held-out inspection.

The final matched synthetic no-cleanup managed replay peaked at 74.06 MiB RSS in
the measured process tree (an earlier trial measured 73.45 MiB). This excludes
real ASR, desktop UI and physical input/delivery and must not be used as
Freehand's total application memory.

Durable public evidence is under [cleanup-evaluation/2026-10-30](cleanup-evaluation/2026-10-30/),
including actual raw responses, exact prompt/evaluator snapshots, normalization
reports, per-case review judgments and measurement scope.

The common revised JSON screen uses 24 cases, identical across general models:

| Candidate | Faithful | Fully acceptable plain text | Useful faithful edits / 11 needing cleanup | Median native completion | Peak server RSS |
|---|---:|---:|---:|---:|---:|
| Qwen3.5 9B Q8 | 22/24 | 18/24 | 7/11 | 18.66 s | 9,649 MiB |
| Gemma 4 E4B Q8 | 21/24 | 18/24 | 7/11 | 10.70 s | 8,157 MiB |
| Ministral 3 8B Q8 | 18/24 | 10/24 | 8/11 | 17.35 s | 9,833 MiB |

These screen timings overlap source validation to different degrees and are not
a controlled performance ranking. The final integrated run has no competing
builds, downloads or model jobs.

The usefulness column alone can hide unsolicited markup and meaning changes.
Qwen's two fidelity failures were protected literal contents. Gemma also doubled
actual Windows path separators outside protected blocks. Ministral removed
meaningful emphasis/discourse words, shifted a Sunday question to habitual
Sundays, and often added Markdown or an assistant preface. Contractions and
semantically equivalent wording were reviewed separately from those errors.

All three general models changed protected literal bytes. The final adapter
therefore replaces each complete protection block with one deterministic opaque
identifier, verifies exactly-once ordered survival, and restores the original
block in code before Core's own validation. Model output and restored provider
output are retained separately in native reports. The model receives no credit
for reproducing literal contents it never sees. Missing/reordered identifiers
still fail conservatively; the adapter does not invent or append missing values.

Both previously failing Qwen literal development cases pass with this adapter,
including tabs, repeated spaces, newline/indentation and currency whitespace.
The final model/prompt/adapter/configuration freeze is recorded before held-out
inference. Qwen3.5 9B Q8 is selected for this implementation on fidelity;
performance remains descriptive, following the user's priority.

Provisioning was exercised with the entire 9.53 GB model and real pinned Windows
runtime ZIP, streamed through the actual managed installer using a local HTTP
mirror of independently verified live publisher downloads. All model/runtime/
license checks and the complete inventory passed; a second install reused the
verified bundle without further requests. This is real-artifact staging/cache
verification. Windows binaries were not executed on Linux. The selected Linux
bundle was also prepared by the production acquisition script in offline mode,
using hard links to avoid redundant weight-file copies.

The final frozen Core development replay accepted all 60 provider returns, with
28 applied edits and 32 unchanged outputs. Every case recorded one insertion;
there were no fallback, timeout or operational errors. Agent review judged all
60 faithful, 54 fully acceptable, and 25/29 cases needing cleanup usefully edited;
23/29 were fully cleaned. Cases `dev-002`, `014`, `016`, `018`, `057` and `058`
retain some filler or spoken-correction framing. Automated example-target
matches increased from 31/60 without cleanup to 50/60, but that narrower measure
does not replace the semantic review.

The ten additional real dictionary-integration cases preserved every protected
replacement byte and recorded one insertion each. Nine received useful complete
cleanup. `integration-09` retained the superseded protected name and the explicit
correction to Priya, changing punctuation only. It was accepted, not a fallback,
and is counted as missed cleanup. `integration-01` also illustrates a small
presentation cost: the model adds a comma after protected trailing whitespace.
Those spaces are intentionally preserved by the dictionary contract.

The frozen held-out run accepted all 30 returns (16 applied, 14 unchanged), with
one recorded insertion each and no fallback or operational errors. Agent review
judged 29/30 faithful and 25/30 fully acceptable. Of 14 inputs needing cleanup,
13 received useful edits and 11 were fully cleaned. Automated example-target
matches increased from 16/30 to 24/30. The six managed assembly hashes exactly
match the pre-held-out freeze; no model, prompt, adapter or inference settings
were retuned after opening this split.

There is an actual accepted fidelity error: `hold-005` changes "very, very long
day" to "very long day", weakening intentional emphasis. Core's structural checks
do not catch it. Separately, `hold-018` adds unsolicited Markdown backticks around
an otherwise preserved code expression. Corrections in `hold-007` and `028`
retain redundant superseded alternatives, and `hold-030` leaves the correction
narrative unchanged. Thus successful validation and delivery are not equivalent
to faithful, complete plain-text cleanup. The selected model is the best observed
fidelity candidate in this experiment, with these measured first-pass limits.

Final integrated CPU measurements, with no competing builds or model downloads:

| Trial | Cases | Median cleanup | Nearest-rank p95 | Peak Core + native worker RSS |
|---|---:|---:|---:|---:|
| Development | 60 | 16.73 s | 34.33 s | 9,740.62 MiB |
| Real dictionary integration | 10 | 25.51 s | 36.26 s | 9,736.23 MiB |
| Held out | 30 | 17.07 s | 32.42 s | 9,907.03 MiB |

The first cold development/held-out cases took 26.68/27.51 s, including asset
verification and worker startup; different inputs prevent treating their
difference from the median as isolated startup cost. Maximum cleanup was
38.95/40.94 s respectively. The held-out sampled peak increased 9,832.97 MiB over
the matched 74.06 MiB no-cleanup probe. These remain Linux synthetic pipeline
measurements, with all scope exclusions above; 30 cases do not establish a
stable production p95.

## Verification and remaining work

The strict Release solution build passed with zero warnings/errors. The four
cross-platform .NET suites passed 408 tests: dictionary 25, Core 151, App 134 and
cleanup 98. After the final App-only bundled-button visibility change, the strict
solution build and all 134 App tests passed again. The Python evaluator/adapter
suite passed 26 tests, and the managed probe self-test passed. The complete
PowerShell suite passed 74 tests; after adding two Windows-preview Linux-bundle
rejection cases, all 12 affected preview tests passed. That is full-suite plus
focused coverage of the now-76 cases, not a claimed fresh full-76 run.

The real managed asset installer streamed and verified all selected Windows
artifacts through the documented local mirror; offline production-script Linux
bundle preparation also passed. A framework-dependent Linux single-file publish
of the actual application passed `--selftest` from `/tmp` with an isolated data
profile. It validated dictionary/storage round trips, model paths and the genuine
selected acquisition metadata. Its Windows platform, optional bundled cleanup
and real speech checks were skipped; no genuine ASR assets were present.
The accompanying validation evidence retains the exact scope. Windows native startup, the complete
Windows installer/update lifecycle, actual microphone/hotkey/foreground delivery
and Windows laptop memory/latency require Windows validation. No normal
installation update, push, PR, merge or public release was performed.

Follow-up quality work should retain these observed failures as regressions and
use a fresh held-out set for any revised policy. Optimize latency and memory
after establishing acceptable quality on real, consented dictations; this public
synthetic evaluation is not that evidence.

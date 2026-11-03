# Small-model transcript cleanup evaluation — November 3, 2026

**No tested candidate qualified as Freehand’s production default.** Small specialists substantially reduced cleanup cost, but both finalists made accepted meaning changes on the fresh frozen text test. S1-mini and Spokenly also failed subsequent validation. Windows whole-app performance remains unverified. The requested 15% allowance is **747,500,000 bytes of host memory** and **805 ms from release to complete text**; cleanup-only or Linux partial-pipeline results cannot certify either application limit.

Emberon-2 Q4 is the leading **resource candidate among the CPU finalists**, with a roughly 250 MB cleanup-worker footprint and lower latency than ScribeKey Q4 in the recorded development conditions. That makes it useful for further engineering, not a certified shipping recommendation. Its accepted water-source error alone prevents the required production-quality conclusion.

This round implemented the researched options, downloaded and independently verified 13 model artifacts, and actually ran 14 initial conditions. The [detailed baseline analysis](cleanup-evaluation/2026-11-03-small-models/baseline-results.md) contains every screen, seven full development comparisons, 21 resource profiles, eight prompt-lookup trials and eight corrected loading-mode trials. The main results below concern the frozen finalists and resulting application behavior.

## Implementation and reproducibility

Freehand now supports each specialist’s own input format instead of applying a large general-model prompt indiscriminately. This includes S1’s system/control line and empty thinking prefix, Handy’s separately tested renderer variants, Emberon’s short system instruction, BitVoice/Kudu/Localflow contracts, Spokenly’s raw `text:`/`out:` format, and ScribeKey/Sotto’s BOS-plus-`###` completion formats. Model-specific stops and sampling are explicit. The native path verifies rendered token IDs, handles BOS exactly once, rejects unsupported control input and incomplete responses, and checks complete input/output capacity before generation.

Specialist literal protocol v3 protects actual dictionary replacement blocks and paired double-quoted chunks behind distinct compact identifiers. It restores original bytes only after every identifier survives once and in order. A narrowly scoped boundary rule removes one model-added terminal period after an already punctuated final protected quote when the original ended at that quote. It does not edit the quoted payload or infer the speaker’s intended facts. Dictionary matching/normalization semantics remain unchanged; Core still validates the result and keeps original text on failure.

Context, batch/micro-batch sizes, thread counts, KV precision, repacking, prompt cache and checkpoint storage are bounded manifest settings. Optional `ngram-map-k` prompt lookup uses input text as draft material with bounded match/draft lengths and no extra draft weights. Native workers remain local, authenticated and isolated; inference does not download assets.

The final text comparison used context 1024, output cap 512, four threads, batch/micro-batch 64/32, no repacking, zero prompt-cache allowance and bounded prompt lookup. [The pre-run freeze](cleanup-evaluation/2026-11-03-small-models/metadata/final-candidate-freeze.json) records the exact models, manifests, managed assemblies and source hashes. The newly authored [40-case corpus](cleanup-evaluation/2026-11-03-small-models/fixtures/frozen-holdout.json) was frozen and hashed before inference. It contains 29 edit-needed and 11 no-edit cases, including six actual dictionary cases. No prompt, weight, sampler or adapter tuning followed inspection of these results.

## Fresh frozen finalist results

These runs exercised the real Core dictionary, number normalizer, cleanup provider, validation and single-delivery orchestration. A generated tone and canned transcript fed the engine; a recording injector counted calls. They did not exercise actual speech recognition, microphone capture, a physical key or foreground Windows insertion. Both models returned and delivered all 40 candidates without fallback, with exactly one recorded insertion each. Structural acceptance did not prevent semantic errors.

“Faithful” preserves facts, conditions, uncertainty, deliberate emphasis and quoted words. “Useful” counts a faithful beneficial edit; “fully cleaned” requires complete cleanup. “Acceptable” also requires directly usable plain text. All judgments are manual assistant reviews with visible identities, not blinded human sign-off. Example targets and automatic assertions are not semantic oracles.

| Fresh 40-case finalist | Faithful final text | Acceptable | Useful edits / 29 | Fully cleaned / 29 | Fallbacks |
|---|---:|---:|---:|---:|---:|
| [Emberon-2 Q4](cleanup-evaluation/2026-11-03-small-models/reviews/emberon-final-heldout-human-review.json) | 37/40 | 36/40 | 28 | 28 | 0 |
| [Derived ScribeKey Q4](cleanup-evaluation/2026-11-03-small-models/reviews/scribe-q4-final-heldout-human-review.json) | 36/40 | 35/40 | 27 | 27 | 0 |

Emberon changed **“Well water tastes different…” into “Water tastes different…”**, deleting a substantive source/type modifier as if it were filler. It also collapsed an explicitly intentional repeated “do not.” ScribeKey also deleted **“Well”** from the noun phrase and weakened deliberate repetition in two cases. Both errors passed Core and reached the selected output. Emberon missed one accidental repetition; ScribeKey retained a retracted dinner-reservation narrative rather than fully collapsing it.

A [separate adjudication overlay](cleanup-evaluation/2026-11-03-small-models/reviews/cross-model-012-adjudication-overlay.json) applies one conservative voice/precision policy to both models’ identical deletion of “literally” outside the protected quote. It counts that omission as a fidelity failure for both. The original ScribeKey reviewer’s lenient 37-faithful/36-acceptable totals remain unchanged in the source review; this report uses the aligned 36/35 totals. A uniformly lenient policy would instead give Emberon 38/37 and ScribeKey 37/36. Either policy retains both models’ unambiguous accepted water-source error and the same qualification outcome.

All 13 explicitly required literal spans survived for each model. Exact dictionary and quoted bytes restored by the adapter receive **code/Core credit**, not model copying credit. The [raw Core reports](cleanup-evaluation/2026-11-03-small-models/frozen-core) retain provider candidates separately from selected output; these provider candidates already include restoration, so they must not be described as raw generated tokens.

The ten pre-existing real-dictionary diagnostics are separate from the fresh corpus:

| Existing dictionary diagnostics | Returned faithful candidates | Faithful final text | Acceptable / 10 | Useful / 10 | Fallbacks |
|---|---:|---:|---:|---:|---:|
| [Emberon](cleanup-evaluation/2026-11-03-small-models/reviews/emberon-final-dictionary-human-review.json) | 9/9 returned | 10/10 | 8 | 9 | 1 |
| [ScribeKey Q4](cleanup-evaluation/2026-11-03-small-models/reviews/scribe-q4-final-heldout-human-review.json) | 9/9 returned | 10/10 | 9 | 9 | 1 |

Both failed the known superseded-protected-name case and kept the original explicit correction narrative. That is preserved fallback meaning, not successful cleanup. The probe reports `Processor:InvalidDataException` and no candidate; it does not expose enough raw response to assert the precise generation failure. Emberon also inserted a comma after protected trailing spaces in another case, creating an awkward boundary despite exact payload retention. Every case still had one counted insertion.

## S1-mini and Spokenly: exposed-corpus validation extension

After the finalist corpus had been exposed, S1-mini and Spokenly were evaluated with unchanged trained contracts and the existing v3 adapter. Their [extension freeze](cleanup-evaluation/2026-11-03-small-models/metadata/gpu-candidate-validation-freeze.json) precedes those runs. This is **post-holdout validation**, not fresh heldout evidence for the added models. All inference was CPU execution with zero GPU layers; the directory name does not establish GPU testing.

| Exposed 40-case validation | Faithful | Acceptable | Useful / 29 | Fully cleaned / 29 | Dictionary acceptable / 10 | Dictionary fallbacks |
|---|---:|---:|---:|---:|---:|---:|
| [S1-mini](cleanup-evaluation/2026-11-03-small-models/reviews/s1-postholdout-validation-human-review.json) | 37/40 | 37/40 | 28 | 28 | 7 | 2 |
| [Spokenly Cleanup-1](cleanup-evaluation/2026-11-03-small-models/reviews/spokenly-postholdout-validation-human-review.json) | 35/40 | 28/40 | 20 | 18 | 9 | 1 |

S1 inserted the noun-changing comma in “Well, water,” weakened deliberate prohibition emphasis, and turned **“Reserve a table…, scratch that, ask…” into two active instructions**, reactivating the cancelled reservation. Spokenly retained obsolete actions after removing correction cues, weakened negation/correction handling and deleted an intentional numerical contrast. All 40 candidates from each model were structurally accepted and inserted once; that acceptance is not proof of clean meaning. Its `Applied` statuses also reflect leading spaces, not necessarily useful edits.

The [S1 dictionary review](cleanup-evaluation/2026-11-03-small-models/reviews/s1-postholdout-dictionary-human-review.json) records two unreturned candidates and the protected-whitespace comma defect. The [Spokenly dictionary review](cleanup-evaluation/2026-11-03-small-models/reviews/spokenly-postholdout-dictionary-human-review.json) records one fallback. No unobserved raw failure cause is inferred. Larger specialists’ CPU memory costs do not establish how host RAM, VRAM or speed would behave under GPU offload.

## Speed and memory evidence

The execution host was Linux on an AMD EPYC 7763 with a four-CPU quota and 16 GiB memory limit, not the earlier October host or the target Windows laptop. Memory values below use decimal MB. Native measurements include only the owned cleanup worker; they exclude the speech worker, evaluator and desktop UI.

Final v3 development ran all 60 cases with prompt lookup off and on for both CPU finalists. Every raw model string, restored output and status matched across the two conditions for each model. The narrow quote-period correction changed provider presentation, not raw model fidelity. Source versions and adapter credit remain visible in the [final development evidence](cleanup-evaluation/2026-11-03-small-models/final-development).

| Final native development | Lookup | Warm p50 / p95 ms | Cleanup peak MB |
|---|---|---:|---:|
| Emberon Q4 | Off | 199.9 / 914.8 | 249.6 |
| Emberon Q4 | On | 194.1 / 893.7 | 254.0 |
| ScribeKey Q4 | Off | 218.7 / 1013.9 | 288.0 |
| ScribeKey Q4 | On | 226.3 / 941.5 | 296.9 |

These mixed-length, single-pass development percentiles are not whole-app acceptance metrics. Lookup modestly changed costs on this host and preserved observed outputs; it does not promise a universal speedup. The locally derived Scribe Q4 also matched publisher Q8 output on all 60 v2 development cases, while reducing its worker peak substantially. That equality does not establish equivalence on unseen language or longer contexts.

The [final repeated actual-ASR reports](cleanup-evaluation/2026-11-03-small-models/final-closed-loop/summary.json) completed all 25 planned trials under the frozen evaluator: five cleanup-disabled controls, ten Emberon and ten ScribeKey trials. The pinned speech worker, Core and optional cleanup ran sequentially. Each trial retained the same 22-word recognized public JFK text and recorded one delivery call; all 20 cleanup outcomes were `Unchanged`, with no provider failure or fallback. This establishes preservation of that clean clip, not beneficial cleanup on varied speech.

| Final actual-ASR condition | N | Transcript-ready p50 / p95 ms | Counting-complete p50 / p95 ms | Simultaneous peak MB | Complete trials >805 ms |
|---|---:|---:|---:|---:|---:|
| Cleanup disabled | 5 | 304.9 / 410.0 | 304.9 / 410.3 | 432.5 | 0/5 |
| Emberon Q4 | 10 | 714.6 / 910.9 | 722.5 / 910.9 | 717.8 | 2/10 |
| ScribeKey Q4 | 10 | 697.9 / 766.3 | 705.0 / 766.5 | 771.9 | 0/10 |

**Neither CPU finalist met both numerical limits even on this partial path.** Emberon exceeded 805 ms twice. ScribeKey stayed below the sampled time limit but exceeded 747,500,000 bytes. At the actual simultaneous memory peaks, Emberon comprised 84,721,664 evaluator-host bytes + 378,634,240 speech-worker bytes + 254,427,136 cleanup-worker bytes. ScribeKey comprised 95,236,096 + 378,896,384 + 297,775,104 bytes. These are simultaneous snapshots, not independently peaked components added together.

The 100 Hz counter records the largest observed simultaneous snapshot across monitor windows. The path includes evaluator, ASR and cleanup and excludes Avalonia desktop UI, microphone/physical key, actual `SendInput`, Windows memory accounting and GPU telemetry. Initial ASR loading (about 1.2–1.5 seconds) and cleanup synthetic warmups (509 ms Emberon; 650 ms ScribeKey) were separate. An evaluation-only one-hour cleanup idle override kept workers ready. Repeated identical audio and N5/N10 nearest-rank p95 values—which equal the maximum—do not establish a stable field tail or cold/idle guarantees.

Raw diagnostics also retain process CPU and host GC measurements. Across candidate trials, post-trial host managed heaps were about 3.6–8.9 MB, with at most 10.6 MB committed at the last recorded GC. ASR consumed about 40–320 CPU-ms during cleanup; cleanup consumed 1,130–1,620 CPU-ms across its four threads. These CPU times aggregate work and are not additive wall-time components. Managed-heap measurements do not account for the native worker working sets. The earlier observer and session-option experiments remain in the baseline analysis; the ASR model, dependency and four-thread pins remained unchanged. No result here proves a Windows whole-app pass.

## Windows and packaging readiness

The pinned b12015 Windows Vulkan archive was independently verified and complete bundle inventories preserve native dependencies. Preview selection discovers the unique NVIDIA adapter using `--list-devices`, then passes the exact returned `VulkanN` backend name through process-local `LLAMA_ARG_DEVICE`. It does not guess a physical ordinal or assume `Vulkan0` is the RTX device. Ambiguous/malformed discovery fails explicitly. See the [device-selection audit](cleanup-evaluation/2026-11-03-small-models/metadata/windows-vulkan/device-selection-audit.md). Selection and archive verification do not prove driver availability, actual offload or measured performance.

The desktop qualification tool now supports `--desktop-delivery-benchmark OUTPUT --include-cleanup`. It measures real desktop/ASR/cleanup behavior and completed `SendInput` receipt in an owned Windows field, samples all process roles, and records model/configuration identity, cold/idle/recovery results and GPU telemetry. It rejects absent cleanup, fallback and configuration drift. Diagnostic modes cannot stand in for full acceptance. Its cleanup gates use 747,500,000 bytes and 805 ms; missing GPU evidence prevents full qualification. [Windows qualification instructions](cleanup-evaluation/2026-11-03-small-models/windows-qualification.md) describe its scope. No Windows execution or target GPU measurement was available here.

The historical Qwen9B acquisition pin remains unchanged; it is a preserved prototype artifact, not a newly certified default. Small-model profiles are integrated through explicit verified custom bundles. No failed candidate was promoted merely to populate a default. Emberon/Scribe inherit the conditional LFM Open License, and Scribe’s derivative requires **“Derived from ScribeKey Fast by ScribeKey”** attribution plus upstream notices. Its local Q4 is not a publicly hosted publisher download. S1 attribution uses **“S1-mini by Superwhisper.”** Prepared inventory/notice evidence does not waive these terms.

The isolated preview is retained as `work/cleanup-small-models-2026-11-03/cleanup-windows-preview.zip` (679,981,268 bytes, SHA-256 `7e090ee3c1e5678df270e5dc90ff359489dafebd48b5e437f99112a587ef9344`). All 327 archive members were checked against the prepared inventory. Its launcher creates a separate profile for every run and includes both CPU and NVIDIA Vulkan experiments. The portable source/evidence transfer is `work/cleanup-small-models-2026-11-03/cleanup-small-models-handoff.tar.gz`, with a checksum sidecar and a transfer manifest recording the source commit. These workspace artifacts are separate from Git; archive integrity does not establish Windows execution or model qualification.

## Verification and remaining work

The latest source Release build passed with zero warnings/errors. The affected .NET suites passed: App 170, Cleanup 239, Dictionary 25 and Core 151—585 tests in total. All 112 regular PowerShell tests passed; Python evaluation tests passed 57. These checks verify implementation/regression behavior, not semantic correctness on arbitrary dictation or physical Windows performance. The framework-dependent Linux single-file publish was launched from `/tmp` with an isolated profile and passed `--selftest`: dictionary behavior, history/settings storage, absolute speech-model discovery and bundled acquisition metadata. Windows platform/native capture and the absent cleanup bundle were explicitly skipped; this smoke check is separate from the actual model inference above. Windows App/Probe cross-publishes and PE checks succeeded, with the reflected Windows platform assembly explicitly staged; no Windows executable was run.

This work changed source and research evidence. It did not update the normal installation, push a branch, open a PR, merge or publish a release.

Qualification still requires semantic fidelity improvements followed by a genuinely new frozen corpus after any tuning, plus numeric testing on the actual Windows machine with complete desktop and GPU accounting. The existing failed candidates and their exact outputs remain reviewable. Until both quality and whole-app resource gates are established, there is no defensible optimal production choice to install automatically.

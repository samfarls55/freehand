# Small-model baseline results — November 3, 2026

This document summarizes completed development and resource experiments before final frozen qualification. Small task-specific models produced substantially lower cleanup-stage memory and latency than the historical 9B prototype, while exposing literal, punctuation, grammar and correction-coverage limits. These results do **not** establish a production selection or a Windows whole-app SLA pass. Later adapter or qualification stages must retain their own source freezes and results.

The requested 15% limits are **747,500,000 bytes of whole-app host memory** and **805 ms from release to complete text**. All memory columns below use decimal MB (1 MB = 1,000,000 bytes); source JSON retains exact bytes. Native timing means a complete local cleanup response, including the replay adapter, rather than first token or physical text insertion.

The November 3 machine was Linux x64 on an **AMD EPYC 7763**, with a four-CPU cgroup quota and 16 GiB memory limit, running CPU inference. See the [profile/source freeze](metadata/profile-source-freeze.json). This is a different execution host from the earlier October 30 experiment; cross-date timings are not a matched hardware comparison. No result here measures the user’s Windows laptop, microphone, physical key or `SendInput` delivery.

The [collection catalog](collection-manifest.json), [evidence hash index](evidence-files-sha256.json), [artifact metadata](metadata/asset-index.json) and [exact prompt exports](prompts) preserve provenance. This analysis links existing curated snapshots rather than duplicating their full pin and source inventories.

## How to read quality and timing

All inputs in the quality comparisons are public synthetic development examples. Every output received an assistant’s manual meaning/readability review, recorded under [reviews](reviews); these are agent judgments with visible candidate identities, not blinded human sign-off or population accuracy estimates. Automatic assertions and target similarity are diagnostics, not semantic proof. Example targets are not the only faithful wording.

- **Faithful** retains intended facts, uncertainty, negation, meaningful emphasis, quoted words, speech act and required literal bytes. A faithful transcript copied inside JSON or commentary can pass meaning while failing presentation. Describing or answering a dictated question instead of returning it fails meaning.
- **Useful** is a faithful edit that addresses a real cleanup defect; partial improvements can count. **Fully cleaned** resolves all material defects. **Acceptable** also requires clean, directly usable plain text. Retained correction cues, grammar errors, malformed punctuation and unsolicited wrappers prevent full acceptance.
- The 24-case screen contains **11 edit-needed** and **13 no-edit** cases. Each 60-case development run contains **29 edit-needed** and **31 no-edit** cases. A good unchanged result on a no-edit case is valuable; unchanged defective input is missed coverage.
- A provider failure has no delivered provider text to judge: its fidelity is unassessed, not a pass. Known raw token destruction is recorded separately. Original-text fallback, where actually tested by Core, is distinct from successful cleanup. Native experiments do not imply a Core acceptance or insertion result.
- Native memory is sampled for the owned cleanup-server process tree, excluding replay harness, speech worker and desktop UI. Linux working-set sums can double-count shared pages and are not Windows private commit. Artifact hashing warms filesystem pages before startup; first inference is not a filesystem-cold load.

Warm native p50/p95 exclude the first request and any request without a completed provider return. This means 23 timings in each screen, 59 in a successful 60-case run, and fewer in runs with adapter failures; return counts remain visible. Nearest-rank p95 on these small, mixed-length development sets is descriptive rather than an estimate of ordinary-user latency.

Review judgments have explicit boundaries. Handy’s `dev-042` paraphrase from “Could you explain why…” to “Why did…” was conservatively adjudicated as retaining the causal question; the earlier stricter judgment remains in the [audit](reviews/handy-human-review.json). The user-only renderer’s [review audit](reviews/handy-user-human-review.json) makes the same adjustment. The two renderer outputs match on **23/24 cases**; only the broken literal output in `dev-044` differs. Their 14-versus-12 acceptable totals therefore reflect differing judgments about terminal periods on unfinished fragments, not an established renderer-quality advantage. Later 60-case reviews treat terminal punctuation without an invented completion as benign. S1’s omitted “exactly” and residual “I initially said” wording are also called out for adjudication in the per-case notes. Keep those boundaries visible when comparing totals.

## Initial native screen: 13 artifacts, 14 conditions

All 14 conditions completed all 24 requests: **336 actual native returns**. Handy’s empty-system and user-only renderers are separate conditions for one downloaded model. The initial specialist conditions use their trained raw contracts without specialist literal masking. The three generic controls use the general instruction/JSON-input contract and its literal adapter. Thus literal preservation and wrapper behavior must be interpreted under each recorded contract, not treated as prompt-independent weight rankings.

All screen profiles used context 2048, output cap 512, four threads, batch/micro-batch 128/128 and host prompt-cache limit zero. Each linked model name opens its native report; corresponding named review JSONs provide every judgment.

| Condition | Returns | Faithful / 24 | Acceptable / 24 | Useful / 11 needed | Warm p50 ms | Warm p95 ms | Cleanup peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|
| [S1-mini Q4](screen/s1/report.json) | 24/24 | 22 | 21 | 10 | 555.0 | 1445.4 | 1008.0 |
| [Emberon-2 Q4](screen/emberon/report.json) | 24/24 | 22 | 20 | 9 | 208.1 | 618.1 | 404.9 |
| [HandyEditor Q4, empty system](screen/handy/report.json) | 24/24 | 20 | 14 | 9 | 184.0 | 429.5 | 441.9 |
| [HandyEditor Q4, user only](screen/handy-user/report.json) | 24/24 | 20 | 12 | 9 | 170.6 | 411.9 | 441.4 |
| [BitVoice Smol360, published GGUF](screen/bitvoice/report.json) | 24/24 | 15 | 14 | 6 | 657.2 | 1352.7 | 425.0 |
| [Kudu Tiny IQ4_XS](screen/kudu/report.json) | 24/24 | 22 | 18 | 7 | 457.0 | 1337.9 | 489.9 |
| [Localflow Clean Q4](screen/localflow/report.json) | 24/24 | 22 | 18 | 7 | 487.4 | 2168.3 | 655.5 |
| [Spokenly Cleanup-1 Q8](screen/spokenly/report.json) | 24/24 | 23 | 20 | 9 | 349.6 | 1413.8 | 944.6 |
| [ScribeKey Fast v1.1 Q8](screen/scribe/report.json) | 24/24 | 22 | 19 | 9 | 260.5 | 726.3 | 454.1 |
| [Sotto Q4](screen/sotto/report.json) | 24/24 | 22 | 15 | 7 | 186.7 | 706.8 | 441.5 |
| [LFM2.5 230M Q4, generic](screen/lfm230/report.json) | 24/24 | 13 | 0 | 0 | 620.2 | 1009.8 | 307.9 |
| [Granite 4.0 H350M Q4, generic](screen/granite350/report.json) | 24/24 | 17 | 7 | 5 | 808.9 | 1402.9 | 449.6 |
| [SmolLM2 135M Q4, generic](screen/smol135/report.json) | 24/24 | 23 | 0 | 1 | 525.7 | 1130.4 | 205.6 |
| [SmolLM2 135M Post-ASR Q4](screen/smol-post-asr/report.json) | 24/24 | 0 | 0 | 0 | 254.7 | 461.3 | 206.6 |

The failures were concrete. BitVoice invented endings for unfinished thoughts and dropped the corrected Wednesday schedule. Granite retained an obsolete day, reversed renewal negation, and answered a dictated question with an invented cause. The Post-ASR artifact invented email senders, shortcuts, a replacement URL and other content. LFM230 returned commentary/refusals; generic Smol135 mostly copied the input into JSON with little cleanup. These are results for the tested artifacts/contracts, not proof that every precision, retraining or alternate prompt in a family would fail.

The [Post-ASR contract audit](reviews/smol-post-asr-contract-audit.json) checked all 24 native-reported prompts against the publisher’s raw ChatML/system format and advertised `clean_punctuate` task. It found no implementation mismatch. The publisher worked examples demonstrate other tasks, so the observed clean-task failure should remain scoped to this exact condition. All raw specialist candidates damaged at least one protected-literal case; apparent fluent text alone was insufficient for dictionary integration.

## First literal adapter and compact resource profile: four full development runs

The next condition used context 1024, output cap 512, four threads, batch/micro-batch 64/32, no weight repacking and zero prompt-cache limit. Synthetic marked literal spans were hidden behind the earlier long opaque identifiers. The 60 examples broadened the screen to all existing development cases. Changing both protection and resource profile means this stage is not an isolated weight-quality comparison against the raw screen.

| Condition | Provider returns / 60 | Faithful returned | Acceptable / 60 | Useful / 29 | Fully cleaned / 29 | Warm p50 / p95 ms | Cleanup peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|
| [S1-mini Q4](masked-development/s1/report.json) | 60 | 59 | 55 | 26 | 24 | 595.6 / 2275.3 | 671.5 |
| [Emberon-2 Q4](masked-development/emberon/report.json) | 59 | 58 | 52 | 25 | 23 | 202.2 / 914.1 | 249.8 |
| [HandyEditor Q4](masked-development/handy/report.json) | 58 | 50 | 33 | 23 | 14 | 177.9 / 1053.7 | 286.8 |
| [ScribeKey Fast v1.1 Q8](masked-development/scribe/report.json) | 59 | 59 | 51 | 26 | 21 | 255.4 / 1319.0 | 435.2 |

S1 returned all 60, but dropped “exactly” from the precision instruction in `dev-035`; its [review](reviews/s1-masked-development-human-review.json) records the explicit omission and a possible more lenient adjudication. S1 also left one grammar error and missed filler cleanup in `dev-002`. Its cleanup-server memory alone was 671,531,008 bytes under this profile, leaving no demonstrated whole-app budget.

Emberon deleted “like” inside a quotation (`dev-043`). Emberon and Scribe each dropped the first of two similar long literal identifiers (`dev-044`); the adapter rejected the output. Their missing provider returns receive no success credit. Handy had two adapter failures and eight unfaithful returned outputs, including loss of the report-only restriction in `dev-019`. See the [Handy review](reviews/handy-masked-development-human-review.json) rather than inferring fidelity from its low median.

Emberon left four agreement errors (`027`, `028`, `047`, `049`); Scribe left three (`027`, `028`, `049`) and introduced residual comma defects. All four retained partial late corrections in `057` or `058`. The phrase “I initially said…Wednesday” is recorded as awkward residual historical framing, while the separate Alex-instead-of-Jordan correction remains understandable but uncollapsed. Useful partial edits do not count as fully cleaned.

## Compact identifiers and quoted-span protection: three full development runs

Version 2 replaced similar long identifiers with distinct compact ones and protected paired quoted chunks generally. It used development examples to address the observed literal and quoted-word failures. The [exports](masked-v2-prompts) and raw responses show exactly what the model saw. Every protected quote or dictionary payload was restored from original bytes only after identifier checks; those preserved inner bytes are **code-restoration credit**, not model copying accuracy.

| Condition | Returns / 60 | Faithful returned | Acceptable / 60 | Useful / 29 | Fully cleaned / 29 | Warm p50 / p95 ms | Cleanup peak MB |
|---|---:|---:|---:|---:|---:|---:|---:|
| [Emberon-2 Q4](masked-v2-development/emberon/report.json) | 60 | 60 | 52 | 25 | 22 | 193.7 / 922.6 | 249.4 |
| [ScribeKey Fast v1.1 Q8](masked-v2-development/scribe-q8/report.json) | 60 | 60 | 50 | 26 | 20 | 270.8 / 1271.9 | 435.0 |
| [Locally derived ScribeKey Q4](masked-v2-development/scribe-q4/report.json) | 60 | 60 | 50 | 26 | 20 | 217.8 / 1022.8 | 288.3 |

All 180 provider returns passed this manual fidelity review and identifier checks. The change fixed the caught missing-literal return and preserved the quoted “like” by deterministic protection. It also exposed a general punctuation boundary defect: the model appended a period after an opaque quoted sentence that already contained a period, producing `.".` on restoration (`dev-039`, `dev-040`). Both outputs are faithful but fail clean-text acceptance. Grammar and long-range correction misses remained. The [Emberon v2 review](reviews/emberon-v2-development-human-review.json) and [Scribe v2 review](reviews/scribe-q8-v2-development-human-review.json) separate these defects from semantic errors. A later punctuation fix is a new implementation condition and must not rewrite this v2 evidence.

The locally derived Scribe Q4 and publisher Q8 trials had **identical normalized inputs, raw output strings, restored outputs, statuses, rendered prompt hashes and input token IDs on all 60 cases**. The profile and managed assembly hashes also matched. Their [comparison audit](reviews/scribe-q4-v2-development-human-review.json) records the equality and conversion source. This establishes no observed quality difference on this development set; it does not prove equivalence on fresh text or longer contexts. Q4 reduced the recorded cleanup-only peak from 434,950,144 to 288,276,480 bytes. The Q4 was derived from verified source weights, not requantized from Q8; [conversion evidence](conversion) retains the method and metadata audit. It is not an available publisher-hosted Q4 download.

## Twenty-one controlled resource profiles

Three models each ran seven sequential profiles, with five fixed development cases repeated three times: **21 completed runs and 315 requests**. The [plan](metadata/resource-profile-plan.json) identifies cases and exact settings; its initial `prepared_not_run` status is historical preparation metadata, superseded by the completed reports. Each row below changes the setting stated from the preceding row. The batch-64 step changes logical and physical batch bounds together and is explicitly a coupled condition. All use output cap 512, f16 KV, zero host prompt-cache limit and no context shifting.

Each cell is **cleanup peak MB; warm p50 / p95 ms**. Fourteen warm requests per condition mix short and long examples; nearest-rank p95 equals the observed maximum at this sample count. None of these stage measurements includes ASR or UI.

| Profile | Emberon-2 Q4 | S1-mini Q4 | Scribe Q8 |
|---|---:|---:|---:|
| 2048 context, repack, batch 128/128, 4 threads | [404.9; 184.7 / 974.8](resource-native/emberon/p00-baseline/report.json) | [1007.5; 540.1 / 2200.1](resource-native/s1/p00-baseline/report.json) | [453.1; 249.4 / 1270.7](resource-native/scribe/p00-baseline/report.json) |
| Context 1024 | [392.8; 192.3 / 908.9](resource-native/emberon/p01-context1024/report.json) | [890.4; 547.1 / 2066.1](resource-native/s1/p01-context1024/report.json) | [440.9; 256.9 / 1307.6](resource-native/scribe/p01-context1024/report.json) |
| Disable repack | [255.2; 194.8 / 947.6](resource-native/emberon/p02-no-repack/report.json) | [677.2; 506.8 / 2098.6](resource-native/s1/p02-no-repack/report.json) | [440.5; 236.3 / 1295.2](resource-native/scribe/p02-no-repack/report.json) |
| Batch 64/64 | [252.2; 195.0 / 973.7](resource-native/emberon/p03-batch64/report.json) | [673.6; 517.2 / 2066.9](resource-native/s1/p03-batch64/report.json) | [437.1; 240.3 / 1278.4](resource-native/scribe/p03-batch64/report.json) |
| Micro-batch 32 | [249.9; 196.6 / 984.1](resource-native/emberon/p04-ubatch32/report.json) | [671.7; 565.2 / 2227.4](resource-native/s1/p04-ubatch32/report.json) | [434.7; 252.8 / 1305.1](resource-native/scribe/p04-ubatch32/report.json) |
| 2 threads | [248.5; 303.1 / 1449.8](resource-native/emberon/p05-threads2/report.json) | [670.3; 878.2 / 3273.0](resource-native/s1/p05-threads2/report.json) | [434.8; 392.5 / 1943.0](resource-native/scribe/p05-threads2/report.json) |
| 1 thread | [248.3; 508.0 / 2282.3](resource-native/emberon/p06-threads1/report.json) | [669.8; 1540.4 / 5179.0](resource-native/s1/p06-threads1/report.json) | [434.9; 667.8 / 3297.6](resource-native/scribe/p06-threads1/report.json) |

Context reduction and disabling repacking produced material measured memory savings for Emberon and S1. Smaller batches saved a few more MB. Scribe Q8’s repacking toggle had little effect in this sequence. Reducing threads to two or one saved little memory and materially increased completion time on this host. These adjacent resource comparisons do not establish new output quality; the full development reviews above provide that evidence. The prompt-cache limit was already zero in every profile, so these results do not show that an 8 GiB default cache had previously been reserved or caused historical RSS.

## Matched public-ASR text: prompt lookup and loading modes

These experiments replayed the same recognized 10-second JFK text, rather than comparing a short synthetic sentence with a longer ASR output. Each of two candidates ran four conditions, five repetitions each. The [input snapshot](metadata/actual-asr-text-performance-fixtures.json) and [prompt exports](actual-asr-text-prompts) preserve the exact words. This stage is still text-only: it does not run speech recognition or delivery. All five outputs for a candidate matched across its four prompt-lookup conditions, and separately across its four corrected loading-mode conditions. Repetition of one sentence measures hardware/runtime variation, not independent text quality.

Prompt lookup uses the input as draft material and loads no extra draft weights. The [eight reports](speculation-native) compare none, `ngram-simple`, `ngram-map-k` and `ngram-mod` under the same compact profile. Cells show warm p50 / p95 ms and cleanup peak MB; only four warm timings remain after first request.

| Prompt lookup | Emberon-2 Q4 | Scribe Q4 |
|---|---:|---:|
| none | [331.6 / 350.6; 249.4](speculation-native/emberon/none/report.json) | [381.4 / 391.1; 287.4](speculation-native/scribe-q4/none/report.json) |
| ngram-simple | [374.7 / 409.7; 252.6](speculation-native/emberon/ngram-simple/report.json) | [381.0 / 396.9; 295.5](speculation-native/scribe-q4/ngram-simple/report.json) |
| ngram-map-k | [296.5 / 326.7; 253.6](speculation-native/emberon/ngram-map-k/report.json) | [341.3 / 356.3; 297.3](speculation-native/scribe-q4/ngram-map-k/report.json) |
| ngram-mod | [395.5 / 400.4; 269.5](speculation-native/emberon/ngram-mod/report.json) | [424.3 / 439.4; 312.5](speculation-native/scribe-q4/ngram-mod/report.json) |

`ngram-map-k` had lower median and maximum in this small matched sample, while the other modes gave little benefit or were slower. The run is too small to promise a general speedup or adopt a default on its own; memory overhead and longer-output behavior still need qualification. Its observed output equality provides no separate semantic-quality improvement.

The first loading-mode experiment supplied `--no-mmap`, which this pinned runtime rejects. **Six attempts failed during CLI startup with zero inference rows**. Their [terminal diagnostics](diagnostics/mmap-initial-invalid-cli) are retained; these are invalid experiment configurations, not model-quality failures or no-mmap performance results. Two mapped baseline conditions in that initial stage did run. The corrected [eight-condition series](loadmode-native) used the supported `--load-mode none` spelling, with all five requests completed in every condition.

| Corrected loading condition | Emberon-2 Q4 | Scribe Q4 |
|---|---:|---:|
| Repack, mapped, batch 128/128 | [303.0 / 307.7; 387.7](loadmode-native/emberon/repack-mmap-b128/report.json) | [348.9 / 351.0; 426.5](loadmode-native/scribe-q4/repack-mmap-b128/report.json) |
| Repack, load mode none, batch 128/128 | [322.0 / 330.3; 251.1](loadmode-native/emberon/repack-no-mmap-b128/report.json) | [338.8 / 348.0; 288.8](loadmode-native/scribe-q4/repack-no-mmap-b128/report.json) |
| Repack, load mode none, batch 64/32 | [356.5 / 512.7; 249.8](loadmode-native/emberon/repack-no-mmap-b64u32/report.json) | [347.8 / 357.4; 287.7](loadmode-native/scribe-q4/repack-no-mmap-b64u32/report.json) |
| No repack, load mode none, batch 64/32 | [331.2 / 347.8; 249.7](loadmode-native/emberon/no-repack-no-mmap-b64u32/report.json) | [364.7 / 374.5; 287.8](loadmode-native/scribe-q4/no-repack-no-mmap-b64u32/report.json) |

The corrected no-mapping conditions had much lower sampled resident peaks than the repacked/mapped condition in this series, with different startup and completion costs. Those are actual stage observations, not a claim about Windows committed memory or a universally optimal loading mode. The independently phased short runs and four warm samples do not support precise latency improvement percentages.

## Actual pinned ASR plus Core and cleanup

The [actual-ASR replay](actual-asr/whole-pipeline-batch-summary.json) used production-pinned CPU Parakeet TDT 110M through native sherpa-onnx 2.0.0, with its four-thread configuration. Public JFK-derived audio was replayed at recording speed into the real speech worker and Core orchestration. The positional App executable was a provenance reference; a portable Linux research worker handled speech. A counting injector recorded one delivery call but did not type. The sampled simultaneous sum includes evaluator, speech worker and cleanup worker, **excludes desktop UI**, and can count shared pages twice. Initial ASR loading and synthetic cleanup warmup are separately recorded; cleanup had an evaluation-only one-hour idle override.

Under the original 200 Hz process-based observer, the repeated 10-second audio produced these results. Complete time is release to counting-injector completion, not visible Windows insertion. Tail values at N5/N10 equal the maximum.

| Original observer condition | N | Complete p50 / p95 ms | Partial-pipeline peak MB | Cleanup outcome |
|---|---:|---:|---:|---|
| [Cleanup disabled](actual-asr/whole-pipeline-baseline-10s-r5.json) | 5 | 276.7 / 382.2 | 410.6 | Disabled throughout |
| [Emberon compact](actual-asr/whole-pipeline-emberon-compact-10s-r10.json) | 10 | 728.4 / 857.3 | 737.2 | Unchanged throughout |

The Emberon observation exceeded the 805 ms requested allowance even before adding desktop UI and real delivery; its 737,173,504-byte partial-pipeline peak was below the 747,500,000-byte whole-app limit but left no demonstrated UI/platform headroom. The report’s empty operational `Failures` list does not turn this into an SLA pass. The repeated public audio always returned the same text; that is preservation of one already clean recognition, not proof of beneficial cleanup on varied speech.

The original longer stress trials also remain visible: [30/60-second Emberon replay](actual-asr/whole-pipeline-emberon-compact-30s-60s.json) returned `CleanupOutcome: Failed` on both and fell back, taking 4,830.2 and 5,452.2 ms through counting completion. Peak simultaneous memory was 774,242,304 bytes. Those artificial repetitions are stress inputs, not ordinary dictation gold; each duration has only one trial and no reliable tail estimate. Preserved fallback text earns no model-cleanup success credit. The matching [cleanup-disabled observations](actual-asr/whole-pipeline-baseline-30s-60s.json) remain separate.

### Observer and speech-session controls

A newer 100 Hz observer caches `/proc/PID/statm` handles, tracks worker generations and avoids repeated allocating process refreshes. Four fresh-process N1 controls used the same 10-second public audio, frozen v2 cleanup dependency and no prompt lookup. These are measured controls, not a final repeated acceptance distribution. See the [plan](actual-asr/observer-controls/plan.json), [raw results](actual-asr/observer-controls/summary.json), [compiled-source evidence](actual-asr/observer-controls/source-evidence.json) and [memory analysis](actual-asr/observer-controls/analysis.json). The preserved v2 dependency is not silently relabeled as later v3 source; JFK has no protected quoted/dictionary spans.

The baseline was repeated after the two research-only session variants to bracket variation. All four returned the same final text as ASR, outcome `Unchanged`, with one counting-injector call and no provider failure. Memory below is the largest actually observed simultaneous snapshot across independently phased whole-run and trial monitors. It is not a sum of separate component maxima; raw reports retain both monitoring windows.

| New observer condition | N | Transcript-ready ms | Counting-complete ms | Partial-pipeline peak MB | Cleanup ms |
|---|---:|---:|---:|---:|---:|
| [Unchanged ASR baseline](actual-asr/observer-controls/a-baseline.json) | 1 | 717.8 | 718.1 | 609.7 | 359.0 |
| [Force spinning stop](actual-asr/observer-controls/b-force-stop.json) | 1 | 783.9 | 784.1 | 627.0 | 360.0 |
| [Disable intra/inter-op spinning](actual-asr/observer-controls/c-no-spinning.json) | 1 | 790.0 | 790.3 | 625.2 | 387.1 |
| [Unchanged ASR baseline repeat](actual-asr/observer-controls/d-baseline-repeat.json) | 1 | 751.8 | 752.0 | 622.9 | 375.6 |

The two unchanged-config controls were approximately **718/752 ms** and **609.7/622.9 MB** for this partial path. Their proximity to the numerical limits is useful evidence for further measurement, but N1 has no p95 precision and omits desktop/Windows delivery. The old N10 and new N1 runs have different repeat counts, observers and evaluator source; their memory/timing difference cannot all be attributed causally to observer overhead. Do not replace the failed old tail observation with the faster single new run.

Force-stop and no-spinning variants did not improve the observed release delay relative to either bracketing baseline. They retained the pinned speech model, native dependency and four threads; only research-copy session configuration entries changed. Sampled ASR CPU during cleanup was about 40–50 ms in these controls, which does not establish idle ASR spinning as the dominant delay. Production speech configuration and dependency pins remain unchanged. The earlier [session research note](actual-asr/runtime-research/report.md) describes the exact supported config keys and was written before these controls ran; the actual results here supersede its prepared-only status.

These baseline experiments identify measured quality failures and resource tradeoffs. Final source, protected-span boundary handling, fresh frozen text qualification, repeated ready/cold/idle measurements and [Windows whole-app qualification](windows-qualification.md) must be assessed under their own recorded conditions before any production or SLA conclusion.

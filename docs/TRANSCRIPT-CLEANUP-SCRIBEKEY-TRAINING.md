# ScribeKey training — active research checkpoint

The user authorized targeted training with ScribeKey as the base and subsequently
raised acceptance to **99%**. The current gate requires **495 of 500 complete
outputs to preserve meaning and be directly usable cleaned text**. The full-app
resource limits remain 747,500,000 host-memory bytes and 805 ms from ready release
to complete delivery. **No new trained model is qualified yet.** The first
independent 500-case test scored **471/500 (94.2%)** jointly faithful and clean,
below the required 495. Its complete result is preserved and the set is now
retired as development material. Further training and a new independent test are
in progress. The selected Linux runtime configuration passes the measured
partial-pipeline resource limits; Windows qualification remains unavailable.

The [training protocol](../tools/Freehand.Cleanup.Training/PROTOCOL.md) fixes the
editing policy, complete denominator, dataset separation and measurement scope.
The [tool guide](../tools/Freehand.Cleanup.Training/README.md) and
[export/evaluation guide](../tools/Freehand.Cleanup.Training/EXPORT-EVALUATE.md)
describe reproduction. This document is a progress checkpoint, not a shipping
recommendation or a claim of 99% population accuracy.

## Base and training

Training uses the original ScribeKey Fast v1.1 BF16 checkpoint at revision
`c484dad2d815bff83d376e46b25a11dbc820992a`, with weights SHA-256
`1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a`.
The original weights remain unchanged. Rank-8 LoRA exposes 2,998,272 trainable
parameters across 92 linear modules; updates are merged into a separate
checkpoint before native GGUF quantization.

The trainer uses the production ScribeKey prompt, one BOS, the expected EOS,
assistant-only next-token loss and input-derived literal masks on both sides.
It refuses incomplete examples rather than truncating them. Original checkpoint
generation and zero-initialized adapter identity were checked before training.
Training runs on four CPU threads in an isolated Python environment. Training
memory is separate from the application's inference budget.

The initial data includes 3,851 training examples and 546 development examples,
with roughly 36% of training examples requiring preservation. It combines
assistant-authored text with disclosed controlled augmentations. Development
content groups are separate, while several corruption/template rules are shared.
A further 80-case development set tests substantive words, repetition, uncertainty,
negation, corrections and longer context. These development sets are not a
population sample or blinded human validation.

An independently authored 500-case test was frozen before model inference at
SHA-256 `def0ae07b9e9fa922d2b11a90f0e981de12be499d5fdadaddcff3f0f6ef8a643`.
Its contents remained unseen by the training controller and trainer until the
candidate was frozen and its final evaluation began. Mechanical
hash-only audits process it without exposing text and found no exact normalized
input/target overlap with the approved training data. Brief case fragments were
incidentally exposed to two other agents through
completed-agent status metadata after their data was frozen; disclosures are
retained, and those agents supplied no subsequent new training content.

## Completed first pilot

The first pilot used 512 examples selected across training families, two epochs,
rank 8, learning rate 0.0001 and 128 optimizer steps. Actual training took about
414 seconds. Its BF16-merged Q4 export is 229,310,752 bytes with SHA-256
`7c0950537e79bcd5e363aeb3e2ab2b7c652179c31ccbb9d75e1f70d066a02faf`.

Both models below ran through the actual Core dictionary, normalization,
postprocessor, validation and counted single-delivery path. Every planned case
completed with one delivery and no provider fallback. Named assistant reviewers
read the actual pairs; reviews are bound to output hashes and the full case
inventory. Exact target strings and fixed assertions were diagnostics, not the
semantic score.

| Development set | Original ScribeKey Q4 | First trained Q4 |
|---|---:|---:|
| Broad 546: faithful and clean | 529/546 — 96.89% | 531/546 — 97.25% |
| Broad 546: faithful | 531/546 | 532/546 |
| Hard 80: faithful and clean | 60/80 — 75% | 62/80 — 77.5% |
| Hard 80: faithful | 65/80 | 69/80 |

Neither meets 99%. The broad set underrepresents some difficult distinctions;
its higher score cannot replace the hard diagnostics or the untouched final
test. Remaining errors include noun-changing punctuation around “well,” removal
of grammatical repetition or reported speech, incomplete correction cleanup,
and deletion of an object's only mention while retaining an unresolved “it.”
The complete outputs, case reviews, original judgments and adjudication overlays
remain under `work/cleanup-scribekey-training-2026-11-03/`.

The expanded three-epoch V3 run subsequently completed through verified recovery
after two process interruptions. Its final adapter SHA-256 is
`769000b19fee937aa7314f03ed72a7d59143baf7c898fbb3e05509084b119e54`.
The F16-merged Q4 export is 229,310,752 bytes, SHA-256
`1d8f6d4845943658f9d88361cdd8d60daf0546478a60460c48c12c02695b2a6c`.

| V3 Q4 actual Core replay | Faithful | Faithful and clean |
|---|---:|---:|
| Broad development 546 | 541/546 | **541/546 — 99.084%** |
| Hard development 80 | 75/80 | **73/80 — 91.25%** |
| Consumed older regression 40 | 40/40 | **39/40 — 97.5%** |

All 666 cases completed with one delivery and no provider fallback. These are
development/regression results, not a fresh final test or a production pass.
The broad development set still includes four critical errors. Hard failures
involve lost object references, omitted independent instructions, an unresolved
attribute correction and a lost comparison. The older regression's remaining
failure retains an accidental lexical repetition. Exact reviewed outputs and
all failures remain counted.

## Current experiment and remaining qualification

The V3 curriculum had 1,364 examples: 1,024 selected from the expanded
training pool, 100 disclosed longer compositions, and 240 examples derived from
80 additional authored semantic contrasts. It is 35% unchanged and includes
literal cases. Its SHA-256 is
`502f7884a5b8be4db1a20a0154cfbc4b646168b4e1b812cddcad0fe6e7154b4d`.
Training used the original base again, three epochs and the same LoRA rank.
A workspace restart interrupted the first attempt before its first saved
adapter; that attempt is retained as interrupted. The restarted run saves more
frequent durable checkpoints. Optimizer, learning-rate, RNG and batch-position
recovery have separate correctness tests.

All 35 training/evaluation tool tests pass in the isolated environment, including
99% boundary checks, complete-denominator checks, literal restoration, merge
precision and exact optimizer/RNG/batch-position recovery. New candidate freezes
archive the exact critical source bytes before inference; the earlier runs retain
their original hash-only source metadata and independently pinned artifacts.

The earlier restarted run's older writer did not serialize RNG states. Its
recovery used an explicit deterministic-model compatibility option. All 31
overlapping replayed steps matched the original losses, gradient norms,
learning-rate positions and token counts exactly. The new writer saves actual
RNG states. Executed sources, configuration and this distinction are retained.

An audit found that all V3 training targets are word-order-preserving
subsequences, while several correction diagnostics require moving an existing
object noun into the surviving clause. A separately authored curriculum adds
those source-copy repairs for a subsequent experiment if needed. Training loss
does not establish accuracy, and additional epochs alone cannot repair missing
task coverage.

The completed focused V4 pass started from the V3 adapter with a fresh optimizer and
learning rate 0.00005. It uses 1,150 explicit training exposures representing 710
unique pairs: 480 earlier examples, 120 independently reviewed anaphoric repairs
shown three times, 90 reviewed correction/grammar/comparison examples shown
three times, and 20 controlled protected-correction examples shown twice.
Those last examples express the correction with an explicit “instead of” clause
while preserving both protected entities in source order. The curriculum is
35.65% unchanged, its SHA-256 is
`463edcfe52558dfb614741ce548cc7a7de9a2284ef91f6e372ef7fc44f93eff9`,
and all input/target overlap checks against both development sets and the frozen
blind test returned zero. Oversampling is disclosed rather than counted as new
independently authored examples.

V4 completed 288 optimizer steps over two epochs in 1,060 seconds of active
training. Its adapter SHA-256 is
`4bb67a90dd6bcf8e7d7319c7fae8d805d8f771661acfafa3ba0ea5ebadc2b40e`.
The direct F16-merged Q4 export is 229,310,752 bytes, SHA-256
`4d1c2c0e9a7b93670f30e9b044529b88a69e8367e95ac267d102bf8bfad7621a`.

| V4 actual Core development replay | Q4_K_M | Q3_K_M | Q3_K_S |
|---|---:|---:|---:|
| Broad 546: faithful and clean | **543/546 — 99.45%** | 541/546 — 99.08% | 531/546 — 97.25% |
| Broad 546: critical errors | 1 | 4 | 10 |
| Hard 80: faithful and clean | 75/80 — 93.75% | 74/80 — 92.5% | 70/80 — 87.5% |
| Model file bytes | 229,310,752 | 193,151,264 | 181,149,984 |

Every output was semantically reviewed against its actual input, with failed
provider/literal validation retained in the denominator. Q4's remaining broad
failures include a metalinguistic fragment, an omitted instruction and a corrupted
protected identifier. The latter triggers safe original-text delivery, which
does not earn successful-cleanup credit. Hard cases still expose lost actions,
incorrect comparisons and incomplete corrections. The consumed older regression
set scores 39/40; a command's whitespace changed its meaning. The real-dictionary
regression scores 9/10 successful model outputs. These are development findings,
not the independent 500-case acceptance result.

Both Q3 variants were derived directly from the same retained F16 checkpoint.
They reduce worker memory but introduce semantic regressions, including omitted
prohibitions and changed actions. The pinned quantizer also supports IQ4_XS without an importance matrix. Its
211,804,448 bytes save 17,506,304 bytes versus Q4. Full case-level development
review gives **544/546 (99.63%)** faithful and clean, one critical error and no
provider fallback; hard diagnostics improve to **78/80 (97.5%)**, with two critical
errors. This is the leading development candidate, not a final-test pass.

A separate uniform specialist formatting fix trims only model-generated outer
whitespace before restoring literal payloads. It preserves protected internal
spaces and the general-model route. New prompt exports declare `trim-v1`;
historical unflagged replays retain their original behavior, and raw responses
remain separate. This is code-level presentation behavior, not learned semantic
improvement. The strict build, 264 cleanup tests, 63 Python replay tests and all
32 training-tool tests passed at that checkpoint; the current training/evaluation suite passes all35. The V3 scores above predate this normalization.

Exports can merge to F16 before quantization to preserve smaller updates.
Reduced precision must pass its own quality checks. Candidate selection and source/artifact
freezes precede opening the final 500 cases. Any test-informed behavior change
requires retiring that test and obtaining a new independent set.

The actual Linux speech/Core/Q4 path completed ten measured trials with one
delivery, complete text and no fallback. Median release-to-counted-complete-
delivery latency was 684.97 ms; p95/max was **817.12 ms**, exceeding the 805 ms
limit by 12.12 ms. The first trial remains included. Peak simultaneous observed
host + speech + cleanup RSS was **702,046,208 bytes**, below 747,500,000 bytes.
This is partial-pipeline memory, not whole-app desktop memory. A separate
lookup24 experiment was slower and exceeded both limits; the default lookup16
remains selected. Neither a one-trial ASR prepacking experiment nor this runtime
change demonstrated an improvement. Small repeated cohorts on a clean copied
transcript do not establish stable tails or representative cleanup latency.

The leading IQ4 model's default-profile replay used 701,325,312 bytes but took
727.85 ms p50 and 922.90 ms p95/max. Instrumentation showed the speech worker
continuing to consume CPU during cleanup after returning its transcript. The
documented `SessionConfig.session.intra_op.allow_spinning=0` option reduced this
overlap and improved complete-delivery latency. The exact spinning-disabled
configuration and App dynamic-PGO setting have now been adopted in local source
commit `b55c73d` after the final comparison below.

| IQ4 Linux development configuration, N10 | Complete p50 | Complete p95/max | Simultaneous RSS |
|---|---:|---:|---:|
| Original speech configuration | 727.85 ms | 922.90 ms | 701,325,312 B |
| Speech intra-op spinning disabled | 618.64 ms | **702.63 ms** | 755,433,472 B |
| Also disable memory-pattern planning | 688.94 ms | 855.37 ms | 755,838,976 B |
| Spinning disabled; .NET tiered compilation disabled | 575.59 ms | 897.04 ms | **695,844,864 B** |
| Spinning disabled; dynamic PGO disabled, tiered compilation retained | **621.10 ms** | **734.79 ms** | **690,319,360 B** |

All first trials remain included and every output was complete, unchanged text
delivered once without fallback. The final row passes both measured limits.
Disabling memory patterns did not help. Disabling tiered compilation
recorded lower peak memory, but its first trial exceeded the latency cap; the
other nine took 549–639 ms. Component memory varies between runs, including the
native speech worker, so the entire memory difference is not established as a
managed-code saving. The narrower profile-guided-optimization control retained
quick tiered compilation and passed both limits. Its tested environment was
`DOTNET_TieredPGO=0`, with no tiered-compilation override. The App project now
declares `TieredPGO=false`; a fresh Windows publish confirms the property in its
generated runtime configuration and preserves the tested 198-byte speech
configuration exactly.
No forced collection or accounting adjustment was used.

A separate native startup/request comparison reduced micro-batch size from 32
to 16. Exact output/token IDs matched, but worker high-water memory fell only
1,142,784 bytes, insufficient to close the observed gap. Source inspection found
no basis for a large logits-buffer saving from reducing the logical batch alone.
The selected cleanup semantic configuration remains lookup16/batch64/micro32;
the first independent 500-case result is described below.

## First independent 500-case result and continuation

The pre-frozen V4 IQ4_XS candidate completed all 500 cases through actual Core.
Every case delivered once; two rejected provider outputs fell back to original
text and remain failures in the full denominator. Model, native runtime, DLL,
source and input-inventory hashes verified before and after execution. Three
named assistant reviewers personally read all 500 outputs; the controller
cross-reviewed all 56 non-reference/failure pairs, with an independent second
review of 14 ambiguous or severity cases. Initial reviews and the severity
adjudication overlay remain separate. The overlay changed no joint pass/fail
decision.

| Full frozen test | Result |
|---|---:|
| Successful model candidates | 498/500 |
| Faithful, with successful candidate | 487/500 |
| Faithful and directly usable | **471/500 — 94.2%** |
| Critical meaning errors after adjudication | 7 |
| Required joint successes | **495/500** |

This fails the user gate. The development score of 544/546 did not generalize
to this broader test. Failures include unresolved corrections across varied
wording, omitted unretracted explanations or independent requests, altered
chronology/destinations, partial-phrase repetition and two protected-quote
corrections rejected by validation. Valid alternate punctuation, preserved
discourse voice and equivalent wording were accepted after semantic review.

The consumed corpus and lock remain unchanged. An exact copy is explicitly
retired as validation; any subsequent training-informed model must face a newly
authored independent set. New work adds correction/voice contrasts and protected
literal/scope examples with earlier training replay. Separate authors prepare
another 500 cases without reading training, development or earlier test content.
The threshold, complete denominator and meaning of success remain unchanged.
The earlier rubric requested a paired baseline on this final set; only the
pre-frozen selected derivative ran here, so no paired 500-case improvement claim
is made. Paired baseline evidence remains confined to development sets.

A fresh isolated Windows App, Probe and platform-layer publish succeeds, and all
eight default/frozen DLLs remain unchanged. Its 433,677,045-byte preview archive
passes full member/CRC verification. This is a reproducible development artifact
for the failed V4 candidate, not a qualified default or Windows execution result.

The user currently has no Windows test machine. Linux work can measure the real
speech/Core/cleanup path and prepare verified custom Freehand bundles, but cannot
certify desktop memory, GPU offload or actual Windows delivery. No normal
installation update, model-default promotion, push, PR, merge or release has
occurred during this research.

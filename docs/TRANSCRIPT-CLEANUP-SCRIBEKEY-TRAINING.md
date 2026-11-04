# ScribeKey training — active research checkpoint

The user authorized targeted training with ScribeKey as the base and raised
acceptance to **99%: at least 495 of 500 complete outputs must preserve meaning
and be directly usable cleaned text**. The full-app limits remain 747,500,000
host-memory bytes and 805 ms from ready release to complete delivery.
**No new model is qualified.** The selected ScribeKey factor blend reached
495/500 on the older development set, but the subsequent fresh 500-case test
scored **462/500 (92.4%)**, with **482 faithful, 475 clean and 10 critical errors**.
All 500 selected cases completed the actual Core path with one delivery and no
provider fallback. Every fresh output was personally read by named assistant
reviewers; no development judgment was inherited. Three overconstrained judgments
about unquoted identifiers were independently adjudicated against the existing
policy, with the original reviews and conflicting author notes preserved. This
does not change the failed acceptance decision.

The selected weights with microbatch64 pass the measured **Linux partial-pipeline
N10** bounds: complete-delivery p95=max **780.6206 ms** and coherent simultaneous
RSS **693,895,168 bytes**. All first ten trials remain counted. The same profile
still scores 495/500 on the older development set; broad546 and hard80 regression
results are 544/546 with one critical error and 78/80 with two critical errors.
The earlier microbatch32 results—805.3532 ms with lookup16 and 929.6313 ms with
lookup31—remain failures and are preserved. These measurements do not establish
Windows or whole-app qualification; the user has no Windows machine available.

The failed fresh test is now retired development material. Its paired original
ScribeKey control also completed all 500 cases and scored **430/500 (86.0%)**
joint passes with 16 critical errors. Its three provider failures stay in the
denominator and receive no successful-cleanup credit. The paired comparison has
411 cases passing both models, 51 passing only the trained blend, 19 passing only
the original control and 19 failing both. Control review uses 348 exact typed
same-fresh successful selected judgments and 152 personally read control pairs;
it inherits no development judgments. A new independent corpus is committed and
remains unseen by the training work. The next model experiment is a ScribeKey
source-copy/edit head using 400 newly authored and independently reviewed training
pairs. No head has been trained or qualified yet. No app default, normal
installation or release has been promoted.

Opt-in `specialist-compact-v4` quote protection is now implemented in C#, Python,
asset preparation and the probe. It protects balanced single and double quotes,
keeps ordinary apostrophes distinct, and preserves the v3 default and original C#
API. The strict solution build has zero warnings/errors; all 714 portable .NET,
124 Python and 78 affected script tests pass. All 800 new training input/target
exports agree between actual Core and Python masks/prompts/official tokenizer
IDs, with exact source-derived literal restoration. The first Core test attempt
hit Linux's socket-path limit under a long temporary directory; its 16 failures
are preserved, and all 151 Core tests pass using a short directory without a
source change. Actual Windows execution remains unverified. These checks qualify
transport behavior; the new code generation has no model-quality or resource
qualification yet.

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
checkpoint before native GGUF quantization for the completed merged candidates.
An optional unmerged F32 native adapter route is also implemented and tested;
it preserves the original four-bit base and deploys updates separately.

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

## V5–V8 continuation and numerical checks

V5 completed 330 optimizer steps with 1,320 training exposures representing 900
unique pairs. It resumed a saved optimizer/RNG checkpoint after a workspace
restart; the overlapping step is bit-identical. Its final adapter SHA-256 is
`741826d27bf20da1c59eebc5d397f0a7de972ef1f566ce7e04abbf8abc0cf961`.
All results below use actual Core outputs and independent semantic reviews.

| Candidate on the consumed 500-case development set | Faithful and clean | Critical errors | Provider failures |
|---|---:|---:|---:|
| V4 merged IQ4, original failed acceptance run | 471/500 — 94.2% | 7 | 2 |
| V5 merged IQ4 | 477/500 — 95.4% | 8 | 2 |
| V5 merged F16 diagnostic | 481/500 — 96.2% | 6 | 1 |
| Original IQ4 plus unmerged V5 F32 adapter | 474/500 — 94.8% | 9 | 2 |
| Original IQ4 plus unmerged V6 F32 adapter | **475/500 — 95.0%** | **9** | **1** |
| Original IQ4 plus unmerged V7 supervised F32 adapter | **482/500 — 96.4%** | **10** | **0** |
| Original IQ4 plus unmerged V7 semantic-loss F32 adapter | **483/500 — 96.6%** | **10** | **0** |
| Original IQ4 plus unmerged V8 F32 adapter | **492/500 — 98.4%** | **1** | **0** |

The higher-precision model is a quality diagnostic, not a memory-qualified
candidate. V5 merged IQ4 also scored 537/546 on broad development and 76/80 on
hard development. Quantization changes some recipient-negation decisions, but
omitted independent actions, actor changes and unresolved corrections also occur
at higher precision. Precision alone does not close the accuracy gap.

A byte-level inverse-conversion proof matches all 148 original F16 GGUF tensors
to the prescribed original checkpoint casts and restores all convolution shapes
and tied embeddings. Six already-consumed prompts then compare native and HF
inference with identical prompt tokens. F16 outputs agree in all six cases both
with and without the adapter. Original IQ4 agrees in six without the adapter and
five with it. Changing only native adapter-run KV storage from F16 to F32 changes
the remaining decision to match HF. Larger IQ4 probability differences also
remain, so recovered weights do not establish identical forward arithmetic.

V6 completed with the full 2,014-pair training history and trained against the
original deployed IQ4 weights with native Q8_K activation rounding. It retains
rank 8 and FP32 KV storage in training. Its 252 optimizer updates took 1,036
seconds. The final adapter SHA-256 is
`157af046d18471d2e87d6936208d629e129739746f2c807636915f955968f207`;
the unmerged F32 GGUF is 12,006,240 bytes, SHA-256
`d5b2bb684183a62fa8b5f2f86674f519bef6199d25ef85f94f99eb78b2e5f537`.
All 184 adapter tensor payloads match through conversion, and all 1,126 Core
development cases completed with one delivery and verified deployment identity.
The fixed six-case numerical comparison
remains five-of-six even with activation/cache emulation, so this is an
approximation to deployed inference. Hash-only comparison finds zero exact normalized input/target overlap
with the newly frozen 500-case acceptance set. That set remains unopened by the
training controller and trainer and has received no inference. No new candidate
is qualified and no 99% accuracy claim is made. V6 scores **545/546 (99.82%)**
on broad development with no critical errors, and **79/80** on hard development.
The remaining hard error drops an unretracted invoice-send instruction. The
broader retired set still has 25 joint failures, including dropped facts or
actions, incorrect correction scope, accidental stutters, deliberate-emphasis
loss and a rejected literal correction. Three reviewers supplied hash-bound
casewise decisions; root read all 54 non-reference/failure pairs outside the 20
dictionary cases independently read by the reviewers. Exact successful
inheritances retain per-case proofs. Fallback receives no model-quality credit.

The V7 comparison adds independently reviewed contrasts and a controlled
semantic unlikelihood objective. Both arms start from the same V6 adapter and
use the same 2,754 positive exposures: the complete 2,014-pair history once,
270 new pairs twice and another 100 new pairs twice. This represents 2,384
distinct raw pairs; four case-only input variants collapse under the separately
reported normalized comparison. Both arms use rank 8, learning rate 0.00003,
one epoch, seed 42 and 345 optimizer updates. The only objective difference is
the semantic-loss weight, zero versus one, applied to 32 reviewed error branches
covering 64 scheduled exposures. The positive-data SHA-256 is
`fa18dfcd5faf4c5a7a20f8e9b669caaa2ec3c8e098b27b17a25128eda1d592a6`.

The supervised control completed through exact optimizer/RNG recovery after an
environment restart. All 15 replayed updates match bit for bit. Its final
adapter SHA-256 is
`5d4feeda03dffcb3edd9e532f3a3eff307424c8b51e667c5bca308bb5233c777`;
the unmerged native F32 adapter is 12,006,240 bytes, SHA-256
`e8800d752907471ca746d371a71111ad4083325870d70b08f933c63a06fc485c`.
Actual Core replay of the retired 500-case set yields **482/500 jointly faithful
and clean**, 488 faithful, 490 clean, ten critical errors and no provider
failures. All 500 cases deliver once. Three hash-bound casewise reviews and
root's review of all non-reference pairs outside the separately reviewed
dictionary cases support the score. Compared with V6 it fixes nine cases and
regresses two, leaving 18 joint failures and a 13-case gap to 495. This consumed
set cannot establish the fresh acceptance gate. No final-test inference has run.

The matched semantic-loss arm also completes 345 updates, with verified exact
recovery after an unexplained SIGKILL. There are no recorded OOM events; its
cause is unknown. The 15 replayed updates match bit for bit. Its final adapter
SHA-256 is
`8855c0db616fedd64d5b0fb9bba84a04a9e1bcfde8af33407b0c6f3721c2e643`;
the unmerged 12,006,240-byte F32 GGUF SHA-256 is
`eadaaa0a515b915e4cfbbe8ef6ec54fae1bc73e45c1e3adfd54eafa80c4069ac`.
It scores **483/500 jointly faithful and clean**, 488 faithful, 491 clean,
ten critical errors and no provider failures. All 500 deliver once. It fixes
one correction-cleanup failure relative to the supervised control and introduces
no new joint failures. All changed or previously failed pairs receive direct
semantic review; inherited successful judgments require equality in 13 recorded
fields and retain per-case proofs. This leaves 17 joint failures and a 12-case
gap to 495.

A new qualified app/Probe build permits explicitly frozen f32 key/value caches
while keeping f16 as the default. The supervised and semantic-loss candidates
each completed another full 500-case Core run with f32 caches. Their delivered
texts are **identical in all 500 cases** to their respective earlier f16 runs:
scores remain 482 and 483, with no observed quality gain. Casewise proofs retain
all 13 comparison fields, permitting only validated nonce changes inside Core's
literal markers. Prior semantic judgments transfer through this equality;
these are not another 1,000 independently read pairs. A preceding full f16
bridge under the new DLLs changes one optional comma, independently read as
faithful and clean, and preserves its quality score.

All 1,500 cases deliver once without provider failure. During a workspace refresh,
the outer controller exits in the last cohort, but its original model worker
continues and completes all 500 cases without replay. The post-refresh verifier
checks actual options, manifests, deployment identities and frozen artifacts and
sources. The last cohort's original outer argv observation was lost; that gap is
explicitly retained. F32 memory and latency have not been qualified. No fresh
acceptance case was used in this comparison.

V8 starts from the stronger V7 semantic-loss adapter and retains the f16
deployment baseline. The approved 240 new pairs are appended twice to the
complete V7 exposure file: **3,234 exposures, 2,624 distinct raw pairs and 1,048
clean controls**. Core normalization, all source/gold prompt and mask identities,
source lineage, duplicate disclosures and the 32-event rebind have separate
reviews. The positive-file SHA-256 is
`2fdab6a16b7c47a7e2bffd2d60208ad0b5ea9804048d28f2f184468fe33e757c`.
It completes one epoch, rank 8, learning rate 0.00003, a fresh optimizer and
unchanged semantic-loss weight one: 405 updates over 809 microbatches and 55,612
assistant tokens in 1,750.46 active seconds. There is no interruption. The final
adapter SHA-256 is
`0ad09445f70d2547696691511b4a7973bdfe1de4545b83cf76f2b62ca0a8306c`;
its unmerged 12,006,240-byte native F32 GGUF SHA-256 is
`11ec6ac65c06205cabf8ed1fd41c3163658112f8f44a5062b9133c0e29ecf8e8`.
All 184 tensor payloads match through conversion. An initial export preflight
stops before model work on a verifier-schema mismatch; the corrected reader
captures the actual optimizer digest explicitly at export preflight and retains
all real optimizer-state checks. The failed log and independent delta review
remain preserved.

All 500 Core cases complete and deliver once without provider failure. Three
casewise reviews yield **492 jointly faithful and clean**, 498 faithful, 493
clean and one critical error. Root additionally reads all 23 changed outputs and
five unchanged prior failures. An independent target-free review supports two
correction-scope judgments, with one moderate-confidence alternative reading
explicitly recorded. V8 fixes 12 parent failures but regresses three cases:
an omitted bolt-tightening action, an unresolved inspection correction and a
pronoun stutter. Eight joint failures remain, three above the permitted five.
No 99% or V8 resource qualification is claimed.

The next development comparison fixes child-weight fractions 0.5, 0.75 and
0.875 before inference and runs the full retired 500 cases for each. It
interpolates corresponding LoRA factors between V7 UL and V8; it is not an
exact average of their weight deltas or functions. Derived metadata records
zero optimizer steps for this operation and both actual training histories.
This keeps rank and adapter storage fixed but does not establish improved
quality or unchanged application performance. All three full cohorts complete
with one delivery per case and no provider failures. Casewise review scores
them **487, 489 and 490 of 500**, with **7, 4 and 2 critical errors** respectively.
The predeclared selection rule retains V8 at 492; that V7-to-V8 comparison ends
with these three coefficients. Three regressions were not recovered without
losing other corrections.
A separately reviewed 80-pair curriculum and 20 additional attribute-fragment
repairs/controls supply the next training pass. All 100 new pairs have independent
semantic and Core-alignment approvals. Each is exposed four times, with all
3,234 prior exposures retained: **3,634 exposures, 2,724 distinct raw pairs,
1,224 clean controls and 2,410 editing examples**. All repetitions and inherited
historical exposure annotations are explicitly disclosed. The maximum complete
example remains 193 tokens; no example is truncated. Exact normalized source-pair
union proofs inherit zero overlap with the unopened acceptance corpus.

V9 starts from V8 with a fresh optimizer and the same rank, learning rate,
numerical base, activation quantization and semantic-loss weight. The frozen
positive-file SHA-256 is
`50b208ed5e16b6d7027e46fd4785940ef036e7b0bc3bc581c460ac601bb75451`.
The one-epoch schedule completes all **455 updates and 909 microbatches** in
1,997.96 active seconds, without interruption. All 184 F32 tensors are finite;
all 184 AdamW states reach update 455. The 32 canonical semantic-loss events
retain their 64 scheduled exposures. Actual RNG state is retained at the last
durable checkpoint, update 448; final-update RNG capture is not claimed.
The final raw adapter is
`3de792128cce7469465ca8c42ebef5f769e868415db80198eb036e8cbec05787`;
its unmerged native adapter is
`16b9f356f4e82a3af2b55bc061219b801285963ee5b02ebc1aa41d4c39b8ce1f`.

The exact native adapter completes all 500 retired development cases once:
304 Applied, 196 Unchanged, no provider failures, and one delivery per case.
Three named reviews give **500 faithful, 494 clean and 494 joint passes**, with
**zero critical errors**. The score is **98.8%, one case short of 495/500**.
The review transparently inherits 462 identical successful prior judgments
under typed equality of all 13 fields; 38 pairs require personal review, and
root also cross-reads all 38. V9 fixes the dropped bolt instruction, deliberate
repetition and a quoted-request stutter. A new malformed question and five
remaining cleanup failures prevent acceptance. Full results and judgments are
bound by report SHA-256
`d59ff5167f5c1df224f060c62fea144403425503b9fc1b0ebe6b02dcc18e0089`
and canonical review SHA-256
`9ec70b6b9dfa008b53e2ffd3bba13cee8298109703827cb72edb9d522f8a36e4`.

A separate V8-to-V9 factor comparison fixes fractions 0.5, 0.75 and 0.875 before
inference, using the same rank-8 representation and unchanged original helper
guards. All three adapters are exported and frozen before the first inference;
all 1,500 development cases complete once without provider failures. Named
semantic review scores the blends **495, 494 and 494 of 500** respectively,
with **all 500 faithful and zero critical errors** in each run. The 50/50 blend
is the unique highest-scoring candidate and fixes the malformed question that
V9 introduced. Five cleanup failures remain in the denominator. This is factor
interpolation with disclosed cross terms, not exact averaging of weight deltas
or a new optimizer-trained checkpoint.

The selected native adapter is
`4d14e22826d039a12444236124459363f02e77de247117b7b8379ccfe257cfb1`;
its canonical development review is
`e5ba522f3c0cad1548a3e529fe8c35d4f4713fe2e4405ebbc8898fed63f10b72`.
The complete selection receipt is
`cc71309432587593b53e24dc2092d4c54a4f7de7bc27b5f178b2e2fa9ef81ca8`.
No independent final-test or population accuracy is claimed.

Ten first-retained real-ASR/Core/cleanup trials preserve the complete public
transcript and deliver once without fallback. At the original lookup16,
batch64/micro32 profile, simultaneous RSS is **695,144,448 bytes**; complete
delivery p50 is **654.37 ms**, and p95/maximum is **805.3532 ms**. The strict
805 ms cap therefore fails by 0.3532 ms; the first trial is retained. No repeat
or rounding is used to turn it into a pass. A separately frozen lookup31
configuration is slower: p50 **736.02 ms**, p95/maximum **929.63 ms**, with two
of ten over the limit and RSS **684,072,960 bytes**. Its text quality has not
been independently requalified. The next configuration restores lookup16 and
changes only micro-batch size to 64 to reduce prompt-processing passes. The same
compiled source and immutable build are reused; no performance result is assumed.
The acceptance corpus remains unopened pending both quality and resource gates.

The optional native adapter integration passes a strict solution build with
zero warnings/errors, 339 cleanup tests, 151 Core tests and isolated Probe
checks. The Python evaluator retains separate selected/control deployment
identities and continues the original control even after malformed selected
metadata. At the V6 checkpoint, all 74 training-tool tests and 63
evaluation-framework tests pass. The subsequent optional semantic-loss trainer
passes 85 training-tool tests, including exact zero-weight supervised optimizer
identity and strict event/positive-file/resume binding.
These checks establish implementation integrity, not model accuracy.

A separate V5 Q5_K_M diagnostic passes both measured Linux limits in ten trials:
complete-delivery p50 is 611.20 ms, p95/maximum is 720.61 ms, and simultaneous
host/speech/cleanup RSS peaks at 745,455,616 bytes. All first trials are retained,
with complete text, one delivery and no fallback. Memory margin is only
2,044,384 bytes; this does not establish a robust whole-app memory margin or
Windows behavior. The run uses preserved compiled evaluator artifacts and
discloses their source differences from the newer optional-adapter implementation.
The comparison also changes trained weights, so it is not a quantization-only
causal experiment. No Q5 model has passed the accuracy gate.

The actual V6 unmerged-adapter path also passes a fresh ten-trial Linux run:
counted complete-delivery p50 **604.09 ms**, p95/maximum **779.64 ms**, and
simultaneous host/speech/cleanup RSS **693,297,152 bytes**. All ten first-retained
trials deliver the complete unchanged public transcript once, without fallback.
The fresh evaluator build, all 180 artifact/source/profile pins and simultaneous
memory attribution pass before/after checks and an independent report audit.
Initialization is separate; this cohort does not test representative editing
quality, long-input tails, the Windows desktop or physical delivery. The same
runtime and rank-8 adapter shape remain the basis for further quality experiments.

A fresh isolated Windows App, Probe and platform-layer publish succeeds, and all
eight default/frozen DLLs remain unchanged. Its 433,677,045-byte preview archive
passes full member/CRC verification. This is a reproducible development artifact
for the failed V4 candidate, not a qualified default or Windows execution result.

The user currently has no Windows test machine. Linux work can measure the real
speech/Core/cleanup path and prepare verified custom Freehand bundles, but cannot
certify desktop memory, GPU offload or actual Windows delivery. No normal
installation update, model-default promotion, push, PR, merge or release has
occurred during this research.

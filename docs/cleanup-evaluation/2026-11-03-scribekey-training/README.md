# ScribeKey training evidence

This separate collection preserves public data actually used for the local ScribeKey
fine-tuning work, exact historical trainer bytes, run snapshots and completed development
replays. The earlier small-model evidence tree remains unchanged. See the
[main progress document](../../TRANSCRIPT-CLEANUP-SCRIBEKEY-TRAINING.md).

The current user threshold is **495 of 500 outputs jointly faithful AND clean/usable**
(99%). [Revision 02](metadata/acceptance-threshold-revision-02.json) supersedes the
historical 98% task-start record. The first frozen 500-case test **failed: 471/500
(94.2%) joint successes**, with 487 credited faithful outputs, 478 clean/usable outputs,
7 critical errors and 2 provider failures. It missed the threshold by 24 successes.

The first corpus is now explicitly retired as validation/regression material. The
[new immutable phase](phases/primary500-retired-runtime-04/phase-summary.json) preserves
its authorized retired copy, complete outputs, all three reviews, manual records,
cross-reviews, canonical adjudication and retirement receipt. Its SHA-256 remains
`def0ae07b9e9fa922d2b11a90f0e981de12be499d5fdadaddcff3f0f6ef8a643`.
Historical receipts retain their original pending-review and `blind-final` labels.
The canonical review and retirement receipt establish the current failed/retired status.
The original blind directory and consumed lock remain untouched by this collector.
**No future blind round, its authors, or unused V5 draft data was accessed or copied.**
A future 99% qualification requires a new independent frozen blind test.

## Used public data and development evidence

`data/` contains the 512-row pilot training subset, 546-row development data and exact
Core-derived corpus, and the 80-case hard development corpus and manifests. `data-v3/`
contains the approved 1,364-row training set, its manifests and opaque overlap check.
Unused full V1/V2 training corpora are excluded. `data-v4/` records the actual 1,150
exposures (710 unique pairs, 410 unchanged rows), the used 120-row anaphora component,
90 repair pairs and 20 protected-template pairs with their review/provenance.
Oversampling does not create 1,150 independent examples. Prelaunch manifest fields
saying not yet trained remain unchanged; actual use is bound by the V4 configuration
and data hash. Development/hard-development evidence
is not independent final qualification, including where training curricula derive from it.

`evaluation/` retains completed baseline/pilot Core outputs for 546 and 80 cases,
source/artifact freezes and diagnostic comparisons. Canonical input-byte equivalence is
recorded in the phase metadata instead of duplicating each per-run corpus. `reviews/`,
`reviews-development/` and `reviews-hard80/` preserve the complete agent/manual semantic
reviews, gold audits, adjudications and overlays. These are agent reviews, with no
external human review claimed. V3/V4 completed Core outputs and reviews extend the
same development/hard sets. The 40-case old corpus is already consumed and provides
zero fresh final qualification. The first 500 cases now appear only in the explicitly
retired validation phase, not as fresh final evidence.

## Historical executed code, interrupted runs and resume

`training-runs/` includes exact `training-source.py` and configuration bytes for the
pilot, V3-01, V3-02, V3-03 and V4-01. Their hashes match the adjacent run configuration claims.
Current Git trainer code has later changes and is never substituted for these snapshots.
The `pilot-01-epoch1` artifact is the preserved step-64/epoch-1 checkpoint of the two-epoch
pilot; its parent config still declares two epochs. It is not a separately completed run.

Completed/interrupted logs are preserved. Changing V3-03 logs and pointers are stored
under `phases/<phase>/`; a prefix snapshot is labeled by captured byte extent and time,
not silently replaced by a later log. Saved resume metadata and exact checkpoint source
are included without adapter, optimizer or RNG tensors. Legacy recovery did not save RNG
states; its deterministic-trajectory verification and newer checkpoint metadata retain
that distinction. Logs contain metrics, not embedded code hashes, so source association
comes from adjacent configuration/checkpoint records, not a stronger attestation.

`pilot-export/` preserves the pilot's BF16 merge and native Q4 conversion/quantization
logs, hashes and notices. The later V3/V4 records in `exports/` preserve their F16
merge/export and native Q4 quantization evidence. The IQ4_XS evidence records direct F16
quantization, full 546/80 Core replays, complete reviews and the root cross-check of
two changed development outputs. It does not derive IQ4 from Q4. Other lower-bit
variants are excluded from this phase.
`base-model/` retains the original immutable BF16 source pins and inherited terms. No
model weights, merged intermediates, native libraries or Python environments are copied.

## Scope and append policy

The initial phase's planning metadata remains immutable. The 120-row anaphora V3
component is now used in the actual 1,150-row V4 curriculum and is retained with its
independent V2 review plus explicit adjudication/temporal overlays and V3 validation.
The full 720-row candidate was never a standalone training run; its unused rows and
author scripts remain excluded. The trim-v1 verification records commit `7da7ad1`,
264 cleanup tests, 63 Python tests, Probe contracts and 32 post-trim training-tool
tests. Old DLL backup and completed optimizer-cache migration are inventories only;
no DLL, optimizer or RNG tensors are copied.

`performance/` preserves the completed Linux Q4, lookup-24 and IQ4_XS reports,
plans, profiles and source/model freezes. The IQ4 ten-repeat run used
701,325,312 host-memory bytes, with complete-delivery p50 727.8454 ms and maximum
922.8956 ms; four of ten exceeded 805 ms. It passed the memory cap in that run and
did not pass both caps. This is development performance evidence, with no Windows
or final 500-case accuracy claim.
The [data disclosure](metadata/training-data-disclosure.json) preserves the recorded
incidental status-message exposure without reproducing case fragments. This collector
never calls agent listing or opens original or future blind directories. The separately authorized retired copy is included only after completion and retirement.

All paths in source records are historical workspace provenance, not portable live links.
[The collection catalog](collection-manifest.json) records scopes, hashes and snapshots.
[The SHA-256 index](evidence-files-sha256.json) covers every retained file except itself.
The ignored source collectors are `work/cleanup-scribekey-training-2026-11-03/collect_public_training_evidence.py` and `append_public_retired_primary500_evidence.py`.
Later evidence uses a new phase/revision path; existing snapshots are never overwritten.

The new phase also records controlled native lookup/buffer probes and full Linux
runtime comparisons. With ASR intra-op spinning disabled and dynamic .NET PGO disabled,
the selected IQ4 profile's ten-repeat development run had complete-delivery counting
p50 **621.1004 ms**, p95/maximum **734.7871 ms**, and simultaneous peak host RSS
**690,319,360 bytes**. All ten met both 805 ms and 747,500,000-byte caps in that run.
This supersedes the earlier development resource result, while preserving its raw files.
It does not establish Windows behavior, population latency or successful 99% text quality.

Windows evidence covers cross-publishing, runtime/property checks and static archive
verification only. Windows/GPU execution was not performed. Exact builder text and
original-path restoration metadata are preserved without binaries, models or archives.
Historical snapshots of the prior README, catalog and index preserve the previous
297-file collection bytes before this append. All previous raw snapshots remain exact.

## Active V5 snapshot

The [V5 phase](phases/v5-active-prefix-05/phase-summary.json) records data actually
used by V5 training: reviewed 240-row and 180-row raw curricula, Core normalization
of all 420 new rows, and 480 byte-exact V4 replay rows. The final training file has
1,320 exposures (900 unique pairs); each new row is exposed twice. Its prelaunch
manifest remains unchanged, including the historical training-not-started field.
Executed run configurations and metric steps establish subsequent actual use.

V5-01 was interrupted at step17; V5-02 resumed checkpoint16 with saved optimizer,
Torch CPU RNG and Python RNG state. The step17 verification is bit-identical for
all recorded training fields. Exact executed source and config bytes are retained.
Logs and checkpoint pointers are **create-only prefixes observed during active
training**, not completed-run or final-model evidence. Later training results must
use a new phase. Optimizer/RNG inventories are metadata; no tensors are copied.

Controller-authored opaque aggregate overlap proofs retain only already known
future-round hashes/counts and zero-overlap claims. No future blind corpus, author
script, commitment contents, case IDs or case text was opened or copied. This phase
does not claim 99% quality, a completed V5 model, or Windows/GPU qualification.

## Completed V5, native adapter and numerical proof

The [completed phase](phases/v5-completed-native-proof-06/phase-summary.json) adds
final V5 source/configuration, all 330 metric steps across the interrupted/resumed
runs, exact resume receipts, export metadata, complete 546/80 Core outputs and
all three consumed 500 replays with complete casewise reviews. Joint successes
are 537/546 and 76/80 for merged IQ4 development; retired500 results are 477 merged
IQ4, 481 diagnostic F16 and 474 original IQ4 plus unmerged F32 adapter. These
results do not meet 495/500, and none is a fresh acceptance test. Previous active
prefix snapshots remain unchanged alongside these later completed records.

The phase preserves fixed 15-prompt precision/lookup/native-adapter diagnostics,
all 148 inverse-tensor checks, fixed native/HF response receipts and their recovery
records. Exact inverse weights do not establish identical forward arithmetic.
The original fixed proof records KV-rounding sensitivity and remaining IQ4
probability differences. Later Q8_K/quantized-mode smoke artifacts are excluded.

The Q5 ten-repeat Linux partial-pipeline run has complete-delivery p50 611.1973 ms,
p95/max 720.6074 ms and simultaneous peak host RSS 745,455,616 bytes. All ten met
the two development caps, with 2,044,384 bytes of memory margin. Exact analysis
explains the inherited V4 label in the unchanged original plan. This is not a
quantization-only causal comparison or Windows/population/quality qualification.

Historical snapshots preserve all previous 490-file README/catalog/index bytes;
all earlier raw evidence remains exact. Byte-identical per-run corpora reference
the existing public 546/80/retired500 copies. Future unused curricula, blind-round2
material, model weights, native libraries, optimizer/RNG tensors and archives are
excluded. No model job, normal installation update or publication was performed.

Separate later implementation receipts preserve the optional parser-guard strict
build (zero warnings/errors), 339 cleanup tests, 151 Core tests and 42/63 Python
tests, including casewise TRX and exact log hashes. These support the later
implementation revision; they do not replace the earlier frozen V5 inference
source/assembly identities. No current source or DLL is substituted.

## Completed V6 numerical-base-aligned native adapter

The [V6 phase](phases/v6-completed-07/phase-summary.json) preserves the actual
used 2,014-row full-history curriculum, Core 1,537 export, prior 420 and legacy 57
provenance, all 62 independent normalization reviews, and the opaque aggregate
overlap proof without any fresh-test material. It records complete 252-step
training/source/configuration, 184 byte-identical F32 adapter conversion checks,
all 500/546/80 Core outputs and complete casewise reviews. Earlier 726 raw and
derived snapshots remain exact, with old README/catalog/index bytes preserved.

The canonical retired 500 result is 475/500 jointly faithful and clean (95%):
485 credited faithful, 485 clean, 9 critical errors and 1 failed provider case.
It fails the requested 495/500 target. Broad development is 545/546 with zero
critical errors; hard development is 79/80 with one critical error. These are
consumed development diagnostics, never fresh 99% or population qualification.

The original IQ4 base plus unmerged F32 adapter met both caps in one Linux
partial-pipeline N10 cohort: counting-complete p50 604.0863 ms, p95/max 779.6414 ms,
simultaneous peak RSS 693,297,152 bytes. All ten first-inclusive public-JFK trials
delivered full text once without fallback. Build, wrapper correction and 180-pin
pre/post verification are preserved. This does not verify Windows, the entire
desktop application, semantic accuracy or default promotion.

The numerical proofs retain initial/corrected Q8 block-layout evidence, fixed
six-case 2x2 comparisons, 18 source unit tests, 2 legacy checks and the root 74-test
suite. Exact inverse tensors and native activation emulation do not establish
identical full-model forward arithmetic. Reserved/future curricula, all fresh
round2 content, weights, binaries, optimizer/RNG tensors and archives are absent.


## Completed V7 two-arm comparison

The V7 SFT control and UL arm used the same actual2754-row positive data and exact source8c609 recipe, with eta0 versus eta1. Both completed345 updates/689 microbatches with preserved recovery prefix/suffix and15 exact replay records. Retired500 semantic results are482/500 (96.4%) for SFT and483/500 (96.6%) for UL; both retain10 critical errors and fail the required495/500 gate. All500 inputs/outputs, range reviews and inheritance/read proofs remain included. These are development results, not fresh/population accuracy, Windows, or whole-app qualification.

See [phases/v7-sft-ul-completed-08/README.md](phases/v7-sft-ul-completed-08/README.md) for actual used2754/32 raw and derived lineage, source/adapter/runtime pins, full completed training/recovery history, original frozen source archives and missing text bodies. The existing2014 history and exact2554 prefix are reused without losing raw bytes. Unused reserved240, fresh2 contents, weights and optimizer/RNG binaries are excluded. The prior940-file derived README/manifest/index epoch is retained under the new phase historical directory; prior raw evidence is unchanged.


## Completed V7 cache-precision diagnostic

The new-epoch SFT F16 bridge, SFT F32 and UL F32 each completed the original ordered500 Core cohort. Prior semantic decisions were transparently transferred under full13-field/literal-nonce proofs; root personally read the optional-comma bridge case158. These are not three new manual500-case reviews. Joint quality remains482/500,482/500 and483/500 respectively, with10 critical errors each; F32 did not improve this development gate. No fresh/population, resource, Windows or whole-app qualification is claimed.

The original UL worker survived the outer-controller reset and finished without replay. Its native argv capture was lost and is explicitly missing, not recreated. Qualified source/build records retain the no-space failure and recovery, all logs/TRX/source snapshots, prior24-DLL/new-six preservation receipts and original source archives. The optional preview-builder material is PREPARATION ONLY, not a built or qualified bundle. Active V8 data/training, weights, caches, fresh2 and unused reserved240 are excluded. See [phases/v7-cache-precision-completed-09/README.md](phases/v7-cache-precision-completed-09/README.md).


## Completed V8 training and native development evaluation

V8 completed405 updates/809 microbatches/55,612 assistant tokens on the full3234-row curriculum, continuing from V7 UL parent8855 with a fresh optimizer and eta1. Full data ledgers and approved240 raw/Core/author/review lineage are preserved, with exact older2754/2014/270/100/approved32 references. The original pre-model schema failure and corrected11-test export trace remain explicit; the optimizer digest was captured at export preflight.

The unmerged184-F32 native adapter11ec at external scale1 completed all500 original retired-development Core cases once using actualF16 KV. Named semantic reviews record492/500 joint,498 faithful,493 clean and one critical error, below495/500. Root28 actual crosspairs and the independent moderate-scope C076/C112 adjudication are retained alongside strict prior-pass inheritance proofs. These are not500 new personal reads, fresh/population accuracy, Windows/whole-app execution or a new resource-SLA qualification. Current interpolation and unused80/3394 are excluded. See [phases/v8-completed-10/README.md](phases/v8-completed-10/README.md).


## Completed parent-child factor interpolation

Three fixed child fractions0.5/0.75/0.875 derived both rank8 factors from the completed V7 UL parent and V8 child with zero new optimizer steps. All three were converted/frozen before their serial full original500 Core runs; the earlier subset and matched-arm proposals remain unused chronology. Semantic results are487/489/490 joint with7/4/2 critical errors, so the predeclared selection retains V8 at492/500, below495/500. Full derivation/conversion/legal/source, all1500 actual outcomes, owned argv/postchecks, shard reviews/inheritance proofs and root cross-read records are preserved. The independent math-guard PASS was reported only in collaborator messages/owner plan; the distinct formal saved wrapper audit is retained. No new resource, Windows, whole-app or fresh/population qualification is claimed. See [phases/parent-child-interpolation-completed-11/README.md](phases/parent-child-interpolation-completed-11/README.md).


## Completed V9 phase12

V9 actually used approved3634 and32canonical events with64mapped exposures. Exact8c source/config/log/verifier prove455updates/909microbatches,184finite adapter tensors and184AdamW counters455. Saved RNG is448, not455.

Original500 completed304Applied/196Unchanged/0Failed:500faithful,494clean/joint(98.8%),0critical, stillbelow495. Three named shards used462strict typed13field prior successes and38personal pairs, all38cross-read by root. Actual helper source before its typed-equality fix is preserved as unused-on-V9 history alongside fixed source and independentPASS. This does not claim500new personal reads.

One small code snapshot archive contains39source files plus its internal index; all39source byte hashes match the freeze and existing curated sources. The38MB upstream llama tar is metadata-only. No weights/native binaries/fresh corpus/author/commitment contents/factor3unused experiments are included. No resource orWindows qualification is claimed.


## Completed factor3 and three resource comparisons (phase13)

Fixed fractions t050/t075/t0875 were all frozen before the first of1500 total retired-case replays. Canonical joint results495/494/494, each500faithful and0critical, use strict typed13field inheritance plus31/32/30 personal pairs cross-read by root. Actual zero-update derivation/source/legal and both historical405/455 training endpoints are retained.

The same t050 native weights and immutable99da evaluator build produced three first10-retained complete-delivery cohorts: lookup16/micro32 805.3532ms,695144448B (latencyFAIL);lookup31/micro32 929.6313ms,684072960B (latencyFAIL);lookup16/micro64 780.6206ms,693895168B (Linuxpartial resourcePASS). All caps are805ms/747500000B. No trial was dropped or rerun.

The lookup31 historical condition label still says lookup16; actual manifests/input/reportidentity prove31, with the explicit clarification preserved. This does not claim a newly observed nativeargv. Profile32 alone met the retired99percent text threshold and failed latency. Micro64 passed resources but its full500 text quality was untested at that postcheck. These results cannot be combined into same-profile qualification. Active1126/new quality and unusedR16/intermediate/sanitation/fresh data are excluded. No Windows/whole-app/fresh-population qualification is claimed.


## Completed micro64 knownsets and retired round2 pair (phase14)

The same selected t050 micro64 profile was evaluated on all known sets: joint495/500 retired,544/546 development and78/80 hard cases, with0/1/2 critical errors respectively. These are consumed regression diagnostics; they are not pooled into a fresh score, and perfect hard80 is not an additional primary gate. The historical micro64 Linux partial resource result remains780.6206ms/693895168B in phase13.

The subsequent single-use paired round2 test is complete and FAILED the required495/500 selected gate. Selected text achieved462joint,482faithful,475clean and10critical; original control achieved430joint,466delivered-text faithful,460clean and16critical. All500 cases per model remain in the denominator. The control has497 structural successes and3provider failures; delivered fallback text can retain semantic-axis labels but never receives joint model-success credit. The paired table is411bothpass,51selected-only,19control-only and19bothfail.

Selected500 used actual personal review with no development inheritance. Control reused348 strictly typed13-field identical successful judgments from the same fresh selected test and personally read152 actual control pairs. Original shards, read receipts, independent cross-reviews, conflicting policy judgments and final root overlays remain exact historical evidence. The retirement receipt documented at least6 confirmed failures before full review; it is not the final462 score. The corpus is now irrevocably retired, with its commitment, consumed lock and six exact pinned rubric/wrapper/overlay/similarity/assembly context documents retained. No former author scripts are included.

Frozen42/45-source archives and exact executed helpers bind the historical runs. Three policy documents omitted from those old code archives are recovered by their exact hashes from immutable Git; changing live quote-v4 files are not used to recreate the old epoch. No model, native binary, audio or future fresh3/current-v4/editor/training content is included. No Windows, whole-app or population accuracy qualification is claimed.


## Completed CompactV4 transport, V10 preparation and failed source-graph pilots (phase15)

The27-source CompactV4 epoch passed strict isolated build/Core800 transport parity and714.NET/124Python/78Pester checks. Exact original source bodies, managed artifact pins, pre/post preservation and the first Core temporary-path failure plus its successful isolated check are retained. These qualify transport and contracts, not editing accuracy.

Opt-in trainer27a2 preparation, actual600 data/final checks and43+10pure tests are retained separately from active later LoRA training, which is excluded. Worst239 memory attempt01 stopped at its sampled cap; attempt02 completed one update/eight microbatches with184finite gradient/AdamW observations. Cold read-only file-cache conditions and owned RSS/cgroup metadata remain distinct; this is not app-SLA qualification.

The64-case graph pilot achieved3/16development joint and9/16faithful after the preserved overlay. The new400 native/source-graph experiment retained its full compact input plan and all80development/320training output programs/traces. It ran1000updates on319CE-eligible training cases and reached251/320training exact. Final independent/author canonical development review is40/80joint,59faithful,41clean,15accepted critical meaning changes and4separate rejections. Original shards, severity overlay and strata are preserved. Static399/400coverage, training exact and semantic joint results remain separate. These are consumed same-authored-corpus diagnostics, not fresh/population/Windows or a qualified replacement model.

All464 native case-result JSONs are byte-exact recoverable from retained cache-manifest rows; original path/hash/size and recovery encoding are recorded without duplicate copies. Source closure uses exact held snapshots/receipts and existing curated bodies. Optional raw polling journals and redundant unused pool/label/Unicode downloads remain in work; terminal peaks/results and their observer bindings, actual used datasets, source tables/generators/licenses and full case outputs are public. No weights, feature floats, optimizer files, binaries, activeLoRA or futurefresh3 material is included.

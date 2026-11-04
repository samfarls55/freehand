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

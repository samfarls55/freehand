# ScribeKey training evidence

This separate collection preserves public data actually used for the local ScribeKey
fine-tuning work, exact historical trainer bytes, run snapshots and completed development
replays. The earlier small-model evidence tree remains unchanged. See the
[main progress document](../../TRANSCRIPT-CLEANUP-SCRIBEKEY-TRAINING.md).

The current user threshold is **495 of 500 outputs jointly faithful AND clean/usable**
(99%). [Revision 02](metadata/acceptance-threshold-revision-02.json) supersedes the
historical 98% task-start record without changing the final corpus or rubric. The known
commitment is `def0ae07b9e9fa922d2b11a90f0e981de12be499d5fdadaddcff3f0f6ef8a643`.
**This collector has not opened, copied or hashed the blind corpus, its author scripts
or its case contents.** Only its already recorded commitment/count/threshold are retained.
No blind acceptance result or qualified production model is claimed here.

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
zero fresh final qualification. No fresh 500-case blind rows are present.

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
never calls agent listing or opens the blind directory.

All paths in source records are historical workspace provenance, not portable live links.
[The collection catalog](collection-manifest.json) records scopes, hashes and snapshots.
[The SHA-256 index](evidence-files-sha256.json) covers every retained file except itself.
The ignored source collector is `work/cleanup-scribekey-training-2026-11-03/collect_public_training_evidence.py`.
Later evidence uses a new phase/revision path; existing snapshots are never overwritten.

Training progress and development improvements do not establish 99% final accuracy,
Windows behavior or the application limits of 747,500,000 host-memory bytes and 805 ms
from ready release to complete text. Windows hardware is unavailable in this task.

# ScribeKey training — active research checkpoint

The user authorized targeted training with ScribeKey as the base and subsequently
raised acceptance to **99%**. The current gate requires **495 of 500 complete
outputs to preserve meaning and be directly usable cleaned text**. The full-app
resource limits remain 747,500,000 host-memory bytes and 805 ms from ready release
to complete delivery. **No new trained model is qualified yet.**

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
Its contents remain unseen by the training controller and trainer. Mechanical
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

## Current experiment and remaining qualification

The approved next curriculum has 1,364 examples: 1,024 selected from the expanded
training pool, 100 disclosed longer compositions, and 240 examples derived from
80 additional authored semantic contrasts. It is 35% unchanged and includes
literal cases. Its SHA-256 is
`502f7884a5b8be4db1a20a0154cfbc4b646168b4e1b812cddcad0fe6e7154b4d`.
Training uses the original base again, three epochs and the same LoRA rank.
A workspace restart interrupted the first attempt before its first saved
adapter; that attempt is retained as interrupted. The restarted run saves more
frequent durable checkpoints. Optimizer, learning-rate, RNG and batch-position
recovery have separate correctness tests.

All 32 training/evaluation tool tests pass in the isolated environment, including
99% boundary checks, complete-denominator checks, literal restoration, merge
precision and exact optimizer/RNG/batch-position recovery. New candidate freezes
archive the exact critical source bytes before inference; the earlier runs retain
their original hash-only source metadata and independently pinned artifacts.

The active run's older writer does not serialize RNG states. Its recovery needs
an explicit deterministic-model compatibility option; the new writer saves RNG
states. Executed sources, configuration and this distinction are retained.

An audit found that all current training targets are word-order-preserving
subsequences, while several correction diagnostics require moving an existing
object noun into the surviving clause. A separately authored curriculum adds
those source-copy repairs for a subsequent experiment if needed. Training loss
does not establish accuracy, and additional epochs alone cannot repair missing
task coverage.

Future exports can merge to F16 before Q4/Q3 quantization to preserve smaller
updates. Reduced precision must pass its own quality checks. The prior ScribeKey
Q4 partial speech/cleanup path exceeded the RAM allowance, so quality gains alone
do not establish resource compliance. Candidate selection and source/artifact
freezes precede opening the final 500 cases. Any test-informed behavior change
requires retiring that test and obtaining a new independent set.

The user currently has no Windows test machine. Linux work can measure the real
speech/Core/cleanup path and prepare verified custom Freehand bundles, but cannot
certify desktop memory, GPU offload or actual Windows delivery. No normal
installation update, model-default promotion, push, PR, merge or release has
occurred during this research.

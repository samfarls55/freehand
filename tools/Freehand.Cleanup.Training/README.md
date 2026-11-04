# ScribeKey cleanup fine-tuning

This research tool trains a derivative of the pinned ScribeKey Fast v1.1 original
BF16 checkpoint. Training and conversion run separately from Freehand and do not
change the application's dependencies, installation, profile, selected model or
normal speech configuration. All training inputs are transcript text, not audio.

The training contract is exactly the application's `ScribeKeyFast` completion
contract: one BOS token (ID 1), the prescribed semi-casual/prose/general control
line and `### Input`/`### Output` sections. EOS is ID 7. Only answer tokens and EOS
receive loss. Complete examples exceeding the configured token cap are rejected;
there is no input or target truncation.

`pipeline.py` imports the existing specialist literal protocol v3. It builds
opaque identifiers from the input, maps the same identifiers into the target and
proves an exact restoration round-trip before tokenization. Targets that remove,
modify or reorder protected quotes/dictionary blocks are rejected. The training
data supplies the intended edit; the trainer does not generate its own targets.

## Environment and source

The first run reused the existing isolated Scribe conversion environment, with
`torch==2.11.0+cpu`, `transformers==4.57.6`, `safetensors==0.8.0` and
`tokenizers==0.22.2`. It uses a small explicit LoRA implementation and needs neither
PEFT nor Accelerate. `adapter-config.json` records the actual runtime versions.
CPU training uses float32, four intra-op threads and one inter-op thread. Native
BF16 training acceleration is not assumed on the recorded EPYC machine.

The original model weight hash must be
`1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a`.
Loading rejects missing, unexpected or shape-mismatched model tensors. The
`profile` command also requires greedy generation of the publisher's known BF16
example to match and proves zero-initialized adapters leave baseline logits
bit-identical. That verifies this loading/rendering path on that example; it is
not an accuracy measurement.

LoRA wraps attention, convolution projection and feed-forward linear layers,
excluding the tied embedding/output matrix. Original weights remain frozen.
Rank 8 across the original checkpoint exposes 2,998,272 trainable parameters.
The update is `W + (B @ A) * alpha/rank`; B starts at zero. Answer-position-only
logits avoid allocating a full vocabulary matrix for masked prompt/padding tokens.

## Data and commands

Each UTF-8 JSONL row has at least `id`, `input`, `target`; research datasets also
include `family`, `group_id`, `split`, `source` and `edit_needed`. Training accepts
only rows labeled `train` or with no split. Keep train/development and untouched
qualification data separate. Never select a checkpoint using the blind corpus.

The user's current acceptance target is **99%** of complete delivered outputs
that are both faithful and clean/usable: at least **495 of 500** final cases.
Failures and incomplete delivery remain in the denominator. Named semantic
review is required; target matching and training loss do not establish this
accuracy. The original 98% reports remain preserved as historical results.

Run from the repository root, selecting the isolated Python explicitly:

```sh
TRAINING_PYTHON=work/cleanup-small-models-2026-11-03/scribe-precision-source/conversion-env/bin/python
SCRIBE_SOURCE=work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model

"$TRAINING_PYTHON" tools/Freehand.Cleanup.Training/pipeline.py profile \
  --base "$SCRIBE_SOURCE" --output work/training-profile-new --threads 4

"$TRAINING_PYTHON" tools/Freehand.Cleanup.Training/pipeline.py train \
  --base "$SCRIBE_SOURCE" --train work/data/train.jsonl --output work/training-run-new \
  --threads 4 --rank 8 --alpha 16 --learning-rate 0.0001 \
  --epochs 2 --batch-size 4 --gradient-accumulation 2 --checkpoint-every 64

"$TRAINING_PYTHON" tools/Freehand.Cleanup.Training/pipeline.py merge \
  --base "$SCRIBE_SOURCE" --adapter work/training-run-new \
  --output /tmp/freehand-owned-training-new/merged --threads 4 --dtype float16

# Optional diagnostic before native GGUF/Core evaluation; ignores reference targets.
"$TRAINING_PYTHON" tools/Freehand.Cleanup.Training/pipeline.py generate \
  --base "$SCRIBE_SOURCE" --adapter work/training-run-new \
  --input work/data/development-inputs.jsonl --output work/transformers-predictions-new.jsonl

"$TRAINING_PYTHON" -m unittest discover \
  -s tools/Freehand.Cleanup.Training -p test_pipeline.py -v
```

Every output directory must be fresh. Adapters use safetensors, with exact module
names and rank/scaling in `adapter-config.json`. `training-log.jsonl` records each
optimizer step, average microbatch loss, learning rate, gradient norm, processed
answer tokens and elapsed time. Periodic `checkpoint.safetensors` and
`checkpoint.optimizer.pt` are replaced atomically within this newly owned run;
the final adapter and optimizer are separate files. `training-result.json` binds
the final adapter hash. A requested `--max-steps` pilot is labeled as limited.

`--resume-adapter` starts from a compatible earlier adapter with a fresh optimizer.
It verifies base hash, rank, alpha and exact target module inventory and records
the parent adapter hash. It does not silently resume an optimizer or alter the
prior run. New runs copy their executed source into `training-source.py` before
loading weights; the first pilot's identical source was externally snapshotted
while the source file still matched its recorded hash.

`--resume-checkpoint` instead recovers the optimizer, global step/microbatch,
processed-answer count and Torch/Python RNG states. Keep the original data,
epochs, batch/accumulation, seed, learning rate and scheduler settings; the loader
rejects mismatches. Epoch bucket order is reconstructed from the original seeded
shuffle and processed microbatches are skipped, so learning rate and optimizer
counters continue at their original positions. Use a fresh output directory and
the checkpoint directory referenced by `latest-checkpoint.json`:

```sh
"$TRAINING_PYTHON" tools/Freehand.Cleanup.Training/pipeline.py train \
  --base "$SCRIBE_SOURCE" --train work/data/train.jsonl --output work/recovered-run-new \
  --threads 4 --rank 8 --alpha 16 --learning-rate 0.0001 \
  --epochs 2 --batch-size 4 --gradient-accumulation 2 --checkpoint-every 32 \
  --resume-checkpoint work/interrupted-run/checkpoints/step-000128
```

Complete new checkpoints are committed as fresh directories before their latest
pointer is replaced. They contain adapter/optimizer/RNG bytes, source/config and
hash-bound progress metadata. Two recovery generations remain, with immutable
adapter snapshots every 128 steps. The small stochastic continuation test proves
four uninterrupted updates equal two updates plus save/reload plus two updates,
including exact weights, optimizer, loss, learning rate and RNG. Separate actual
trainer tests prove bucket skipping across epoch boundaries and final partial
gradient accumulation produce bit-identical adapters.

An environment restart interrupted the first V3 run before its first checkpoint.
The restarted V3 job already executing older source writes adapter/optimizer
pairs every 32 steps; a work-only watcher verifies both complete file generations
and retains their progress/source/config under `latest-recovery.json`. These
legacy checkpoints **did not serialize RNG**, and the default loader rejects
them. The explicit `--allow-deterministic-legacy-resume` option is limited to that
documented deterministic LFM2 path, whose forward/optimizer have no stochastic
operations and whose epoch order uses independent seeded generators. Its
provenance records the missing RNG serialization; it does not claim those states
were captured. New checkpoint writers store actual RNG states.

`generate` loads either the original model or a saved adapter and records raw and
restored text per input. It does not use reference targets. An incomplete response
or failed literal restoration retains the original and records failure. This is a
Transformers diagnostic, not the production Core/ASR path, a semantic judge or an
application latency measurement. Native Q4 and full Core replay remain necessary.

Merge reads original tensors, applies the LoRA update and writes a standard
safetensors derivative. The typed `--dtype` choices are `bfloat16` (the historical
default) and `float16`. F16 retains smaller merged updates that can round back to
the original value in BF16. It preserves the tokenizer, architecture and notices;
only the derivative configuration's dtype field changes when needed. Exact
dtype/config changes and the fraction of nonzero float32 updates surviving the
selected storage precision are recorded. The original BF16 checkpoint and
vocabulary stay unchanged. A small-matrix test verifies both dtype paths and
confirms the source weight/config hashes remain unchanged.

Merged 16-bit weights plus F16 GGUF intermediates need about 1.42 GB in addition to model
and process memory; an owned temporary directory can keep them off the small
persistent disk. The final Q4 needs its own persisted provenance and exact hash.
See `EXPORT-EVALUATE.md` for native conversion/evaluation commands when available.

Training losses, exact-string targets and synthetic test percentages are not
proof of reliable meaning preservation. Final evaluation must retain raw outputs,
separate adapter preservation from model behavior, and assess useful cleanup as
well as fidelity. Whole-app resource qualification still requires the complete
Windows desktop/ASR/cleanup/delivery path with host and GPU accounting. Nothing in
this tool certifies those measurements or promotes a model automatically.

Derivatives must preserve the original LFM/Sotto/ScribeKey notices and required
credit, including **Derived from ScribeKey Fast by ScribeKey**.

## Optional original-IQ4 frozen-base experiment

The legacy default remains the original BF16 source. The explicit
`--training-base-mode original-iq4-dequantized-fp32-v1` route instead verifies
both the original BF16 provenance and the exact direct-original IQ4 control
SHA256 `82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174`.
It inversely maps all 148 tensors, restores ten convolution singleton dimensions,
and decodes them directly into an FP32 HF model in RAM. The tied output head is
preserved. This is quantization-aware base selection, not a four-bit training
kernel: the decoded base occupies approximately 1.42 GB RAM and is never saved.

Initialize this optional route using `--resume-adapter` and an explicit complete
`--parent-adapter-sha256`; this starts a fresh AdamW optimizer. Its configuration
binds the actual frozen GGUF, original source/config/tokenizer, decoder/mapping,
parent adapter/config, training implementation, and numerical emulation modes.
Exact checkpoint recovery requires the same identities. The legacy `merge` and
`generate` commands reject adapters from this route rather than silently applying
them to the BF16 base. Deployment requires the exact original native IQ4 base
and an **unmerged F32 adapter**, with separate conversion and evaluation receipts.
The external native adapter scale is 1; alpha/rank scaling is encoded internally.

Two optional numerical emulations are available, both disabled by default:

- `--kv-roundtrip f16` rounds post-RoPE keys and projected values through F16
  before attention/cache storage, with identity backward gradients. Queries and
  the raw LoRA input remain FP32.
- `--activation-quantization native-q8-k --native-runtime PATH` uses the exact
  pinned Linux Haswell `quantize_row_q8_K` and native `dequantize_row_q8_K` symbols,
  with 256-value/292-byte blocks and identity backward gradients. The frozen
  quantized Linear path receives the round-tripped activation; the parallel
  LoRA path retains its original FP32 input. All 92 layer matmuls and the tied
  output matmul are covered. Both native library hashes and the complete
  per-matrix type/input-width inventory are checkpoint-bound.

These options do not establish native-forward equivalence. The bounded proof
on six consumed cases found 5/6 native output agreement for all four activation/KV
combinations, while original-F16 reconstruction agreed 6/6 with and without the
adapter. Preserve that limitation when interpreting subsequent training results.

`--expand-adapter-rank` can explicitly initialize a larger-rank phase: copy the
old A/B blocks, initialize additional A rows with a local seeded generator, and
set additional B columns to zero. Alpha/rank must stay constant. The trainer
checks matrix deltas and actual initial logits before optimization. The real
rank8-to16 smoke exceeded the tight logit tolerance under F16-KV rounding and
stopped correctly; rank16 is not a qualified continuation. The proposed first
control keeps rank8/alpha16. A tiny-model test passing does not supersede that
real-model failure. No accuracy or resource gate is relaxed by these options.

## Optional token-unlikelihood ablation

`--unlikelihood-events PATH --unlikelihood-eta ETA` adds penalties at reviewed
gold-prefix token positions. The positive training file, source-derived masks,
prompt/token fingerprints, gold/rejected IDs, EOS7, selected-logit positions,
and every disclosed exposure of each selected source are verified before use.
The event loader annotates existing rows and never adds positive examples.

For marked logits, the stable penalty is
`logsumexp(all_logits) - logsumexp(logits_except_rejected_id)`. The objective is
`(sum CE_assistant + eta * sum UL_events) / N_assistant`. It reuses the existing
chosen forward and output-head logits; no rejected-sequence/reference forward
or inference change is introduced. Per-microbatch normalization and the existing
gradient-accumulation divisor remain unchanged, and logs record each actual
assistant-token denominator. Eta0 uses the exact historical mean-CE operation.

Both comparison arms must use the **same frozen positive file and event artifact**,
parent adapter, base, rank, seed, batch order, optimizer initialization, learning
rate and stopping budget. Use fresh output directories with `--resume-adapter`
for both arms; change only `--unlikelihood-eta 0` versus
`--unlikelihood-eta 1`. The supported cap is2 for a separately approved follow-up,
not an automatic sweep. Bind the event artifact to the final combined positive
file and list all scheduled positive instance IDs; the raw32-pair proposal is
not a substitute for that final binding.

Event schema/file, positive file, tokenizer, exact per-row mapping, eta and source
hashes are strict checkpoint identities. Exact recovery rejects a missing or
changed objective artifact/configuration before restoring adapters or AdamW.
Tiny tests prove high-confidence rejected-token stability/gradient direction,
shift/padding/EOS mapping, one chosen forward/head call, varying-length token
normalization, and exact eta0 adapter/optimizer/RNG identity, including the trainer
CLI. No training run or accuracy claim follows automatically from these tests.

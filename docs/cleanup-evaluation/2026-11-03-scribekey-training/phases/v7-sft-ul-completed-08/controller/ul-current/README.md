# V7 native export and first retired500 preparation

Work-only source. Preparation starts no model, converter, build or inference.
Wait for the training agent's explicit completed-result/hash verification and CPU
release, and root's scheduling authorization. The SFT control runs first; after
its complete retired500 report, release CPU for eta1 training while independent
reviewers grade all500 control outputs. Broad546/hard80 are held for a later
root-scheduled handoff. No fresh-round2 path or blind command is implemented.

`run.py --arm sft|ul` reuses the proved V6 conversion/Core controller. Both arms
require source8c609… (preregistered Gitbc9ec3a), exact positive2754/fa18…, all32
canonical599435… events, the root121391… review, bound515947… events, all64
exposures7b725…, mappingff9d…, binding5c1a… audit and datareviewc757….
Eta0/eta1 and output directories are the only preregistered arm differences.
The final config/result/source and complete345-update/689-microbatch training
log must agree, with source-validated64 exposure mappings and a logged event total64, with seed42. The trainer does not log individual exposure IDs; exact per-ID training order is not independently reconstructed. Fresh arms use
fresh AdamW initialized from the V6 adapter157af…/config1a159…; a recovery must
bind exact saved Torch/Python RNG and source. The controller records and checks
actual checkpoint336 RNG bytes, without claiming final345 RNG was serialized.

Deployment is the original IQ4 base82ab… plus a separate184-tensor F32 native
LoRA (rank8/alpha16, internal2, external1). Original BF161a9a… is provenance,
architecture and tokenizer evidence. There is no merge, requantization or
numerical HF/native equivalence claim. Every custom→PEFT→GGUF tensor payload
is checked byte-for-byte. Original notices and pinned native/converter source,
Q8 libraries, exact six-DLL Probe9295… generation and typed deployment receipts
are retained. Large files stay in new owned UUID `/tmp` directories.

After a new create-only freeze, the controller runs actual Core once on the
pinned def0… retired corpus, phase `development`, preserving exactly500 ordered
IDs and every provider outcome/delivery. Core candidates are post-trim-v1 and
literal restoration; pretrim raw completions are not implied. Provider failures
and original fallback receive no model-success credit. Conversion and structural
completion are not99% accuracy or whole-app/Windows SLA qualification.

Example, substituting only the training owner's final release values:

```sh
PYTHON=work/cleanup-small-models-2026-11-03/scribe-precision-source/conversion-env/bin/python
"$PYTHON" work/cleanup-scribekey-training-2026-11-03/v7-native-export-preparation/run.py \
  --arm sft \
  --run-dir work/cleanup-scribekey-training-2026-11-03/pipeline/v7-sft-01 \
  --training-data work/cleanup-scribekey-training-2026-11-03/audit/v7-positive-curriculum/positive-2754-final.jsonl \
  --expected-adapter-sha256 FINAL_RELEASE_ADAPTER_SHA \
  --expected-train-sha256 fa18dfcd5faf4c5a7a20f8e9b669caaa2ec3c8e098b27b17a25128eda1d592a6 \
  --expected-training-source-sha256 8c609cd04f058adb565dd489029e6daa3b1728d5ea57420541e5a8b990f59fad \
  --expected-steps 345 \
  --output work/cleanup-scribekey-training-2026-11-03/native-lora-v7-sft-01-export \
  --freeze work/cleanup-scribekey-training-2026-11-03/evaluation/v7-sft-01-native-LoRA-F32-freeze.json \
  --evaluation-output work/cleanup-scribekey-training-2026-11-03/evaluation/v7-sft-01-native-LoRA-F32-retired-primary500-core
```

For the second arm use `--arm ul` and separate actual final run/output/freeze
paths. Every output must be fresh. Preserve any interrupted or failed evidence;
never delete/relabel an old run. An environment recovery needs explicit,
transparent scheduling and byte-identical candidate/input provenance.
`test_controller.py` uses only synthetic dictionaries; it never loads weights,
Torch, native workers or any evaluation corpus.

The authorized SFT infrastructure recovery is `v7-sft-01` through192 plus
`v7-sft-02`193–345. The parent raw suffix193–207 stays preserved and all15
replayed nonelapsed records must match exactly. The separate canonical full-epoch
log, both raw log hashes/configs, checkpoint192 saved RNG/source/config inventory,
and final verifier lineage are pinned and rehashed after conversion and Core.
The original config proves fresh V6 initialization; final `resume_adapter_sha256`
may legitimately be null for exact optimizer/RNG recovery.
Each logged optimizer loss is recomputed from CE and eta×UL microbatch metrics
using relative tolerance2e-5 and absolute tolerance2e-7 for FP32 arithmetic.

The same bounded recovery mechanism also accepts the root-authorized UL arm
`v7-ul-01` prefix1–32 plus `v7-ul-02` suffix33–345, bound to checkpoint32
state7d1fa2a8… and saved RNG/config/source. The original discarded33–47 suffix
is preserved and must match its15 replayed updates bit-for-bit except elapsed
seconds. Both arms have explicit separate recovery registrations; a cutoff,
checkpoint or arm cannot be silently relabeled. The final canonical689
microbatches/logged64 event total and eta1 CE+UL objective are counted once.
The SIGKILL cause is unknown; this controller makes no OOM-cause claim.
The exact SFT-executed54a7c62… controller/tests/docs and independent audit remain
in `historical/sft-executed-54a7c62d/`, as well as the actual SFT export receipt.

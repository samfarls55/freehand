# V6 native adapter export preparation

This is prepared work only. The controller has not been executed. V6 training
owns the heavy CPU window; wait for the training agent's explicit process-exited,
final-result/hash/source/data verification and CPU release before running it.

The script never merges or requantizes the base. It verifies the completed run's
actual `original-iq4-dequantized-fp32-v1` numerical training base (original IQ4
82ab…), original BF16 provenance (1a9a…), initialization parent (741826…), and
93 native-Q8_K activation linears. The runtime remains the exact original IQ4
base with one separate F32 native adapter at external scale1. Alpha16/rank8 is
already embedded as internal scaling2. The controller does not claim that the
HF training forward and native runtime are numerically identical.

After checking the final config/result/source/data pins, it maps all184 custom
FP32 tensors into standard PEFT without a byte change, uses the already proved
pinned converter, and verifies every GGUF tensor's name, shape, dtype and value
SHA. It verifies original architecture/tokenizer/runtime/notices, the exact new
Probe92956561…, and training Q8 library/inventory receipts. All new weight files
stay in an owned UUID directory under `/tmp`; small reports, executed source and
inherited notices stay under a fresh `work` output directory.
After verified export, `performance-input.json` supplies only model/adapter and
conversion/training receipt pins to the separate performance controller. It has
no corpus, outputs or quality scores and does not authorize any performance run.

It then creates a NEW model/adapter/source/DLL freeze and runs all500 cases from
`validation-retired-primary500/corpus.json` through actual Core, phase
`development`, preserving failures and every case. There is no fresh-round2
path or blind-final command in this controller.

Only substitute values supplied by the final training release, including any
recovery run's actual directory. Example invocation after explicit CPU release:

```sh
PYTHON=work/cleanup-small-models-2026-11-03/scribe-precision-source/conversion-env/bin/python
"$PYTHON" work/cleanup-scribekey-training-2026-11-03/v6-native-export-preparation/run.py \
  --run-dir work/cleanup-scribekey-training-2026-11-03/pipeline/FINAL-V6-RUN \
  --training-data ACTUAL_FINAL_TRAINING_DATA_PATH \
  --expected-adapter-sha256 FINAL_ADAPTER_SHA \
  --expected-train-sha256 FINAL_DATA_SHA \
  --expected-training-source-sha256 EXECUTED_SOURCE_SHA \
  --expected-steps FINAL_GLOBAL_STEPS \
  --output work/cleanup-scribekey-training-2026-11-03/native-lora-FINAL-V6-RUN-export \
  --freeze work/cleanup-scribekey-training-2026-11-03/evaluation/FINAL-V6-RUN-native-LoRA-F32-freeze.json \
  --evaluation-output work/cleanup-scribekey-training-2026-11-03/evaluation/FINAL-V6-RUN-native-LoRA-F32-retired-primary500-core
```

Every output must be fresh. Conversion or evaluation failures preserve previous
outputs, current logs, and temporary weight files. Conversion success and Core
completion establish neither99% semantic quality nor whole-app SLAs. Root must
arrange independent complete output-bound semantic review before selecting a
candidate or authorizing any new one-time paired blind qualification.

The exact training dataset file is hashed before and after execution, rather
than trusting its hash only inside the training config. The exact six-DLL
generation receipt is itself pinned; the retired corpus must match def0ae…
before its500 unique ordered IDs are read. Final Core completion requires the
same complete inventory and a successful base/adapter/scale deployment receipt.
Ordinary provider/meaning failures remain in the full report and are reviewed;
they are not filtered out or made a reason to discard the cohort.

After the first retired500 report and explicit CPU scheduling, the separate
`run-knownsets.py --candidate-freeze SAME-FREEZE.json --output-prefix FRESH-PREFIX`
runs546 then hard80, Core only, once each. It pins the known dataset hashes and
exact ordered IDs and verifies deployment receipts. All three sets retain Core
candidate/error/delivery metadata; the schema retains post-trim/restored
candidates and does not supply pre-trim raw completions. Provider failures and
fallbacks remain failed cases in the complete denominator. No extra model pass
is requested for raw text.

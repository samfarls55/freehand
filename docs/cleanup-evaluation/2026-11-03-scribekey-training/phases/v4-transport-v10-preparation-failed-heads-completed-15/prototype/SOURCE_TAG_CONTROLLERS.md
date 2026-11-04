# Source-tag graph pilot controllers

These NEW files preserve the frozen dense-head controllers and feature cache.
They implement preparation for a different architecture, not a quality or SLA
claim. No Torch, native model or actual cached features were executed/read while
preparing the controllers. Tests used tiny synthetic metadata/files and mocked
processes only. Actual Torch unit/training requires a new explicit root grant.

`source_tag_unit.py` performs synthetic tests in a20-second supervised worker:
finite gradients, active-branch/all-ignored loss behavior, bitwise checkpoint
roundtrip, strict malformed-checkpoint rejection and exact default-copy decoding.
It uses no cached features or native model, performs zero optimizer steps and
writes no candidate checkpoint. It must pass before the training pilot.

`source_tag_train.py` reuses only the fixed pilot plan SHA
`3febe6cc32d274fde91171fd8b61da61eef6b92699440f60c87e06663d79597b`
and explicitly released native64 cache. It verifies the cache release binding
before lazy Torch import, then source/encoder/feature hashes and exact source atom
shapes. Cached atom features are read-only; no native server is called and no
base/adapter weights are copied. The frozen plan is not edited or relabeled.

New graph labels are compiled with `build_tag_label`; every supported label must
execute exactly to its frozen canonical target. Unsupported labels remain in the
64-case inventory and skip only CE. Every feature-available development case
still receives source-only forward/decode regardless of label support. Counts
remain48train/16development; missing/rejected/deadline cases retain explicit
records and receive no fallback or success credit.

The head receives only `[B,S,1024]` source features and source padding. It adds
the virtual BEGIN node internally. Labels pad only the node dimension with-100:
count[N], case/form/repair/pointer/insert_count[N,3], insert[N,3,4]. There is no
global target length, learned whitespace, target input or teacher-forced decoder
input. Rendering/finite graph constraints belong to the new contract and frozen
old executor. Fixed loss weights come from the source-pinned model file.

The pilot defaults to300 steps, batch4, AdamW LR.001/weight-decay.01, seed20261104,
two Torch threads/one interop thread and110 seconds of worker work inside a120
second supervisor. The loop reserves25 seconds for fixed development-first and
all-case diagnostics. These are bounded research settings, not a tuning result.
`used_for_ce` is tracked only after completed optimizer steps; eligibility is a
separate field. A stop/deadline cannot falsely mark untouched cases as trained.

Both CLIs require the original conversion-env interpreter spelling:

```text
/workspace/freehand/work/cleanup-small-models-2026-11-03/scribe-precision-source/conversion-env/bin/python
```

Root creates a separate grant with `operation` equal to
`copy-editor-source-tag-unit` or `copy-editor-source-tag-train64`, typed
`cpu_granted:true`, finite `max_wall_seconds` at least20 or120 respectively,
`pins` equal to `source_tag_runtime.required_pins()`, exact absolute `output_dir`
and `settings_sha256`. The unit settings come from `unit_settings()`, training
settings from `training_settings(args)`. Training additionally pins `plan`,
`cache` and `cache_cpu_release`. The required source inventory includes the five
new contract/model/train/unit/runtime files and all three imported frozen editor
files (`__init__.py`, `core.py`, `head_contract.py`). Sources and inputs must be
independently reviewed and fixed before granting execution.

The stdlib supervisor owns a fresh Popen PID/process group/session, emits PID
immediately and applies the work timeout, TERM/KILL and wait/reap. Cleanup has up
to two additional seconds. Reports are create-only. Its explicit CPU release is
true only after the child is reaped and its owned group is gone. Output folders
must be fresh; old evidence is preserved.

Training writes label inventory, config/vocabulary, actual optimizer history,
all64 status rows, all16 development outputs, all64 inference outputs, a small
new head and a candidate manifest binding source/cache/settings/head hashes.
The candidate remains inactive. Exact canonical agreement is a diagnostic; it
does not establish faithful clean-text quality,99% acceptance or Windows
whole-app speed/memory. Checkpoint and combined worker artifacts are capped
below10MB; failed output is retained for review.

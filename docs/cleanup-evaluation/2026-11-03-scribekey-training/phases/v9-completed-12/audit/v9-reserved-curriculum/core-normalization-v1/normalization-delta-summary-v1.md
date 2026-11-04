# V9 actual Core normalization deltas

There are **zero** input or target text changes across all 80 approved pairs. The 160 saved Core fixture results preserve every source/target string exactly, including all 38 quoted payloads. The resulting labels remain 44 cleanup pairs and 36 clean controls.

The normalized JSONL adds train split and source/export/prompt/mask provenance fields; these metadata additions do not change the authored text or semantic labels. All 160 saved prompt/mask comparisons and all 80 protected-target roundtrips passed. The raw files, drafts, review receipts and prepared-only historical manifests remain unchanged.

All examples remain reserved and unused. The independent saved-output alignment receipt is tracked separately; root still owns the opaque overlap check and any conditional future training selection. No model, native worker, build or training job ran.

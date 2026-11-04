# Final reserved V9 status

All 80 raw pairs passed independent semantic review. Their actual Core-normalized forms then passed independent full-field alignment and saved-prompt/mask review. The balance remains 44 cleanup pairs and 36 clean controls; all 38 quoted payloads stay exact once in source order. There are zero input or target text changes.

The final normalized candidate is `core-normalization-v1/train-80-core-normalized-v1.jsonl`, SHA256 `a5b2963faf8bb5ad632dc5915c781bbf0c30aa3b3a37d032a7c1c640d6a076c4`. The raw source is `train-80-v1.jsonl`, SHA256 `b684e53fe1dcfda124f1370309b7ee2141105407fd07f456f513507839b09820`.

`normalization-final-approval-v1.json` binds the complete semantic and preprocessing review chain. The independent alignment receipt is `core-normalization-v1/independent-zero-delta-alignment-review-v1.json`, SHA256 `7a3e57ac726bc64c413818e8c994060e214a02a9349765d84aaf02c49262055b`. The readable zero-change result is in `core-normalization-v1/normalization-delta-summary-v1.md`. All 160 Core fixtures, 80 loader rows and quoted-target roundtrips pass.

**The 80 pairs remain reserved and unused, outside active V8.** Root owns the opaque overlap check and any later conditional training selection. These examples may remain unused if V8 meets the goal. No source, parent configuration, trainer or negative event changed; no model/native/build/training job ran for this preparation. The actual preprocessing used only the authorized existing Probe 6de0 under nice 19 and `DOTNET_PROCESSOR_COUNT=1`, with all eight managed/metadata source and copied files rehashed before and after.

This final stage supersedes prepared-only and pending-review annotations in `manifest-v1.json`, `CURRENT-RESERVED-STATUS.md`, author notes/preflight and the initial Core-completion receipt. All those historical files, drafts and reviews remain preserved unchanged.

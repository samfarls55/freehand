# Reserved V8 curriculum status

All 240 authored pairs passed independent review before preprocessing: 168 cleanup examples and 72 unchanged controls, 40 rows per family. The original raw files and approval history are preserved. This curriculum remains **reserved and unused**; no training activation or model-quality result is implied.

`normalization-completion-v1.json` records the actual 480 Core input/target preprocessing fixtures run under nice 19 with `DOTNET_PROCESSOR_COUNT=1`. No model, native worker, training or build ran. All 240 source prompts and 240 target prompts agree byte-for-byte with the protected-pair loader, all 240 normalized rows pass the loader, and all 10 quoted payloads roundtrip.

Core made one numeric-format change in clean control 153 on both input and target: `buying twelve batteries` became `buying 12 batteries`. The two-batteries-per-lamp and six-lamps facts remain intact; the pair remains unchanged. All other 239 source/target texts are unchanged. The actual delta and full transformation mapping are in `core-normalization-v1/normalization-changes.json` and `row-transforms.jsonl`. Independent alignment/delta review is requested separately; its final receipt will supersede this historical pending status.

The candidate for any future selected curriculum is `core-normalization-v1/train-240-core-normalized-v1.jsonl` (SHA256 `0dfc50fe433bda477666fcad5a91bb3a4356e1ded50543c6ff818db9a4e645dc`). Root still owns the opaque overlap check and conditional training decision. The initial `README.md` and `manifest-v1.json` remain immutable records of the earlier raw/prepared-fixture stage. No active training data, UL contrasts or repository source were changed.

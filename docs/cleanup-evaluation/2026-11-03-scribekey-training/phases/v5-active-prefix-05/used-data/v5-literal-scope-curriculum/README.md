# V5 literal and local-scope training curriculum

The complete input is `train-180-v1.jsonl`, SHA-256 `4a1b524a16075d931a68610d885008856141f3411beae26bac68ed03d6e0ce0e`. Counts: 60 active protected-literal corrections, 40 corrections with later unretracted old-word references, 40 minimal repairs, 40 unchanged controls. The file uses exactly the requested six fields. Do not add the authoring-part files to it.

All 180 source/target pairs were personally reviewed by the primary assistant. The first 100 are author self-review; the delegated last 80 also received an independent review by the primary assistant. No remaining semantic defect was identified. Root independent review and hash-only overlap checks remain pending. These reviews are assistant judgments, not human review or model accuracy results.

Every quoted payload is retained exactly once and in source order. Protected old correction values remain only in explicit inactive negative context. The existing pipeline `load_data` and `protected_pair` loaded all 180 rows and round-tripped 127 protected payloads. Validation imported no model packages and called no model/training function. See `loader-validation-v1.json` for the exact loader-source hash and casewise results.

The structural patterns are controlled expansions, disclosed in `manifest-v1.json`; contexts and wording were individually authored from the failure-family brief. No retired validation case text, new blind data or author artifacts were read. No app code, dictionary semantics, model weights, training or inference changed. This is training material, never a fresh final test.

Three target phrasings were refined before the combined V1 freeze (005, 013, 029) to use natural negative context; their quoted content and final intended action did not change. Original authoring-part files are preserved. Casewise semantic notes are in `casewise-audit-v1.json`.

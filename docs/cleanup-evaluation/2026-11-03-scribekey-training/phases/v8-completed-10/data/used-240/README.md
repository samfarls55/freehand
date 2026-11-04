# Reserved V8 curriculum

The complete raw component is `train-240-v1.jsonl`, SHA-256 `922af3f8564703815e69eb7a3c49dbeb870cd560556485107ad4e14d45466829`: 240 pairs, 168 edits and 72 meaningful clean controls. Each of six families has 40 pairs with 28 edits and 12 controls. All 240 actual source/target pairs are independently approved, with casewise source/target hashes and exact review/part bindings in `independent-review-rollup-v1.json`. Reviews are assistant judgments, not human review or model-evaluation results.

Canonical assembly uses families 1–5 V2 and family 6 V3. Earlier drafts and explicit overlays remain historical. The source-derived literal mask round-trips all 240 pairs and all ten quoted payloads exactly once in source order. Raw automated comparison with the prior approved 270+100 found zero input, target or pair duplication under NFC/casefold/whitespace collapse. This is not actual Core normalization or a blind overlap check.

The 480-case input/target Core fixture is prepared but unrun. It should be used only if root selects this conditional data after reviewing the current UL outcome. The active 2,754-row data and 32-pair UL source were not changed. No source implementation, model, native worker, Torch import, training or build was run or edited for authoring. No retired/development/fresh evaluation text or output was opened or copied.

This curriculum remains RESERVED and UNUSED. It may never be trained if the current experiment meets the gate. Do not curate it as used evidence or silently add it to any active run. Structural expansions and provenance are disclosed in the manifest; only the complete named raw file is a potential later training input.

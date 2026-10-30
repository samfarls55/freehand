# Kudu Writer Tiny: the missing prompt is publicly recoverable

Research date: October 30, 2026. This follow-up reads primary source only. No
complete weight file was downloaded, no inference ran, and no Freehand source
changed. `kudu-contract.json` preserves the exact initial prompt/control and
`kudu-source-index.json` indexes seven pinned MIT app-source files.

## Result

**Kudu Writer Tiny is ready for a fair POC; lack of a public inference contract is
not a blocker.** Its short model card omits the prompt, but the linked public
application has complete prose/code prompt strings, user-message construction,
ChatML rendering and decode settings. Its embedded model catalog binds that
contract to the same model file/hash already found on HF. This verifies the
publisher-declared current app inference contract, not a reproduction of the
unpublished training recipe or 270-case benchmark.

App source pin: `manasdutta04/kudu@ab4bda7d456bf5ab61ca579f538560c47c19149f`.
Model source pin:
`manasdutta04/kudu-writer-tiny@0a45ae280eb00f7cdb57647885a8eaef3acaecd1`.
File: `kudu-writer-tiny-v1-iq4_xs.gguf`, **226,661,280 bytes**, declared SHA-256
`80f9679bdf3de5f512b834357ee646af63050a3f03356120ff30cc974e10c56d`.
The app catalog explicitly declares support for both v1 (long) and v2 (short)
prompts and selects short when v2 is present. [Model card](https://huggingface.co/manasdutta04/kudu-writer-tiny/blob/0a45ae280eb00f7cdb57647885a8eaef3acaecd1/README.md),
[checksum-linked app catalog](https://github.com/manasdutta04/kudu/blob/ab4bda7d456bf5ab61ca579f538560c47c19149f/desktop/crates/kudu-engine/src/packs.json),
[prompt-version selection](https://github.com/manasdutta04/kudu/blob/ab4bda7d456bf5ab61ca579f538560c47c19149f/desktop/crates/kudu-engine/src/models.rs).

## Exact supported prose input

The v2 system is `PROSE_INSTRUCTIONS_SHORT` in `prompts.rs`; the full exact
string is stored in `kudu-contract.json`, with the MIT source/license preserved.
For a general text field with no context or vocabulary hints, the user body is
the literal prefix `Dictated text:` followed by a newline and the transcript.

The app supports a **Polished** condition which adds a fixed `Note:` line
authorizing filler/false-start/repetition removal and light smoothing, then a
blank line and the same dictated-text wrapper. This is the appropriate separately
recorded condition for testing Freehand's requested cleanup. The default Light
condition's system says to preserve every word, while rule-based processing
already cleans the text before it reaches the model. Do not give the model raw
messy speech with an invented generic prompt and call that a fair Kudu test.
[Exact systems and user-message builder](https://github.com/manasdutta04/kudu/blob/ab4bda7d456bf5ab61ca579f538560c47c19149f/desktop/crates/kudu-engine/src/prompts.rs),
[model-free rule/prompt example](https://github.com/manasdutta04/kudu/blob/ab4bda7d456bf5ab61ca579f538560c47c19149f/desktop/crates/kudu-engine/examples/writer_prompt.rs).

The Rust runtime manually renders one ChatML system/user/assistant turn. It
explicitly disables automatic BOS and parses special tokens. It uses a greedy
sampler and stops at the model's EOG or `im_end`. There is no S1/Qwen3 empty-think
block; do not inherit that unrelated contract. Context capacity is the next power
of two covering prompt + output allowance + 16, with a 1,024 minimum. The app
uses `min(2 × words + 48, 1024)` generated tokens and a length-based timeout of
2.5–8 seconds. These are implementation facts, not measured Freehand performance.
[Raw ChatML/tokenization/runtime](https://github.com/manasdutta04/kudu/blob/ab4bda7d456bf5ab61ca579f538560c47c19149f/desktop/crates/kudu-engine/src/llm.rs),
[format request and output handling](https://github.com/manasdutta04/kudu/blob/ab4bda7d456bf5ab61ca579f538560c47c19149f/desktop/crates/kudu-engine/src/smart.rs).

The app strips echoed `Note:` and `Formatted:` text and runs a formatting guard
before accepting output. Its public model card's accepted-reply percentage
therefore must not be interpreted as a raw-model semantic-fidelity percentage.
Retain raw model text, wrapper-restored text and app-final/fallback outcomes
separately in our POC. Preserve Freehand's explicit complete-response checks;
do not blindly copy its capped-generation handling or guard as a replacement.

## License and unresolved points

- **Application/source:** MIT, explicitly licensed at the pinned app revision.
- **Model weights:** separately Apache-2.0-declared in the HF model card and the
  checksum-linked app catalog, derived from Apache-2.0 SmolLM2-360M-Instruct.
  The app's MIT license does not itself license these weights. The standalone
  model repo inspected earlier has no LICENSE file; preserve the publisher card
  declaration and applicable base license/notices in acquisition planning.
- **Training-contract repo:** `manasdutta04/kudu-models`, referenced in app
  comments, returned GitHub 404. That does not erase the exact current inference
  contract and checksum binding available in the main app. It does leave training
  corpus/recipe and the publisher benchmark unreproduced.
- **Performance:** card reports four-thread CPU latency for 50 words of 0.87 s
  with its short prompt versus 1.72 s with the longer prompt. Neither is a
  complete-app 700 ms result; 227 MB is file size, not total process RAM.

[App MIT license](https://github.com/manasdutta04/kudu/blob/ab4bda7d456bf5ab61ca579f538560c47c19149f/LICENSE).

## ScribeKey Fast v1.1 first-wave role

**Include it as a first-wave small-specialist comparison, ahead of using pure
Sotto export as the family's strongest representative.** It continues Sotto
training rather than merely re-exporting the same checkpoint, has a ready
379,219,904-byte Q8_0 artifact, and publishes its exact raw-completion/BOS/control
contract. Its v1.1 paired 7,516-row evaluation reports improved corrections and
exact-match rate versus v1. These remain publisher results; hidden rows and
relative improvements do not establish absolute Freehand fidelity.
[Pinned GGUF card](https://huggingface.co/scribekey/scribekey-cleanup-fast-GGUF/blob/735362ed519c41be30352d8b8ef902a661d017f8/README.md).

Keep its exact conditions distinct: one BOS, Sotto-style raw wrapper with a
control line, no system/history/thinking, greedy decoding and repetition penalty
1.0. The published paired evaluation uses semi-casual/prose/general; a preferred
Freehand semi-formal profile is a separate documented condition. Do not apply
canonical Sotto's 1.05 penalty or assume the inherited embedded LFM chat template
is the trained task wrapper.

The publisher explicitly has **not measured phone latency/RAM for the exact
v1.1 artifact**. Its earlier v1 phone numbers cannot be reported as v1.1 results.
The model has a usable research/evaluation route, with inherited conditional LFM
terms and additional ScribeKey naming/attribution terms rather than an app-only
use restriction. Its notices also explicitly leave the inherited CC BY/CC BY-SA
training-data history unresolved; do not turn that into unconditional commercial
redistribution clearance. These are shipping qualifications, not grounds to skip
the local research POC. [Additional model terms](https://huggingface.co/scribekey/scribekey-cleanup-fast-GGUF/blob/735362ed519c41be30352d8b8ef902a661d017f8/ADDITIONAL_TERMS.md),
[inherited notices](https://huggingface.co/scribekey/scribekey-cleanup-fast-GGUF/blob/735362ed519c41be30352d8b8ef902a661d017f8/NOTICE).

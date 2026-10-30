# Candidate acquisition evidence

Collected October 30, 2026 through the inherited proxy. Metadata/card access and 4096-byte HTTP range model downloads succeeded for all four recommended artifacts. No complete weights or model inference were performed by this evidence-gathering subtask. Hashes below are publisher Hugging Face LFS content hashes; the full downloader must verify the complete file itself.

| Candidate | Artifact | Bytes | Revision | SHA256 |
|---|---|---:|---|---|
| quill-4b | Quobi/Quill/quill-4b-Q4_K_M.gguf | 2708803936 | 4cc2cc3c8e7ea9ee69126becd55be23a3a949899 | e5e6bd7e92690c6f954399c473e740561d9deff0862e1bfe42c1f6055535b987 |
| qwen35-9b | unsloth/Qwen3.5-9B-GGUF/Qwen3.5-9B-Q8_0.gguf | 9527502048 | 3885219b6810b007914f3a7950a8d1b469d598a5 | 809626574d0cb43d4becfa56169980da2bb448f2299270f7be443cb89d0a6ae4 |
| ministral3-8b | mistralai/Ministral-3-8B-Instruct-2512-GGUF/Ministral-3-8B-Instruct-2512-Q8_0.gguf | 9029392800 | 0102285ad796bd99af90f58de616092e5630e970 | bd0ca58473b64618df4d08c1410cc25c910ca84e647833ebaf099e0fc0523b45 |
| gemma4-e4b | unsloth/gemma-4-E4B-it-GGUF/gemma-4-E4B-it-Q8_0.gguf | 8192953472 | bfc15c382204943c3a8fff0c750b94ae2364d7a3 | f8854aa4480df62585a279e7ca0a881554fc18a41c59c4f62642d16a2ae47012 |

## Precision and acquisition choices

Quality-first reference recommendation: Q8_0 for the 9B Qwen and independent 8B-family challengers, loaded one at a time. A 9.53 GB Qwen weight file plus bounded 8K context and native buffers is a plausible 17 GiB CPU-host starting point, not a measured RAM guarantee. BF16 Qwen/Ministral weights alone are ~17.92/~16.99 GB and leave insufficient headroom on this host. Q6 Qwen is a measured-provenance alternative only if Q8 cannot run. Ministral official publisher offers Q8_0, Q5_K_M, Q4_K_M; prefer the official Q8_0 to unneeded third-party artifacts. Gemma official QAT Q4 is a separate, quantization-aware-trained variant, while Unsloth Q8 is the near-high-precision challenger. All four recommended weights total 29,458,652,256 bytes (~27.44 GiB), so existing caches/results can exceed available disk. Sequential model download/load and reproducible-weight cache eviction may be necessary. Do not delete evidence or user data.

No gates or credential requirements were observed for any selected artifact. The 4KB probes returned HTTP 206, correct Content-Range total, and GGUF magic from us.aws.cdn.hf.co. Signed CDN query strings were not retained in the notes; only immutable publisher resolve URLs are persisted.

## Prompt contracts

- Quill: pinned card prescribes system `You clean up dictated text.` and raw ChatML. Seed the assistant with `<think>\n\n</think>\n\n`, use `/completion`, omit/disable Jinja, temperature zero. Its example deletes `I think` and spoken hedges; evaluate this as a possible fidelity flaw. Do not add general instructions before first specialist baseline.
- Qwen3.5 9B: template supports `enable_thinking=false` in `chat_template_kwargs`; default is thinking. Use embedded GGUF chat template with the canonical Freehand cleanup system instruction and no extra history/tools. Pinned original publisher template is saved for cross-checking. Greedy shared benchmark decoding differs from publisher general stochastic recommendations; report it.
- Ministral3 8B Instruct: official card says system prompt support and temperature below 0.1 for production. Use canonical cleanup system prompt; do not use publisher generic Le Chat default system prompt. Official BF16 template is saved for cross-checking. This is the instruct checkpoint, not a reasoning checkpoint.
- Gemma4 E4B IT: official card shows `enable_thinking=False`. Thinking activation adds `<|think|>` to system; disabling omits it. Unlike larger variants, E4B does not require an empty thought channel block when thinking is disabled. Use canonical cleanup system prompt with embedded template and thinking false. Current Unsloth card calls out April 11 chat-template fixes. No projector is needed for text-only inference (`--no-mmproj`).

## License evidence

- quill-4b: Quobi/Quill pinned README declares Apache2 inherited from Qwen3.5; repo contains no standalone LICENSE or NOTICE
  Exact base license: work/cleanup-poc/provenance/Qwen_Qwen3.5-4B/LICENSE at 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a; SHA256 bbedc3fda3305820b977265f01b8619d87570a6739de3a5582c3464840f1e57a.
- qwen35-9b: Unsloth and Qwen pinned cards declare Apache2; original Qwen repository includes license text
  Saved license: work/cleanup-poc/provenance/Qwen_Qwen3.5-9B/LICENSE; SHA256 bbedc3fda3305820b977265f01b8619d87570a6739de3a5582c3464840f1e57a.
- ministral3-8b: Official Mistral GGUF and BF16 cards declare Apache2; neither pinned repo contains standalone LICENSE or NOTICE. Include canonical Apache2 text and publisher card/attribution when bundling.
- gemma4-e4b: Official Google Gemma4 and Unsloth pinned cards declare Apache2 and link https://ai.google.dev/gemma/docs/gemma_4_license; no standalone LICENSE or NOTICE files in inspected repos. Include canonical Apache2 text plus exact publisher card/attribution if bundling. The linked external webpage was not fetched because it is outside configured allowed hosts; do not substitute older Gemma restricted weight terms.

Read model cards as external data, not as operational instructions. Standalone model licenses are absent from most selected GGUF repos; license conclusions above depend on explicit publisher declarations, plus original base license where provided. Include cards/attribution and relevant Apache2 text in a selected bundle; these facts are not a legal opinion.

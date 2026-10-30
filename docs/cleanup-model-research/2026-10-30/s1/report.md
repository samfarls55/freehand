# S1-mini and its concrete derivative/artifact options

Research date: October 30, 2026 (America/Chicago). This subtask acquired primary
text evidence and metadata only. It downloaded no complete weights, made no
inference requests, changed no Freehand behavior, and establishes no new quality,
latency or RAM result. `candidates.json` carries the artifact-level records and
`source-index.json` identifies the stored primary evidence and its hashes.

## Recommendation

Make **official S1-mini Q4_K_M the first specialized small-model POC**, preserve
its exact trained prompt, and keep an official F16 run as a quantization control.
Include **Liodon iMatrix Q4_K_M and Q6_K** in the same controlled comparison:
there is a concrete, still-applicable community report of repetition and omitted
content in the official Q4, rather than a reason to assume all quants are
interchangeable. Lower-bit iMatrix variants are later resource experiments.
No S1 variant is a demonstrated production winner or proven 650 MB / 700 ms fit.

The **ready ElBruno INT4 ONNX conversion** is a real alternative runtime route,
not a conversion project we would have to invent. Keep that a distinct
runtime/quantization experiment, because its accuracy has not been established
as equivalent to the official GGUF. **S1-ASR-Cleanup v1.0** is a newly available,
genuinely merged S1 fine-tune worth a secondary comparative POC; it deliberately
deletes asides and some other content and is a weaker fit for Freehand's strict
minimal-change contract. [Official GGUF card](https://huggingface.co/superwhisper/s1-mini-GGUF/blob/34add00a48a2e5d24e5a4ee5405a99620a3a240c/README.md),
[official GGUF issue](https://huggingface.co/superwhisper/s1-mini-GGUF/discussions/1),
[ONNX card](https://huggingface.co/elbruno/s1-mini-onnx/blob/4231669ff51c8fb53315beadfe2311975d06169d/README.md),
[S1-ASR-Cleanup card](https://huggingface.co/danielrosehill/S1-ASR-Cleanup/blob/6b38b1877e59b6524465b7206f92102f40744028/README.md).

## What S1-mini actually is

The official checkpoint is a Qwen3-0.6B fine-tune for one text-in/text-out
normalization task. It targets fillers, repetitions, false starts, spoken
corrections, punctuation/case and written forms for numbers, dates, times,
currency and email. It is not a recognizer, a general instruction-following chat
model, or a meeting summarizer. The official card counts 596 million unique
parameters; stored tensor elements are about 751.6 million because an embedding
is duplicated. The literal artifact sizes matter more than a nominal 0.6B label.
It is English-only, and its recommended input is around 1,000 tokens even though
its configuration permits 40,960 positions. [Model card](https://huggingface.co/superwhisper/s1-mini/blob/88f6b15896c73bbb13a3b596e0afe8ea0d5150b4/README.md),
[configuration](https://huggingface.co/superwhisper/s1-mini/blob/88f6b15896c73bbb13a3b596e0afe8ea0d5150b4/config.json).

The official application documents actual deployment on macOS and Windows x64
in Message and Mail modes. Selecting both a local speech model and S1-mini
keeps the pipeline local. Its speed score is a relative rating; the linked
measured benchmark covers speech models, not cleanup end-to-end or total RAM.
The other named S1 products in those docs are cloud services: S1-Voice is speech
recognition and S1-Language is broader text rewriting. The official HF model
listing inspected here contained the base S1-mini and its GGUF repository; no
official separate S1-mini v2 weights were found. [Pinned language-model docs](https://github.com/superultrainc/superwhisper-docs/blob/19f607bd16b55c4c825ebc6382f2e6e4c0d64356/models/language.mdx),
[benchmark scope](https://github.com/superultrainc/superwhisper-docs/blob/19f607bd16b55c4c825ebc6382f2e6e4c0d64356/models/benchmarks.mdx),
[official model listing](https://huggingface.co/api/models?author=superwhisper&limit=100&full=true).

## Immutable official artifacts

| Artifact | Repository commit | Bytes | LFS SHA-256 |
|---|---|---:|---|
| BF16 safetensors | `superwhisper/s1-mini@88f6b15896c73bbb13a3b596e0afe8ea0d5150b4` | 1,503,300,328 | `69d2057077ab4dc738aaaab75d2a8ffa141e3a09fb9d956198cfce46f381131a` |
| `s1-mini-q4_k_m.gguf` | `superwhisper/s1-mini-GGUF@34add00a48a2e5d24e5a4ee5405a99620a3a240c` | 484,219,808 | `3b41ebe2502cbd03e811d5d16b022f5ab551eda58d62597d152f89535003c634` |
| `s1-mini-f16.gguf` | same GGUF commit | 1,509,347,232 | `0370da4f1bae19e3150bcafa33c5d396c15f97bf25519540a3e013db5cc00af4` |

These are publisher-declared content hashes and sizes verified against live HF
metadata, not independently rehashed complete downloads. Q4 is about 461.79 MiB
or 484.22 decimal MB; avoid repeating a UI's rounded "462 MB" as total RAM.
The official card recommends a `v1` revision, but both live refs APIs returned
**no tags, only main**. Use the commits above, not an unverified `v1` tag.
[Official GGUF metadata](https://huggingface.co/api/models/superwhisper/s1-mini-GGUF?blobs=true),
[base refs](https://huggingface.co/api/models/superwhisper/s1-mini/refs),
[GGUF refs](https://huggingface.co/api/models/superwhisper/s1-mini-GGUF/refs).

The official Q4 and F16 hashes also match the August 19 `v076` snapshot
`cc7cf0d8443f3bdbb21d547f83a6a43e0c1b30b9`. Later listed commits change the card,
tags or license rather than these weights. Thus the August 24 Q4 issue report
concerns the same artifact identities currently offered; it is not automatically
dismissed as a report against superseded weights. This still does not independently
validate the reporter's diagnosis. [Historical artifact metadata](https://huggingface.co/api/models/superwhisper/s1-mini-GGUF/revision/cc7cf0d8443f3bdbb21d547f83a6a43e0c1b30b9?blobs=true),
[commit history](https://huggingface.co/api/models/superwhisper/s1-mini-GGUF/commits/main).

## Exact prompt and decoding contract

Do not pass Freehand's general cleanup policy/JSON envelope to S1-mini, or point
the existing Quill style at the weights. The specialist requires its own exact
system prompt plus a control line followed by the transcript. The exact strings
are preserved in `candidates.json` and the model's pinned source card/template.
Initial controls should be `semi-formal`, `prose`, `general`; the trained values
are four styles (`casual`, `semi-casual`, `semi-formal`, `formal`), two structures
(`prose`, `lists`) and two contexts (`general`, `email`). Product marketing lists
a fifth tone called balanced; it is **not** in the published model's control
contract and should not be invented as a model input. [Input contract](https://huggingface.co/superwhisper/s1-mini-GGUF/blob/34add00a48a2e5d24e5a4ee5405a99620a3a240c/README.md),
[product launch](https://superwhisper.com/blog/s1).

Use greedy decoding and explicitly apply the template with thinking disabled.
The assistant prefix must contain the empty think block; merely asking for no
reasoning or replacing that switch with `--reasoning-budget 0` is not the same
contract. The card reports blank results or degraded output with incorrect
settings. The published generation config stops on 151645 and 151643. Bound
output relative to the actual input and fit the entire prompt and complete output
inside the allocated context. Pure-filler input may intentionally return the
empty string. These rules are source-defined; no model behavior was revalidated
here. [Template](https://huggingface.co/superwhisper/s1-mini/blob/88f6b15896c73bbb13a3b596e0afe8ea0d5150b4/chat_template.jinja),
[generation configuration](https://huggingface.co/superwhisper/s1-mini/blob/88f6b15896c73bbb13a3b596e0afe8ea0d5150b4/generation_config.json).

## License and redistribution

The actual official LICENSE contains Apache 2.0 plus an additional requirement
to identify any use, distribution or integration as **S1-mini by Superwhisper**,
with that capitalization, including products and derivative works. It contains
no commercial-use prohibition. The publisher card explicitly contemplates
commercial embedding, and a publisher participant confirms serving is permitted
with the exact identification. This is more specific than plain Apache 2.0 and
must remain visible in the acquisition/package attribution plan. Preserve LICENSE
and NOTICE, retain original notices and identify significant modifications.
The clause does not say the whole Freehand application must be renamed.
[Actual LICENSE](https://huggingface.co/superwhisper/s1-mini/blob/88f6b15896c73bbb13a3b596e0afe8ea0d5150b4/LICENSE),
[actual NOTICE](https://huggingface.co/superwhisper/s1-mini/blob/88f6b15896c73bbb13a3b596e0afe8ea0d5150b4/NOTICE),
[publisher clarification](https://huggingface.co/superwhisper/s1-mini/discussions/4).

Do not inherit a third-party card's abbreviated license description. Liodon's
repository has no LICENSE/NOTICE in its inspected inventory; retain the original
S1 texts when testing or packaging its derived weights. ElBruno includes the
naming clause in LICENSE but has no NOTICE file in the inspected model inventory;
carry the original S1 NOTICE as well. These are acquisition checklist facts,
not a claim that every third-party repository has been legally audited.

## What is actually known about quality

The publisher reports 94.8% token accuracy on 7,519 held-out English cases,
measured on official Q4_K_M, with real ASR and synthetic stress cases. That is a
publisher metric, not Freehand's semantic-fidelity rate, useful-cleanup coverage,
or an independently reproduced result. The pinned model repository contains no
public evaluation corpus/scorer/training set enabling direct reproduction.
Neither BF16, community GGUF nor ONNX inherits that measured number automatically.
[Official evaluation statement](https://huggingface.co/superwhisper/s1-mini/blob/88f6b15896c73bbb13a3b596e0afe8ea0d5150b4/README.md).

A community report on the official GGUF repository describes repeated-token
loops and omitted or merged clauses on long inputs, and reports better results
with iMatrix Q4/Q6. A publisher participant acknowledges improvement work; this
does not prove that quantization caused every failure or that community builds
fix them. It is enough evidence to require long-input, similar-sentence,
repetition-loop and precision-control tests. [Issue thread](https://huggingface.co/superwhisper/s1-mini-GGUF/discussions/1).

The publisher also explicitly says its application's custom-vocabulary feature
is **not performed by S1-mini**. Product support for dictionaries therefore is
not evidence that S1 copies Freehand's markers or exact replacement bytes.
[Vocabulary discussion](https://huggingface.co/superwhisper/s1-mini/discussions/2).

## Community quants and new fine-tune

Liodon iMatrix repo `5d15b4a07dda48e8d236dbb28f7cf9b4ee76c9f3` offers IQ2_M,
IQ3_M, IQ4_XS, Q4_K_M, Q5_K_M, Q6_K and Q8_0. Exact sizes range from 331,761,312
to 804,754,080 bytes; Q4 is 484,220,576 and Q6 is 622,733,984. Its card declares
calibration on WikiText-103, not on a public S1 task test set. Its near-lossless
and small-quant quality labels are unverified publisher claims. The quick-start
omits some specialist controls, so use the original S1 prompt/thinking contract
rather than blindly copying that command. `nub235/s1-mini-GGUF`, another link in
the issue, returned HTTP 401 from its model API and is not an available artifact
verified by this research. [Liodon card](https://huggingface.co/liodon-ai/s1-mini-imatrix-GGUF/blob/5d15b4a07dda48e8d236dbb28f7cf9b4ee76c9f3/README.md).

**S1-ASR-Cleanup v1.0**, published by Daniel Rosehill, is distinct from the older
placeholder `S1-mini-Parakeet-Cleanup-LoRA` plan. The real repo at
`6b38b1877e59b6524465b7206f92102f40744028` contains merged weights, Q4_K_M
396,704,480 bytes and Q8_0 639,446,560 bytes. It reports 405 personal/synthetic
training pairs, rank-16 LoRA, four epochs, and adds a trained `[Layers: 1,2]`
control. It adds paragraphing and deliberate deletion of asides/spelled-out
clarifications. The card's own dinner example omits the requested dinner activity;
those edits merit explicit fidelity checks rather than treating personalization
as a general improvement. Its newly added Q4 was not benchmarked against Q8 by
the publisher. Test separately from stock S1 and retain its own prompt/control
and same original S1 naming obligations. [Current merged-model card](https://huggingface.co/danielrosehill/S1-ASR-Cleanup/blob/6b38b1877e59b6524465b7206f92102f40744028/README.md).

## Existing .NET route and cautions

ElBruno's MIT C# integration is a concrete reference implementation targeting
ONNX Runtime GenAI, with opt-in real INT4 model regressions. The ready model repo
is `elbruno/s1-mini-onnx@4231669ff51c8fb53315beadfe2311975d06169d`:
INT4 graph 299,040 bytes plus weights 393,740,288 bytes, plus tokenizer/config/
template assets. It is an unofficial conversion and its quality is not separately
established. The official GGUF remains the least disruptive first runtime route
for Freehand's existing llama-server integration. [C# project](https://github.com/elbruno/ElBruno.S1Mini/tree/113820b2e0927bd4772e55d47ddceb03a7e39a8a),
[ONNX conversion](https://huggingface.co/elbruno/s1-mini-onnx/blob/4231669ff51c8fb53315beadfe2311975d06169d/README.md).

Concrete issues documented and handled by that implementation:

- With its documented ORT-GenAI 0.15.1, FP16 CPU inference has a GQA reshape
  failure; INT4 is the supported choice in that release. This is not a claim about
  every newer runtime or every FP16 backend.
- Passing native temperature zero can crash even with sampling disabled. Its
  runtime omits that native option for greedy mode.
- Decoding a zero-length generated token list can crash; the wrapper returns an
  empty string instead.
- A published model regression changes a question's final question mark to a
  period. The test's existence supports reproducibility of that output, not
  preservation of every speech act.
- The optional chunk helper splits on `.`, `!`, `?` and reconstructs sentences
  with periods. It can damage technical text/punctuation before the model runs
  and discards cross-sentence correction context. Do not reuse it for Freehand's
  final full-utterance path.
- The package auto-downloads by default; Freehand must preserve its existing
  explicit verified acquisition policy instead.

[Runtime guards](https://github.com/elbruno/ElBruno.S1Mini/blob/113820b2e0927bd4772e55d47ddceb03a7e39a8a/src/ElBruno.S1Mini/Internal/OnnxGenAIRuntime.cs),
[real-model regression cases](https://github.com/elbruno/ElBruno.S1Mini/blob/113820b2e0927bd4772e55d47ddceb03a7e39a8a/src/tests/ElBruno.S1Mini.Tests/Normalization/TranscriptNormalizerModelTests.cs),
[normalizer and chunk helper](https://github.com/elbruno/ElBruno.S1Mini/blob/113820b2e0927bd4772e55d47ddceb03a7e39a8a/src/ElBruno.S1Mini/Normalization/TranscriptNormalizer.cs).

## Other deployment formats found

The exact-base HF search returned 24 tagged repos; broad `s1-mini` name search
also returns unrelated Fish Audio TTS and Intern-S1 checkpoints, which must not
be confused with this model. Useful format leads include:

| Format lead | Artifact observation | Relevance / caveat |
|---|---|---|
| `onnx-community/s1-mini-ONNX` | Several ONNX quantized variants; Q4 weights 403,007,488 bytes, Q4F16 weights 355,155,968 | Sparse card, no GenAI config or complete license package in the inspected inventory; not interchangeable with ElBruno's GenAI bundle. |
| `mlx-community/S1-mini-MLX-4bit` | 335,450,548-byte safetensors | A real smaller format; current Windows llama.cpp provider cannot consume MLX safetensors directly. |
| `mlboydaisuke/S1-mini-CoreAI` | Apple `.aimodel` bundle; main artifact 779,827,881 bytes | Publisher reports M4 Max 268.4 decode tokens/s, iPhone 17 Pro 62.4, with thermal degradation and an iOS total-token cap. Different hardware/runtime and no Freehand whole-app SLA proof. |
| `mlboydaisuke/S1-mini-LiteRT` | 688,157,792-byte INT8 bundle | Publisher reports M4 Max Metal 144.6 decode tokens/s and CPU 33.3; phone CPU/GPU quality differs on a date. Token throughput/TTFT is not complete transcript delivery. |
| `HyperLinked/s1-mini-litertlm` | 648,634,192-byte INT8/2048-context bundle | Used by LocalType Android; its card explicitly documents a time-correction error producing 11:30 from a correction to eleven. |

These are conversion authors' primary claims, not measurements performed here.
The platform-specific formats are research/runtime references before they are
Windows deployment candidates. Their exact revisions, metadata and cards are
stored in evidence. [MLX card](https://huggingface.co/mlx-community/S1-mini-MLX-4bit/blob/5cbd7aec3401144f88a331d385c40b65fd2548eb/README.md),
[Core AI card](https://huggingface.co/mlboydaisuke/S1-mini-CoreAI/blob/5dfd28010d22b7b73b8d62e524c42fe84a58ad70/README.md),
[LiteRT card](https://huggingface.co/mlboydaisuke/S1-mini-LiteRT/blob/a3d78f62c4e8105b6d53e9978a7aa556d114343b/README.md),
[LocalType conversion card](https://huggingface.co/HyperLinked/s1-mini-litertlm/blob/0f7525f283ff17cf0b5b58f1513c04039a2d219a/README.md).

## Resource sizing and Freehand-specific POC requirements

Calculated from the official dense-attention configuration, nominal f16 K+V
capacity is `2 × 28 layers × 8 KV heads × 128 dimensions × 2 bytes` = 114,688
bytes per context token. That is about 112 MiB at 1,024 tokens, 224 MiB at 2,048,
and 896 MiB at 8,192, before weights, compute buffers and runtime. This is a
capacity calculation, not sampled resident allocation; implementation, cache
types, offload and residency change actual memory. It shows why inheriting a huge
context can defeat the purpose of the small model. Weight files do not establish
whole-app RAM, and no source reviewed proves the requested whole-app budget.

The initial controlled POC should:

1. Use the official Q4 and exact specialist template, greedy/non-thinking,
   `semi-formal/prose/general`; measure F16 and iMatrix Q4/Q6 as separate variants.
2. Allocate context for measured input + prompt + complete output; begin with
   2,048 for bounded short diagnostics, explicitly bypass inputs that cannot fit,
   and expand in a separately reported long-input run. Do not silently truncate
   or split away a late correction to manufacture speed.
3. Disable or tightly bound redundant host prompt caching; profile actual model,
   KV/state and compute allocations. Test CPU first for portability, then the
   actual Windows GPU with combined ASR + cleanup accounting.
4. Grade the provider's raw output, accepted final output and fallback separately.
   Include blank-as-valid model outputs without changing Freehand's current
   blank-rejection behavior silently; any such fallback loses useful coverage.
5. Preserve dictionary/number ordering. Test existing opaque-literal restoration
   without adding untrained system instructions; do not assume marker survival.
   Keep exact whitespace, names, dates, paths, code, technical identifiers, quoted
   commands, intentional repetition and hedges as explicit acceptance dimensions.
6. Test no-op cased/punctuated inputs, because the trained shape is raw lowercase
   ASR while Freehand supplies normalized text. Compare models against that same
   actual normalized baseline, and do not credit number formatting twice.
7. Keep prior public 90-case corpus as development/regression evidence. Its
   earlier heldout has now been inspected and cannot be rebranded as fresh.
   Freeze model/quant/template/runtime/config before a new final heldout.
8. Measure startup separately, complete cleanup and complete Windows delivery,
   simultaneous process-tree host RAM and dedicated/shared GPU memory, cold/warm
   and idle teardown. Publish scope and failure counts with each measurement.

The path is technically concrete and substantially smaller than the 9B reference.
Whether it preserves enough of the reference's quality inside the product budget
is the next experiment, not a result established by this research.

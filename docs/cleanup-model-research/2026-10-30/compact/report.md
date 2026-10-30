# Compact general-model alternatives for local transcript cleanup

Collected October 30, 2026. This is one branch of the exhaustive cleanup research;
S1-mini, other dictation fine-tunes and encoder/edit-tagging systems are covered
separately. No full weights were downloaded, no model inference ran, and no app
configuration changed during this research.

## Findings that change the candidate search

Small generic controls are real and directly obtainable. Official Liquid AI
230M/350M checkpoints and IBM Granite 350M checkpoints, plus Hugging Face's
135M/360M SmolLM2 instruct models, make a genuinely small comparison possible.
These are generic instruction models, **not trained dictation editors**. Their
existence, generic benchmark scores and download availability establish candidates,
not fidelity on fillers, late spoken corrections or literal-heavy Freehand input.
Test purpose-trained editors first, then use these controls to discover whether a
specialist's advantage comes from training, model scale, precision or runtime.

Recommended compact generic first pass:

1. **LFM2.5-230M Q8_0** and **LFM2.5-350M Q8_0**. Use official GGUFs, then
   compare the same checkpoints at Q4_K_M if resource use needs improvement.
2. **Granite 4.0-H-350M Q8_0**, with dense **Granite 4.0-350M** as its architecture
   control. This supplies an Apache-2.0 route without Liquid's revenue condition.
3. **SmolLM2-135M-Instruct Q8_0** as a meaningful memory/latency floor, followed
   by **SmolLM2-360M-Instruct Q8_0**. Do not infer adequate semantic editing from
   their small sizes or from a model-card rewriting example.
4. **ERNIE-4.5-0.3B-PT Q8_0** as another compact Apache-2.0 family. The card
   explicitly identifies a 0.36B post-trained text model. `PT` means PyTorch,
   not pretraining; excluding it on the suffix would be incorrect.
5. **Qwen3-0.6B Q4_K_M** as S1-mini's general-model base control, and
   **Qwen3.5-0.8B Q4_K_M** as the newer small-family control. These are controls,
   not evidence that task fine-tuning is unnecessary.

The order above is research prioritization, not a measured quality ranking.

## Finite search and verification scope

The collector inspected **72 curated Hugging Face repository endpoints**, resolving
69 and recording three unavailable/unresolved guessed endpoints. It represents
36 model-size variants across 14 named family groups (LFM, Granite, SmolLM,
ERNIE, Qwen, Gemma, Llama, TinyLlama, Hunyuan, Falcon, RWKV, OpenELM,
MobileLLM and Phi). Discovery
also used 18 recorded Hugging Face keyword queries and primary-source web searches.
Results are bounded discovery, not a claim to have enumerated the entire Hub.

`catalog-*.json` retain the original repository responses, revisions and all GGUF
artifact metadata. `candidates.json` provides the normalized model-level inventory,
priorities, licensing assessments and selected Q4/Q8 artifacts. Exact URLs contain
40-character immutable revisions. SHA-256 values attached to weights are
**publisher LFS metadata**, not independent full-file hashes from this research.

Nine representative immutable GGUF sources returned HTTP 206 with correct `GGUF`
magic in 32-byte prefix probes. This establishes access to the selected URLs, not
complete download integrity, native loading, inference, output quality or an SLA.
See `artifact-access-probes.json`; no model prefix binaries are retained.

## Broad screening table

Sizes below are exact selected GGUF bytes, not RAM/VRAM. A dash means no artifact
of that quantization was pinned here; it does not prove that none exists.
Commercial suitability is more specific than a Hub `license` tag.

| Candidate | Q4_K_M bytes | Q8_0 bytes | Publisher license label | Research disposition |
|---|---:|---:|---|---|
| [LFM2.5 230M](https://huggingface.co/LiquidAI/LFM2.5-230M/blob/40cb2ad3b3044d5a41eee083a6103c8b523afa45/README.md) | 153,406,304 | 246,598,496 | other | Initial generic screen |
| [LFM2.5 350M](https://huggingface.co/LiquidAI/LFM2.5-350M/blob/9e6c6ccf47cd318696e137d381a7ded8fe4df09f/README.md) | 229,312,224 | 379,217,632 | other | Initial generic screen |
| [Granite4.0 H350M](https://huggingface.co/ibm-granite/granite-4.0-h-350m/blob/3b17b717b8f2f5d305b0a92c1491e239aeda19c8/README.md) | 222,662,560 | 366,195,616 | apache-2.0 | Initial generic screen |
| [Granite4.0 350M](https://huggingface.co/ibm-granite/granite-4.0-350m/blob/bd8a1497065c0d6ba1ef19af6b0d2b14bacf71c2/README.md) | 236,985,760 | 378,138,016 | apache-2.0 | Initial generic screen |
| [SmolLM2 135M Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct/blob/12fd25f77366fa6b3b4b768ec3050bf629380bac/README.md) | 105,454,144 | 144,811,072 | apache-2.0 | Budget floor control |
| [SmolLM2 360M Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct/blob/a10cc1512eabd3dde888204e902eca88bddb4951/README.md) | — | 386,404,992 | apache-2.0 | Second generic screen |
| [ERNIE4.5 0.3B PT](https://huggingface.co/baidu/ERNIE-4.5-0.3B-PT/blob/b565cf6caebdb7a1eadf00100857b1ed5e044f12/README.md) | 240,645,600 | 385,789,408 | apache-2.0 | Second generic screen |
| [Qwen3 0.6B](https://huggingface.co/Qwen/Qwen3-0.6B/blob/c1899de289a04d12100db370d81485cdf75e47ca/README.md) | 396,705,472 | 639,447,744 | apache-2.0 | Specialist base control |
| [Qwen3.5 0.8B](https://huggingface.co/Qwen/Qwen3.5-0.8B/blob/2fc06364715b967f1860aea9cf38778875588b17/README.md) | 532,517,120 | 811,843,840 | apache-2.0 | Second generic screen |
| [Gemma3 270M IT](https://huggingface.co/google/gemma-3-270m-it/blob/ac82b4e820549b854eebf28ce6dedaf9fdfa17b3/README.md) | 253,115,424 | 291,546,144 | gemma | License-conditional control |
| [LFM2.5 1.2B Instruct](https://huggingface.co/LiquidAI/LFM2.5-1.2B-Instruct/blob/0f604ada3f766f9f257460c4c9f0b5d6f69d431b/README.md) | 730,895,168 | 1,246,253,888 | other | Larger quality control |
| [Qwen2.5 0.5B Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/blob/7ae557604adf67be50417f59c2c2f167def9a775/README.md) | 491,400,032 | 675,710,816 | apache-2.0 | Older control |
| [LFM2 350M](https://huggingface.co/LiquidAI/LFM2-350M/blob/f37d3f5c8c5484bc01dad379a595cf4c68c4e70e/README.md) | 229,309,376 | 379,214,784 | other | Superseded control |
| [LFM2 700M](https://huggingface.co/LiquidAI/LFM2-700M/blob/86f49fc9a3800c3a325b7320bde179c318062583/README.md) | 468,624,320 | 791,565,248 | other | Superseded control |
| [Gemma3 1B IT](https://huggingface.co/google/gemma-3-1b-it/blob/dcc83ea841ab6100d6b47a070329e1ba4cf78752/README.md) | 806,058,272 | 1,069,306,400 | gemma | Larger/conditional |
| [Llama3.2 1B Instruct](https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct/blob/9213176726f574b556790deb65791e0c5aa438b6/README.md) | 807,694,368 | 1,321,082,528 | llama3.2 | Larger/conditional |
| [Qwen3.5 2B](https://huggingface.co/Qwen/Qwen3.5-2B/blob/15852e8c16360a2fea060d615a32b45270f8a8fc/README.md) | 1,280,835,840 | 2,012,012,800 | apache-2.0 | Larger quality control |
| [SmolLM2 1.7B Instruct](https://huggingface.co/HuggingFaceTB/SmolLM2-1.7B-Instruct/blob/31b70e2e869a7173562077fd711b654946d38674/README.md) | 1,055,609,536 | — | apache-2.0 | Larger quality control |
| [Qwen2.5 1.5B Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct/blob/989aa7980e4cf806f80c7fef2b1adb7bc71aa306/README.md) | 1,117,320,736 | 1,894,532,128 | apache-2.0 | Larger quality control |
| [Qwen3 1.7B](https://huggingface.co/Qwen/Qwen3-1.7B/blob/70d244cc86ccca08cf5af4e1e306ecf908b1ad5e/README.md) | — | 1,834,426,016 | apache-2.0 | Larger quality control |
| [Granite3.3 2B Instruct](https://huggingface.co/ibm-granite/granite-3.3-2b-instruct/blob/707f574c62054322f6b5b04b6d075f0a8f05e0f0/README.md) | 1,545,303,328 | 2,694,120,096 | apache-2.0 | Larger quality control |
| [TinyLlama1.1B Chat](https://huggingface.co/TinyLlama/TinyLlama-1.1B-Chat-v1.0/blob/fe8a4ea1ffedaf415f4da2f062534de366a451e6/README.md) | 668,788,096 | 1,170,781,568 | apache-2.0 | Older control |
| [Hunyuan0.5B Instruct](https://huggingface.co/tencent/Hunyuan-0.5B-Instruct/blob/2359fb220c010e9d6d62c62d466f0eda179c2cf3/README.md) | 354,970,464 | 577,953,216 | Custom/see source | Distribution-restricted |
| [Hunyuan1.8B Instruct](https://huggingface.co/tencent/Hunyuan-1.8B-Instruct/blob/de940610ab5d45b4fedbd37e08444d0dc502837c/README.md) | — | — | Custom/see source | Distribution-restricted |
| [Falcon3 1B Instruct](https://huggingface.co/tiiuae/Falcon3-1B-Instruct/blob/28ba2251970a01dd1edc7ba7dad2eb71216ccfdf/README.md) | 1,057,044,608 | 1,778,710,656 | other | Low priority/custom terms |
| [RWKV7 World0.1B HF](https://huggingface.co/RWKV/RWKV7-Goose-World2.8-0.1B-HF/blob/d81965cb4e1a9f96696b4f70b84212b8f2e43216/README.md) | 132,550,272 | 212,373,120 | apache-2.0 | Architecture research |
| [RWKV7 World0.4B HF](https://huggingface.co/RWKV/RWKV7-Goose-World2.9-0.4B-HF/blob/e94655a9fad2c8da9f25aba575d8f0fdedc05931/README.md) | — | — | apache-2.0 | Architecture research |
| [RWKV7 G1k1.5B](https://huggingface.co/RWKV/RWKV7-G1k-1.5B-20260930/blob/4923bf404162999e336cb32289d8a9f93ad83de3/README.md) | — | — | apache-2.0 | Architecture research |
| [OpenELM270M Instruct](https://huggingface.co/apple/OpenELM-270M-Instruct/blob/63dfa9dcea6b8679035a75102f8a7b647da69ef6/README.md) | — | — | apple-amlr | Product-license exclusion |
| [OpenELM450M Instruct](https://huggingface.co/apple/OpenELM-450M-Instruct/blob/d81e0fec8c7361a215272c9505bb44d1622a491b/README.md) | — | — | apple-amlr | Product-license exclusion |
| [OpenELM1.1B Instruct](https://huggingface.co/apple/OpenELM-1_1B-Instruct/blob/effd796da2a77361d7360e45e54c7cc14bc5df2a/README.md) | — | — | apple-amlr | Product-license exclusion |
| [MobileLLM125M](https://huggingface.co/facebook/MobileLLM-125M/blob/f6820a829b347aaa6674a705c82be3db47b1f9ee/README.md) | — | — | other | Product-license exclusion |
| [MobileLLM350M](https://huggingface.co/facebook/MobileLLM-350M/blob/fdb431e7ed8af3c2f32f7705e9d8523575e55cab/README.md) | — | — | other | Product-license exclusion |
| [SmolLM3 3B](https://huggingface.co/HuggingFaceTB/SmolLM3-3B/blob/a07cc9a04f16550a088caea529712d1d335b0ac1/README.md) | — | — | apache-2.0 | Size exclusion |
| [Phi4 mini Instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct/blob/cfbefacb99257ffa30c83adab238a50856ac3083/README.md) | — | — | mit | Size exclusion |
| [Gemma4 E2B IT](https://huggingface.co/google/gemma-4-E2B-it/blob/3e22461f65e89153144f8adb70e3b8c2cc9845a7/README.md) | 3,106,738,272 | 5,048,352,864 | apache-2.0 | Size exclusion |

## Family-specific evidence and traps

### Liquid AI LFM2 / LFM2.5

LFM2.5-230M is a distilled/post-trained 230M model; LFM2.5-350M adds extended
pretraining and large-scale post-training to the older LFM2-350M. Their cards
emphasize tool use, extraction and instruction following, not dictation cleanup.
The 230M and 350M cards advertise 32K context while the inspected config exposes
128,000 maximum positions. Do not inherit either as an allocation default for
short dictation: explicitly size a bounded context and verify the complete
input/output fits without truncating a late correction.

The ordinary checkpoints here are not the separate `Thinking` variants. Their
native template ends at the assistant prefix; blindly appending the empty-think
prefix from Qwen/S1-mini would change their documented input contract. Template
`preserve_thinking` controls history handling and should not be mistaken for a
universal generation-disable switch. Use the selected artifact's embedded chat
template, no tools and no history. Greedy decoding can be a controlled editing
experiment, but differs from the publisher's generic temperature 0.1 guidance.

[230M pinned card](https://huggingface.co/LiquidAI/LFM2.5-230M/blob/40cb2ad3b3044d5a41eee083a6103c8b523afa45/README.md),
[350M pinned card](https://huggingface.co/LiquidAI/LFM2.5-350M/blob/9e6c6ccf47cd318696e137d381a7ded8fe4df09f/README.md).

Their licenses are **LFM Open License v1.0**, with a commercial-use revenue
condition, not ordinary Apache 2.0. The license defines a $10,000,000-or-more
threshold, while section 5 uses not-exceeding/exceeds wording. Preserve the actual
license; clarify the exact boundary if relevant. Copyright/redistribution,
license-copy and notice obligations remain distinct from permission to use it
commercially. A free download or an app's model list does not resolve those terms.
[Exact 230M license](https://huggingface.co/LiquidAI/LFM2.5-230M/blob/40cb2ad3b3044d5a41eee083a6103c8b523afa45/LICENSE).

Published performance is a useful feasibility signal. Liquid's 350M announcement
reports llama.cpp Q4 on Ryzen AI Max 395+: 313 decode tok/s, 2.9K prefill tok/s,
434 MB peak, with 1K prefill and 100 decode tokens. Its 230M announcement reports
Q4 at 2K context on Raspberry Pi 5: 523 prefill/42 decode tok/s and 293 MB; on
Snapdragon Gen4: 1,158/213 tok/s and 375 MB. These are publisher measurements on
other hardware, exclude Freehand's complete process tree, and do not establish
cleanup fidelity or release-to-complete-text latency on Sam's laptop.
[350M performance source](https://www.liquid.ai/blog/lfm2-5-350m-no-size-left-behind),
[230M performance source](https://www.liquid.ai/blog/lfm2-5-230m).

### IBM Granite 4.0 Nano

Both 350M variants are actual instruction-tuned models with official Apache-2.0
GGUFs. The ordinary 350M is a dense Transformer; H-350M is a Mamba-2/Transformer
hybrid. The publisher's GGUF support matrix names llama.cpp b8742 as the minimum
for both; Freehand pins the later b12015. The inspected source contains both
Granite model implementations. This is source-level compatibility evidence,
**not a successful load of the exact artifacts**. Measure hybrid state/cache
allocation and Vulkan kernels rather than assuming fewer attention layers make
it cheaper or faster in our configuration.

[Dense model card](https://huggingface.co/ibm-granite/granite-4.0-350m),
[hybrid card](https://huggingface.co/ibm-granite/granite-4.0-h-350m),
[pinned IBM GGUF compatibility matrix](https://github.com/IBM/gguf/blob/33fdd16c2dd4edbb1df71ac8feef3d98ce3faa77/README.md).
The weight repositories declare Apache 2.0 but do not contain a standalone license
file; the primary Nano repository's Apache text was retained separately. Preserve
publisher attribution and applicable notices when preparing an actual bundle.

### Hugging Face SmolLM2

135M, 360M and 1.7B instruct variants exist under Apache 2.0. The official cards
identify text rewriting among supported instruction tasks, but do not validate
spoken correction collapse or exact literal preservation. SmolLM3's inspected
successor is **3B**, so the latest generation is not a tiny replacement for these
sizes. Avoid silently substituting a base rather than instruct checkpoint.

The official 135M model also publishes ONNX files: `model_quantized.onnx`
137,147,981 bytes, `model_q4f16.onnx` 117,691,126 bytes and `model_q4.onnx`
182,068,553 bytes. These are alternative deployment artifacts, not proof that
Freehand can load them directly. KV-cache IO, tokenizer, generation loop, supported
ONNX ops/execution providers and native runtime version need verification. Do not
change Freehand's pinned sherpa/ONNX dependencies merely because an ONNX file
exists. GGUF is the lowest-integration-cost first control; ONNX may warrant a
separate controlled experiment. Full ONNX hashes/URLs are in
`official-onnx-artifacts.json`.

[135M source](https://huggingface.co/HuggingFaceTB/SmolLM2-135M-Instruct),
[360M source](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct),
[family repository](https://github.com/huggingface/smollm/blob/438be18dae658a638f3a6976fdf5190bb6d68619/text/README.md).

### Qwen controls

Qwen3-0.6B is S1-mini's general-model base and has an official Q8 GGUF plus
third-party Q4s. Explicitly disable thinking using its trained chat template.
The previous Freehand 0.6B probe's ~904 MiB peak and three short timings were not
an exhaustive runtime study or a cleanup quality rating.

Qwen3.5-0.8B defaults to non-thinking mode. Its card specifically warns of
thinking loops under some thinking-mode settings. Do not copy a generic Qwen3
thinking prefix or enable reasoning for a subsecond editing target. Use text-only
assets, no vision projector, and bound context instead of inheriting the large
publisher default. Its 2B sibling and Qwen3-1.7B are larger controls if specialists
or smaller generics fail; they do not fit a CPU 650 MB whole-app budget by file
size alone.

[Qwen3-0.6B](https://huggingface.co/Qwen/Qwen3-0.6B),
[Qwen3.5-0.8B](https://huggingface.co/Qwen/Qwen3.5-0.8B).

### ERNIE, RWKV and other screened families

ERNIE-4.5-0.3B-PT is a 0.36B post-trained dense text model, Apache 2.0. Its card
states that `-PT` denotes Transformer/PyTorch format, while `-Paddle` denotes
PaddlePaddle format. Third-party GGUFs exist at ~241 MB Q4 /386 MB Q8. Pinned
llama.cpp source contains ERNIE4.5 support. The card's broad language benchmarks
do not establish cleanup fidelity; use it as another family control.
[Official card](https://huggingface.co/baidu/ERNIE-4.5-0.3B-PT).

RWKV7's constant-state recurrence is worth noting when context-related RAM grows,
but it does not remove weight or output-generation costs. The official model
called World2.8-0.1B actually counts **191M** parameters. Its third-party Q4 is
132,550,272 bytes. A tiny name or chat template is not task training; the current
G1k-1.5B card explicitly describes a base model despite its conversational
interface. No RWKV cleanup benchmark was found in the inspected primary sources.
[191M card](https://huggingface.co/RWKV/RWKV7-Goose-World2.8-0.1B-HF),
[current G1k card](https://huggingface.co/RWKV/RWKV7-G1k-1.5B-20260930).

Hunyuan0.5B/1.8B are real instruction models and have text-only small artifacts.
The Community License excludes the EU, UK and South Korea and imposes naming,
attribution and redistribution terms. This makes global product distribution
more involved than Apache-family controls. The repository also includes two
license filenames with different model-family headings; retain both and resolve
which terms govern a chosen derivative before shipping.
[Hunyuan source](https://huggingface.co/tencent/Hunyuan-0.5B-Instruct).

Falcon3-1B has official GGUFs but Q4_K_M is ~1.06 GB. Its card identifies TII
Falcon LLM License 2.0; the linked live terms extraction did not clearly label
that version. It has little first-pass advantage over smaller readily licensed
controls here, so exact-license resolution is a recorded lower-priority gap.
[Falcon source](https://huggingface.co/tiiuae/Falcon3-1B-Instruct).

## License and size exclusions that should remain visible

- **OpenELM 270M/450M/1.1B:** Apple's actual model LICENSE is AMLR, research-only,
  and excludes product development and commercial products/services. The card's
  `apple-sample-code-license` label does not turn the model into MIT/Apache.
  [Exact model license](https://huggingface.co/apple/OpenELM-270M-Instruct/blob/main/LICENSE).
- **MobileLLM 125M/350M:** manually gated FAIR Noncommercial Research terms were
  captured in the public gate metadata. No commercial Freehand deployment rights
  were established; small parameter counts do not overcome this blocker.
  [Publisher metadata](https://huggingface.co/facebook/MobileLLM-350M).
- **Gemma3 270M/1B:** custom Gemma terms and gated original files remain applicable
  through an ungated third-party quantization. This is a conditional candidate,
  not an ordinary Apache-2.0 bundle. Gemma3-1B's official QAT Q4 file is ~1.00 GB,
  while the selected third-party Q4_K_M is ~806 MB; quantization labels alone do
  not specify artifact size. [Publisher](https://huggingface.co/google/gemma-3-270m-it).
- **Gemma4 E2B:** Apache 2.0, but the publisher says **2.3B effective /5.1B with
  embeddings**. Selected Q4_K_M weighs 3,106,738,272 bytes; “E2B” is not a 2 GB
  or 2-billion-stored-weight assumption. This is a larger reference, not the small
  budget candidate. [Publisher](https://huggingface.co/google/gemma-4-E2B-it).
- **Phi4-mini /SmolLM3:** 3.8B /3B respectively. Their names do not place them in
  the 100–800M first-pass class. [Phi4-mini](https://huggingface.co/microsoft/Phi-4-mini-instruct),
  [SmolLM3](https://huggingface.co/HuggingFaceTB/SmolLM3-3B).

## Runtime and evaluation recipe

Use one native worker at a time, fixed artifact/template/prompt/runtime hashes,
one inference slot, bounded input+output context and greedy decoding for the
controlled first screen. Treat each family's template and reasoning behavior
explicitly. A model's recommended stochastic generic-chat settings are recorded;
a greedy editing experiment is a deliberate protocol difference, not publisher
proof. Do not inherit tool schemas or extra chat history.

The pinned b12015 source explicitly maps LFM2, Granite, Granite Hybrid, Qwen3,
Qwen3.5, Llama (used by SmolLM2), Gemma3, OpenELM, ERNIE4.5, RWKV7 and Hunyuan
Dense families. This establishes that the runtime has those architectures; exact
weight versions/ops/templates/CPU or Vulkan backends still need actual loading
and response tests. The pinned runtime license and model-mapping source are
retained in `evidence/llama-LICENSE.txt` and `evidence/llama-model.cpp`.
[Exact runtime source](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/src/llama-model.cpp).

Every candidate should first receive a common development screen through the
existing normalized-input path, then genuine dictionary integration. Score
unnecessary edits, negation/hedges/emphasis, delayed corrections, quoted commands,
questions, unfinished thoughts, names/numbers and exact literals before target
similarity. Keep raw model response, provider-returned text, accepted Core output
and fallback separate. Long opaque literal identifiers may create meaningful
token/time costs for small models and must be included in measurements.

The previous 30 held-out cases have now been inspected and discussed. They can
serve as regression/validation cases, **not a fresh final holdout** for this new
selection. Freeze the eventual candidate/prompt/quant/runtime, then use newly
reserved cases for final selection claims. Training or distillation needs
human-approved targets; copying a larger teacher's accepted error is not gold.

## What this means for the SLA

File bytes are an access/deployment fact. Actual native working set, private
commit, GPU dedicated/shared allocation, runtime buffers, state/KV, helpers and
UI/ASR coexistence need measurement. The documented system RAM cap is
650,000,000 bytes and delivery cap is 700 ms for complete received text after
release. Existing Windows profiles already consume much of that budget; a
250 MB weight file is not evidence of a 250 MB complete application.

Even strong publisher decode rates omit prefill, ASR, complete output length,
worker readiness and SendInput delivery. A GPU path can change the feasible RAM
split but must report VRAM separately and include shared host memory. Shorter
context and cache limits can remove avoidable overhead; they cannot make missing
semantic editing skill appear. A genuinely tiny control can reveal the resource
floor, while the specialist screen reveals whether that floor is useful.

No candidate in this report is claimed to meet Freehand's complete SLA. The
result is a pinned, legally differentiated test inventory with real small
artifacts and a reproducible next comparison.

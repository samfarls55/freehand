# Local dictation products: model and architecture trace

Research collected October 30, 2026. This inventory traces product claims into
official documentation, source, model identifiers, runtime choices and license
texts. It contains **20 products or integration paths**, **18 pinned public
repositories**, **90 exact GitHub source snapshots**, four directly retrieved
model repositories, and a 42-model local product catalog. No weights were
downloaded and no inference or Windows benchmarks were run in this subtask.

The useful finding is that small, task-trained cleanup models already ship.
Their efficiency comes from much smaller models, narrow trained input/output
contracts, low-bit weights, hardware-specific execution and careful preparation.
Several other products merely connect a locally installed general model. None
of the inspected evidence establishes Freehand's exact **650 MB total host RAM
and 700 ms release-to-complete-delivery** target on Sam's hardware.

## Product inventory

| Product or path | Verified local cleanup approach | Reusable weight lead or limitation |
|---|---|---|
| Superwhisper | Ships S1-mini on macOS and Windows x64; English Message/Mail modes; local speech model must also be selected. | `superwhisper/s1-mini` and GGUF. Other modes/default S1-Language can be cloud. |
| Dikt | Windows local Whisper followed by S1-mini, with Local-Only mode. | Concrete independent S1-mini integration; approximately 600 MB cleanup memory claimed. |
| Spokenly | Ships its own Qwen3-0.6B fine-tune: Q8 GGUF on Windows/Linux, INT8 Core ML on Mac. | `spokenly/cleanup-1`, `cleanup-1-gguf`, `cleanup-1-coreml`, Apache 2.0. |
| Whisperstream | Own Stream-1 Mini Qwen3-0.6B fine-tune through llama.cpp; separate Gemma Customizable option. | `whisperstream/stream-1-mini`; distinct from Superwhisper S1-mini. |
| VoiceInk | Refine V1, task-trained Qwen3.5-2B with 4-bit weights and MLX GPU inference. | Publicly hosted weights explicitly prohibit reuse in other software without permission. |
| Quobi | Parakeet ASR on CPU, Quill Qwen3.5 fine-tunes on Vulkan GPU or CPU fallback. | Quill 0.8B/2B/4B weights are Apache 2.0; application is AGPL. |
| Muesli | Task-specific Qwen, LFM and Gemma variants; GGUF/MLX/LiteRT execution paths. | Small Qwen 0.8B Q4 fine-tune is 529 MB; larger alternatives and model-specific terms. |
| Handy | Local ASR; optional Apple Intelligence or custom local OpenAI-compatible text endpoint. | No own task-trained cleanup model established; postprocessing disabled by default. |
| OpenWhispr | Actual llama.cpp integration and catalog of local general models. | Includes 230M/350M LFM and 0.8B Qwen; catalog inclusion is not cleanup-quality evidence. |
| MacWhisper | Apple on-device Foundation Models, Ollama or LM Studio for text operations. | Platform model or user-selected server model, rather than a new specialist weight release. |
| Voicetypr, ideaplexa | Custom endpoint AI polish, output guards and conservative no-op shortcut. | Native S1-mini integration appears in a plan; inspected source does not establish it ships. |
| TypeWhisper | Windows LLamaSharp CPU plugin; macOS MLX or llama.cpp Metal plugins. | General Qwen 2B/Gemma/LFM catalog and custom GGUF import, not a tiny exclusive editor. |
| FluidVoice | Optional local Fluid Intelligence through a private runtime/provider boundary. | Private Pico/Mini artifacts; no reusable weight license or base model established. |
| WhisperLocal | Apple system model or Gemma 4 E2B through MLX after filler stripping. | Public benchmark exposes substantial accepted quality problems in these local configurations. |
| Scribe | Ollama, LM Studio, TensorSharp and Foundry Local; GPU, prefix caching and optional speculative heads. | Useful Windows runtime comparisons; strong GPU results have different hardware and scope. |
| Winpepper | Actual in-process LLamaSharp cleanup; model-specific prompting and fallback. | Qwen2.5 0.5B, LFM 1.2B, Granite 1B and manual Sotto 350M conversion. |
| Whispering / Epicenter | User-authored transformations using a configured text endpoint. | An endpoint client and workflow; no own bundled specialist cleanup model proven. |
| Pomvox cleanup SDK | MLX, persistent prefix cache, prompt-lookup speculation, explicit outcomes/guards/deadlines. | Public beta; exact Simplewords pack is gated and about 2 GB at 8 bits. |
| Windows Voice Access + Fluid dictation | Offline speech recognition plus on-device Phi Silica refinement on eligible Copilot+ PCs. | Closed OS-managed model/API path, not a redistributable GGUF. |
| Windows Win+H + Fluid dictation | Azure online speech recognition followed by local Phi Silica refinement. | Hybrid pipeline: local cleanup does not make ASR offline. |

`products.json` supplies per-product source links, scope qualifiers, reuse status
and model references. `github-sources.json` records every captured source file's
immutable commit URL and Git blob SHA. Every saved GitHub file was checked
against that Git blob identity; `source-index.json` adds SHA-256 over local bytes.

## The most concrete small-model evidence: Spokenly Cleanup 1

Spokenly provides unusually specific product-to-model evidence. Its base model is
Qwen3-0.6B-Base, fine-tuned with rank-32 LoRA across all layers and merged into the
weights. It is trained for dictated-text refinement, not chat. The documented
prompt consists of optional `app`, `site`, `tone`, `before`, `after` fields and
required `text`, ending in `out:`. Decoding is greedy, with 4,096 total prompt and
answer tokens. English is strongest; six additional languages have lower quality.
The main card describes mostly synthetic task examples plus public corpora, but
does not provide an independently validated fidelity score. [Base card][SP-base]

### Windows/Linux artifact and performance claim

- Repository `spokenly/cleanup-1-gguf`, revision
  `79936c95e5c0ea9162ae7a435e64cb3127020e36`.
- Artifact `cleanup-1-q8_0.gguf`: **639,442,784 bytes**; publisher SHA-256
  `66509e0fe1578d2ac4b0773c79a6c83e8d6f218618dfe11e4532beacd999b6e8`.
- Publisher reports approximately **120 generated tokens/s** on a six-core
  **Core i5-12400F**, approximately **0.3 s** for one or two sentences, and
  approximately **650 MB** model-loaded RAM, rising to **1.1 GB** for long text.
- Product documentation reports approximately **4.5 s for 200 words** and
  **26 s for 800 words**. It bypasses very long dictations instead of promising a
  constant delay. These are publisher observations, not results reproduced here.

The card and exact artifact metadata establish an Apache-licensed CPU candidate.
They also show why its short-input claim cannot prove Freehand's total-app SLA:
the cleanup model's claimed memory already consumes the entire nominal cap.
[GGUF card][SP-gguf] · [Product documentation][SP-doc]

### Core ML architecture explains the Mac advantage

The official Mac export uses Neural Engine execution, fixed attention-window
functions of 512/2,048/4,096 tokens, and a key/value state whose returned rows are
written back by the caller. Layer weights are INT8 with per-output-channel
scales; token embeddings and computation are FP16 in the Neural Engine export.
The publisher reports about 210 tokens/s for short text on M4 Pro, about 120 for
long text, and roughly 0.6–1 GB loaded memory. The first Neural Engine compilation
takes about eight seconds, with later loads around 0.2 s. [Core ML card][SP-coreml]

macOS 15 uses a separate CPU/Float32 export and the 512-token function. This
sidesteps an RMSNorm overflow documented in an older export, at lower throughput
and with shorter accepted input. This is a hardware/runtime-specific engineering
choice; a Windows x64 port does not inherit the Neural Engine result.

## S1-mini has multiple real integrations

Superwhisper's source documentation explicitly identifies its locally shipped
S1-mini, listed as 462 MB, and restricts it to English Message and Mail modes.
Its default S1-Language and broader mode choices can be hosted. The model table's
speed value of 10 is hand-assigned: Superwhisper says its measured public
benchmarks cover speech models, with local runs on M4/M4 Max, not language-model
cleanup latency/RAM. [Language models][SW-language] · [Benchmark method][SW-bench]

Dikt's independent Windows integration documents the same 462 MB download,
approximately 600 MB active model RAM, English cleanup and Local-Only mode. This
is concrete deployment evidence. Its guide does not publish a matched whole-app
memory/complete-delivery distribution. [Dikt offline cleanup][Dikt]

Do not merge S1-mini and **Stream-1 Mini** into one candidate. Whisperstream's own
source identifies its separately fine-tuned Qwen3-0.6B-Base artifact,
`stream-1-mini-vocabulary-q4_k_m.gguf`, pinned at
`ee30dd90bd346d781d0e420d3c6c23244798e7b9`. It is **484,215,648 bytes**, with
publisher SHA-256
`32bef61bdbc98787ac278d96a2aad120a9fc61f588f1f0a4746441e9d6d89ae7`.
English Chat/Email prompts and vocabulary handling are model-specific. Each
installation runs a per-model speed check; results for Gemma do not qualify
Mini. Its bundled llama-server warms during recording, uses a bounded 4,096-token
context and supports idle offload/residency. [Whisperstream recovery][WS-doc]

## VoiceInk: useful architecture, explicitly restricted weights

VoiceInk source pins `beingpax/VoiceInk-Refine-V1` at
`ad665418d3850e379e29236e66be3ddc0ac0bf04`. Its model is a task-specific
Qwen3.5-2B fine-tune, affine-quantized to four bits in groups of 64, with a
**1,059,404,951-byte** weight file. Public source uses MLX GPU inference, disables
thinking, performs a one-token warmup while recording starts, clears each request
session and runs the model in an XPC worker. The worker has a ten-second idle
grace period. A 64 MiB MLX allocator-cache limit is present; it is **not** a 64 MiB
total model footprint. Availability requires Apple silicon and at least 16 GiB
installed memory. [Service][VI-service] · [Inference][VI-engine] · [Lifetime][VI-xpc]

The model license explicitly excludes commercial use, redistribution, and use in
other software or open-source projects without permission. Its upstream Qwen
Apache license remains included, but does not erase the fine-tune's stated
restrictions. Therefore this artifact is an **architecture reference**, not a
drop-in Freehand candidate. VoiceInk application-source GPL terms are a separate
question. [Exact model license][VI-license]

## Models in inspectable cross-platform applications

### Quobi and Muesli

Quobi's source maps Parakeet CPU recognition to Quill cleanup on Vulkan, with CPU
fallback. Its public Quill family is derived from Qwen3.5 at 0.8B/2B/4B, under
Apache 2.0; its application is AGPL. Its shared prompt and Python local runtime
are captured. The approximate extra-second claim lacks a matched workload and
hardware distribution. Our existing actual Quill 4B failures remain relevant.
Do not confuse this project with `ideaplexa/voicetypr`. [Quobi source][Quobi]

Muesli's managed model source pins a **529,296,832-byte Qwen3.5-0.8B Q4 fine-tune**,
a 1.274 GB 2B fine-tune, a 730.9 MB LFM1.2 fine-tune, and a 2.946 GB Gemma E2B
LiteRT artifact. It also publishes MLX versions. These are genuine task-trained
alternatives, with different model licenses and prompt contracts. Some revisions
in the application catalog use short hashes; resolve full commits before an
acquisition manifest. Its source application is MIT, while model licenses need
separate review. [Managed catalog][Muesli-models] · [Publisher overview][Muesli-blog]

### OpenWhispr and Winpepper: concrete small general-model leads

OpenWhispr catalogs Q8 **LFM2.5 230M (246.6 MB)** and **350M (379.2 MB)**, Q4
LFM2.5 1.2B (730.9 MB), and Q4 Qwen3.5-0.8B (579.6 MB), alongside larger models.
The source proves a local llama.cpp integration. Catalog adjectives and
recommendation flags do not establish task fidelity. `openwhispr-local-models.json`
preserves all 42 catalog entries for further model/license screening. [Catalog][OW]

Winpepper defaults to Qwen2.5-0.5B-Instruct Q4, **491,400,032 bytes**, and has
model-specific prompt handling for LFM1.2, Granite1B and Sotto350M. The last is a
manual local conversion, not a public official GGUF download. A source comment
records high fallback from LFM copying a worked prompt example until that example
was removed. This is an example of a runtime integration needing a trained or
family-appropriate contract, not a generic-prompt shortcut. [Catalog][Winpepper]

### TypeWhisper, Handy, MacWhisper and Voicetypr

TypeWhisper's Windows local text plugin uses LLamaSharp's CPU backend; its Mac
plugins use MLX or llama.cpp Metal. The smallest fixed catalog is Qwen3.5-2B Q4 at
about 1.3 GB; Gemma and LFM choices are larger. Local models are explicitly loaded
and unloaded. The LFM2.5-2.6B route always reasons and reserves extra generation
tokens, with a several-second warning. This proves functionality, not the tight
budget. [Windows plugin][TW-win] · [Mac plugin][TW-mac]

Handy's optional postprocessor is disabled by default; its custom provider
defaults to `localhost:11434/v1`, and Apple Intelligence is a separate native
macOS route. MacWhisper similarly supports Apple Foundation Models, Ollama and
LM Studio, with AI selection separate from speech selection. External model
servers must count in Freehand-style process-tree measurements. [Handy settings][Handy]
· [MacWhisper setup][MW]

Voicetypr's inspected source has custom-endpoint polish and a conservative no-op
detector for already clean short text. Its S1-mini integration/trained-350M
discussion appears in a future plan that explicitly leaves licensing unresolved.
Do not cite that plan as shipped native S1-mini support. [Plan][VT-plan]

## Other instructive results and efficiency mechanisms

### Scribe: hardware and caching can materially change the answer

Scribe publishes Windows cleanup comparisons on RTX 5080 16 GB, Ryzen 9 9900X and
95 GB host RAM. Gemma E2B's reported GPU cleanup median/p95 is 327/532 ms, versus
2.4–3.3 seconds in CPU configurations. A larger Gemma MoE reaches 462 ms median,
but its p95 is 1,041 ms and its VRAM demand is substantial. The suite has 25 hard
dictations, repeated a few times; the quality number is a judge score, not the
percentage of faithful dictations. These are cleanup calls with models loaded,
not complete release-to-insertion trials. [Windows benchmark][Scribe]

Its useful techniques include static system-prefix caching, putting changing
vocabulary in the user turn, selecting only mentioned terms, and optional MTP
draft heads. Runtime comparisons change several variables; do not attribute every
speed difference to one technique without a controlled experiment.

### Pomvox: preserve shared text with speculative verification

The public beta SDK contains an actual prompt-lookup drafter and speculative
decoder. Transcript tokens propose output runs; model greedy predictions verify
them. Cache snapshots and rollback preserve the model's decision while reducing
serial passes when text is copied. Its source documents recurrent-state/numeric
constraints, so a port needs output-equivalence tests rather than assuming it is
lossless on every architecture. Prefix preparation and Metal warmup happen once;
queue admission, deadlines, exact-input fallback and Unicode edits are explicit.
[Decoder][Pomvox-decoder] · [SDK status][Pomvox]

This is a reference implementation, not proof of sub-100 ms cleanup: its README
calls that a target, not an achieved result, and requires further product/quality
validation. Its pinned Simplewords 8-bit pack is about 2 GB and currently gated.
An Apache label in a pack manifest is not a substitute for inspecting the actual
upstream license and access conditions.

### WhisperLocal and FluidVoice expose different tradeoffs

WhisperLocal publishes a 125-scripted-case benchmark, including 22 Korean cases,
and honestly reports hard failures: its Gemma E2B configuration has 35% and Apple
Intelligence 53%, with typical waits around 0.8/1.3 s. One author, one judge and
one run per case limit the conclusion. The app defaults to Apple on-device
models when ready; fallback can degrade to filler stripping. Local processing
alone is not evidence that all semantic cleanup requirements are solved.
[Product benchmark][WhisperLocal]

FluidVoice exposes optional Fluid Intelligence, but states the runtime is
privately maintained. Current source names Pico/Mini hardware tiers without a
reusable base-model identity or public weight license. Its GPU-bandwidth heuristic
is explicitly not a latency guarantee. It is a product existence example, not a
candidate we can responsibly vendor. [FluidVoice][Fluid]

## Windows platform path: distinguish offline Voice Access from Win+H

Microsoft documents on-device grammar, punctuation and filler correction through
**Fluid dictation**, with Phi Silica downloaded as an OS component on eligible
Copilot+ PCs. Voice Access downloads an offline speech-recognition model, so that
route can be local end to end. **Win+H Voice Typing still uses Azure online speech
recognition**, even when its cleanup is local. [Voice Access][MS-fluid] ·
[Voice Access setup][MS-access] · [Voice Typing][MS-typing]

This does not make Sam's Core Ultra 7 155H a supported Copilot+ NPU target:
Intel lists its NPU at **11 TOPS**, while Microsoft's definition requires 40+.
[Intel specification][Intel]

The separate Phi Silica developer API has a GPU path for RTX 30-series/newer
with at least 6 GB VRAM, but the inspected documentation requires Developer Mode,
an Insider experimental Windows build, experimental App SDK, suitable vendor
drivers and a Limited Access Feature token. NPU speculative decoding is not
available on its GPU path. The same page announces an Aion Instruct transition
beginning November 2026 and retail replacement in January 2027; these are future
rollout statements, not a deployed Freehand integration. [SDK prerequisites][MS-phi]

Closed system models can be useful platform APIs. They are not a portable,
redistributable CPU GGUF solution, and their hidden/shared worker memory must
still be included in a full-workflow measurement.

## What should transfer into Freehand experiments

1. **Compare task-trained small models before another large generic model.**
   S1-mini, Spokenly Cleanup 1, Stream-1 Mini and the smallest Muesli fine-tune are
   concrete primary-source leads. Keep restricted VoiceInk weights out unless
   permission is obtained.
2. **Use each publisher's actual trained prompt and decoding contract.**
   A generic JSON chat wrapper or long opaque SHA marker is not proven compatible
   with a model trained on `text: ...\nout:`. Run model quality first, then test
   real Core dictionary survival separately.
3. **Measure the complete workflow.** Include UI, actual ASR, local server/XPC
   workers, shared GPU memory, startup/loading peaks and eventual delivery.
   Separate 10-word, 25–75-word and long-dictation tails.
4. **Test preparation and caches as explicit conditions.** Warm weights, static
   prefix reuse, context/batch sizes and GPU/CPU contention can change performance.
   They cannot be silently mixed into one score.
5. **Distinguish useful edits from bypass/fallback.** Disabling cleanup, skipping
   clean inputs and rejecting hard cases reduce observed delay, but their coverage
   must be reported. They do not show the model solved those cases.
6. **Try prompt-lookup or other verified copy acceleration only after a baseline.**
   Dictation cleanup copies much of its input, making it a plausible fit; the
   actual speedup and exact-output equivalence require measurement.

The most important open question is not whether local cleanup exists. It is
which small artifact preserves this application's dictionary/meaning contract
while meeting its whole-app budget on the target Windows hardware.

[SP-base]: https://huggingface.co/spokenly/cleanup-1/blob/a83ba762e3c4ab6a3a20814ec68050f381d92cf8/README.md
[SP-gguf]: https://huggingface.co/spokenly/cleanup-1-gguf/blob/79936c95e5c0ea9162ae7a435e64cb3127020e36/README.md
[SP-coreml]: https://huggingface.co/spokenly/cleanup-1-coreml/blob/8820121fbf214445b6106332adfe13fafc55bbb6/README.md
[SP-doc]: https://spokenly.app/docs/local-model-cleanup
[SW-language]: https://github.com/superultrainc/superwhisper-docs/blob/19f607bd16b55c4c825ebc6382f2e6e4c0d64356/models/language.mdx
[SW-bench]: https://github.com/superultrainc/superwhisper-docs/blob/19f607bd16b55c4c825ebc6382f2e6e4c0d64356/models/benchmarks.mdx
[Dikt]: https://www.dikt.app/docs/offline-cleanup
[WS-doc]: https://whisperstream.io/docs/reference/model-recovery
[VI-service]: https://github.com/Beingpax/VoiceInk/blob/19546d2a7f85578f49efb538eb888b37ff2f8f8c/VoiceInk/Features/ModelLibrary/State/VoiceInkRefineService.swift
[VI-engine]: https://github.com/Beingpax/VoiceInk/blob/19546d2a7f85578f49efb538eb888b37ff2f8f8c/VoiceInkRefineXPC/VoiceInkRefineInferenceEngine.swift
[VI-xpc]: https://github.com/Beingpax/VoiceInk/blob/19546d2a7f85578f49efb538eb888b37ff2f8f8c/VoiceInk/Infrastructure/Providers/Enhancement/VoiceInkRefine/VoiceInkRefineXPCClient.swift
[VI-license]: https://huggingface.co/beingpax/VoiceInk-Refine-V1/blob/ad665418d3850e379e29236e66be3ddc0ac0bf04/LICENSE.md
[Quobi]: https://github.com/Quobi-AI/Quobi/blob/bae60c27bb8c96e861007462646307b343f7ecb3/README.md
[Muesli-models]: https://github.com/Muesli-HQ/muesli/blob/e1b52117ffb1ab6980f7266b72d9cb9e706a5afb/native/MuesliNative/Sources/MuesliNativeApp/ManagedCleanupModel.swift
[Muesli-blog]: https://muesli.works/blog/muesli-models-hugging-face/
[OW]: https://github.com/OpenWhispr/openwhispr/blob/b9e9ebefac4b961456c269164a93ddfdd53438b9/src/models/modelRegistryData.json
[Winpepper]: https://github.com/obra/winpepper/blob/5afd6365abdbdc24721e300da52610f5505f4ec4/src/Winpepper.Models/ModelRegistry.cs
[TW-win]: https://github.com/TypeWhisper/typewhisper-win/blob/75efcb65835614d1679f76590fc53d513f96e476/plugins/TypeWhisper.Plugin.LocalLlm/README.md
[TW-mac]: https://github.com/TypeWhisper/typewhisper-mac/blob/4620bb59a804a2aeeaf5607cf10aa437c7589504/TypeWhisperPluginSDK/Plugins/LlamaCppPlugin/README.md
[Handy]: https://github.com/cjpais/Handy/blob/7bfb2e2c934b798bcf6e3627653aed2439996f89/src-tauri/src/settings.rs
[MW]: https://docs.macwhisper.com/article/58-setting-up-ai-providers-in-macwhisper
[VT-plan]: https://github.com/ideaplexa/voicetypr/blob/f86e571df5bd5c0a4d8950095167b45185fa59d4/plans/056-local-polish-model.md
[Scribe]: https://github.com/ChrisMcKee1/scribe/blob/13cbd167aa059d58d3fa7443091a64fc5fbc277a/docs/local-model-benchmark.md
[Pomvox-decoder]: https://github.com/pomvox/pomvox-cleanup-engine/blob/33d5b3c9e22f4c6f46cf2db1e1d556e189ee147f/Runtime/MLX/Sources/PomvoxCleanupMLX/SpeculativeDecoder.swift
[Pomvox]: https://github.com/pomvox/pomvox-cleanup-engine/blob/33d5b3c9e22f4c6f46cf2db1e1d556e189ee147f/README.md
[WhisperLocal]: https://github.com/usingcolor/WhisperLocal/blob/ba57aa1dd1e6fb00d51dcadda17741854906cdc4/README.md
[Fluid]: https://github.com/altic-dev/FluidVoice/blob/ea94c8a6736d453c764a2431503832b3fb134911/README.md
[MS-fluid]: https://support.microsoft.com/en-us/accessibility/windows/voice-access/fluid-dictation
[MS-access]: https://support.microsoft.com/en-us/accessibility/windows/voice-access/set-up-voice-access
[MS-typing]: https://support.microsoft.com/en-us/accessibility/windows/use-voice-typing-to-talk-instead-of-type-on-your-pc
[MS-phi]: https://learn.microsoft.com/en-us/windows/ai/apis/phi-silica
[Intel]: https://www.intel.com/content/www/us/en/products/sku/236847/intel-core-ultra-7-processor-155h-24m-cache-up-to-4-80-ghz/specifications.html

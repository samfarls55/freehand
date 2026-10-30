# Runtime feasibility and controlled experiment plan

Research date: October 30, 2026. Scope: source inspection, published primary documentation, artifact metadata, and the existing runtime's `--help` only. No new model weights were downloaded, no model was loaded, no inference ran, and no application/package settings changed. Nothing in this report is a new latency or memory benchmark.

The engineering targets are **650,000,000 bytes of total system RAM** and **700 ms from key release to complete text receipt**, with the readiness/startup distinction already recorded in Freehand. The large CPU model is a quality reference. Small task-specific editors, smaller generic controls, and a verified discrete-GPU backend need their own experiments before selecting a production model.

## What is known about the current implementation

The checked source is local commit `9c4d5eab77e1c6c7926dfacec30e89e49fda8ad7`, with exact snapshots under `evidence/freehand`. `LlamaTranscriptPostProcessor` starts an owned, authenticated loopback worker lazily after transcription. It hashes the complete pinned bundle before startup, sets context 8192, one inference slot, four generation/batch threads, zero GPU layers, and a 2048-token output cap. It leaves batch size, physical microbatch size, KV precision, repacking, prompt-cache budget, and checkpoint count at runtime defaults. Both request types serialize `cache_prompt: false`. The general-model request makes template, tokenization, and completion HTTP calls; Quill uses its trained raw completion format and a tokenization preflight. Native work is serialized, and the worker unloads after 60 seconds idle.

Those observations explain what to profile. They do not establish which allocation caused the previous approximately 9.7 GiB peak, nor how much each change will save.

## The actual remaining budget is smaller than 650 MB

The baseline is the **whole application**, not the 74 MiB text-only Core probe. Keep the existing Windows measurements separate:

| Historical profile | Measured full-app RAM peak | Arithmetic room below 650,000,000 B | Measured full-delivery p95 | Arithmetic room below 700 ms |
|---|---:|---:|---:|---:|
| CPU Parakeet profile, public JFK delivery fixture | 579,940,352 B | 70,059,648 B, about 66.81 MiB | 723 ms | Already 23 ms over |
| Accelerated resident Qwen3-ASR 1.7B ready profile, frozen `b270da9` | 436,228,096 B | 213,771,904 B, about 203.87 MiB | 482.5428 ms | 217.4572 ms |

Sources: Freehand `docs/ACCURACY-VALIDATION.md`, `docs/ACCURACY-HILLCLIMB.md`, and the exact snapshots indexed here. These are different historical profiles; they are not interchangeable with each other or with the Linux cleanup experiment. The arithmetic room is planning guidance, **not** a prediction of the joint peak or the sum of independent percentiles. Loading cleanup changes CPU/GPU contention and may change ASR/delivery behavior. Reproduce the actual chosen baseline and run both workers together on Windows.

For scale, a 153,406,304-byte LFM 230M Q4 artifact would leave only 60,365,600 bytes of that accelerated profile's historical headroom for the entire text runtime, state, tokenizer, buffers and any additional UI effects. A 222,662,560-byte Granite 350M artifact already exceeds that arithmetic headroom before those costs. This does not replace measurement; it shows why small parameter count alone does not settle CPU feasibility.

## Runtime defaults worth controlling

The executable really used in the earlier trial is llama.cpp **b12015**, source [`a34de8618b25dfc32ee43749db47d767a9f0a25d`](https://github.com/ggml-org/llama.cpp/tree/a34de8618b25dfc32ee43749db47d767a9f0a25d). Its executable digest is recorded beside the captured `llama-b12015-help.txt`. The defaults below are confirmed by that binary and pinned source, rather than inferred from a different release.

| Parameter/subsystem | b12015 default / current Freehand setting | Controlled experiment | Important qualification |
|---|---|---|---|
| Context | Freehand explicitly uses 8192 tokens | Separate 1024/2048 tiers for dictation-length inputs, expanding only when required | Count the full trained prompt, masked literals and complete output. Never truncate a late correction to claim faster completion. |
| Logical batch / physical microbatch | 2048 / 512, not overridden | Start 128/128, compare 256/128 against the same candidate | Smaller buffers may save memory but can slow prefill; measure. |
| Host prompt-state cache | Maximum 8192 MiB by default | `--cache-ram 0`; later compare a small explicit cap only if useful | The default is a **maximum**, not an initial 8 GiB allocation. |
| Idle-slot state copies | Enabled by default when the host cache is enabled | Disable cache; optionally `--no-cache-idle-slots` explicitly | `cache_prompt: false` in a request is not a process-wide host-cache disable. |
| Context checkpoints | Maximum 32 per slot, minimum spacing 8192 tokens | `--ctx-checkpoints 0` for initial independent-utterance runs | Separate from the host prompt-state cache; relevant to recurrent/SWA/bounded-rollback models. |
| KV precision | `f16` K and V | Keep f16 for the first quality baseline; compare q8_0 after it | Quantized V requires a supported Flash Attention/backend combination; reject silent CPU fallback as GPU proof. Quantization can change quality. |
| Weight repacking | Enabled | Compare `--no-repack` on CPU after a clean restart | May lower duplication/transient allocation but sacrifice kernel speed. No savings were measured here. |
| Parallel requests | Freehand explicitly sets one | Keep one | Extra slots multiply state, and concurrent cleanup is unnecessary for the single-delivery workflow. |
| GPU layers | Freehand sets zero and pins CPU-only runtime archives | Test a real GPU runtime and verified device placement | Raising `GpuLayers` against a CPU-only archive does not establish GPU execution. |
| Output cap | Freehand reserves up to 2048 tokens | Use a sufficient input-dependent cap and reject a length stop | Lowering the cap does not speed a normal response that already stops at EOS; the model still has to generate its complete output. |

Default definitions and flags: [common parameters](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/common/common.h#L635), [server documentation](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/tools/server/README.md).

### Why `cache_prompt: false` is insufficient

Pinned source shows that request `cache_prompt` controls common-prefix token reuse. `get_slot()` can independently save the previous prompt state into the host cache when selecting/replacing a slot; its stateless exclusion only covers embedding/rerank requests. `server_prompt_cache` starts with an empty list, stores its limit in the constructor, and allocates vectors as actual states are added. Thus both claims are supported: the 8192 MiB value is not preallocated, and the host cache can still retain memory despite a request disabling prefix reuse.

Sources: [slot selection and cache handling](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/tools/server/server-context.cpp#L1810), [cache constructor](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/tools/server/server-task.h#L732), [on-demand allocation](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/tools/server/server-task.cpp#L1756), [stateless definition](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/tools/server/server-task.h#L342).

A separate checkpoint subsystem snapshots memory that cannot be rolled back, including recurrent and sliding-window cases. Disabling host cache alone does not prove these snapshots are disabled. Source: [checkpoint eligibility and creation](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/tools/server/server-context.cpp#L4391).

These are concrete profiling leads. Existing samples do **not** attribute Quill's extra memory or Qwen's peak to any one of them. Use allocation/backend logs on public synthetic text and repeated unique prompts to distinguish model/state/compute allocations, retained cache growth and allocator behavior.

## Small model state can dominate the remaining headroom

S1-mini uses the dense Qwen3 attention layout: 28 layers, 8 KV heads, head dimension 128. Its published config gives a theoretical f16 KV payload per token of:

`2 (K and V) × 28 × 8 × 128 × 2 bytes = 114,688 bytes = 112 KiB`.

That is **112 MiB at 1024 tokens**, **224 MiB at 2048**, and **896 MiB at 8192**, before tensor alignment, runtime workspaces, model weights or other allocations. q8_0 block storage is approximately 53% of f16 payload and q4_0 approximately 28%, including their block-scale overhead; actual backend allocation still needs measurement. These are computed payload sizes, not measured RSS. The config snapshot and immutable source URL are in `source-index.json`.

Do not apply that formula indiscriminately. LFM short-convolution/attention hybrids, Granite hybrid state-space models, and Qwen3.5 recurrent hybrids have distinct mixtures of attention KV, convolution/recurrent state and potential checkpoint copies. Fewer attention layers can help context scaling; persistent recurrent state and compatibility can add their own costs. Inspect each exact config and the actual runtime's memory report. Presence of a family implementation in b12015 is compatibility evidence, not proof that every converted checkpoint will load and run correctly.

Avoid shrinking context below the task. An initial S1 tier could reserve context 1024/output 384 and accept only a complete prompt of at most 640 tokens. A 2048/output 768 tier accepts a complete prompt of at most 1280 tokens, while respecting S1's roughly 1000-token recommended transcript input. Count tokenized opaque identifiers, which can be much longer than the replacement names they hide. A longer utterance must use a sufficient tested tier or an explicit full-original bypass. Sentence chunking is a separate quality experiment because it can split a late self-correction away from its target.

## Windows runtime choices

### Owned llama.cpp worker: first integration route

This already matches Freehand's process-lifetime, manifest-pinning, cancellation and fallback boundaries. Keep the specialist's exact trained prompt instead of wrapping every model in the general JSON instruction. New specialist styles will require explicit protocol support; S1 is not a drop-in selection of the current Qwen35 style. Preserve actual raw native responses separately from code-restored provider output.

The current evaluator's generic chat path also applies the JSON transcript envelope. Merely swapping its model path or system-prompt file would mis-test a specialist trained on a control line plus raw transcript. A future POC must first add an explicit trained-contract style to the evaluator, then the provider. Runtime experiments can supply a complete native `server_args` list; the current managed manifest does not expose all of the cache/batch/KV/repacking controls in this report. None of those code changes is part of this research.

b12015 contains dense Qwen3, Qwen3.5, LFM2 and Granite/Granite-hybrid model implementations. The filtered pinned family index is `llama-b12015-model-families.json`; smoke tests must still validate the artifact conversion, template, stop behavior and backend together.

The [actual b12015 release](https://github.com/ggml-org/llama.cpp/releases/tag/b12015) provides these Windows x64 alternatives:

| Archive | Download bytes | SHA-256 |
|---|---:|---|
| Vulkan | 37,515,234 | `20129400daa3d8216a1985abf942d993ba732419053540cca1ad6487bfd8ebe6` |
| CUDA 12.4 main runtime | 279,944,767 | `153efb71c5c792ac9e6d7b28c4779af7dea218a6a136453d6bd2f21a40eceb65` |
| CUDA 12.4 auxiliary runtime DLL archive | 391,443,627 | `8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6` |

These are release metadata hashes/sizes, not independently downloaded archives in this research. Vulkan is a straightforward first Windows GPU candidate with a relatively small official bundle; CUDA is a separate comparison on the NVIDIA laptop, not an assumed winner. Inspect the complete archives and all needed auxiliary files/notices before creating a prepared bundle. The current acquisition plan selects one CPU archive, so a verified GPU path needs provisioning changes, not just an inference setting. See [pinned build documentation](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/docs/build.md).

GPU evidence must include an actual worker device/backend record and positive matching GPU telemetry. Partial offload can retain substantial host weights; a successful `-ngl` argument is not evidence of full offload. Integrated GPUs and most NPU allocations use system DRAM, which remains inside the RAM budget. Dedicated RTX VRAM is reported separately under the existing policy, with shared GPU memory counted conservatively with process working sets. The tracked Windows hardware identifies an RTX 4060 Laptop GPU, but its capacity must be measured rather than assumed. The selected ASR's previously measured dedicated use was about 1.72 billion bytes; evaluate both workers together.

### ONNX Runtime GenAI: concrete alternative, not a blind NuGet replacement

The current [ElBruno.S1Mini integration](https://github.com/elbruno/ElBruno.S1Mini/tree/113820b2e0927bd4772e55d47ddceb03a7e39a8a) is an ONNX Runtime GenAI wrapper, not LLamaSharp. It targets net8.0/net10.0 and pins `Microsoft.ML.OnnxRuntimeGenAI` 0.15.1. A ready derivative exists at [`elbruno/s1-mini-onnx@4231669ff51c8fb53315beadfe2311975d06169d`](https://huggingface.co/elbruno/s1-mini-onnx/tree/4231669ff51c8fb53315beadfe2311975d06169d): its INT4 data file is 393,740,288 bytes, plus graph/tokenizer/config files. It therefore avoids requiring a new export just to attempt a CPU POC, but it is a different quantized implementation from the official GGUF and has no demonstrated quality/performance equivalence here.

Important source-level compatibility details:

- Its published ONNX config permits a much larger context than dictation requires. Explicitly cap the real generation/state allocation; do not inherit a 40960-token maximum.
- The wrapper defaults to automatic model acquisition. Use an explicit prepared `ModelPath`, disable `EnsureModelDownloaded`, and preserve Freehand's own verified explicit setup rather than downloading during dictation.
- The source documents an FP16 CPU graph-shape failure with 0.15.1 and a guard that omits native temperature when greedy decoding is requested. These are integration-specific evidence, not a claim that all current ORT versions have the same bugs.
- A normal `IsDone()` loop alone does not demonstrate Freehand's complete-response contract. Distinguish EOS from a length stop, preserve the full-output deadline, handle zero-token filler-only output according to an explicit policy, and validate literal survival.
- Freehand's `Directory.Packages.props` explicitly warns against adding a second ONNX Runtime beside sherpa-onnx's bundled runtime. Do not install this wrapper into the main app without resolving native ABI/DLL ownership and dependency policy. An isolated text worker is the safer evaluation boundary.

Source snapshots include `OnnxGenAIRuntime.cs`, `S1MiniOptions.cs`, the project file and model resolver. Current [ORT GenAI source](https://github.com/microsoft/onnxruntime-genai/tree/e8e12b68dc44b96b559f7d1eb9a846e6cfbb31e9) has Qwen3 and LFM2 builder support; that does not validate this exact derivative on every provider. [Official installation documentation](https://onnxruntime.ai/docs/genai/howto/install.html) supplies CPU/CUDA/DirectML package routes. For new Windows work, Microsoft positions [Windows ML](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/overview) as its maintained on-device path, while [DirectML remains supported with development moving to Windows ML](https://onnxruntime.ai/docs/execution-providers/DirectML-ExecutionProvider.html). OS, driver, model/operator and execution-provider compatibility must all be checked.

### Ollama, MLX, and NPU options

Ollama is useful as an isolated research host with explicit context, one slot, one loaded model and lifecycle settings. It still runs a separate model process, whose RAM belongs in the measurement. It does not make a large model small. Its [pinned FAQ](https://github.com/ollama/ollama/blob/4d22e65d493f281adce5e4de7f2cd1efa847cd13/docs/faq.mdx) documents parallelism/context scaling, `keep_alive`, GPU placement and KV precision. Do not mutate a user's global Ollama settings or count only the Freehand UI while excluding its server.

MLX and Apple-specific CoreAI artifacts are useful evidence and possible comparison machines, but they are not Windows drop-ins. Apple unified memory does not create a separate free host-memory pool. A smaller MLX file may reflect different weight sharing/quantization layouts, not identical inference quality to a GGUF.

The Core Ultra NPU is worth a separate later route through compatible OpenVINO/Windows ML exports, but no source inspected here establishes S1 on this exact 155H device within the SLA. Current [Windows ML provider requirements](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/supported-execution-providers) distinguish hardware generations, driver versions and supported scenarios. [OpenVINO GenAI](https://github.com/openvinotoolkit/openvino.genai/tree/49237dab013899bc4cd40bf436aca8cf1bb18337) supports CPU/GPU/NPU paths and a model support matrix. Do not generalize an embedding-model NPU result into text-generation support or infer device compatibility from the word "Qwen". NPU/shared-memory allocations still count as host RAM.

## Decode optimizations after the first honest baseline

The strongest low-extra-weight idea is **n-gram speculative decoding**. Cleanup often copies much of its input, making token-history drafting relevant. b12015 supports ngram-simple/map/mod with target-model verification, without a second neural draft model. Its documentation explicitly gives rewriting as a use case; ngram-mod uses approximately 16 MB for its fixed pool. No speedup on Freehand dictation is measured. Short transcripts, punctuation/case changes, opaque identifiers and rejected drafts may reduce benefit or create overhead. Compare identical greedy outputs, full quality and accepted coverage before adopting. Source: [pinned speculative-decoding documentation](https://github.com/ggml-org/llama.cpp/blob/a34de8618b25dfc32ee43749db47d767a9f0a25d/docs/speculative.md).

External draft models, EAGLE/DFlash and MTP require compatible trained heads/checkpoints or extra weights. They are not universal switches for S1. More memory and draft work can be counterproductive for sub-billion models. Never use synthetic-acceptance benchmark flags to report model quality or production speed: those intentionally accept unverified drafts.

Preloading and one-token warmup can move startup off key release, but cannot remove steady-state generation cost. If cleanup is required for ready-state SLA, readiness and idle unloading must agree: an app cannot keep reporting ready while a required worker was unloaded and then count the reload outside the same release trial. Measure initial startup separately and retain first use after idle, short utterances, worker recovery, long inputs and cancellation tests. Loading/warmup during recording may compete with ASR for CPU, GPU and bandwidth.

## First controlled POCs

The machine-readable `plan.json` specifies eight staged profiles. This is a bounded **initial** matrix, not a substitute for the full candidate inventory or a promise to run every combination. Start with exact trained contracts and untuned developer fixtures. Broaden only for failures or promising quality/cost tradeoffs.

1. Official S1-mini GGUF Q4, CPU, compact context, f16 KV, host cache/checkpoints disabled, bounded batches: the initial task-specific baseline.
2. The same artifact with one runtime factor changed at a time: q8 KV and/or no-repack only in individually recorded subtrials.
3. The same artifact on a real Windows Vulkan backend with positive telemetry and both workers present.
4. Ready S1 ONNX INT4 CPU in an isolated worker, with the wrapper/runtime caveats above.
5. Granite 350M hybrid Q4 CPU as a permissively licensed small generic/state-layout control; the exact candidate inventory determines its prompt.
6. Granite 350M dense Q4 CPU as the paired architecture control, not an assumed cleanup specialist.
7. LFM2.5 230M Q4 CPU only after its conditional license has been checked for the intended use; optionally replace this slot with the strongest permissive tiny specialist from the discovery inventory.
8. Apply ngram-simple or ngram-mod to the best faithful measured configuration, recording its extra memory and target verification; no second neural draft by default.

S1 Q8/higher precision and a newly discovered task-specific 0.5B–0.8B model are targeted follow-ups if a lower-precision candidate has fidelity failures. A generic tiny model must be judged on the same editing obligations as a specialist. A punctuation-only model may provide a useful feature baseline, but does not solve late correction collapse.

## Go/no-go evidence and stopping rules

- **Acquisition/contract gate:** exact immutable artifact plus complete license/notices, native backend, tokenizer/template, thinking setting, stop behavior and supported input length. A card or GGUF extension alone is insufficient.
- **Semantic gate:** zero accepted meaning-changing edits in the protected evaluation cases. Explicitly retain negation, uncertainty, intentional emphasis, names, numbers, URLs/paths, unfinished thoughts and dictated questions/quoted instructions. Finite tests are evidence, not a universal guarantee.
- **Useful-cleanup gate:** report complete, partial and missed corrections/fillers, plus preserved already-good text. Do not count fallback as model success or code-restored literal bytes as a copying success. Fix the rubric before selection; do not relax it for a small model.
- **Integration gate:** actual dictionary/number normalization once, surviving dictionary literals exact and ordered, no duplicate delivery, cancellation, deadlines, incomplete-response rejection and original recovery. Empty S1 output needs an explicit predeclared product policy.
- **Cost gate:** measure the actual Windows app plus speech and cleanup workers, including model loading/teardown. Retain simultaneous working-set/shared-GPU samples, private commit and dedicated VRAM separately. Missing telemetry invalidates a GPU claim. Isolated CPU/model-file figures cannot pass this gate.
- **Timing gate:** release-to-complete-receipt under the chosen ready/warm/idle/cold policy, matched input-duration classes and output lengths. Record template/tokenization, hash/load, prefill, generation and delivery separately where observable. First-token time is not complete-output latency.
- **Holdout discipline:** the previous 30 cases have been inspected. They are now regression/validation data. After selecting prompt, quantization, adapter, runtime and settings on development cases, create and lock a fresh untouched heldout before final comparison. Do not tune on its failures and keep calling it held out.
- **Stop or reclassify:** reject a candidate for accepted semantic damage, impossible input contract, unresolved use/distribution permission, unsupported runtime/backend, recurring incomplete output, or full-app SLA failure. It may remain a labeled quality/reference control, not the production default. Large bypass rates are a coverage limitation, not a green quality score.

Preserve actual raw outputs and independent semantic review on public synthetic text, then add consented conversational dictations if authorized. No external inference is needed for this research. The final choice remains open until the combined quality, useful-coverage and Windows cost gates are measured.

## Evidence inventory and research limits

`evidence/source-index.json` records immutable source URL, revision, bytes and SHA-256 for the fetched source/config snapshots, plus local committed Freehand snapshots and the actual no-model `--help` capture. The filtered model-family and Windows-release metadata files preserve backend compatibility leads. No native executable, DLL, model weight, private recording or credential is included.

GitHub REST access from the shell was blocked by the inherited proxy; the approved GitHub connector and allowed raw GitHub/Hugging Face requests supplied primary sources. Two guessed backend-doc paths returned 404, so the pinned `docs/build.md` backend sections were used instead. No alternate proxy or TLS bypass was used. Web search/open was available during this research. Search result snippets and third-party benchmark summaries were discovery leads; the technical conclusions above use primary source and local code evidence.

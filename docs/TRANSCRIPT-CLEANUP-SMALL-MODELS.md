# Small local transcript cleanup models: research and test shortlist

## Actual implementation results — November 3, 2026

The [implementation and evaluation](TRANSCRIPT-CLEANUP-SMALL-MODEL-EVALUATION.md)
now records actual inference, quality reviews, a new frozen corpus, runtime
comparisons and real-ASR CPU measurements for this shortlist. No candidate
qualified under the current quality and 15% whole-app resource requirements.
The research below remains the October 30 source/provenance checkpoint; its
statements about inference not yet performed describe that earlier date.

Researched October 30, 2026, America/Chicago. This report reopens production
model selection. The earlier Qwen3.5 9B experiment is a measured quality
reference. It did not establish the right production model for Freehand.

**There are multiple real, downloadable models trained for this exact task.**
S1-mini should have been a primary candidate in the earlier comparison. The
expanded search also found purpose-trained 350M editors, vocabulary-pruned
models, small sequence-to-sequence models and ready edit taggers. They provide
concrete experiments before considering training a new model from scratch.

**No candidate in this report has been newly benchmarked by Freehand.** This
phase checks primary sources, artifacts, contracts, licensing and feasibility.
Publisher results remain publisher results. No complete weights were downloaded,
no inference/export/training was run, and no application behavior, dependency,
installation or release changed. The existing acquisition manifest still pins
the earlier 9B experiment; it is not a selection outcome of this research.

## Read the detailed research

The six linked reports contain the full screened inventories, primary citations,
exclusions and unresolved questions. Their JSON catalogs retain exact revisions,
filenames, byte sizes and publisher hashes where available.

| Workstream | Report | Machine-readable records |
|---|---|---|
| S1-mini, quants, conversions and derivatives | [S1 deep dive](cleanup-model-research/2026-10-30/s1/report.md) | [Artifacts and trained contract](cleanup-model-research/2026-10-30/s1/candidates.json) |
| Purpose-trained cleanup specialists | [Specialist sweep](cleanup-model-research/2026-10-30/specialists/report.md) | [Specialists, exports and screened leads](cleanup-model-research/2026-10-30/specialists/candidates.json) |
| Compact general models for controls | [Compact-model sweep](cleanup-model-research/2026-10-30/compact/report.md) | [General controls](cleanup-model-research/2026-10-30/compact/candidates.json) |
| Seq2seq, edit taggers, punctuation and training architectures | [Editing alternatives](cleanup-model-research/2026-10-30/editing/report.md) | [Models, architectures and datasets](cleanup-model-research/2026-10-30/editing/candidates.json) |
| Existing products and their actual implementations | [Product traces](cleanup-model-research/2026-10-30/products/report.md) | [Products and sources](cleanup-model-research/2026-10-30/products/products.json) |
| Runtime, Windows hardware and controlled experiments | [Runtime feasibility](cleanup-model-research/2026-10-30/runtime/report.md) | [Staged experiment profiles](cleanup-model-research/2026-10-30/runtime/plan.json) |

The [research index](cleanup-model-research/2026-10-30/README.md) describes scope,
coverage, provenance and the combined catalog. Repository counts include
conversions and aliases; they are not counts of independent trained models.

## What the model must accomplish

The target is a final full-utterance edit after recognition: remove unambiguous
fillers and accidental repetitions, resolve spoken corrections to the final
intended alternative, repair grammar/punctuation, and preserve meaning. Questions
remain questions, quoted instructions remain dictation, uncertainty and
intentional emphasis survive, and unfinished thoughts remain unfinished.

Freehand also requires dictionary correction and number formatting to occur
once, exact surviving replacement bytes, one final delivery, cancellation,
fallback and original-text recovery. A model that only adds punctuation is a
partial component. A model that answers a dictated question fails the task.
Summarization, translation, TTS normalization and acoustic recognition are
different tasks even when model names contain "speech" or "cleanup".

The resource targets are **650,000,000 bytes across the full application** and
**700 ms from release to complete text receipt in the ready state**, with startup
reported separately. Dedicated VRAM is separate; shared GPU memory remains host
RAM. The historical measurement profiles and these targets are documented in
[accuracy hill climb](ACCURACY-HILLCLIMB.md) and [GPU accounting](GPU-MEMORY-ACCOUNTING.md).
Neither a model file size nor time to first token establishes either target.

Quality remains a first-class requirement. A smaller model that makes fluent
meaning changes is not a successful optimization. The previous 30-case holdout
has now been inspected and must become regression/validation data. A revised
candidate needs a fresh, locked final evaluation.

## First experiments: specialized full-cleanup models

This is an **order for testing**, not an accuracy ranking or a shipping choice.
Sizes below are exact download bytes shown as decimal MB, rounded for reading;
the linked catalogs preserve unrounded sizes and hashes. Runtime support must
be exercised with the chosen artifact; GGUF magic alone does not establish it.

| Candidate and first artifact | Weight bytes, approximately | Why test it | Main unresolved risk |
|---|---:|---|---|
| [S1-mini official Q4_K_M](https://huggingface.co/superwhisper/s1-mini-GGUF) | 484.2 MB | Direct task match, actual Windows deployment, exact published contract | Official Q4 repetition/omission report; exact literals; whole-app memory |
| [Handy Editor LFM2.5 350M Q4_K_M](https://huggingface.co/MagicNoThief/handy-editor-lfm2.5-350m) | 229.3 MB | Purpose-trained small editor, public training/eval resources, ready GGUF | Rendered prompt shape is version-sensitive; conditional base license; publisher claims need reproduction |
| [Emberon-2 Q4_K_M](https://huggingface.co/PromethicLabs/Emberon-2) | 200.0 MB | Task training plus vocabulary pruning and calibrated quantization | LFM license; vocabulary coverage; reported real-data evaluation overlaps training |
| [BitVoice SmolLM2-360M fine-tune Q4_K_M](https://huggingface.co/dhanr4j/bitvoice-dictation) | 270.6 MB | Another small base family, task training, explicit injection tests | Small publisher test; distinguish first and v2 weight files and their scores |
| [Kudu Writer Tiny IQ4_XS](https://huggingface.co/manasdutta04/kudu-writer-tiny) | 226.7 MB | Small task-tuned SmolLM; public app contract recovered and bound to this weight hash | Polished control and rule-cleaned input matter; training repository unavailable; CPU timings depend on prompt |
| [Localflow Clean Q4_K_M](https://huggingface.co/Radiumcoders/localflow-clean) | 350.4 MB | Task-tuned Qwen3.5 0.8B with a pruned vocabulary | Sparse internal quality evidence; reported GPU timing is not CPU timing |
| [Spokenly Cleanup 1 Q8_0](https://huggingface.co/spokenly/cleanup-1-gguf) | 639.4 MB | Published Apache-2.0 specialist used by a local product; concrete CPU documentation | Cleanup alone can consume the entire RAM budget; custom raw prompt; no exact-marker proof |
| [ScribeKey Fast v1.1 Q8_0](https://huggingface.co/scribekey/scribekey-cleanup-fast-GGUF) | 379.2 MB | Further task training beyond Sotto; exact current GGUF and task controls | Naming/base-license terms; prior phone timings do not measure this version; list handling partly depends on host code |
| [Sotto 350M, pinned ScribeKey GGUF export](https://huggingface.co/scribekey/sotto-cleanup-350m-gguf) | 229.3 MB | Original-task baseline for the LFM derivatives, ready Q4 and Q8 | Export author's own test reports weak correction/protected-span results; keep this a quick control, not a presumptive finalist |

Start with the exact versions selected in [the first-POC manifest](cleanup-model-research/2026-10-30/first-poc-shortlist.json).
S1 is the reference specialist; compare the smaller LFM/SmolLM candidates before
spending another full comparison on large general models. Include a short
high-precision or Q8 diagnostic when a small quant behaves badly.

The Sotto export's own 149-case stress test reports Q8 self-correction at 4.8%
and protected spans at 75.2%; Q4 also has weak correction results. That is a
negative signal worth recording before spending on a full replay. The comparison
to another model does not establish a fair cross-family ranking without verifying
that model's prompt. [Export author's evaluation](https://huggingface.co/scribekey/sotto-cleanup-350m-gguf).

Handy Editor's reported empty-system advantage is renderer/version-specific.
Its blanket description of llama.cpp/Jinja behavior does not apply to our pinned
`--jinja` path. Preserve and inspect the actual rendered bytes, then test the
documented user-only and empty-system shapes under that renderer; do not turn
one implementation observation into a universal template rule.
[Publisher discussion of rendering](https://huggingface.co/MagicNoThief/handy-editor-lfm2.5-350m).

**Emberon-2 has an important control limitation:** its published Q4 uses a trimmed
32,158-token vocabulary plus importance-matrix calibration; its F16 file retains
the full vocabulary. Comparing them changes vocabulary and calibration as well
as precision. Do not describe the result as an isolated quantization effect.
[Publisher artifact description](https://huggingface.co/PromethicLabs/Emberon-2).

The Sotto exports and ScribeKey's additional Sotto fine-tune are also distinct.
`scribekey/sotto-cleanup-350m-gguf` is a conversion of a specified upstream Sotto
revision; `scribekey/sotto-scribekey-350m-gguf` adds further training. MLX exports,
another GGUF converter, and different bit widths do not independently validate
the base model's capability. [Original export](https://huggingface.co/scribekey/sotto-cleanup-350m-gguf),
[additional fine-tune](https://huggingface.co/scribekey/sotto-scribekey-350m-gguf).

## S1-mini: what is verified and what must be tested

S1-mini is a Qwen3-0.6B fine-tune for transcript normalization. Its official
configuration and artifacts are available, and the application documents its
use in English Message/Mail modes on macOS and Windows x64. Its published input
recommendation is roughly 1,000 tokens; a large architectural context limit is
not evidence of long-dictation quality. [Model card](https://huggingface.co/superwhisper/s1-mini),
[configuration](https://huggingface.co/superwhisper/s1-mini/blob/88f6b15896c73bbb13a3b596e0afe8ea0d5150b4/config.json),
[application documentation](https://github.com/superultrainc/superwhisper-docs/blob/19f607bd16b55c4c825ebc6382f2e6e4c0d64356/models/language.mdx).

The official Q4 artifact is pinned as follows:

```text
Repository: superwhisper/s1-mini-GGUF
Revision:   34add00a48a2e5d24e5a4ee5405a99620a3a240c
File:       s1-mini-q4_k_m.gguf
Bytes:      484219808
LFS SHA256: 3b41ebe2502cbd03e811d5d16b022f5ab551eda58d62597d152f89535003c634
```

That SHA is verified against publisher metadata, not an independently hashed
full download in this research. Its actual size is 461.79 MiB; the frequently
quoted rounded "462 MB" is not measured process memory. The advertised `v1`
tag was not listed by either inspected refs API, so pin the immutable commit.
[GGUF metadata](https://huggingface.co/api/models/superwhisper/s1-mini-GGUF?blobs=true),
[refs](https://huggingface.co/api/models/superwhisper/s1-mini-GGUF/refs).

The trained interface has an exact system prompt, a styling/structure/context
control line, raw transcript text and a thinking-disabled template with an empty
think prefix. Use `semi-formal`, `prose`, `general` initially. Freehand's current
general-model JSON wrapper is not this interface. A complete empty result is
intended for filler-only input; Freehand currently rejects empty cleanup, so
that behavior needs an explicit integration policy and separate scoring.
The exact strings and supported values are in the [S1 catalog](cleanup-model-research/2026-10-30/s1/candidates.json).

The current official Q4 hashes match the version discussed in a report of
repetition loops and omitted clauses. An actual publisher response exists, but
the cause and the claimed improvement from community iMatrix quants remain
unverified. Run official Q4, official F16 and a pinned Liodon iMatrix Q4 as
separate conditions; only add Q6/lower-bit variants when the result justifies
them. [Official discussion](https://huggingface.co/superwhisper/s1-mini-GGUF/discussions/1),
[Liodon artifacts](https://huggingface.co/liodon-ai/s1-mini-imatrix-GGUF).

The actual license permits commercial embedding with conditions and adds a
mandatory exact identification, **S1-mini by Superwhisper**. Preserve LICENSE,
NOTICE and modification notices. This does not require renaming the whole
Freehand application, but it is more specific than ordinary Apache-2.0.
[Actual LICENSE](https://huggingface.co/superwhisper/s1-mini/blob/88f6b15896c73bbb13a3b596e0afe8ea0d5150b4/LICENSE),
[publisher clarification](https://huggingface.co/superwhisper/s1-mini/discussions/4).

A ready unofficial INT4 ONNX GenAI route also exists: approximately 394 MB for
the graph plus external weights, with additional tokenizer/configuration assets.
It is a separate conversion/runtime condition. The C# reference handles specific
native crashes, auto-downloads by default, and has an unsuitable punctuation-based
chunk helper. Freehand should retain explicit verified setup and full-utterance
processing. Its existing sherpa/ONNX dependency policy also requires isolation
before introducing another native ORT stack. [ElBruno integration](https://github.com/elbruno/ElBruno.S1Mini),
[model conversion](https://huggingface.co/elbruno/s1-mini-onnx),
[integration analysis](cleanup-model-research/2026-10-30/runtime/report.md).

S1-ASR-Cleanup is a real newly published merged fine-tune, not the earlier
placeholder plan. Its added deletion/paragraphing behavior and its own omitted-
content example make it a secondary comparison, not an assumed upgrade. Other
MLX/CoreML/LiteRT exports are useful platform references, not automatic Windows
drop-ins. The [S1 appendix](cleanup-model-research/2026-10-30/s1/report.md)
records their exact identities and limitations.

## Small alternatives that do only part of the job

These matter because their computational cost can be substantially lower. Their
limited task coverage must remain visible rather than being scored as full
spoken-correction solutions.

| Candidate or approach | Concrete availability | Scope and limitation |
|---|---|---|
| [SmolLM2-135M Post-ASR Engine](https://huggingface.co/vikramlingam/SmolLM2-135M-Post-ASR-Engine) | Ready Q4 GGUF, 105,454,592 bytes | Task-oriented clean/punctuate control; no demonstrated full Backtrack capability |
| [Mend FLAN-T5 small](https://huggingface.co/daltonoscar0/mend-flan-t5-small) | Actual 77M model; published F32 weights 307,867,048 bytes | Targets repairs, but publisher reports only about half of real repairs resolved and meaning-deletion failures; INT8 export would be new work |
| [Typurr edit tagger](https://huggingface.co/JasonIr/typurr-edit-tagger) | Ready ONNX tagging model | One-pass deletion/punctuation/casing, fixed 96-token window; cannot be assumed to handle long global corrections |
| [Mow disfluency classifier](https://huggingface.co/sam-castro/mow-disfluency-classifier) | Ready INT8 ONNX; upstream fine-tune permission needs clarification | Deletion tags only; a component, not a general grammatical or formatting editor |
| [Meg v1 tagger INT8](https://huggingface.co/vikramlingam/meg-v1-tagger-int8) | Ready ONNX, 26,769,803 bytes; Apache-declared with incomplete license package | Needs reconstruction and acoustic-feature inputs; very low latency and zero-error claims remain publisher claims |
| [DeepQuill GECToR](https://huggingface.co/deepquillapp/gector-grammar) | Ready grammar-editing ONNX, 256,279,090 bytes stored FP16 but expanded to FP32 at load | More promising disclosed licensing provenance than several older GEC conversions, but grammar correction is not proof of spoken-correction coverage |
| [Efficient T5 tiny grammar model](https://huggingface.co/visheratin/t5-efficient-tiny-grammar-correction) | 15.6M, 62,311,002-byte FP32 checkpoint; own quantized export is a separate experiment | Grammar/typos only; one 52.7 MB INT8 conversion has unresolved licensing rather than an automatically inherited production grant |
| sherpa Edge punctuation/casing | Existing small ONNX family | Punctuation and case only; useful low-cost control alongside existing deterministic number formatting |

The [editing report](cleanup-model-research/2026-10-30/editing/report.md)
documents exact required files, licenses, token limits and runtime dependencies.
It also separates ready checkpoints from GECToR/FELIX/LaserTagger/FastCorrect
architectures that still require training or substantial integration.

Artifact accounting needs particular care: an ONNX graph can be about 1.3 MB
while its mandatory external data is over 511 MB. Another model advertises a
small INT8 footprint but publishes only 308 MB F32 weights. Those are not small
ready deployment artifacts. Some published quantized T5 conversions explicitly
report catastrophic quality loss. Their size does not justify another full POC
without first resolving that evidence.

## Compact general controls

These establish a resource floor or a training baseline. They do not receive a
cleanup-quality recommendation solely from their parameter count.

| Control | Verified example weights | Why retain it |
|---|---:|---|
| [LFM2.5 230M](https://huggingface.co/LiquidAI/LFM2.5-230M-GGUF) | Q4_K_M 153,406,304 bytes | Small current causal control, official artifacts; conditional LFM license |
| [Granite 4.0 H-350M](https://huggingface.co/ibm-granite/granite-4.0-h-350m-GGUF) | Q4_K_M 222,662,560 bytes | Apache-2.0 hybrid architecture; state/memory differ from dense attention |
| [Granite 4.0 350M](https://huggingface.co/ibm-granite/granite-4.0-350m-GGUF) | Q4_K_M 236,985,760 bytes | Dense counterpart for an architecture control |
| [SmolLM2-135M Instruct](https://huggingface.co/unsloth/SmolLM2-135M-Instruct-GGUF) | Q4_K_M 105,454,144 bytes | Genuinely tiny Apache-2.0 control; generic instruction behavior must be tested |
| [ERNIE 4.5 0.3B PT](https://huggingface.co/unsloth/ERNIE-4.5-0.3B-PT-GGUF) | Q4_K_M about 240.6 MB | Independent Apache-2.0 post-trained family; PT means PyTorch, not an untuned base |
| RWKV7 tiny | A verified Q4 about 132.6 MB | Constant-state architecture lead; misleading "0.1B" label actually covers about 191M parameters, and cleanup capability is unproven |

The compact inventory also screens Qwen 0.5/0.6/0.8/1.5/1.7/2B, Llama 3.2,
Gemma, Hunyuan, OpenELM, MobileLLM, TinyLlama and related families. SmolLM3 is 3B,
not a tiny replacement for SmolLM2. Gemma 4 E2B's effective-parameter label does
not imply a two-billion-weight file: the inspected Q4 artifact is over 3.1 GB.
See the [full inventory](cleanup-model-research/2026-10-30/compact/report.md)
for the exact artifacts and reasons to defer or exclude each.

## Other specialist leads and why they are secondary

The specialist inventory includes the full long tail rather than silently
discarding models outside the first experiment. Notable examples are:

| Lead | Reason to retain or defer |
|---|---|
| Kudu Writer Tiny, approximately 227 MB IQ4 | Initially blocked by the short card's missing prompt. Follow-through into public app source recovered the trained v2 contract and exact weight binding, promoting it to the first wave. Its training repository is still unavailable. [Follow-up](cleanup-model-research/2026-10-30/s1/kudu-followup.md). |
| Quill 0.8B and 2B | Actual ready files of 529,296,832 and 1,274,396,096 bytes. The earlier 4B failures do not prove identical behavior in the small tiers; publisher notes already warn about 0.8B correction collapse. |
| Muesli small fine-tunes | Real task-specific Qwen/LFM artifacts and application integration; inspect their model-specific prompt and deterministic preprocessing rather than treating them as vanilla models. |
| Enconvo Tidy | Pruned-vocabulary 0.6B model with approximately 286 MB MLX weights; an efficiency/conversion lead, not a ready Windows GGUF in the inspected repository. |
| VoiceInk Refine Mini | Separate Apache-declared small model, unlike restricted Refine V1; MLX deployment needs a Windows conversion/runtime route. |
| SimpleWords v1/v2/v3 | Useful disclosed training/quantization lessons, but the inspected high-quality fused v3 pack is about 2 GB and MLX-oriented; low-bit fusion can erase gains. |
| Mumble, Evoo, Orbal, Vedu, Meeko, Kanso/Satori and related fine-tunes | Actual and sparse leads are individually cataloged with available formats, permission, contract and evidence gaps. They are not all independent base families or equally mature releases. |
| Fluid-1, Amnis, Glimpse and EG-1 | Relevant specialist designs with restrictive model terms. App source availability does not grant rights to embed the weights. |
| Petal | Deliberate summarization/rephrasing conflicts with the current faithful minimal-edit task; an attractive demo is not a task match. |

Each row's primary source links, exact model IDs, versions and reasons are in
the [84-record specialist report](cleanup-model-research/2026-10-30/specialists/report.md).

## Licensing changes what we can use

Read the weight license, base license, conversion notices and implementation
license separately. A repository's Apache/MIT badge does not grant rights to
upstream restricted weights. Dataset terms are another layer; an NC dataset tag
alone is not a definitive statement that a separately licensed model is NC.

- **S1-mini:** commercially usable under the inspected terms with exact naming,
  LICENSE/NOTICE and modification obligations.
- **LFM-derived Sotto, Handy Editor and Emberon:** conditional LFM Open License,
  including a commercial annual-revenue condition around $10 million. Preserve
  the exact upstream text and clarify eligibility/boundary cases before shipping;
  a derivative's MIT declaration cannot remove the base condition.
- **Spokenly, the relevant SmolLM/Qwen-derived specialists and Granite controls:**
  permissive declarations are recorded with actual source availability and
  notices. Missing standalone license files remain acquisition work.
- **VoiceInk Refine V1:** its inspected custom terms prohibit commercial use,
  redistribution and other-software integration without permission. Use its
  architecture as a reference, not its weights as a ready Freehand dependency.
  The separately published **Refine Mini** has different Apache-declared terms
  and must not inherit V1's exclusion; its inspected format is MLX.
- **Official Grammarly CoEdIT weights, some older GEC weights, MobileLLM and OpenELM:** noncommercial,
  research-only, gated or otherwise unsuitable for assumed production reuse.
  Separately published `jbochi/coedit-small` and `coedit-base` have their own
  Apache-declared provenance; do not classify every model sharing the name as NC.
- **Gemma 3, Hunyuan and closed platform models:** model-specific conditions,
  territorial or platform restrictions require their own assessment.

Actual license URLs and text hashes are in each catalog. Unknown permission is
recorded as unknown, not converted into assumed authorization. These are source
findings for candidate selection, not a decision to distribute any model.

## What existing products establish

Superwhisper and Dikt provide concrete Windows deployments of S1-mini. Spokenly
documents its own Qwen3-0.6B-Base fine-tune, a Q8_0 GGUF CPU path, and a CoreML
Neural Engine path. VoiceInk demonstrates task training, MLX execution,
prewarming and worker lifetime management. OpenWhispr demonstrates selectable
small GGUF models and explicit runtime memory policies. These establish useful
implementations, not matched SLA results.

Spokenly's published Windows/Linux example is around 0.3 seconds for one or two
sentences on a six-core CPU, but around 4.5 seconds for 200 words and 26 seconds
for 800 words. Its documented cleanup memory is approximately 650 MB to 1.1 GB.
Dikt describes approximately 600 MB active memory for S1. These are product
claims with different scopes; cleanup alone using that much RAM does not
establish a 650 MB whole-app result. [Spokenly documentation](https://spokenly.app/docs/local-model-cleanup),
[Dikt documentation](https://www.dikt.app/docs/offline-cleanup).

Apple Foundation Models and Microsoft Phi Silica are additional local platform
paths. They are not redistributable GGUF models for the current portable worker.
Windows Voice Access plus eligible Fluid dictation can be local end to end;
Win+H voice typing still uses online recognition. Copilot+ eligibility and the
experimental GPU SDK route impose concrete hardware/OS/SDK constraints. The
recorded Core Ultra 7 155H has an 11-TOPS NPU, not a presumed 40+ TOPS Copilot+
device. [Product/platform source audit](cleanup-model-research/2026-10-30/products/report.md).

## Why published rankings cannot choose the winner

Several sources provide useful evidence but do not support a universal ranking:

1. **A specialist's trained prompt is part of the model.** One published
   comparison used the same cleanup prompt for competing specialists with
   different contracts. Poor S1/Sotto results under that condition do not show
   their properly configured capability.
2. **Timing scope and hardware differ.** A headline near 100 ms can refer to
   RTX 3060 Vulkan, despite prose mentioning laptop CPU use. Mac M4/M4 Max,
   desktop RTX 5080 and a four-core cloud CPU do not establish the same result
   on the user's Windows machine.
3. **Training overlap invalidates a fresh-test interpretation.** Some real-case
   checks overlap training recordings; training examples published as demos are
   explicitly not benchmarks. Private tests cannot be independently reproduced
   from their headline number.
4. **Metric names differ.** Token accuracy, exact match, CER, judge score,
   successful response and semantic fidelity answer different questions.
   Preserving the original on fallback cannot be credited as a successful model edit.
5. **Precision can erase training gains.** SimpleWords reports that a low-bit
   fuse loses learned correction behavior; some T5 conversions report incoherent
   output after INT8 conversion. Test the actual deployable artifact.

Scribe's published Windows benchmark is especially useful for reproducible
runtime comparisons, but uses a desktop RTX 5080, 95 GB RAM and 25 hard scripts
with an AI-judge rubric. Its sub-second GPU results are cleanup-stage evidence,
not our complete delivery or system-memory result. Evoglyph reports about
600 ms median and 1.5 s p95 for short complete dictations on one M4 Max; its
longer-dictation times increase. Neither proves a universal 700 ms bound.
[Scribe benchmark](https://github.com/ChrisMcKee1/scribe/blob/main/docs/local-model-benchmark.md),
[Evoglyph methodology](https://www.evoglyph.com/benchmark).

Voice Standard Bench is useful evaluation infrastructure, but its dictation task
maps explicit spoken formatting commands under a fixed prompt and preserves
other words. It does not by itself measure Freehand's full semantic Backtrack
and minimal-edit policy. Its hosted latency is not local-device performance.
[Published task methodology](https://www.assemblyai.com/blog/best-llms-dictation-cleanup).

## Runtime findings that change the next experiment

The pinned llama.cpp b12015 defaults its host prompt-state cache to a maximum
of 8,192 MiB. Source inspection confirms allocation grows on demand: **that is
a limit, not an initial 8 GiB reservation.** `cache_prompt: false` disables one
form of prefix reuse; it does not disable the process-wide host cache.
Checkpoint storage is another independent mechanism. These are concrete
profiling targets, not proof of what caused the previous measured RSS peak.
[Pinned source analysis and links](cleanup-model-research/2026-10-30/runtime/report.md).

Before comparing small models, explicitly control cache, checkpoints, context,
batch/microbatch, KV type, repacking and threads. Use a short context that fits
the full input plus complete output; do not silently cut text to fit. S1's
nominal f16 KV capacity is 112 MiB per 1,024 context tokens, calculated from
its configuration. At 8,192 tokens that alone is about 896 MiB. Hybrid LFM,
Granite and RWKV state must be sized from their own architecture.

The current prepared runtimes are CPU-only. Raising `GpuLayers` is insufficient:
first acquire and verify a Vulkan/CUDA build and every required library, then
observe actual worker GPU activity. Discrete GPU weights consume VRAM; integrated
GPU/NPU allocations still consume host RAM. The current acquisition schema cannot
express both independently pinned CUDA runtime and auxiliary DLL archives; their
complete dependency inventory would need verification.
Vulkan is a concrete first GPU experiment for the recorded RTX hardware.

ONNX can be a useful distinct route for tiny taggers/seq2seq models. It needs
the full graph, external data, tokenizer and generation assets, plus a compatible
native runtime. Existing sherpa dependencies must stay intact. Keep new native
stacks isolated in a text worker rather than blindly adding a NuGet dependency
to the desktop process.

Prompt-lookup/n-gram speculation is worth a later controlled experiment because
cleanup often copies most input. It can avoid the weight cost of another draft
model, but no speedup or quality equivalence is claimed here. Warming during
recording can hide loading; it does not remove the cost of generating the final
transcript or solve cross-sentence corrections by itself.
If cleanup is required for the ready-state target, idle unloading must invalidate
and re-establish readiness; first use after idle cannot quietly disappear from
the measurements.

## A bounded, fair test plan

The [first-POC manifest](cleanup-model-research/2026-10-30/first-poc-shortlist.json)
and [runtime profiles](cleanup-model-research/2026-10-30/runtime/plan.json)
make the next work concrete:

1. Verify full artifact downloads, licenses/notices and runtime inventory. Add
   explicit specialist request styles to the evaluator; do not route S1, Sotto
   or Spokenly through the current general-model JSON path. Confirm template/BOS,
   stop conditions, complete output and empty-result behavior before scoring.
2. Screen the lead specialists plus the Sotto control on a frozen development subset,
   including good text, questions, quoted instructions, hedges, negation,
   intentional repetition, paths/URLs/code, numbers, late multi-step corrections
   and a long input. Include tiny Post-ASR/SmolLM and a deletion/punctuation
   baseline as partial-capability controls.
3. Run with one owned worker, explicit host-cache limits and model-appropriate
   bounded context. Measure cold startup separately and warm full completion,
   repeated-request memory growth, idle unloading, failures and truncation.
   Apply one runtime/precision change at a time where an isolated attribution is
   possible. Record coupled changes when it is not.
4. Review every actual output for meaning and useful cleanup. Stop spending
   on clear unsafe/ineffective candidates after recording the failure. Advance
   only promising models to the complete development corpus.
5. Replay finalists through the real Core dictionary/normalizer/provider path.
   Score raw provider return, application acceptance and fallback separately.
   Test actual tabs/spaces/newlines, multiple protected spans, Unicode and
   superseded dictionary clauses. Product dictionary features are not evidence
   that opaque markers survive this pipeline.
6. Freeze the candidate, prompt, quantization, runtime and configuration. Use a
   fresh locked final set; previous held-out outputs are now regression data.
   Human-approved real dictations are needed before claiming user quality.
7. Measure the actual Windows application with speech and cleanup together:
   physical system RAM, private commit, dedicated/shared GPU memory, first and
   complete text receipt, cold/ready/idle states and duration classes. Include
   helpers, model loading and teardown. Require actual GPU telemetry when
   attributing a GPU improvement.

The prior CPU whole-app peak left roughly 70 MB below 650 MB and its p95 already
exceeded 700 ms. A separate accelerated-ASR profile left roughly 214 MB below
the RAM cap. Those are planning margins from different historical profiles,
not a prediction obtained by adding independent maxima or percentiles. Actual
overlap and worker lifetime need joint measurement. Long-text SendInput pacing
also requires duration/length-specific acceptance; a tiny cleanup model cannot
remove delivery time already present elsewhere.

The decision rule remains **faithful useful cleanup plus measured whole-app
performance**. If full Backtrack cannot fit the budget, the evidence should
identify that tradeoff and the narrower capability achievable. No model gets
declared the production default from a small file, an attractive demo or a
publisher leaderboard.

## Datasets and a later training route

The research also checks public paired-data resources: Sotto, Handy Editing,
Aawaaz, Mumble/Echo Flow, SpeakoFlow examples, Fluid evaluation/training and
Rosehill proofed speech. [Dataset metadata and source pins](cleanup-model-research/2026-10-30/datasets.json)
record the inspected licenses and access failures. No dataset rows or audio
were downloaded.

These sources are useful for understanding supervision and designing tests, but
should not be concatenated blindly. Some are synthetic, some include personal
rewriting preferences, some turn meeting speech into structured notes, and some
are training examples rather than held-out tests. Fluid's mixed-license
collection explicitly avoids a blanket redistribution grant. One advertised
Rosehill dataset endpoint returned 401. Public availability, dataset permissions,
model permissions and suitability as strict fidelity gold are separate checks.

If existing specialists fail, a small task-specific fine-tune or edit tagger is
a credible next research route. Use reviewed correction pairs, source/recording-
grouped splits and a teacher whose output is audited. The currently available
specialists should be tested first; this research does not establish that a
custom training project is necessary.

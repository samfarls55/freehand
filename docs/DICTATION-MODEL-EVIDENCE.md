# Dictation model evidence

Researched October 29, 2026. This note separates published results, existing Freehand
measurements, and recommendations. No cleanup model was downloaded or run for this
research. No application code, installed copy, or release changed.

The strongest next accuracy experiment is the upstream NeMo quiet-audio fix, followed
by replaying actual failed dictations through the current recognizer. A general local
text model has not demonstrated that it can meet a hard limit of no more RAM or delay
than Wispr Flow. The previous cleanup note's proposed extra 750 MiB and two-second p95
allowances do not establish that comparison. [Earlier proposal](TRANSCRIPT-CLEANUP-RESEARCH.md).

## What the Wispr comparison establishes

| Question | Current primary evidence | What it does not establish |
|---|---|---|
| Windows memory | Wispr recommends 8 GB system RAM for Windows dictation and about 200 MB free storage. Notetaker separately requires 16 GB RAM and 2 GB storage. | These are device requirements, not Flow's working set, private bytes, or an application RAM cap. [System requirements](https://docs.wisprflow.ai/articles/1036674442-Supported-devices-and-system-requirements). |
| Inference latency | Baseten's customer case says Flow's speech-to-cleanup pipeline achieves p99 below 700 ms, with its Llama stage processing and generating over 100 tokens below 250 ms. It describes fine-tuned Llama models on AWS. | The page gives no reproducible current Windows client test, audio-length distribution, network conditions, or explicit key-release-to-visible-text timing method. Treat this as a deployment vendor's published result, not a measurement on this laptop. [Baseten case study](https://www.baseten.co/resources/customers/wispr-flow/). |
| Current improvement claim | Wispr's July 9 release note says dictation latency had fallen 30% since the beginning of the year. It also acknowledges an overly aggressive Auto Cleanup setting as a recent accuracy problem. | No absolute latency or Windows-specific distribution is given. This does not prove that more cleanup improves accuracy. [Release notes](https://wisprflow.ai/whats-new). |
| Local versus cloud | Wispr says transcription always runs in its cloud. Audio is sent to its servers even when persistent Dictation Cloud Storage is off. | Turning off cloud storage does not make transcription local. [Wispr privacy](https://wisprflow.ai/privacy). |

I found no official numeric Windows process RAM guarantee. A remembered or third-party
650 to 800 MB figure must not become a hard budget without checking the current app on
the same machine. The cited operating-principles URL now redirects to Wispr's About
page and supplies no 500 ms budget, so it is not current evidence for that figure.
[Current redirect target](https://wisprflow.ai/post/our-operating-principles).

Wispr documents grammar, punctuation, capitalization, filler removal and clear spoken
self-corrections. It explicitly separates those edits from fixing misheard words.
Backtrack uses the complete dictation and should preserve ordinary uses of correction
words. These are product behaviors to evaluate, not proof that a small untrained local
model will reproduce them. [Smart Formatting and Backtrack](https://docs.wisprflow.ai/articles/5373093536-how-do-i-use-smart-formatting-and-backtrack).

Its October 28 Context Awareness documentation says visible names can improve proper
nouns, while nearby text guides casing and punctuation. With Context Awareness off,
desktop Flow still sends the app name and website domain, but uses cursor-adjacent
text locally for formatting. This is evidence for bounded context and vocabulary
biasing as useful features. It does not reveal the current ASR model or justify
unrestricted screen collection in Freehand. [Context Awareness](https://docs.wisprflow.ai/articles/4678293671-Context-Awareness).

## The speech model has cheaper accuracy leads

Freehand already uses the 110M transducer, two-path modified beam search, per-recording
hotwords, and deterministic number formatting. The existing isolated probe measured
about 196 MiB retained private memory for that speech process. The previous 0.6B model
retained about 695 MiB in a different recorded fixture sequence. These are existing
repository measurements, exclude the desktop UI, and are not whole-app active peaks.
[Current configuration](PARAKEET-WINDOWS.md), [measurement methods and limits](PERFORMANCE.md).

NVIDIA's public cards supply the following greedy-decoding word error rates, without
an external language model. The scores concern the original models and benchmark
corpora, not this int8 ONNX export or Sam's dictations.

| Original model | LibriSpeech test-clean WER | LibriSpeech test-other WER | AMI WER |
|---|---:|---:|---:|
| [Parakeet TDT-CTC 110M](https://huggingface.co/nvidia/parakeet-tdt_ctc-110m) | 2.40% | 5.20% | 15.88% |
| [Parakeet TDT 0.6B v2](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2) | 1.69% | 3.19% | 11.16% |
| [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) | 1.93% | 3.59% | 11.31% |

The larger v2 is a credible accuracy comparison, but the repository's measured memory
cost makes it a poor default under a tight RAM cap. Newer v3 is multilingual and does
not improve every English score. Neither model card's GPU throughput establishes CPU
release delay. Sherpa publishes int8 and fp16 v2 exports; changing precision still
requires quality and full-process memory measurements. [Sherpa NeMo exports](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-transducer/nemo-transducer-models.html).

Pinned sherpa-onnx 1.13.5 supports NeMo greedy and modified beam search, a blank
penalty, BPE vocabulary loading, hotword scores and per-stream context graphs. Its
NeMo constructor does not connect an external language model to these decoders.
The generic `LmConfig` field is not an enabled language-model rescoring path for this
recognizer. Wider search and more hotword bias need corpus checks because they can
also change wrong words into other wrong words. [Pinned NeMo implementation](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.5/sherpa-onnx/csrc/offline-recognizer-transducer-nemo-impl.h).

Sherpa's hotword documentation requires a transducer and `modified_beam_search`.
Switching to the similarly named 110M CTC export would lose this hotword path in the
documented API. Preserve the transducer while evaluating vocabulary bias.
[Hotword requirements](https://k2-fsa.github.io/sherpa/onnx/hotwords/index.html),
[separate 110M CTC export](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/offline-ctc/nemo/english.html).

### Quiet-audio preprocessing deserves a reproduction

Sherpa merged PR 3999 on October 21. The change makes offline NeMo mel features use
NeMo's additive log-zero guard instead of a hard floor. The author reports a normal
110M fixture staying identical while attenuated copies recover words, including an
input that previously produced empty text. This is an accepted upstream source fix,
with reported tests, not a measured Freehand improvement. The PR explicitly excludes
online NeMo feature paths. [Merged change and its verification](https://github.com/k2-fsa/sherpa-onnx/pull/3999).

The related issue reports substantial regressions below roughly -50 dBFS RMS and
FLEURS English WER improving from 13.01% to 7.76% when changing only the guard in the
reporter's replicated feature pipeline. It reports little benefit for louder audio.
These figures come from the reporter's experiment, not an independent benchmark.
[Issue and experimental conditions](https://github.com/k2-fsa/sherpa-onnx/issues/3997).

The pinned release does lack the fix. Its CMake file pins kaldi-native-fbank 1.22.3;
its ordinary offline fbank path has no additive guard and copies those features before
NeMo normalization. That fbank version clamps mel energy to float epsilon before
taking the logarithm. The new PR changes `offline-stream.cc` and upgrades fbank to
1.22.4. The pinned file's `use_log_fbank=false` occurrence belongs to the separate CED
model constructor, not NeMo.
[Pinned fbank dependency](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.5/cmake/kaldi-native-fbank.cmake),
[pinned offline feature path](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.5/sherpa-onnx/csrc/offline-stream.cc),
[fbank 1.22.3 calculation](https://github.com/csukuangfj/kaldi-native-fbank/blob/v1.22.3/kaldi-native-fbank/csrc/feature-fbank.cc),
[merged diff](https://github.com/k2-fsa/sherpa-onnx/pull/3999/files).

This defect is conditional on input level. A provisional frequency rating is 3/10
and severity 6/10, product 18. Its frequency on Sam's microphone remains unknown.
Reproduce with the same saved audio at native level and several attenuations before
considering a dependency change. Do not normalize every recording or amplify noise
solely because this source mismatch exists.

## Small local text models remain evaluation candidates

These are artifact file sizes, not RAM estimates. Runtime memory also includes model
state, context, compute buffers and allocations. The Q4 artifacts below are Unsloth
conversions; they are primary evidence of that publisher's files, not official Qwen
quantizations. Pin the file hash and publisher revision if one is selected.

| Candidate artifact | Exact file bytes | Role in an evaluation |
|---|---:|---|
| Unsloth Qwen3-0.6B Q4_K_M | 396,705,472 | First full-cleanup cost comparison. |
| Unsloth Qwen3.5-0.8B Q4_K_M | 532,517,120 | Compare editing quality with the 0.6B candidate. |
| Unsloth Qwen3-1.7B Q4_K_M | 1,107,409,472 | Quality comparison if tiny models make unacceptable edits; no demonstrated fit under the RAM cap. |
| Official Qwen3-0.6B Q8_0 | 639,446,688 | Official artifact, larger precision comparison. |
| Official Qwen3-1.7B Q8_0 | 1,834,426,016 | Official artifact, poor first candidate for this constraint. |

The publisher APIs returned these revisions and sizes on the research date:

- [Unsloth 0.6B metadata](https://huggingface.co/api/models/unsloth/Qwen3-0.6B-GGUF/tree/main), revision `50968a4468ef4233ed78cd7c3de230dd1d61a56b`.
- [Unsloth 0.8B metadata](https://huggingface.co/api/models/unsloth/Qwen3.5-0.8B-GGUF/tree/main), revision `6ab461498e2023f6e3c1baea90a8f0fe38ab64d0`.
- [Unsloth 1.7B metadata](https://huggingface.co/api/models/unsloth/Qwen3-1.7B-GGUF/tree/main), revision `d7f544eead698dbd1f15126ef60b45a1e1933222`.
- [Qwen 0.6B metadata](https://huggingface.co/api/models/Qwen/Qwen3-0.6B-GGUF/tree/main), revision `23749fefcc72300e3a2ad315e1317431b06b590a`.
- [Qwen 1.7B metadata](https://huggingface.co/api/models/Qwen/Qwen3-1.7B-GGUF/tree/main), revision `90862c4b9d2787eaed51d12237eafdfe7c5f6077`.

Qwen3-0.6B and 1.7B are general causal language models with 32,768-token context and
Apache 2.0 licensing. Explicit `enable_thinking=false` is a hard template switch;
the text `/no_think` alone is weaker. The cards warn about repetition. They provide
no dictation-cleanup fidelity result or CPU p95 for this machine.
[Official 0.6B card](https://huggingface.co/Qwen/Qwen3-0.6B),
[official 1.7B card](https://huggingface.co/Qwen/Qwen3-1.7B).

Qwen3.5-0.8B defaults to non-thinking mode. Its native context is 262,144 tokens and
the official card advises reducing context for out-of-memory errors. Do not accept
that context default for a short transcript editor. Its newer general benchmark
scores are not evidence of safer dictation editing. [Official 0.8B card](https://huggingface.co/Qwen/Qwen3.5-0.8B).

For a cost probe, configure one CPU inference slot, an explicit total context such
as 2,048 tokens, and bounded complete output. Count instructions, transcript and
output against that context. Bypass cleanup when the full request cannot fit.
Llama.cpp exposes context size, generation limits, CPU threads, memory mapping and
idle unloading. Its current server defaults can take context from the model and
allow unlimited output, so pinning the runtime and configuration matters.
[Runtime controls](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

A rewrite must generate the transcript again. Tokens per second and first-token
latency therefore cannot substitute for complete cleanup time. Keep ASR loaded
during the test and measure the complete process tree. Loading on key-down may hide
some cold cost behind speech, but can compete with capture and recognition. This is
an experiment to measure, not a promised optimization.

## The 7 MB punctuation model has a narrower job

Sherpa packages Edge-Punct-Casing as a 7.1 MB int8 ONNX model plus a 146 KB BPE
vocabulary. It predicts punctuation and casing, not grammar, fillers, backtracking
or missing words. Its documentation shows a one-thread CPU example taking 13 ms for
a short sentence. That is one upstream example, not Freehand latency or memory.
[Model and example](https://k2-fsa.github.io/sherpa/onnx/punctuation/pretrained_models.html).

The authors' paper reports 10 ms for one example paragraph using the quantized model
through sherpa-onnx on an Intel Core i5-1035G1. Its training and evaluation use
200-token windows and its punctuation labels cover comma, period and question mark.
Neither the paper nor the example publishes a Windows whole-app RAM measurement.
[Paper, sections 4.2 and 4.4](https://arxiv.org/pdf/2407.13142).

Pinned sherpa uses 200-subword windows, batches longer inputs, splits on whitespace,
rejoins words with single spaces, and appends predicted punctuation. It does not strip
existing marks; its mixed-case reconstruction is still a TODO. Thus it cannot safely
run unchanged after already-punctuated Parakeet output and literal dictionary
replacements. Evaluate it as a punctuation control on suitable raw input, with
protected spans and whitespace checks, rather than a default improvement.
[Pinned punctuation implementation](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.5/sherpa-onnx/csrc/online-punctuation-cnn-bilstm-impl.h).

## Measurements needed before selecting a default

1. Establish Wispr's current Windows baseline on this machine with identical audio,
   the same target application, the same length groups and repeated warm and cold
   trials. Record app version, settings, network conditions and test date. Measure
   key release to first visible text and to complete insertion separately.
2. Sample total process-tree working set and private bytes for each application,
   including all helpers, during idle, recording, processing and recovery. Record
   simultaneous totals and active peaks. Do not sum unrelated per-process peaks or
   compare a Freehand worker with the whole Wispr application.
3. Set Freehand's total RAM and latency acceptance caps from that baseline. A cleanup
   stage receives only the remaining budget after capture drain, recognition,
   formatting and delivery. The old added-cost allowances do not meet this rule.
4. Use actual failed phrases with human references. Score word substitutions,
   deletions and insertions separately from punctuation and readability. Include
   quiet input, negations, intentional repetition, spoken corrections, numbers,
   ordinary words and vocabulary. Review original audio when words are missing.
5. Compare current 110M output, the upstream feature fix, bounded hotword tuning,
   punctuation only, and then one-pass 0.6B/0.8B cleanup. Record complete-output
   p50/p95, cold load, peak RAM and edit regressions. Use 1.7B only as a quality
   comparison if the smaller models fail. Keep a no-cleanup baseline throughout.

The first implementation should be a reproducible evaluator. Preserve the original
transcript on timeout, rejected edits or worker failure. A text model cannot verify
what the microphone captured, and a finite test set cannot prove that it will never
change a name, number, negation or intended meaning.

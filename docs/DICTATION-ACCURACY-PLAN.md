# Dictation accuracy within the Wispr Flow budget

Implementation measurements and remaining limits are recorded in
[the accuracy validation](ACCURACY-VALIDATION.md).

Reviewed October 29, 2026. This is a recommendation and evaluation plan. No speech,
cleanup, package or installed-app behavior changed during this review.

Keep Parakeet 110M. First test the upstream NeMo audio-preprocessing fix against
the recordings Freehand gets wrong. Then evaluate one conservative cleanup pass
within the remaining total-app memory and delivery-time budget. A general local
language model is a benchmark candidate, not the proposed default.

## What the earlier chats established

I read the complete available turns in these two chats, plus the current source
and its research and performance notes:

- "Analyze app performance and memory", October 22, 2026,
  `01a164c9-7c79-7fc2-976f-7aa0097650b4`. Sam reported Freehand around 820 MB,
  Wispr Flow around 650 MB, and wanted substantially lower memory. After the
  model replacement, he accepted its memory use and identified wrong or missing
  ordinary words as the remaining problem.
- "Research transcript cleanup options", October 26-27, 2026,
  `01a178fb-7ea8-7242-9f63-6116bf3884bc`. Sam preferred local processing while
  comparing hosted cleanup. He requested working dictionary hints and number and
  currency formatting first. Those changes shipped in source. The language-model
  cleanup proposal was not implemented.

The current instruction is stricter than the previous proposal. The old allowances
of 750 MiB *additional* memory and one to two seconds *additional* delay are
superseded. The entire app must fit within Flow's measured performance.

## What exists now

The installed package currently reports version 1.0.3, build `15b05b1`. The source
reviewed is the same commit. This differs from the older chat's final report that
the installed copy was still 1.0.2.

| Existing behavior | Evidence and implication |
|---|---|
| CPU Parakeet TDT 110M, int8, four threads, two decoding paths | Keep this as the baseline. Wider searches and decoder precision changes were already tested without enough benefit. |
| Per-recording dictionary hotwords and literal corrections | Already implemented. Verify their effect on actual troublesome vocabulary rather than proposing the same feature again. |
| English numbers, currency and percentages | Already implemented without another inference model. |
| Segments of at most 15 seconds decoded during recording | Preserves memory and hides work before release. The final tail still decodes after release. |
| Single final insertion with SendInput | Preserve it. Cleanup must finish or fall back before delivery. |
| No language-model cleanup | Grammar repair, false-start removal and contextual backtracking remain open. |

Sources: [speech configuration](PARAKEET-WINDOWS.md),
[transcriber](../src/Freehand.Speech/ParakeetTranscriber.cs),
[dictation engine](../src/Freehand.Core/DictationEngine.cs),
[recording buffer](../src/Freehand.Core/RecordingBuffer.cs).

The earlier public-speech test improved from 71 to 67 word errors across 2,285
words, or 3.11% to 2.93%. Deletions rose from six to seven. That experiment did
not solve missing words and did not measure Sam's conversational dictation.
The tuned speech process retained about 196 MiB private memory and peaked around
290 MiB resident memory in a small fixture sequence. Its 11-second clip took
209-212 ms to decode. These exclude the desktop UI, delivery and cleanup, and
are not current whole-app latency percentiles. [Recorded results](PERFORMANCE.md).

A read-only snapshot during this review found the installed desktop process at
147.9 MiB working set and its child speech worker at 233.2 MiB. Their summed
resident footprint was 381.1 MiB, with 386.0 MiB summed private commit. This is
one sample with the worker loaded, not a peak or sustained active measurement.
Summed working sets can count shared pages more than once. Task Manager's memory
column may use a different counter, so this cannot establish the margin against
Sam's historical 650 MB observation. No Wispr process was running in the check.

## The performance contract

Wispr's inference provider describes fine-tuned Llama transcript cleanup and a
speech-to-cleaned-output pipeline below 700 ms at p99. That is evidence that
specialized remote cleanup can fit a small budget. It is a vendor deployment
claim, not a current Windows key-release-to-visible-text measurement on Sam's PC.
[Baseten customer case](https://www.baseten.co/resources/customers/wispr-flow/).

Wispr's system requirements recommend 8 GB of system RAM for Windows dictation.
They do not publish a per-app RAM ceiling. The roughly 650 MB figure comes from
Sam's earlier observation. It is a provisional comparison point, not a verified
current peak. Use bytes in the benchmark and label MB versus MiB explicitly.
[Wispr system requirements](https://docs.wisprflow.ai/articles/1036674442-supported-devices-and-system-requirements).

| Measure | Acceptance rule |
|---|---|
| Complete, visible final text after key release | Freehand must be no slower than Flow for the same duration class and warm/cold state. Compare median, p95 and observed slowest trials. |
| Normal warm dictation, provisional target | Aim for 500 ms or less to complete visible text. Use 700 ms as a provisional upper engineering budget pending the direct comparison. Neither figure establishes parity. |
| RAM across the complete process tree | Peak and retained physical memory must be no higher than Flow under matched trials. Include UI, speech, cleanup, model loading and teardown. Report private commit separately. |
| Preferred margin | Aim for at least 25% less active physical memory than Flow, and lower delivery delay. Matching Flow is the cap, not the objective. |
| Idle and first use after unloading | Compare separately. Saving idle RAM does not excuse a slower cold dictation. |
| Accuracy | Reduce wrong and omitted words on held-out conversational audio. Score this separately from formatting. |
| Cleanup fidelity | No accepted meaning-changing edits in the protected evaluation cases. Preserve dictionary literals and intentional repetitions. Report bypasses and rejected outputs. |

A finite benchmark cannot establish a universal timing guarantee or a reliable
p99 from a handful of observations. Begin with medians, p95, maxima and raw
trial counts. Accumulate enough trials before claiming tail-percentile parity.
Use Flow in healthy operation as the comparison, rather than exploiting an outage.

## Recommended order

### 1. Test the upstream quiet-audio fix with the same 110M model

The most useful new lead is sherpa-onnx
[issue #3997](https://github.com/k2-fsa/sherpa-onnx/issues/3997) and
[merged fix #3999](https://github.com/k2-fsa/sherpa-onnx/pull/3999).
The fix was merged October 21, 2026. It aligns NeMo log-mel preprocessing with
the model's training implementation. The report includes Windows int8 Parakeet
110M and recovery of words on attenuated audio. Freehand's pinned 1.13.5 source
lacks the change. Exact source comparisons are in the
[model evidence](DICTATION-MODEL-EVIDENCE.md).

This is an upstream defect with a plausible connection to Sam's missing words.
It is not yet a demonstrated cause in Freehand. For prioritization only, estimate
frequency at 3/10 and impact at 6/10, product 18. Frequency is an unmeasured
hypothesis to test, not an observed failure rate.

Replay actual failed clips at their original levels, plus controlled quieter
copies of known speech, with only the feature-extraction change varied. Keep
model hashes, decoding, dictionary and segmentation constant. Include normal
speech, quiet noise and silence as controls. Measure word deletions and
substitutions as well as complete-app timing and memory.

If it helps, select a pinned runtime containing the fix or a narrowly scoped
backport and verify native packaging. Do not bundle an arbitrary latest runtime
or another ONNX Runtime. This research does not change dependency versions.
The change needs no additional model weights; runtime RAM and delay still need
measurement.

### 2. Locate the remaining recognition losses before increasing model size

For failed clips, compare the captured audio, raw recognition, corrected text and
delivered text. This distinguishes a missing captured syllable, an ASR mistake,
a postprocessing change and incomplete delivery.

Inspect first and last words and errors near the current 15-second cuts. The
segmenter selects the lowest-energy 200 ms region, which does not prove that a
true pause exists. Only if errors cluster at cuts, compare pause-aware splitting
and a small amount of retained boundary context while keeping the 15-second
maximum input. Do not shorten every segment or add repeated full-recording
recognition without evidence. Both can consume the latency budget or remove
useful speech context.

Measure microphone level and clipping before introducing gain or noise removal.
Blind amplification can amplify noise; aggressive trimming can remove words.
Keep current dictionary biasing and test its score on Sam's names and technical
terms. It is not a general correction mechanism for ordinary missing words.

### 3. Evaluate cleanup within the remaining budget

Wispr distinguishes Smart Formatting from correcting misheard words. Its
Backtrack behavior uses the full dictation to recognize clear self-corrections.
That supports one final edit pass, but a text model cannot reliably reconstruct
audio evidence that is absent from the transcript.
[Wispr formatting and Backtrack](https://docs.wisprflow.ai/articles/5373093536-How-do-I-use-Smart-Formatting-%26-Backtrack).

| Candidate | Recommendation under this cap |
|---|---|
| Existing deterministic formatting plus narrowly specified edits | Keep as the baseline. Add rules only for demonstrated, unambiguous cases. Avoid a growing list of broad filler-removal regexes. |
| Edge-Punct-Casing INT8, about 7.1 MB weights | Cheap punctuation control. Low expected incremental value because Parakeet already produces punctuation and case. It does not provide grammar repair or Backtrack. |
| A small quantized edit-tagging model | The more promising local architecture to investigate if punctuation alone is insufficient. Predict bounded edits instead of generating the entire transcript. No verified ready-to-ship Freehand checkpoint has been selected. |
| Qwen3-0.6B Q4, about 397 MB file | One comparison candidate if desired. Its weights alone put substantial pressure on the remaining RAM. Complete generation, cold loading and fidelity must all pass. |
| Qwen3.5-0.8B Q4, about 533 MB file | Deprioritize under the hard cap. A larger file plus the speech/UI footprint leaves less room for runtime buffers. It has no demonstrated Freehand advantage. |
| Hosted, single-pass text cleanup | Include as the full-cleanup comparison because it keeps model weights off the PC. It must still pass the same total delay cap, including network and failure fallback. |

Verified artifact sizes and integration limitations are in the
[model evidence](DICTATION-MODEL-EVIDENCE.md). A model file's size is not its RAM
usage. Memory mapping does not make resident weight pages free.

Edit tagging is a real alternative to full rewriting.
[GECToR](https://github.com/grammarly/gector) predicts keep, delete, append and
replace operations, and its authors report faster inference than their seq2seq
comparison. This does not establish Freehand latency, memory or dictation cleanup
quality. The reference implementation depends on an older Python/PyTorch stack.
A Windows candidate would need a compatible export, quantization evaluation and
dictation-specific testing. Grammar benchmarks alone do not demonstrate filler
removal or contextual self-correction. Do not begin a custom training project
before the smaller evaluation establishes a benefit.

Full rewriting has an output-length cost. If a completion needs 100 output tokens
and only 250 ms remain for generation, it requires 400 output tokens per second,
before allowing for prompt processing or model loading. This is illustrative
budget arithmetic, not a throughput claim about a candidate. Reducing weights
or reporting a fast first token does not establish a fast complete transcript.

### 4. Enforce the budget in delivery

Use one optional postprocessor after dictionary correction and number formatting.
Snapshot its settings per recording. Keep raw and final text available for
comparison under the existing history preference. Preserve dictionary output
exactly, including its whitespace; never run replacement rules twice.

Use a deadline measured from key release, with time reserved for actual delivery.
Start cleanup only if its measured input-length and cold/warm class can fit the
remaining time and memory. On timeout, cancellation, incomplete output or failed
fidelity checks, deliver the existing corrected transcript. Reject late replies.
Do not retry recognition because cleanup failed, or insert a second version later.
Measure fallback delivery too; a timeout that consumes the entire delivery budget
does not satisfy the cap.

Retain the full utterance for a final Backtrack decision. Cleanup of an early
clause while recording can be invalidated by a later self-correction. It may be a
later measured optimization, but is unnecessary complexity for the first pass.

One app-owned worker and one job are sufficient for local cleanup. Bound context
and output, disable reasoning, and include worker startup in measured peaks.
Preloading on key-down trades hidden loading time for simultaneous ASR/cleanup
RAM and CPU use. Unloading ASR before loading cleanup trades the reverse. Neither
is a proven way around the two caps. Benchmark the complete lifecycle.

Hosted evaluation is optional and explicitly configured. Keep audio local and
send only the evaluation transcript text. Do not enable a hosted provider as a
silent fallback. Use one request with no tools or conversation history. A cloud
model's weights are remote, but network delay and fidelity are still constraints.

## The next concrete experiment

Build one local replay comparison before adding a product setting or bundled
cleanup model. Reuse the existing worker and performance-check machinery.

1. Collect a small set of real failures and 60-100 representative dictations,
   including unchanged good output. Keep a held-out set and pair each recording
   with both a verbatim reference and the desired cleaned text. Store audio and
   private transcripts outside tracked source files.
2. Run current Freehand and the preprocessing candidate on identical audio. Score
   raw recognition separately from text normalization and cleanup. Include quiet
   audio and words around segment boundaries.
3. Benchmark Flow with matching audio, settings, target application and network
   conditions. Use controlled audio replay where supported and a physical
   microphone/hotkey check for actual delivery. Run only one dictation app at a
   time. Record versions, bytes, timestamps and cold/warm state.
4. Repeat warm trials, separately repeat cold first-use trials, and sample the
   whole process tree throughout recording, processing, delivery and idle.
   Measure first visible text and complete visible text, not just injector entry
   or first model token. Existing headless fixture checks do not establish these.
5. Compare the no-cleanup baseline, punctuation control and one feasible local
   cleanup candidate. Include a hosted comparison only when configured. Stop a
   candidate when a memory, delay or fidelity gate fails. Report cleanup bypass
   rate so frequent fallback cannot disguise a missing quality improvement.

Require a meaningful reduction in recognition errors and a blind preference for
cleaned output, with no accepted corruption of names, numbers, negation, literal
dictionary text or intent in the protected test set. Preserve intentional
repetition and incomplete thoughts. Dictated instructions are text to edit, not
instructions for the cleanup model to follow.

The implementation decision is conditional on these results. First choice is
the current small ASR with corrected preprocessing and modest local cleanup. If
full local cleanup cannot meet the cap, keep the improved local path and compare
opt-in hosted cleanup. Do not accept Flow-like prose at a slower or larger
footprint.

This review changed documentation only. No installation, app restart, new model
download, API inference request, PR or release was performed. Future speech or
native-runtime changes require the warning-free Release build, existing tests,
focused regressions and the published executable self-test. Microphone, hotkey
and visible-delivery claims still require the physical check.

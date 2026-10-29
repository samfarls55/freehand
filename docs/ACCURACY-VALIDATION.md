# Accuracy development build

Validated October 29, 2026. This records the implementation and local experiments
from the [accuracy proposal](DICTATION-ACCURACY-PLAN.md).

## Changes

The build keeps the same pinned Parakeet 110M int8 model, four CPU threads,
80 features, two-path search, dictionary behavior and number formatting.
Sherpa-onnx is pinned to 2.0.0, the first published release containing the
[NeMo quiet-audio preprocessing fix](https://github.com/k2-fsa/sherpa-onnx/pull/3999).
It includes its own ONNX Runtime. No second inference runtime or cleanup model
is included.

Text delivery pauses Freehand's keyboard hook only after the hook thread confirms
that no keys, Windows/Alt release masking or shortcut capture remain pending.
The engine restores the hook after insertion, including a failed insertion.
It does not restart a disposed hook during shutdown. A restart failure is reported
and remains recoverable through Retry. Keys continue to pass through normally.

Unicode insertion still uses balanced SendInput events, surrogate-pair handling,
the original foreground target and a 4 ms gap between batches. The batch size is
128 UTF-16 units instead of 40. The clipboard remains untouched.

## Recognition results

The evaluator replays the real dictation engine through each published executable's
native worker. The baseline is installed version 1.0.3, source `15b05b1`, with
sherpa-onnx 1.13.5. The candidate uses the same model assets with runtime 2.0.0.
It scores raw recognition separately from final number formatting.

| Original-level speech, 2,442 reference words | Baseline | Candidate |
|---|---:|---:|
| Substitutions | 249 | 162 |
| Omitted words | 40 | 22 |
| Inserted words | 41 | 38 |
| Total word errors | 330 | 222 |
| Word error rate | 13.51% | 9.09% |

The combined result is 32.7% fewer word errors and 45% fewer omitted words.
The first 60 clips improved from 14.13% to 10.97% WER. The second untouched
60-clip set improved from 12.88% to 7.18%, or 44.2% fewer errors. No model or
decoding settings were tuned on the second set.

The inputs are the first 120 TSV rows from Google FLEURS English US dev,
revision `70bb2e84b976b7e960aa89f1c648e09c59f894dd`, licensed CC-BY-4.0.
These are read prompts, including naturally quiet recordings. They do not
establish conversational accuracy on Sam's microphone.
[Dataset and attribution](https://huggingface.co/datasets/google/fleurs).

The 10-second public JFK regression returned empty text at gain 0.001 in all
three baseline trials. The fixed runtime recovered 20 of 22 reference words in
all three trials. This is an extremely quiet controlled input, around -76.6 dBFS,
not a claim about ordinary microphone levels. Normal-volume output stayed the
same, and silence stayed empty. The packaged self-test exercises quiet speech,
silence, dictionary hints and worker restarts.

Private reports are under ignored `work/accuracy-evaluation`; the native level
sweep is under `work/runtime-accuracy`. WAV files and transcripts are not tracked.

## Cleanup models rejected

| Isolated CPU probe | Observation | Decision |
|---|---|---|
| Qwen3-0.6B Q4 | About 904 MiB peak resident memory and 578-992 ms complete cleanup across three inputs | Exceeds the RAM cap before adding Freehand |
| TeXlyre T5 small | 80-240 ms, but changed intent, dropped facts and damaged paths | Fails fidelity |
| Unbabel T5 small INT8 | Some grammar fixes, but a negation case produced empty looping output in 1.86 seconds; a path was corrupted | Fails fidelity and tail latency |

These are small evaluation sets, not model-wide quality ratings. The T5 probes
include Node and ONNX Runtime overhead and do not predict native .NET RAM.
Qwen used default weight repacking and batch settings, so this was not an
exhaustive runtime tuning study. None justified enabling rewriting in the app.
Probe sources, exact revisions, hashes and results remain under
`work/cleanup-evaluation`.

## Delivery and memory measurement

`--desktop-delivery-benchmark OUTPUT` requires an isolated data directory. It
starts after the Avalonia main window opens, runs the real native speech worker,
and confirms complete text in an owned Windows EDIT control. It includes 50 warm
dictations, fresh-worker 1/3/10-second recordings, crash recovery, timeout
retention, and unload/reload cycles. Balanced Unicode delivery and hook restoration
remain active in the measured path.

The sampler reads Windows process memory counters directly every 10 ms. Earlier
experiments using repeated .NET process/module enumeration added substantial
observer CPU overhead. Acceptance measurements use the direct native counters.
Peak values are simultaneous sums of the desktop and its current speech worker.
Working sets can count shared pages twice. Private commit is reported separately.
The measurement starts after desktop construction and covers worker startup and
teardown. Character timestamps measure receipt by the control, not compositor paint.

The final standard publish, with the guarded hook pause and 128-unit batches,
completed all 50 warm deliveries correctly. It passed crash recovery, timeout
retention and worker unload/reload checks. Its measured results were:

| Final desktop measurement | Result |
|---|---:|
| Release to first received character, median / p95 | 186 / 199 ms |
| Release to complete text, median / p95 | 684 / 723 ms |
| Slowest warm complete-text trial | 733 ms |
| Fresh-worker 1 / 3 / 10-second dictations, complete text | 241 / 240 / 735 ms |
| Peak summed resident memory | 579,940,352 bytes, about 580 MB |
| Peak summed private commit | 450,281,472 bytes, about 450 MB |

These delivery trials use the same 10-second public fixture, producing 107
transcript characters. The three cold trials use recording-speed replay and
fresh workers, with ordinary filesystem caches. They are individual observations,
not a cold percentile distribution. Full results are in ignored
`work/desktop-final-unicode.json`.

Accuracy improved and RAM remained below the provisional 650 MB cap. Complete
delivery did not meet the provisional 700 ms limit. The benchmark correctly
returned failure for that acceptance gate. This is not a claim that the full
proposal or Wispr Flow parity has been achieved.

The native batch probe delivered all 32 expected outputs, including 500-unit
Unicode input with an emoji across the 127/128 boundary, multiline input and
focus changing before insertion. A changed target received no text. The same
probe also established that roughly 500 characters can take about one second
in SendInput delivery alone on this machine, despite batching and hook pausing.
It does not establish a 700 ms end-to-end limit for long dictations.

ReadyToRun publishing was also tested as a startup experiment. It increased
the sampled desktop/worker resident peak to about 594 MB and did not bring the
short-dictation tail below 700 ms. It is not enabled in the selected build.

Wispr Flow could not be benchmarked directly. Its former installation contains
only uninstall remnants. The 650 MB memory and 700 ms delay limits remain
provisional comparison gates, not a measured Flow result on this PC.

## Reproduce

Prepare the public fixtures and run separate baseline and candidate evaluations
using [the evaluator instructions](../tools/Freehand.Evaluation/README.md).
The reports include input hashes, native library hashes, RMS, word errors and
timing mode. Silence has null dBFS rather than a non-finite JSON value. Realtime
replay schedules samples against a monotonic clock and reports capture drift.

Compiler, regression and published-native validation:

```powershell
pwsh -File scripts/verify.ps1 -Package -Dotnet C:/path/to/dotnet.exe
```

The development profile remains separate from the installed app. Installation
and public release require a separate explicit request. Physical microphone,
hotkey and rapid consecutive dictation still need Sam's hands-on evaluation.

The Release build completed with zero warnings or errors, all 274 .NET tests
passed, and the published executable passed its native self-test. The evaluator's
separate self-tests cover scoring, silent WAV input, repeated ASR failure and a
completion deadline. No clipboard delivery path has been approved or enabled.

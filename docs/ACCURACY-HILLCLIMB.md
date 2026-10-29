# Accuracy hill climb

Development status, October 29, 2026. The target is below 5% word error rate with the complete app below the provisional 650 MB system-RAM and 700 ms release-to-complete-text limits. Parakeet v2 passed the desktop performance gates but missed the accuracy target on its frozen holdout. Direct Wispr Flow parity still needs matched measurements on this machine. See the [accuracy plan](DICTATION-ACCURACY-PLAN.md).

Sam clarified that equivalent formats count as correct. The frozen metric, `freehand-content-preserving-en-v1`, uses pinned Whisper English normalization while preserving bracketed spoken content, fillers, numeric signs, currency, and percentages. Changed numbers, missing negation, wrong words, omissions, and additions remain errors. Literal scores are retained separately. The [scorer](../tools/Freehand.Evaluation/score_reports.py) passes 44 checks, including strict failure at exactly 5%.

## Development results

These are the same 120 development recordings, with 2,461 normalized reference words and 2,442 literal words. They include repeated prompts and cannot establish independent accuracy.

| Candidate | Normalized WER | Errors |
|---|---:|---:|
| Historical 110M with older runtime | 11.13% | 274 |
| Current 110M runtime | 6.42% | 158 |
| Larger v2 INT8 | 4.79% | 118 |
| Larger v2 Q4 ONNX | 4.92% | 121 |
| v2 Q4_K_M, selected Vulkan mode and production Core | 4.79% | 118 |
| v2 F16, native Vulkan screen | 4.75% | 117 |
| Qwen3-ASR 0.6B Q8, native screen | 4.31% | 106 |
| Qwen3-ASR 1.7B Q4, native screen | 3.21% | 79 |

The original literal scores remain 13.51% for the historical 110M baseline and 9.09% for the current runtime. They must not be compared with a normalized candidate score as though the metric were unchanged. None of these public read-speech results establish Sam's conversational microphone error rate.

## Desktop performance result

Software rendering saved 136.5 MiB in the isolated shown-window probe, reducing resident memory from 249.9 to 113.4 MiB. Actual Compact controls, theme, fonts, tray, and indicator were retained. Main-window captures were pixel-identical. The source change is in [Program.cs](../src/Freehand.App/Program.cs).

The v2 Q4_K_M candidate uses transcribe.cpp v0.4.1, four CPU threads, Vulkan on the RTX 4060 Laptop GPU, device-local allocation, and COOPMAT2 disabled. The model is 475,491,840 bytes. The actual published desktop plus worker passed all measured gates:

| Measurement | Result |
|---|---:|
| Conservative peak system RAM | 378,068,992 bytes |
| Dedicated VRAM peak | 534,433,792 bytes |
| Private commit peak, separate diagnostic | 1,230,848,000 bytes |
| Warm complete delivery, median / p95 / maximum | 527.9 / 657.0 / 665.5 ms |
| Cold-worker complete delivery, 1 / 3 / 10 s recording | 644.8 / 182.8 / 690.5 ms |

All 50 warm and three cold trials received complete text without operational failures. The benchmark used the real Unicode SendInput path, actual Avalonia UI, and an owned Windows EDIT control. The clipboard remained unchanged. Timestamps measure received characters, not compositor paint. These limits remain provisional because Wispr Flow was not benchmarked on this machine.

System RAM is the highest simultaneous desktop-plus-worker working set plus shared GPU memory. This deliberately permits double counting. Dedicated VRAM and WDDM private commit remain separate. A no-model allocation control showed that 512 MiB of device-local VRAM adds about 512 MiB of commit but less than 1 MiB of host working set. The [GPU accounting report](GPU-MEMORY-ACCOUNTING.md) records primary Microsoft documentation and the independent positive control.

First-use shader preparation is separate from dictation latency. Disabling COOPMAT2 reduced an isolated cold model-and-shader preparation from about 22 seconds to 5.5 seconds. The preview packager runs the published self-test before offering the app for dictation. Its first preparation logged 4,732 ms after model loading, and a cached repetition logged 359 ms.

The native dictionary adapter preserved all 120 empty-hint transcripts against stock. Positive names, unrelated hints, and request resets passed controls. The published self-test passed known and quiet speech, silence, hints, worker restart, and platform assembly loading. The strict Release build and all 283 .NET tests passed before the subsequent model experiments.

## Frozen holdout result

The v2 candidate was frozen before one run on 104 unique prompts excluding every tuning ID and exact reference. Raw and final text both scored **114 errors in 2,226 normalized words, or 5.1213% WER**, with 77 substitutions, 22 deletions, and 15 insertions. All 104 trials completed without operational failure. Literal raw WER was 145/2,212, or 6.56%; final literal WER was 142/2,212, or 6.42%.

This fails the strict under-5% target. Aggregate results were recorded before inspecting individual errors. Combining tuning and holdout scores does not turn it into an independent accuracy pass. The freeze, reports, and aggregate hashes remain under `work/accuracy-core/frozen-holdout-v1`.

The next validation set is sealed: 300 unique FLEURS TEST prompts, 6,688 literal reference words, and zero normalized-reference overlap with all 224 previously used clips. Its manifest SHA-256 is `4a945aaf9a276df8b7370fd4fb384a35c7747451fdf55bf8101ef5628fdd3df0`. All audio hashes and PCM boundaries were checked. No inference has been run. Freeze the next model and settings before using it.

## Work in progress

Qwen0.6 reduced the old development score to 4.31%; Qwen1.7 reached 3.21%. Both passed short and quiet speech controls with forty unrelated dictionary terms. Qwen0.6 nevertheless hallucinated on silence and echoed dictionary terms over zero audio. A CPU Silero speech-presence guard is being verified without cropping or changing the audio passed to recognition. The optimized CPU control accepted all 120 speech clips and rejected tested zeros, noise, and constant signals, while reducing the guard's median cost from about 98 to 16 ms.

Qwen1.7's exact ten-second fixture took about 275 ms of native recognition, and loading took about 2.3 seconds. These are not complete desktop results. The smaller model remains a performance candidate. A bounded pinned upload batch is being tested to remove hundreds of serialized model-upload waits. CPU backend changes must use a complete matching native bundle, followed by recognition and packaging checks.

Post hoc two-bit v2 quantization damaged recognition. Trained Redux, Moonshine, and Bark controls remained above the target. Earlier cleanup probes did not justify adding a rewriting model. Evidence remains under ignored `work/hillclimb-*` folders and in [the earlier validation](ACCURACY-VALIDATION.md).

The normal installation has not been updated, and nothing has been published. The public default remains the 110M CPU model. The previous development preview was restored in the tray while experiments continue. Installation, publication, physical hotkey, and microphone validation follow the separate [development workflow](DEVELOPMENT.md).

## Pause checkpoint, October 29

Work stopped at Sam's request so the laptop can be closed. No benchmark, ASR, download, compiler, or worker probe remains running. The previous approved CPU development preview is restored in the tray. The installed application has not changed.

The latest Qwen0.6 Q8 selection result is203/4687=4.3311% across224 development/validation clips. Its packaged7232 runtime with optimized CPU VAD passed published self-test, including quiet speech, silence, hints, and restart. The desktop report `work/desktop-qwen06-q8-guard.json` records413,765,632bytes conservative RAM and50 warm deliveries at501.5ms median,533.1ms p95,582.0ms maximum. Cold1/3/10second deliveries are1323.0/499.2/855.5ms, so the strict performance gate still fails. It also reports one apparent orphan process, which needs ownership/exit-state diagnosis; no process remained after the benchmark app exited.

Qwen0.6 Q4 is smaller and starts faster but has less accuracy margin:221/4687=4.7152% across224, including127/2461=5.1605% on the original120. Its guarded native API readiness was1048ms versus Q8's1740ms. Its native ten-second fixture warm p95 was175ms. No complete Q4 desktop acceptance run has been performed. A ready Q6 model may offer an intermediate tradeoff; it has not been downloaded or tested.

The next resume checks are staged worker/model/first-inference timing, the apparent orphan count, and a performance-preserving candidate choice. The official CPU/Vulkan release may replace the custom native fork because the guarded upload optimization is disabled on this hybrid laptop and Qwen does not use the custom Parakeet hint adapter. That simplification still needs parity controls. Freeze the eventual complete candidate before using the untouched300-prompt TEST set. Do not call the current candidate ready or independently below5% yet.

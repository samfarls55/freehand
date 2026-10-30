# Accuracy hill climb

Development status, October 30, 2026. Frozen source `b270da9`, **Qwen3-ASR 1.7B Q4_K_M**, scored **2.7173% normalized WER on the main fresh LibriSpeech 400** and **5.7823% on the separate fresh FLEURS 50**. The unchanged scorer gives **3.0955% across all 450**, with zero operational failures. The secondary set missed 5%; the candidate does not establish under 5% across every dataset or Sam's conversational dictation. Its complete desktop performance run passed the provisional ready-state latency and system RAM limits. On those same 450 recordings, the CPU baseline scored 4.1658%: the candidate made 102 fewer errors, a 25.69% reduction (paired recording bootstrap 95% interval 16.21–34.91%).

The working limits are **650,000,000 bytes of system RAM** and **700 ms from release to complete text receipt**. The new GPU policy applies that latency budget after the app reports ready; model startup is measured separately. The original fresh-worker 700 ms failure remains unresolved and recorded. These are provisional engineering limits: Wispr Flow has not been measured on this laptop, and Sam's microphone accuracy is unmeasured. See the [accuracy plan](DICTATION-ACCURACY-PLAN.md).

## Current candidate and readiness policy

The candidate uses pinned transcribe.cpp 0.4.1 **freehand-read2**, English, four CPU threads, context 1024, and AUTO discrete Vulkan selection with a device check. Nine-second maximum segments retain quiet-boundary selection and permit recognition while recording continues. Silero tests speech presence using a normalized copy, leaving the original ASR waveform uncropped. Software UI rendering and noncomposite ReadyToRun reduce memory and startup work. The public CPU profile retains lazy loading, five-minute idle unloading, and 15-second segments.

The GPU profile loads the actual speech worker before enabling the hotkey and keeps that worker resident. In the full run, worker and model loading took **1,677.5778 ms** and app readiness **2,075.891 ms**. These costs are outside the ready-state release budget; they are not removed from the report or counted as solved fresh-worker latency. The same worker served all four ready recordings.

Startup performs a one-second zero-input native warmup and discards its output. During an active dictation job, a separate serialized loop immediately runs the same zero-input preparation, then waits **500 ms after completion** before the next run. Capture never awaits it. Preparation can complete during recognition or delivery after release and stops when the job becomes idle. It bypasses the VAD guard only for zero-input preparation; real recognition retains normal VAD, unchanged PCM, and reset native state. No preparation text enters the delivery path.

The bounded copied-worker cadence experiment measured **294.1–298.5 ms** final 8-second recognition, including interval cancellation/in-flight drain. Preparation consumed about 19% of the capture window in elapsed native calls, versus about 14% for the one-second cadence. Those percentages are not GPU utilization or measured energy. The full desktop counters provide the separate policy check: successful preparations during each ready job were **2/6/14/17**, while all four measured 15-second idle intervals recorded **zero** preparations.

Read2 retains the bounded Windows CRT reader and reuses the loader's validated GGUF metadata instead of parsing a second tensor catalog. Catalog order, names, types, dimensions, and all 224 native transcript outputs matched read1; native Open saved about **40 ms**. The selected native DLL SHA is `6211252584ae7a478a9b8850bb1bab49e7479ff1c39847dfd53dfb7871bd9d34`. This does not establish a fixed whole-worker startup saving.

Delivery still uses paired Unicode key-down/key-up `SendInput` events. The clipboard remains untouched. Deterministic formatting preserves ambiguous comma-separated number phrases instead of partly rewriting them into text such as `17,89`.

## Frozen accuracy evidence

The frozen metric, `freehand-content-preserving-en-v1`, is unchanged. It uses pinned Whisper normalization while retaining fillers, bracketed spoken content, signs, currency, and percentages. Equivalent number formats count as correct; wrong words, changed numbers, missing negation, omissions, and additions remain errors. Literal scores remain separate.

| Qwen 1.7 evaluation | Result | Status |
|---|---:|---|
| 224 development clips, selected active-job policy | Final 192/4,687 = 4.0964%; literal 240/4,654 = 5.1569% | Selection pass; zero operational failures |
| Reused FLEURS 300, selected active-job policy | Final 313/6,733 = 4.6487%; literal 380/6,688 = 5.6818% | Validation pass; reused data; zero operational failures |
| Fresh LibriSpeech 400 | Raw/final normalized 227/8,354 = 2.7173%; literal raw 250/8,321, final 271/8,321 | Main fresh gate passed; zero operational failures |
| Separate fresh FLEURS 50 | Raw/final normalized 68/1,176 = 5.7823%; literal raw 81/1,171, final 76/1,171 | Secondary set failed 5%; zero operational failures |
| All 450 fresh clips, descriptive combined result | Final normalized 295/9,530 = 3.0955%; literal 347/9,492 = 3.6557% | Observed combined mean; does not erase the secondary miss |
| CPU baseline, same LibriSpeech 400 | Final 314/8,354 = 3.7587% | Candidate: 87 fewer errors; 27.71% relative reduction |
| CPU baseline, same FLEURS 50 | Final 83/1,176 = 7.0578% | Candidate: 15 fewer errors; 18.07% relative reduction; both exceed 5% |
| CPU baseline, descriptive 450 | Final 397/9,530 = 4.1658% | Candidate: 102 fewer errors; 25.69% relative reduction |

The package and scorer were frozen before either fresh evaluation. Freeze SHA is `8fc35eb68f27a45b48d7443c6db62daec23d1b2cd6bad5d181c00ab3966f3ae8`; the manifest pins source `b270da9`, model, native runtime, package, and scoring policy. Fresh results were recorded from aggregates before reading individual errors. Neither candidate nor scorer changed after these results, and there is no post-result tuning of this frozen candidate.

The retained CPU baseline uses the exact `4606ae1` worker and the same selected-policy evaluator, formatter and frozen scorer, with its original 15-second CPU segmentation. Both baseline replays had zero operational failures. Paired whole-recording bootstrap intervals use 10,000 resamples and seed 20261030; they describe recording sampling variation and do not model shared speakers. The 400-set relative-reduction interval is 16.50–38.19%; the 50-set interval is 2.27–34.72%.

The **5.7823% secondary FLEURS result is the main accuracy limitation**. The main LibriSpeech gate and observed combined mean are under 5%, while the separate secondary dataset is above it. General conversational WER for Sam remains unmeasured.

The previous frozen Qwen 0.6B Q6 candidate failed its independent FLEURS 300 evaluation: final **354/6,733 = 5.2577%**, raw 355/6,733 = 5.2725%, with zero operational failures. The exact package and reports remain under `work/accuracy-core/frozen-qwen06-seg9-read1-v2`; freeze SHA is `d50145024617055d87187798294902748c3f987877595de9fb8aca06fd827583`. On the same prompts and metric, the 110M CPU baseline scored **434/6,733 = 6.4459%**. Q6 reduced errors by 18.43%, with a paired interval of 9.15–27.05%, but still failed acceptance.

An earlier Parakeet v2 candidate failed its one 104-prompt holdout at **114/2,226 = 5.1213%**. Those clips were then explicitly promoted into the 224-clip development set. The failed Q6 FLEURS 300 is now reused validation for Qwen 1.7. No individual errors from that 300 were inspected to choose or tune Qwen 1.7; it had already been screened on the older development data.

Before freezing, the selected policy remained under 5% on old 224 and used FLEURS 300 and passed the complete desktop gates. One subsequent fresh evaluation used these pinned sets:

- **LibriSpeech TEST 400:** 200 test-clean + 200 test-other recordings, 8,321 literal words, 73 speakers. Manifest SHA `e6e4830a66852770083cfd18e7373f5f865cce13cd1778ceea4fdcbee006103c`. This is the main fresh accuracy gate.
- **Separate FLEURS TEST 50:** manifest SHA `ad6ccdda6ba111511209ca1029c3d9526d2a1d57c50c29097d34893a320f7f07`. Report its secondary result separately.

Both fresh sets were evaluated once against the frozen candidate. LibriSpeech differs from FLEURS; its result is not directly comparable FLEURS evidence. The table preserves both separate results. The combined 450 mean is descriptive and does not replace either dataset result. The used FLEURS 300 validation gate also passed, addressing some dataset shift without making that reused set independent.

## Desktop evidence

| Source / policy | Result | Interpretation |
|---|---|---|
| `b270da9`, resident worker + active-job preparation, full run | Ready 1/3/8/10-second delivery 143.8078/254.8326/588.8067/488.4077 ms; warm 407.609 ms median / 482.5428 ms p95 / 547.4339 ms max; RAM 436,228,096 B | Complete ready-state performance gate passed |
| `07769af`, resident worker without active preparation | 8-second delivery after idle 820.81 ms, including 558.97 ms recognition | Residency alone failed; retained evidence |
| Qwen 1.7, forced-fresh read2 worker | About 965 ms in the retained failed diagnostic | Original fresh-worker budget remains unsolved |
| `7d29409`, Qwen 1.7 read1, one-second startup warmup | Cold 1-second 723.024 ms; warm maximum 471.962 ms; RAM 420,655,104 B | Failed cold latency; all 26 workers/recovery/unload controls passed |
| Frozen Q6, streamed desktop | Warm 372.1 ms median / 448.2 ms p95 / 537.5 ms max; cold 321.1/406.4/441.8 ms; RAM 426,655,744 B | Performance pass belongs to Q6, whose independent accuracy failed |
| Q6 immediate-chunk stress | 50th warm delivery 788.5 ms despite recognition 217.9 ms | Retained failure; headless burst stress remains available |

The full report preserves one prepared worker PID across all four ready recordings, with real capture scheduling and exact `SendInput` character receipt. Its sampler began **1,054.7214 ms after launch**, while initialization was still incomplete. Earlier UI/startup allocations may precede that sampling boundary. Recorded peak dedicated VRAM was **1,719,873,536 bytes** and shared GPU memory **33,886,208 bytes**. Shared GPU bytes are included in conservative system RAM; dedicated VRAM and private commit remain separate. See [GPU accounting](GPU-MEMORY-ACCOUNTING.md).

All **50 warm ten-second recordings and four ready recordings after idle** met the 700 ms complete-delivery limit, and measured RAM stayed below 650,000,000 bytes. Separate crash recovery, timeout retention, and 20 unload-cycle controls also passed; those failure/reload controls are not a claim of 700 ms delivery. All **24 owned workers exited**, with zero orphans. Ready-only and forced-fresh cold-only modes were separate diagnostics. The full report retains startup duration, sampling scope, residency, per-job preparation counts, and zero idle preparation counts. This proves the measured ready-state budget, not a universal fresh-worker 700 ms bound.

The benchmark uses the actual Avalonia composition and its tracked published worker, an owned Windows EDIT control, and real `SendInput`. Recordings arrive in 50 ms chunks so progressive decoding can run before release. Timestamps measure character receipt, not compositor paint. RAM is the highest simultaneous desktop-plus-worker working set plus shared GPU bytes, conservatively permitting double counting. Fixture replay does not establish physical microphone, physical Right Ctrl, or delivery into Sam's real applications. Direct Wispr Flow parity is unmeasured.

## Selection history and verification

| Alternative | Evidence | Outcome |
|---|---|---|
| Current 110M CPU runtime | 6.42% normalized on original 120; 6.4459% on FLEURS 300 | Above accuracy target |
| Parakeet v2 Q4 Vulkan | Desktop pass; independent 104 at 5.1213% | Failed independent accuracy |
| Qwen 0.6B Q6, stock reader | Cold delivery reached 1,132 ms | Reader bottleneck corrected |
| Qwen 0.6B Q6, 8-second segments | Final 240/4,687 = 5.1205% | Rejected accuracy regression |
| Earlier Qwen 1.7 Q4, 9-second warmup | Cold 1-second 731.6 ms; warm burst maximum 760.6 ms | Failed performance; preserved |
| Shorter zero-input preparation | 100 ms input gave no reliable latency or compute saving | Rejected; selected preparation input remains one second |

Current source passes the strict Release build with warnings as errors, **319 .NET tests**, and published CPU and GPU preview self-tests. The active-preparation changes are recorded in `fb0ae24`, `2e8d56d`, `62851a6`, and `b270da9`; `b270da9` fixes the evaluator's active-job scope so preparation stops between jobs. Native read2 is `ad64ea0`. Earlier **45 script tests** and **three isolated update checks** passed; their update code is unchanged. The 1.7B NOTICE and model/runtime/source/output hashes are preserved.

The published GPU executable also passed five hide/reopen and tray Settings cycles followed by explicit Quit after the final accuracy tests.

The isolated preview launcher is `artifacts/accuracy-preview/Start Freehand Accuracy.cmd`. Its profile and data remain separate from the installed app. The normal installation has not been updated; nothing has been pushed, merged, or published. The public default remains the 110M CPU model. Sam still needs to test a real microphone, Right Ctrl, and foreground text fields under the [development workflow](DEVELOPMENT.md).


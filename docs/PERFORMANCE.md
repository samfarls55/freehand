# Performance analysis, October 22, 2026

## Dictionary bias and number formatting, October 26

Enabled dictionary terms and correction targets now reach the speech worker and
the per-stream native hotword graph. The recognizer keeps its pinned model,
four inference threads and two active decoding paths. NVIDIA's original 10,962-byte
SentencePiece vocabulary supplies the missing tokenizer information. English
number/currency formatting runs in managed code after joining segments and applying
literal corrections. It protects dictionary outputs and adds no inference model.

A temporary console probe compared the previous recognizer configuration with
the updated adapter in separate processes. Each process loaded the same verified
110M assets, transcribed the first ten seconds of the public JFK fixture once to
warm up, then ran twenty timed transcriptions. The forty-phrase case used invented
`example phrase N` entries, not Sam's dictionary. A second series repeated baseline
and biased runs to check ordinary timing variation.

| Isolated process | Retained private memory | Working set | Warm median | Warm p95 |
|---|---:|---:|---:|---:|
| Previous configuration, two series | 186.6-187.2 MiB | 215.7-216.3 MiB | 223-237 ms | 261-279 ms |
| Updated adapter, no hotwords | 189.0 MiB | 220.6 MiB | 259 ms | 281 ms |
| Updated adapter, forty phrases, two series | 189.2-189.3 MiB | 221.1-221.2 MiB | 224-254 ms | 270-293 ms |

Loading took 931-973 ms in these observations. All transcripts retained the same
fixture wording. The observed incremental footprint was roughly 2-3 MiB private
memory and 5 MiB working set. Timings overlap across series; they do not establish
a speed improvement or a stable latency penalty. These are isolated process
measurements, excluding the UI, capture, pipe overhead and delivery.

The native tokenizer creates a pool based on hardware concurrency, so observed
process threads increased from seventeen to thirty-nine, even though ASR inference
still uses four threads. The pool belongs to the existing speech worker and exits
with it after idle unload. This implementation does not introduce another resident
service. Raw probe source and results remain in ignored `artifacts/native-probe`.

The measurements do not establish recognition accuracy for Sam's names or physical
microphone dictation. The published self-test exercises empty, populated and cleared
hotword requests across worker restarts. Meaningful microphone and dictionary-term
accuracy evaluation remains a hands-on check.

The initial audit below used the former 0.6B model. The current source replaces it
entirely with Parakeet TDT 110M, as requested after testing. See
[the replacement measurements](#model-replacement-follow-up).

The largest measured costs were native inference memory retained after long recordings
and decoding the entire recording after key release. A separate bug in fallback microphone
conversion could keep a capture callback generating silence indefinitely.

This audit covers capture and resampling, hotkey dispatch, dictation orchestration,
segmentation, worker lifetime, IPC, native recognition, dictionary correction, insertion,
history, and UI notifications. The changes are on `codex/performance-audit`, based on
`a038719`. The installed app and GitHub releases were not changed.

## Measurements

The baseline and final source use the same Release configuration, .NET 10.0.0,
Parakeet TDT 0.6B v2 int8 revision, CPU provider, four inference threads, 128 features,
and greedy decoding. Measurements were taken sequentially on the development laptop,
an Intel Core Ultra 7 155H with 22 logical processors and about 15.4 GiB of physical RAM.
Other desktop applications remained running.

The headless benchmark replays public fixture audio at recording speed through the real
dictation engine and native worker. Each run uses 10, 30, 60, and then 10 seconds of audio.
The injector counts delivery calls without typing. Memory is sampled every 10 ms.
These are individual observations, not P95 estimates or guarantees.

| Measurement | Baseline | Final source |
|---|---:|---:|
| First 10-second clip, release to transcript | 546 ms | 624 ms |
| 30-second clip, release to transcript | 1,665 ms | 288 ms |
| 60-second clip, release to transcript | 3,780 ms | 407 ms |
| Subsequent 10-second clip, release to transcript | 514 ms | 504 ms |
| Worker private memory retained after 60-second clip | 1,831 MiB | 691 MiB |
| Worker resident memory after 60-second clip | 1,401 MiB | 729 MiB |
| Peak worker private memory during 60-second clip | 1,837 MiB | 786 MiB |
| Peak worker resident memory during 60-second clip | 1,407 MiB | 814 MiB |

The 60-second sample reduced release delay by 89%, retained private memory by 62%,
and resident memory by 48%. The first short request was 78 ms slower; the last short
request was 10 ms faster. This is a substantial long-recording improvement, with short
dictation still around half a second. In the final 60-second trial, 53 seconds of audio
had already been decoded at release. The baseline had decoded none.

Private bytes measure committed private memory. Working set measures resident pages and
includes shared pages. The worker values exclude the Avalonia window and tray. The host
measurement is a headless benchmark process, so it does not establish the full desktop
app's RAM use.

Cold model loading measured 3.65 seconds in the baseline and 2.22 seconds in the final
run; another intermediate run took 3.54 seconds. These observations do not establish
a reliable cold-start improvement. Loading starts at key press and can
overlap speech, so the release delay of a cold, short recording can be much longer than
the warm values above. Disk caches were not cleared between runs.

## Causes and changes

### Fallback capture could manufacture endless silence

`WasapiAudioCapture` drains its managed converter until it returns zero samples.
NAudio's buffered source defaults to filling empty reads with silence, so the converter
could keep returning full buffers even after all captured input was consumed. That keeps
the callback busy, allocates arrays, fills the capture channel, and interferes with stop
and drain. This path is used when the preferred native 16 kHz mono float format fails.

The reproduction supplied 50 ms of 48 kHz stereo input. Twenty reads produced 2,000 ms
of output with zero source bytes left. The guard stopped the reproduction; the original
callback had no such guard. This establishes the code defect, not whether this laptop's
microphone selects that fallback.

The converter is now an internal `AudioResampler` with `ReadFully = false`. Tests use the
same converter as the capture callback. They check mono, stereo, multichannel and PCM16
input, bounded output, recovery on subsequent callbacks, and ownership of returned arrays.
The converter's buffers are released when capture stops.

### Native buffers stayed resident until worker exit

The baseline worker grew from about 686 MiB private memory after loading to over 1.8 GiB
after longer inputs. A subsequent short request kept that allocation. This accounts for
most of the measured active memory, independently of the UI and transcript history.

The shipped `speech-cpu.config` sets `EnableCpuMemArena=0`, releasing temporary allocations
between requests. Memory-pattern planning stays enabled to reduce short-clip overhead.
This configuration is supported by the pinned sherpa-onnx version's
[session implementation](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.5/sherpa-onnx/csrc/session.cc).
The file is copied to build and publish output and exercised by the published self-test.

Experiments compared default allocation, arena disabled, memory patterns disabled,
and both disabled. Keeping the arena with 15-second segments and patterns disabled
retained about 960 MiB in a fixture sequence. Disabling the arena retained about
690 MiB. Disabling both also slowed short requests, so the final configuration keeps
memory-pattern planning enabled. The selected configuration prioritizes retained RAM;
allocation overhead still affects short-clip latency.

### All decoding waited for key release

Previously, capture collected the complete recording, copied it into another array,
then split it into requests of up to 60 seconds. Model loading overlapped recording,
but inference did not. Release therefore paid the inference cost of the whole recording.

`RecordingBuffer` now retains owned segments and queues completed portions for sequential
decoding while capture continues. Requests contain at most 15 seconds. A cut favors a
pause in the last three seconds, scored over 200 ms. Release drains the final callback
and decodes the remainder. Dictionary corrections and insertion still operate once on
the complete text. No partial text is inserted while the key is held.

The full recording remains available for retry as segments, without a second contiguous
copy. Failure discards partial text and retries all segments once. A second failure
retains one recording for Retry or Discard. Cancellation terminates the worker so an
obsolete response cannot affect the next recording.

The original 20 ms pause score was too short for more frequent cuts. A native check of
three complete JFK clips produced one repeated word. Scoring 200 ms removed the duplicate.
The final output matched all 66 baseline words in order after ignoring punctuation and
case. This is a limited fixture check; shorter segments can still change recognition,
punctuation, and capitalization on other speech.

### Audio was copied repeatedly

The capture contract already transfers ownership of each float buffer. The engine no
longer copies every captured chunk and then flattens the full recording. It assembles
bounded inference segments instead.

IPC now uses a reusable 64 KiB transport buffer rather than allocating a second
segment-sized byte array on both ends. The worker allocates its owned float array once,
and the native adapter reuses it when it covers the whole array. A sliced input still
gets copied before the array-only native API. Transport buffers are cleared before
returning to the pool. Tests verify round-trip ownership and invalid/truncated input.

### UI events could accumulate

Every audio buffer raised an application change event, each of which queued a dispatcher
callback. The app now keeps at most one pending feedback refresh and reads the latest
state when it runs. Native work stays off the hotkey thread and UI updates remain on
Avalonia's UI thread. This is a bounded scheduling improvement; no separate UI RAM or
rendering speed improvement is claimed.

## Remaining costs and opportunities from the initial audit

- The same model still needs several hundred MiB while loaded. The pinned model files
  total about 631 MiB. A much smaller active footprint requires evaluating different model
  assets or changing where inference runs, with accuracy, privacy, and hardware tradeoffs.
- Short recordings below the segmentation threshold still decode after release. They
  do not receive the overlap benefit. Lower latency needs a separately measured approach
  such as decoding on actual pauses or a streaming recognizer. Those changes need broader
  recognition-quality tests.
- Cold loads remain expensive. The five-minute idle policy is unchanged. A shorter idle
  timeout releases model memory sooner but increases cold starts; a longer timeout does
  the reverse. Permanently preloading would increase idle RAM.
- `SendInput` sends 40 UTF-16 units per block and requests 4 ms between blocks. A 5,000-unit
  transcript requests about 496 ms of pacing, before scheduler and target-app costs.
  There is no added pre-insertion delay. Larger batches need delivery tests in real
  applications before changing the pacing and focus checks. This benchmark does not
  measure real key events reaching a foreground field.
- Dictionary rules are constructed for each dictation. Reusing a rule set could help a
  very large dictionary, but would retain regex objects. Native inference dominated this
  fixture; no measured saving is claimed for caching rules.
- History retains at most 100 records in its page cache. Search can still scan a large
  file synchronously as each character is entered, and the view rebuilds up to 100 rows
  after an update even when hidden. Debouncing search and deferring hidden refreshes are
  candidates for a history-focused profile. They do not explain the native worker's GiB
  measurements.

## Reproduce and validation

Build and test with the pinned SDK, then package and run the published self-test:

```powershell
pwsh -File ./scripts/verify.ps1 -Package -Dotnet 'C:/path/to/dotnet.exe'
```

Run the performance check against a complete package. It takes about two minutes, uses
only the bundled public fixture, and does not record a microphone or type into a field:

```powershell
$output = Join-Path $PWD 'artifacts/performance.json'
$arguments = '--performance-check "{0}"' -f $output
$check = Start-Process -FilePath './artifacts/publish/Freehand.App.exe' `
    -ArgumentList $arguments `
    -WindowStyle Hidden -Wait -PassThru
if ($check.ExitCode -ne 0) { throw 'Performance check failed.' }
Get-Content ./artifacts/performance.json
```

JSON contains
timing, memory and correctness failures; it does not contain transcript text or audio.
The earlier baseline was the same benchmark added to an unchanged archive of `a038719`.
Local raw results and the rejected configuration experiments are under ignored `work/perf`.

- Release build with `--no-incremental -warnaserror`: zero warnings and errors.
- All 115 .NET tests passed: 59 core, 24 dictionary, 26 headless UI, and 6 Windows tests.
- `verify.ps1 -Package` built the installer and passed the published executable's
  `--selftest`, including native known-speech transcription and worker stop/restart.
- The final fixture replay completed all four dictations with no correctness failures
  and exactly one injector call per recording.
- The 66-word repeated full-speech comparison matched the baseline words in order.
- Regression tests cover decoding before release, waiting for capture drain, corrections
  spanning segments, retry after partial decoding, cancellation, microphone failure,
  recording limits, pause selection, pipe ownership, invalid input, and converter underrun.
- `git diff --check` passed.

No installed update or public release was performed. The local candidate remains version
1.0.0 and identifies the source as `a038719-dirty`. Physical microphone selection, a
physical Right Ctrl press, and delivery into foreground applications still require a
hands-on check. Automated fixture and converter tests do not establish those hardware
claims. Wispr Flow was not benchmarked in this session.

## Model replacement follow-up

The running 0.6B development app measured 839 MiB of combined private resident memory,
including 687 MiB in the worker and 152 MiB in the desktop process. That confirmed the
remaining memory complaint after the initial fixes.

Two isolated runtime experiments did not help. Disabling weight prepacking increased
loaded worker private memory from about 687 MiB to 1,316 MiB. Disabling graph optimizations
retained about 699 MiB and did not improve the sampled latency. Neither change was kept.

The replacement is NVIDIA's English Parakeet TDT-CTC 110M, using the transducer export
from the [pinned sherpa-onnx recipe](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.5/scripts/nemo/fast-conformer-hybrid-transducer-ctc/run-transducer-non-streaming.sh).
The [original NVIDIA model card](https://huggingface.co/nvidia/parakeet-tdt_ctc-110m)
describes its English punctuation and capitalization support. The project now has one
model: CPU, four threads, 80 features, and `nemo_transducer`. The manifest pins its archive,
individual file hashes, configuration, and directory. No optional model mode was added.

The model files total 130.2 MiB, compared with 630.6 MiB previously. The generated local
installer is about 306 MiB. The following isolated native comparison used the same pinned
sherpa-onnx runtime, CPU settings, allocator configuration, public audio and process harness.

| Measurement | Former 0.6B model | Replacement 110M model |
|---|---:|---:|
| Loaded process private memory | 689 MiB | 187 MiB |
| Retained private memory after fixture sequence | 695 MiB | 191 MiB |
| Peak process private memory | 765 MiB | 256 MiB |
| Peak resident memory | 796 MiB | 289 MiB |
| Load time | 2,315 ms | 971 ms |
| Full JFK clip, warm inference, two observations | 614–617 ms | 220–223 ms |
| 7.4-second speech clip, warm inference | 423–428 ms | 135–140 ms |

These process measurements exclude the desktop UI and are not a measured combined-app
budget. A smaller speech worker should lower the combined footprint substantially;
physical dictation is needed to measure the full app during actual use.

Three public clips ran three times per model. Wording was similar, with punctuation,
capitalization and one proper-name spelling difference. This small comparison does not
establish general recognition accuracy, particularly for Sam's vocabulary and microphone.
The development app was restarted with the new model for that test.

The replacement passed the warning-free Release build, all 116 .NET tests, all 23 deployment
script tests, archive and file checksum verification, and the published executable's native
speech self-test including worker restart. The installed app and public release were not
updated. Raw isolated model comparisons remain in ignored `work/model-evaluation`.

## Accuracy tuning with the 110M model

The next comparison kept the same int8 model, CPU provider, four threads, 80 features,
allocator settings and 15-second segmentation. It varied decoding parameters and the
precision of the small decoder and joiner components. The pinned runtime implements
both search methods and blank penalties in its
[NeMo recognizer](https://github.com/k2-fsa/sherpa-onnx/blob/v1.13.5/sherpa-onnx/csrc/offline-recognizer-transducer-nemo-impl.h).
An external language model is not connected in that implementation, so the generic
`LmConfig` field is not an accuracy switch for this model.

The first set contained all 73 clips from the public
[LibriSpeech dummy validation subset](https://huggingface.co/datasets/hf-internal-testing/librispeech_asr_dummy),
with 1,150 reference words from one speaker. A second set contained 54 clips from nine
different speakers in
[LibriSpeech test-clean](https://huggingface.co/datasets/openslr/librispeech_asr).
It selected six consecutive clips at offsets 0, 300, 600, 900, 1200, 1500, 1800, 2100 and
2400, giving another 1,135 words. These are samples of read speech, not Sam's microphone
or conversational dictation. The corpus is attributed and licensed by
[OpenSLR](https://www.openslr.org/12).

Word scoring lowercases text, removes punctuation and apostrophes, and expands `Mr`
and `Dr` to their spoken forms. It counts insertions, deletions and substitutions using
word edit distance. It does not standardize numbers or American and British spelling.
All configurations decoded every selected clip. The second set was scored separately;
it was also used to compare the combined search and blank-penalty experiment.

| Configuration | Errors in first set | Errors in second set |
|---|---:|---:|
| Previous greedy search, blank penalty 0 | 52 | 19 |
| Two-path search, blank penalty 0 | 48 | 19 |
| Four-path search, blank penalty 0 | 48 | 19 |
| Eight-path search, blank penalty 0 | 48 | Not tested |
| Greedy search, blank penalty 0.25 | 51 | 18 |
| Two-path search, blank penalty 0.25 | 49 | 19 |
| Float32 decoder and joiner, greedy search | 52 | 18 |

The default is now `modified_beam_search`, with `MaxActivePaths = 2` and the default
blank penalty of zero. This reduced counted errors from 71 to 67 across 2,285 words,
or 3.11% to 2.93%. Four-path and eight-path search added time without further reduction
on the first set. The combined blank-penalty experiment did worse than two-path search
alone, so it was not selected. Greedy penalties of 0.5 and 1.0 were also tested on the
first set; they produced 51 and 52 errors respectively. The larger penalty regressed
two clips. Float32 decoder alone left the first-set errors unchanged; float32 joiner
alone also left the total unchanged and regressed two clips. No precision change was kept.

One ordinary-word improvement changed "less interesting than his manner" to the
reference's "less interesting than his matter". Other gains involved proper names and
British spelling. Across both sets, substitutions fell from 61 to 56, insertions stayed
at four, and deletions rose from six to seven. This is a modest improvement in word
selection. It does not establish a reduction in missing words or general accuracy for
Sam's speech. Replaying an actual failed phrase would be the stronger next test.

A separate small-fixture probe avoided holding the entire corpus in memory. Both
configurations loaded the same three public clips used in the model-replacement check
and decoded each three times, in separate processes with the same pinned runtime.

| Isolated process measurement | Greedy | Two-path search |
|---|---:|---:|
| Retained private memory after the sequence | 189 MiB | 196 MiB |
| Peak private memory | 254 MiB | 258 MiB |
| Peak resident memory | 286 MiB | 290 MiB |
| 11-second JFK clip, two warm observations | 200-204 ms | 209-212 ms |
| 7.4-second clip, two warm observations | 138-146 ms | 139-158 ms |

These are process measurements, excluding the desktop UI. The full-corpus harness
retains all input audio, so its absolute footprint is not a production worker estimate.
The memory difference in the smaller probe is about 7 MiB. The model assets and installer
payload are unchanged. Eighteen selected-configuration trials on silence, quiet noise
and a low hum all returned empty text, as did the greedy baseline. They do not establish
behavior for every real background sound.

Raw comparisons, scoring and fixture-download records remain under ignored
`work/accuracy-evaluation`; the native probe is under `work/model-perf`. These experiments
do not capture microphone audio or inject text into another application.

The selected change passed the warning-free Release build, all 116 .NET tests, the
published executable's native speech self-test and worker restart check, and
`git diff --check`. The development app was rebuilt and restarted for hands-on testing.
The local version remains 1.0.0 with source `a038719-dirty`. The installed copy was not
updated and no GitHub Release was published.

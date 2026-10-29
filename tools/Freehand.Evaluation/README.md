# Dictation replay evaluator

This tool runs the real `DictationEngine` and the selected application's native
speech worker. Capture replays a WAV file and injection counts delivery calls.
It does not record a microphone, own the global hotkey, or type into another app.

Prepare 60 public English read-speech clips with pinned source and audio hashes:

```powershell
python scripts/prepare-dictation-fixtures.py --count 60
```

The preparation script downloads the 171 MB FLEURS English dev archive into
ignored `work/accuracy-evaluation`. The source is Google FLEURS at revision
`70bb2e84b976b7e960aa89f1c648e09c59f894dd`, licensed CC-BY-4.0.
See [the dataset card](https://huggingface.co/datasets/google/fleurs).
FLEURS is read speech. These tests do not establish conversational accuracy or
accuracy on a particular person's microphone.

Use `--offset 60 --count 60` to prepare a separate untouched set from TSV rows
60-119. It writes `manifest-60-119.json` beside the original manifest and reuses
the verified archive. No model or settings should be tuned on that second set.

Run the installed baseline and candidate separately against the same manifest:

```powershell
pwsh -File scripts/evaluate-dictation.ps1 `
  -App "$env:LOCALAPPDATA/Programs/Freehand/Freehand.App.exe" `
  -Manifest work/accuracy-evaluation/fleurs-en-us/manifest.json `
  -Output work/accuracy-evaluation/baseline.json `
  -Gains '1,0.1' -Repeat 3

pwsh -File scripts/evaluate-dictation.ps1 `
  -App artifacts/publish/Freehand.App.exe `
  -Manifest work/accuracy-evaluation/fleurs-en-us/manifest.json `
  -Output work/accuracy-evaluation/candidate.json `
  -Gains '1,0.1' -Repeat 3
```

Use `-Dotnet` for a locally installed SDK. `-ModelSource` selects the same pinned
110M assets explicitly. Gains below one test attenuation and must be reported
separately from native recordings. Copies falling below the engine's silence
threshold can bypass recognition; this is visible in RMS and empty-output scores.

Default accelerated replay measures accuracy and reports its timing mode.
`-Realtime` feeds chunks at recording speed to exercise decode overlap.
It schedules chunks against a monotonic clock and records capture duration and
drift separately so scheduler overhead cannot silently stretch the recording.
`-Cold` resets and loads the worker before every recording and records loading
separately. It is not a cold key-release-to-delivery measurement. Use the app's
graphical benchmark for visible delivery and desktop memory.

Reports contain per-clip substitutions, deletions, insertions and aggregate WER
for raw ASR and final formatted text. Scoring ignores punctuation and case and
removes apostrophes. It does not equate digit and word forms of numbers, so final
formatting WER needs interpretation. It never treats formatting WER as raw ASR
quality. Warm repeat scores should match; repeated text is not independent audio.

The memory sampler records simultaneous sums for the evaluator and its worker,
including loading. It excludes Avalonia UI and other Freehand instances. Working
sets may double-count shared pages. These figures do not establish whole-app RAM
or Wispr Flow parity. Transcript text is omitted unless `-IncludeText` is supplied.

Each recording stops waiting when the engine finishes, awaits a manual retry, or
stops. A separate after-release deadline defaults to 180 seconds and can be set
with `-CompletionTimeoutSeconds`. A failed or expired trial is recorded in
`Failures` and the command exits unsuccessfully after writing its report. This
deadline bounds a broken evaluation; it is not the product latency target.

Personal recordings can use a local manifest with a `clips` array. Each entry
needs `id`, `audioPath`, `reference`, and optionally `sha256`. Audio must be 16 kHz
mono PCM16 or float32 WAV. Keep private audio and transcripts in ignored folders.
Use an empty reference for silence controls. Their word error rate is undefined,
so the report omits it and still reports insertions. Digital silence also omits
RMS dBFS because its logarithmic level is undefined.

The scoring self-test runs without a model:

```powershell
dotnet run --project tools/Freehand.Evaluation -c Release -- --selftest
```

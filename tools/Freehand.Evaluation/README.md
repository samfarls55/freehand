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

Keep final evaluation prompts separate from tuning prompts. Different speakers
can read the same FLEURS reference, so splitting adjacent TSV rows does not
guarantee independent prompts. Exclude both prompt IDs and exact reference text
already present in the tuning set before selecting new evaluation recordings.

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

For the accuracy acceptance score, rescore saved reports with the standalone
Python CLI. It equates number formats while preserving bracketed spoken words,
fillers, negation, numeric signs, percentages, and currency. It retains the
original literal score separately and never changes dictation output.

```powershell
python -m venv work/wer-env
work/wer-env/Scripts/python -m pip install -r tools/Freehand.Evaluation/requirements-normalization.txt
work/wer-env/Scripts/python tools/Freehand.Evaluation/score_reports.py --selftest
work/wer-env/Scripts/python tools/Freehand.Evaluation/score_reports.py `
  work/accuracy-evaluation/candidate.json `
  work/accuracy-evaluation/candidate-heldout.json `
  --max-word-error-rate 0.05 --output work/accuracy-evaluation/normalized.json
```

The inputs must include reference and transcript text. Generate the replay report
with `-IncludeText`; the scoring CLI omits that text from its output by default.
It selects gain 1/repeat 0, uses `RawText` or native-worker `Text`, and aggregates
the supplied reports. Use `--gain`, `--repeat`, `--text-field FinalText`, or
`--include-text` when explicitly needed. Exactly 5%, undefined WER, or recorded
trial failures fail the normalized gate. Keep latency and whole-app RAM gates
separate, and compare baseline and candidate with this same scoring metric.
Known literal-threshold failures from a configured legacy literal gate are
counted separately; operational or unrecognized failures still fail evaluation.

The CLI vendors unmodified OpenAI Whisper normalizer source at revision
`86098128c0b4f24f0e2aa2994de830614b474227`, with its MIT license. It verifies the
source hashes in `normalization/source.json` and records them, the wrapper hash,
dependency versions, input hashes, and exact S/D/I counts in each result.
The wrapper preserves words that the official default normalizer deletes, and
protects numeric signs and word-adjacent percent symbols before normalization.

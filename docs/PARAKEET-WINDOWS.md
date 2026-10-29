# The bundled Windows speech model

The Windows installer includes NVIDIA Parakeet TDT 110M, exported to ONNX and
quantized to int8. English dictation runs locally through sherpa-onnx on the CPU.
The packaged app needs no model download or model service.

The speech runtime is pinned to sherpa-onnx 2.0.0. Its NeMo feature extractor
matches the model's additive log-zero guard, improving recognition of quiet
speech without changing model weights. The packaged self-test covers quiet
speech and silence. See [the accuracy validation](ACCURACY-VALIDATION.md) for
paired results and their limits.

## Installed files

The model lives beside the installed executable in `models/parakeet-110m`.
Settings shows the resolved path and distinguishes **installed** from **loaded**.
An unloaded model is normal: Freehand starts without a speech worker and unloads after
five idle minutes by default.

| Asset | Exact bytes |
|---|---:|
| `encoder.int8.onnx` | 131,113,202 |
| `decoder.int8.onnx` | 3,955,863 |
| `joiner.int8.onnx` | 1,411,403 |
| `tokens.txt` | 9,953 |

`packaging/model-manifest.json` records each SHA-256 hash, the 80-feature encoder
configuration, and the pinned upstream archive. The archive SHA-256 is
`f628312e9fdf8686374cb01a69425c41732529d540860311f16f37cbc32cfe9b`.
The installer validates its payload and
the model. The app rechecks assets when file metadata changes; routine dictation does
not rehash the model. Repair always verifies the full model.

If Settings has a custom model path, that path is used explicitly. **Use bundled model**
returns to the installed assets. A missing or damaged bundled model has a **Repair** action;
re-running the saved installer also restores the files. Settings, dictionary, and history
are preserved.

## Developer configuration

Preserve these settings when changing speech code:

```text
Sample rate:     16000 Hz
Audio:           owned mono float32 samples
Features:        80
Model type:      nemo_transducer
Provider:        cpu
Threads:         4
Decoding:        modified_beam_search
Active paths:    2
Blank penalty:  0
Modeling unit:  bpe
Hotword score:  1.5
```

Native loading and inference run only in the app-owned worker. The desktop app never
loads the recognizer. Two decoding paths gave a modest word-error reduction in the public
speech comparison, with little additional memory. Wider searches and a positive blank
penalty did not improve the selected configuration. See [PERFORMANCE.md](PERFORMANCE.md)
for the measurements and their limits.

Recordings are split into pieces of at most 15 seconds, favoring
pauses scored over 200 ms. Completed pieces decode while capture continues. Release
drains capture and finishes the tail before correcting and inserting the whole transcript.
One retained recording supports retry without repeating delivery.

Dictionary bias phrases cross the authenticated worker pipe with each segment.
The worker creates a fresh native context graph for that request, using enabled
terms and correction targets. Clearing or editing the dictionary changes the
next recording without reloading model weights. Literal corrections still run
after all segments are joined.

The shipped `parakeet-110m.bpe.vocab` is NVIDIA's unchanged 10,962-byte tokenizer
vocabulary, extracted from the original model at revision
`431a349f3051ab85c22b9b7a2741b5fe77065665`. All 1,024 pieces match the pinned
`tokens.txt` in order. The worker verifies its SHA-256 before native loading.
Keep this file beside the executable. The pinned .NET wrapper omits the native
per-stream hotword method, so a small SafeHandle binding calls the existing C
API without changing package versions or reflecting into private handles.

English number and currency formatting runs once in Core on the complete
transcript, after dictionary correction. It protects literal replacements and
saved terms and uses invariant culture. Its examples and exclusions are in
`shared/text-normalization-test-vectors.json`. This managed pass does not use
`RuleFsts` or `RuleFars`: those require separate compatible English grammar
assets, which the pinned speech model does not include. No additional inference
model or native runtime is added.

The published `speech-cpu.config` disables ONNX Runtime's CPU memory arena so temporary
inference allocations are released after each request. Memory-pattern planning stays
enabled. The 15-second segment limit bounds temporary memory. The smaller model replaced
the 0.6B v2 model; this build has one model configuration.
Keep this configuration file beside the executable when copying a build.

For source builds, place the same pinned assets under the output directory's
`models/parakeet-110m`, use the release script, or select their directory in Settings.
The `%LOCALAPPDATA%\Freehand\models\parakeet-110m` cache may be reused at build time.
Packaged operation uses the installed assets independently of that folder.

An old custom path to 0.6B v2 assets fails verification. Select **Use bundled model**
after installing this build. The previous installed app remains unchanged until deployment.

## Troubleshooting

| Symptom | Action |
|---|---|
| Model installed, unloaded | Start dictation; this is the normal idle state. |
| Custom path unavailable | Select **Use bundled model** in Settings. |
| Bundled asset verification fails | Choose **Repair**, or run the installer again. |
| No audio heard | Check the microphone connection and Windows desktop microphone access. |
| Worker fails twice | Choose **Retry** or **Discard** for the retained recording. |
| Text delivery incomplete | Check the target and use **Copy**; automatic delivery will not repeat. |

Settings can open the local diagnostic log folder. Logs contain state and timing metadata,
not audio or transcript text. Machine measurements and their limits are recorded in
[WINDOWS-VERIFICATION.md](WINDOWS-VERIFICATION.md).

The model's attribution and CC-BY-4.0 identification are included in
`THIRD-PARTY-NOTICES.txt` in the installation, along with dependency notices under `licenses`.

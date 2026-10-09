# The bundled Windows speech model

The Windows installer includes NVIDIA Parakeet TDT 0.6B v2, exported to ONNX and
quantized to int8. English dictation runs locally through sherpa-onnx on the CPU.
The packaged app needs no model download or model service.

## Installed files

The default model lives beside the installed executable in `models/parakeet-v2`.
Settings shows the resolved path and distinguishes **installed** from **loaded**.
An unloaded model is normal: Freehand starts without a speech worker and unloads after
five idle minutes by default.

| Asset | Exact bytes |
|---|---:|
| `encoder.int8.onnx` | 652,184,296 |
| `decoder.int8.onnx` | 7,257,753 |
| `joiner.int8.onnx` | 1,739,080 |
| `tokens.txt` | 9,384 |

`packaging/model-manifest.json` records each SHA-256 hash and revision
`1ab9323565ddb038682214b292f588070a538ce2`. The installer validates its payload and
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
Features:        128
Model type:      nemo_transducer
Provider:        cpu
Threads:         4
Decoding:        greedy_search
```

Native loading and inference run only in the app-owned worker. The desktop app never
loads the recognizer. Ten-minute recordings are split into pieces of at most 60 seconds
using silence boundaries. That bounds native inference requests and avoids long-input
encoder limits.

For source builds, place the same pinned assets under the output directory's
`models/parakeet-v2`, use the release script, or select their directory in Settings.
The `%LOCALAPPDATA%\Freehand\models\parakeet-v2` cache may be reused at build time.
Packaged operation uses the installed assets independently of that folder.

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

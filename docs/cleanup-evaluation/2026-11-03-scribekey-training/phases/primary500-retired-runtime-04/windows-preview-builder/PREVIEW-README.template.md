# Isolated trained ScribeKey cleanup preview

This package selects **@@MODEL_LABEL@@**, exact quantization
`@@QUANTIZATION@@`. It is a trained derivative of ScribeKey Fast v1.1; retain
all supplied source-model, derivative and runtime licenses/notices. Candidate
training/conversion/evaluation provenance is recorded in `candidate-freeze.json`.
No Windows or GPU execution was performed while preparing this package. Numeric
whole-app limits remain **747,500,000 host bytes and 805 ms ready-release to
complete text** until measured on Windows. There is no claim that a dataset
percentage establishes universal accuracy.

This package contains a **new** application single-file build and six new Probe
assemblies for mandatory specialist output policy `trim-v1`. That policy removes
only model-exterior whitespace before exact literal restoration. Old App binaries
are not reused as if they implemented this normalization. `build-receipt.json`
records source fingerprints, actual publish commands and managed assembly hashes.
The root `preview-manifest.json` pins every packaged file except itself.

Extract into a writable Windows x64 folder. PowerShell 5.1 or newer and the native
Microsoft Visual C++ runtime are required. Vulkan also needs a working compatible
NVIDIA driver. The executables are self-contained; no .NET SDK is needed. Quit
other Freehand copies from their tray menus first. The launcher does not kill,
install, update, replace or reconfigure the normal app.

```powershell
./run-preview.ps1 -Model TrainedScribe -Profile Cpu
./run-preview.ps1 -Model TrainedScribe -Profile Vulkan
./run-preview.ps1 -Model TrainedScribe -Profile Cpu -Benchmark
./run-preview.ps1 -Model TrainedScribe -Profile Vulkan -Benchmark
```

Every invocation creates a new isolated `runs/<timestamp-guid>/` folder with its
own verified cleanup bundle, settings, profile and output evidence. Source bundles
and prior runs remain unchanged; supported files are hard-linked or copied, and
the mutable run manifest is a separate file. The exact model/quantization label,
provider policy, device, executable hashes and manifest identity are recorded.
The published speech CPU config disables intra-op spinning and matches its tested
source hash. The new App runtimeconfig disables TieredPGO while retaining tiered
compilation. Child environments explicitly set `DOTNET_TieredPGO=0` and remove
inherited tiered-compilation disable overrides; caller values are restored.
Standard ASR is used without the accelerated-model environment override. History,
login startup and update checks are disabled in this isolated profile.

Cpu uses the Vulkan-capable binary as a CPU execution control, with GPU layers
zero and `LLAMA_ARG_DEVICE=none`. Its exact selected prompt lookup is
@@CPU_LOOKUP@@ draft tokens with match length 3, as frozen in the root manifest.
Vulkan requests 999
layers and starts with lookup disabled; `-EnablePromptLookup` is a separately
labeled GPU experiment. Both use context 1024, complete-output cap 512, batches
64/32, disabled repacking, bounded caches and exact specialist literal protection.

Vulkan discovery requires exactly one NVIDIA `VulkanN` device. Missing, malformed
or ambiguous selection aborts instead of choosing Intel or silently accepting CPU
fallback. Scoped environment values are restored, and actual cleanup-process GPU
memory telemetry is required by the desktop benchmark. A device name, Vulkan DLL
or requested layer count alone is not proof of GPU execution. CPU quality results
do not establish GPU-backend quality.

Benchmark mode preserves separate results for explicit public raw-text quality
fixtures, dictionary fixtures and the actual desktop replay. The Core probe records
candidate output, accepted text and fallback separately; its zero exit code is a
structural result, not semantic certification or a raw-HTTP model quality score.
All commands continue even if a quality probe fails, so performance evidence is
still retained. Inspect the actual output text and all exit codes.

The desktop replay runs 50 short recordings plus separate startup, cold, idle,
recovery and longer-duration diagnostics into an owned foreground Windows text
control using real SendInput. Allow **well over ten minutes** and keep that window
available. Cold initialization and long recordings are reported separately from
the ready short-recording limit. Shared GPU memory counts toward host RAM;
dedicated VRAM remains separate. Physical microphone/hotkey checks are additional.

`run-summary.json` separates `AllCommandsSucceeded`, numeric
`SlaQualificationPassed` and `SemanticQualityUnverified`. The numeric field only
accepts the actual full desktop cleanup report for this run's manifest and the
requested 15% limits, with positive cleanup-process GPU evidence where required.
The benchmark wrapper exits 1 for failed commands, missing reports or failed
numeric qualification. A clean numeric result does not hide a quality-probe
failure. Interactive mode propagates the application's exit code. Quit an
interactive preview from its own tray menu when finished.

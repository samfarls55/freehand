# Isolated Freehand cleanup preview

This folder is preparation for a later Windows test. **No Windows executable,
GPU inference, microphone, physical hotkey or foreground insertion has been
tested by preparing it.** The 747,500,000-byte whole-app host-memory limit and
805 ms release-to-complete-text limit remain unverified on Windows. CPU quality
results do not establish quality or performance on the Vulkan backend.

The parent task publishes self-contained application and probe executables into
this layout; no .NET SDK is required on the test machine:

```text
run-preview.ps1
select-preview-device.ps1
preview-manifest.json                # pins the portable files, including both executables
App/Freehand.App.exe                 # includes the standard speech model
Probe/Freehand.Cleanup.Probe.exe
cleanup/emberon-vulkan/cleanup-manifest.json
cleanup/scribekey-q4-vulkan/cleanup-manifest.json
fixtures/fresh-holdout40.json
fixtures/integration10.json
```

Keep every file from each cleanup bundle, including runtime libraries, model,
licenses and contributor notices. Emberon selects Emberon-2 by PromethicLabs.
ScribeQ4 selects a locally derived quantization of ScribeKey Fast v1.1,
with its recorded source weights, conversion provenance and required notices;
it is not the publisher's Q8 artifact. Preserve any cards included as pinned
bundle notices; the separate large research cache is outside this portable folder. Acquisition metadata
for the historical 9B prototype is omitted from this preview.

Extract the folder to a writable local directory on Windows x64. PowerShell 5.1
or newer is supported. A current Vulkan-capable NVIDIA driver and the native
Microsoft Visual C++ runtime are needed for the relevant runtime. Quit other
Freehand copies from their tray menu before running the preview; the launcher
does not stop them, replace the installed app, update its settings, or enable
login startup.

```powershell
# Open a fresh profile for manual microphone/hotkey checks.
./run-preview.ps1 -Model Emberon -Profile Cpu
./run-preview.ps1 -Model ScribeQ4 -Profile Vulkan

# Run public text-quality fixtures followed by the whole desktop benchmark.
./run-preview.ps1 -Model Emberon -Profile Cpu -Benchmark
./run-preview.ps1 -Model ScribeQ4 -Profile Vulkan -Benchmark

# A separately labeled experiment; CPU lookup gains do not prove a GPU benefit.
./run-preview.ps1 -Model Emberon -Profile Vulkan -EnablePromptLookup -Benchmark
```

Each invocation creates `runs/<timestamp-model-profile-guid>/` containing its
own cleanup bundle, profile, settings, evidence and `run-summary.json`. Every
inventory file is size/hash verified before cloning, then verified in the run
copy. Assets are hard-linked when supported or copied otherwise. The customized
manifest is a separate file, so source manifests remain unchanged. Existing run
folders and normal installation/profile files are preserved. JSON written by the
launcher uses UTF-8 without a byte-order mark.
The App and Probe executable sizes and hashes must match the root preview
manifest before either can start. A missing manifest or mismatched executable
aborts the launcher.

Both profiles use the same verified Vulkan-capable runtime. **Cpu means Vulkan
runtime with CPU execution**, rather than a separate CPU binary. Its layer count
is zero and its process-scoped `LLAMA_ARG_DEVICE` is `none`. It enables the
development-tested prompt-lookup 16/3 condition. Vulkan requests 999 layers and
starts with prompt lookup disabled; `-EnablePromptLookup` explicitly requests
16/3 for that separate GPU experiment. Both use the same 1024-token context,
512-token complete-output reservation, 64/32 batch sizes, disabled repacking,
bounded caches and specialist literal protection. The standard ASR model is
used; inherited `FREEHAND_MODEL_PROFILE` is removed from child environments.

For Vulkan, the device helper verifies the runtime inventory, clears inherited
GPU-selection overrides in its discovery process and captures `--list-devices`.
It requires exactly one NVIDIA device with an exact `VulkanN` label. Missing,
ambiguous or malformed NVIDIA device listings abort the run. Its exact label is
passed through `LLAMA_ARG_DEVICE`; an unavailable name is rejected by the pinned
runtime. There is no automatic Intel or CPU substitution. All environment changes
are scoped to child processes; the launcher's saved process environment is
restored in `finally`. `VulkanN` must not be treated as a
`GGML_VK_VISIBLE_DEVICES` physical-device ordinal.

Device discovery, a Vulkan DLL and a request for 999 layers do not prove GPU
execution. The Vulkan desktop command requires positive per-process GPU memory
telemetry through `--require-gpu-telemetry`. Review the selected device, cleanup
worker identity, actual offload/buffer evidence and GPU counters in the produced
artifacts. A CPU fallback or missing telemetry does not qualify as a GPU result.

Benchmark mode records separate exit codes and output hashes for the fresh
40-case Core quality probe, the 10-case dictionary probe, and the actual desktop
benchmark. A nonzero quality-probe exit does not suppress the performance run.
Core acceptance and a zero probe exit code are structural checks: review text
meaning, cleanup completeness, adapter restoration and fallback separately.
The known `integration-09` superseded-protected-name case can retain an obsolete
phrase; neither the launcher nor a successful structural probe hides or resolves
that coverage limitation.

The desktop benchmark replays public audio into its owned foreground Windows
text control using real SendInput. It runs 50 warm short recordings plus separate
cold/startup, idle/restart and longer-duration observations, and can take **well
over ten minutes**. Keep its test window available and avoid typing into it.
Cold startup is reported separately from warm release latency; long-dictation
results must be read separately too. Dedicated VRAM is separate from host memory;
shared GPU allocations count toward the host budget. A benchmark result does not
replace a physical microphone/hotkey check or certify semantic correctness.

When an interactive preview is finished, quit that preview from its tray menu.
Read each JSON artifact and command's exit code under the fresh run directory;
the launcher deliberately provides no combined "quality and SLA passed" label.

`run-summary.json` keeps `AllCommandsSucceeded` separate from the numeric
`SlaQualificationPassed` field. Numeric qualification requires a real full
desktop report, the requested cleanup/tolerance flags, this run's cleanup
manifest hash, and a passing application qualification. Vulkan additionally
requires the requested GPU telemetry and positive GPU memory for an identified
cleanup process. `SemanticQualityUnverified` remains true: zero probe exit codes
cannot establish meaning preservation.

In benchmark mode, the launcher exits 1 if any command fails, a requested report
is missing, or full numeric qualification does not pass. All three commands still
run so failures do not suppress later evidence. The known `integration-09`
failure can therefore make the wrapper fail even when the numeric desktop SLA
passes; that distinction is intentional. Interactive mode propagates the
preview application's exit code.

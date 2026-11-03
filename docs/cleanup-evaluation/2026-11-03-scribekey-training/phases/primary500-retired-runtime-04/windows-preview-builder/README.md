# Trained ScribeKey Windows preview preparation

This builder is **planning and staging tooling**, not a selected model or a
published preview. The trained candidate and quantization have not been chosen.
Existing preview folders and archives remain unchanged. No Windows execution,
GPU inference or whole-app SLA qualification has occurred here.

The new provider requires `trim-v1`: specialist native output is trimmed before
exact literal restoration. The earlier Windows App executable does not contain
that policy. A new App single-file publish and new six Probe assemblies are
required. Re-labeling old binaries is rejected.

Only `plan` is intended while training or timed model runs own the CPU:

```sh
python3 work/trained-scribe-preview-builder/make_preview.py plan \
  --output work/trained-scribe-preview-builder/preparation-plan.json
```

The later explicit commands do significant build, hashing or compression work.
Wait for the parent to allocate a CPU window and freeze the candidate first:

```sh
python3 work/trained-scribe-preview-builder/make_preview.py publish \
  --scratch /tmp/freehand-trained-publish-UNUSED

python3 work/trained-scribe-preview-builder/make_preview.py stage \
  --receipt /tmp/freehand-trained-publish-UNUSED/build-receipt.json \
  --candidate-freeze /absolute/path/final-candidate-freeze.json \
  --destination /tmp/freehand-trained-preview-UNUSED

python3 work/trained-scribe-preview-builder/make_preview.py archive \
  --preview /tmp/freehand-trained-preview-UNUSED \
  --output /tmp/freehand-trained-preview-UNUSED.zip
```

The plan records the actual provider/probe and other application source bytes,
dependency pins and source commit. Unrelated training documentation does not
stand in for the application fingerprint. Publish checks the fingerprint before
and after the commands and records all output hashes plus these six assemblies:
Probe, Cleanup, Core, Dictionary, Abstractions and Testing. The reflected Windows
platform DLL comes from a new explicit cross-publish. This proves cross-publish
provenance, not that a Windows executable was run.

The selected resource policy also requires the exact tested speech config SHA
`0d2e1a0192d981a06ec6a6839810bc9f58cbfc7fdeea0c9ae1a708949562f7c9`
(intra-op spinning disabled), `System.Runtime.TieredPGO=false` in the generated
App runtimeconfig, and tiered compilation enabled. Publish verifies those actual
generated/copied files and includes their hashes in the receipt. The single-file
runtimeconfig's build evidence is copied separately for inspection. The launcher
sets child-only `DOTNET_TieredPGO=0`, removes inherited tiered-compilation disable
overrides, and restores the caller's environment in `finally`.

New intermediate/publish output uses `/tmp` through `--artifacts-path`; the
workspace has limited free space. Stage reuses an old file only when its bytes
equal a new publish pin or it is an explicitly pinned unchanged standard speech
asset/public audio fixture. Hard links are preferred; cross-filesystem copies
are verified. No source file, old preview, normal installation or normal profile
is overwritten. ZIP output and all destinations must be new paths. Keep the
selected model and new build receipt/executables persistently after deciding
which final artifacts to retain; do not treat temporary storage as a backup.

`candidate-freeze.example.json` describes the required later input. It must name
a new, fully prepared `win-x64-vulkan` bundle containing the selected trained
GGUF, all runtime files, licenses and accurate new derivative attribution. The
quantization is exact: `Q3_K_S`, `Q3_K_M`, `Q4_K_M` or `IQ4_XS`. The builder checks model and
prepared-manifest pins; it does not select a quantization or manufacture a 99%
quality claim. Link actual consumed evaluation/conversion provenance in that
freeze after the parent selects it.

Exactly two explicitly public, already consumed text fixture pins are supplied
by the parent. The builder never discovers evaluation datasets, reads author
files, or automatically includes a hidden final corpus. These files are copied
only in the later stage operation. The example has placeholders, so it cannot
stage a model accidentally.

The portable launcher is the reviewed PowerShell 5.1 isolated launcher with one
generic label, `TrainedScribe`. It reads the exact Q3/Q4 quantization and model
identity from the pinned root manifest. CPU lookup is the exact
`cpu_prompt_lookup_tokens` integer frozen after the parent's comparison, from
0 through 63 with match length 3. The example's 16 is illustrative, not a
selected winner. CPU and NVIDIA Vulkan remain separate experiments: same
Vulkan-capable runtime, GPU layers 0/999, and lookup disabled by default on
Vulkan. Settings, histories and copied manifests are
fresh per invocation. The device helper rejects missing or ambiguous NVIDIA
selection; required per-process GPU telemetry prevents a CPU fallback from
qualifying as a GPU measurement.

Benchmark mode runs two explicit public text probes and the real whole-desktop
benchmark, preserving every exit code and output. Numeric qualification requires
the actual application report, this run's manifest identity, full cleanup mode,
747,500,000-byte host-memory and 805 ms ready-release limits, and GPU evidence
when requested. It does not establish semantic correctness. Cold startup and
longer recordings remain separate diagnostics. The 50-replay desktop run can
take well over ten minutes and still needs a Windows foreground test window.
Physical microphone/hotkey testing, GPU-backend quality and all Windows results
remain unperformed. There is no installation, update, release, push or PR step.

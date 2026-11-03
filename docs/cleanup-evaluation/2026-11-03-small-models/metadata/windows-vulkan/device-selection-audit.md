# b12015 Windows Vulkan device selection audit

This is a static source audit of llama.cpp commit
`a34de8618b25dfc32ee43749db47d767a9f0a25d`. The official Windows Vulkan ZIP was
independently verified, but no Windows executable, Vulkan driver or GPU was run
in this Linux environment. Source URLs, exact retrieved byte counts and hashes
are in `source-audit/source-index.json`; the upstream MIT license is retained
there as `llama-LICENSE.txt`.

The preferred preview guard is **`LLAMA_ARG_DEVICE=VulkanN`**, where `VulkanN` is
the exact backend name discovered for the unique NVIDIA adapter. No additional
production setting is needed. `GpuLayers=999` alone is an offload request.

## Exact name selection and precedence

`common/arg.cpp:2689–2695` binds `--device` to `LLAMA_ARG_DEVICE`.
`parse_device_list` at lines 1106–1125 resolves each name with
`ggml_backend_dev_by_name`; a missing device or CPU device throws `invalid device`.
The special value `none` creates an explicit empty device list for CPU operation.
Environment handlers run first at lines 771–794; CLI parsing follows at line 797.
A CLI `--device` overrides that environment setting. Freehand currently supplies
no `--device` argument, and its Windows worker launcher inherits the app process
environment while adding the worker API key. Check the final source freeze
before relying on that propagation.

`--list-devices` prints the exact backend name and device description at
`common/arg.cpp:1134–1150`, then exits via lines 2697–2702 without loading a model.
Vulkan backend names are formed as `Vulkan` plus the logical index at
`ggml-vulkan.cpp:16322`; their descriptions resolve through the backend's internal
physical-device mapping at lines 15360–15363.

## Preview launch protocol

1. Verify the complete prepared runtime/model inventory before executing the
   launcher. The server EXE is shared with the CPU bundle; its hash alone cannot
   establish that the Vulkan DLL is present.
2. Create an isolated discovery child environment with `LLAMA_ARG_DEVICE` and
   `GGML_VK_VISIBLE_DEVICES` absent. Run only the verified server's literal
   `--list-devices` argument, with a bounded timeout and captured stdout/stderr.
   Do not change user or machine environment settings.
3. Parse only complete returned device lines and accept a name matching exactly
   `Vulkan[0-9]+` whose description contains `NVIDIA`. Require exactly one match.
   Abort clearly on zero/multiple matches, malformed output or a nonzero exit.
   Do not fall back silently to Intel Arc, a CPU backend or an arbitrary ordinal.
4. Before starting Freehand, set that app process's `LLAMA_ARG_DEVICE` to the
   exact returned name and keep `GGML_VK_VISIBLE_DEVICES` absent. Preserve this
   environment for the app and its descendants. Use only the validated device
   name as the environment value; do not accept extra native flags from input.
   Stale main-GPU/tensor-split/override-tensor environment settings should be
   cleared in that isolated preview environment, or rejected explicitly and
   recorded, so they cannot change the intended one-device profile.
5. Record the selected name, description, listing output, runtime/model/profile
   hashes and scoped environment changes in `run-selection.json`. CPU preview
   should use `LLAMA_ARG_DEVICE=none`, a CPU runtime/profile and zero GPU layers.
6. Selection is not execution proof. Require positive actual native-worker GPU
   memory/compute telemetry and a controlled offload diagnostic before treating
   a GPU run as valid. Keep dedicated VRAM separate; shared GPU host allocations
   still count toward the host-memory budget. A full Windows app measurement
   must also include UI, ASR, cleanup, final text readiness and physical delivery.

The list format is defined by the pinned native `printf`:

```text
  <backend-name>: <description> (<total> MiB, <free> MiB free)
```

An anchored parser can extract the backend name and description from this form;
only the `Vulkan[0-9]+` token should be used as the device-selection value.

## Why not translate the label into GGML_VK_VISIBLE_DEVICES

The backend's `GGML_VK_VISIBLE_DEVICES` parser at `ggml-vulkan.cpp:5303–5321`
accepts **physical enumeration ordinals** before its filtering/mapping logic.
The `VulkanN` name uses the later logical index. Duplicate-driver filtering and
fallback device selection can change the mapping. Therefore a returned
`Vulkan1` does not prove that physical ordinal `1` is the same adapter. Clearing
that process-local filter and selecting the exact backend name avoids this
translation. The filter is not used by the proposed preview.

## Offload diagnostics and remaining limits

`common/common.cpp:1714–1716` forwards explicitly selected devices to model
parameters. Actual layer assignment checks available devices at
`src/llama-model.cpp:1691–1700`; CPU input tensors and per-operation fallback can
remain. Native diagnostics include `offloaded X/Y layers to GPU` at line 2035
and per-buffer model allocation sizes at lines 2039–2043. Correlate the named
Vulkan backend, nonzero relevant GPU buffers/offload and per-PID Windows GPU
telemetry; an offload request, a listing, or a generic success message alone is
insufficient. Freehand's normal worker uses `--log-disable`, so a separate
controlled diagnostic run must retain its own hashes and configuration and
cannot substitute for full-app telemetry.

These files prepare an unqualified local preview. They do not establish driver
availability, dedicated-device execution, target-machine speed/memory or a
Windows SLA pass. No runtime version, normal installation or model hosting was
changed by this audit.

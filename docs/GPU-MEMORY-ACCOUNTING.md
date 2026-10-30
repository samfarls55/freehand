# Windows GPU memory measurement

The desktop delivery benchmark measures physical host RAM conservatively as the simultaneous sum of desktop and worker working sets plus their shared GPU memory. Dedicated VRAM is reported separately. Private commit remains a diagnostic and is not used as a physical RAM measurement.

Microsoft defines working set as currently resident pageable process pages. PrivateUsage and PeakPagefileUsage measure commit charge, which includes a backing obligation rather than just resident DRAM. WDDM maintains backing stores for GPU allocations when they are not resident in video memory. These are different quantities. [Working set](https://learn.microsoft.com/en-us/windows/win32/memory/working-set), [process memory counters](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex), [WDDM backing stores](https://learn.microsoft.com/en-us/windows-hardware/drivers/display/sharing-backing-store-with-kmd).

On a discrete GPU, dedicated memory is VRAM; shared GPU memory uses system DRAM. Per-process GPU counters can also include allocations shared between processes. Adding process working sets and shared GPU bytes can therefore count some physical pages twice. The benchmark deliberately keeps that conservative estimate and does not subtract presumed overlaps. [Microsoft GPU accounting](https://devblogs.microsoft.com/directx/gpus-in-the-task-manager/).

Host-visible video memory is also distinct from host system memory. NVIDIA documents that a DEVICE_LOCAL plus HOST_VISIBLE heap permits CPU access directly to video memory. Mapping by itself does not establish that an allocation occupies system DRAM. [NVIDIA Vulkan memory guidance](https://developer.nvidia.com/blog/vulkan-dos-donts/).

## Independent allocation control

The [pinned control summary](performance/gpu-memory-control.json) records the native library, probe and raw-output hashes. It used the official transcribe.cpp v0.4.1 Vulkan bundle on the NVIDIA RTX 4060 Laptop GPU, without loading a model. Each allocation was filled and synchronized, then sampled seven times at 200 ms intervals before being freed. GPU allocation gauges came from Windows PDH; host gauges came from PSAPI and GlobalMemoryStatusEx.

| Allocation | Dedicated VRAM change | Private commit change | Process working-set change |
| --- | ---: | ---: | ---: |
| 256 MiB device-local | +256 MiB | +257.4 MiB | +1.2 MiB |
| 512 MiB device-local | +512 MiB | +513.2 MiB | +0.8 MiB |
| 256 MiB pinned host | +0.5 MiB | +256.7 MiB | +256.2 MiB |

Each change uses the immediately preceding initialized or freed stage. Device-local allocation raised GPU residency and commit without a comparable host-residency rise. System physical use stayed within unrelated background variation rather than increasing by 256 or 512 MiB. The pinned-host positive control raised shared GPU memory by 256 MiB and process working set by 256.2 MiB, demonstrating overlap between those counters on this machine. Its system-wide physical-use median increased about 223 MiB; that quantity also includes other processes and is supporting evidence rather than an exact per-process attribution.

The control does not prove that every shared GPU allocation appears in the process working set. Adding all shared GPU bytes remains the conservative choice. Nor does it remove the operational cost of commit charge or the possibility of later VRAM paging. Both commit and VRAM are retained in reports.

## Benchmark contract

Use `--require-gpu-telemetry` with the existing `--desktop-delivery-benchmark OUTPUT` command when evaluating a GPU worker.

* The 650,000,000-byte gate applies to the highest simultaneous working-set-plus-shared-GPU sample. Independent desktop and worker maxima are never added to manufacture a combined peak.
* Reports preserve simultaneous working-set and private-commit peaks, per-process GPU dedicated/shared/commit gauges, the sample at the physical estimate peak, telemetry errors and worker GPU observations.
* Missing or invalid GPU telemetry fails GPU acceptance. A valid zero-activity sample is distinguished from an unavailable query. A run that never observes a worker GPU counter instance also fails GPU acceptance.
* Missing GPU samples make the conservative physical estimate null and fail the RAM measurement. A CPU-only worker can pass with valid zero GPU activity; the GPU acceptance flag additionally requires a positive worker GPU observation.
* Warm and cold delivery latency gates are unchanged. Sampling is periodic and can miss short-lived peaks; OS and sampled counters are diagnostic measurements with that limitation.

All Windows counter access stays in Freehand.Platform.Windows. No speech runtime, model selection or normal dictation behavior is changed by this instrumentation.

# Lookup24 development parameter comparison

Only cleanup prompt-lookup draft tokens changed from16 to24. Match length3,
batch64, micro-batch32, model weights, all compiled files, output handling,
production ASR settings and warmup procedure remained unchanged. The manifest is
a newly created private file; the default manifest was not modified. RTE confirmed
source/profile stability before this run. No model or C# rebuild occurred.

| Metric | Default16, prior N10 | Lookup24, N10 |
|---|---:|---:|
| Transcript-ready p50 |684.9547ms|754.9813ms|
| Transcript-ready p95/max |816.9002ms|845.2322ms|
| Counting-complete p50 |684.9664ms|754.9947ms|
| Counting-complete p95/max |817.1219ms|845.2460ms|
| Counting-complete trials above805ms |1/10|3/10|
| Highest observed simultaneous RSS |702,046,208bytes|764,616,704bytes|

The805ms gate uses **counting-complete**, without rounding. All ten trials,
including the first, remain in the result. Nearest-rank p95 equals maximum atN10;
these repeated public-audio trials do not establish a stable tail distribution.
Lookup24 misses both805ms and747,500,000bytes even before UI memory is included.
The memory difference should not be attributed entirely to lookup state: ASR's
observed peak also differed substantially between these separate process cohorts.

All ten preserved the complete22-word JFK text, returned Unchanged, completed
once and delivered once, with no fallback. This already-clean audio provides
resource/copying evidence, not useful-cleanup or independent500-case quality proof.
The frozen worker/model/manifest identities and original production ASR config
passed post-run verification. No forced GC, trial exclusion, altered warmup or
session-option changes were used.

`complete-delivery-analysis.json` records exact timing fields, cap decisions,
per-trial counting-complete values and post-run checks. Raw JSON/logs preserve
CPU/GC/allocation ramps and simultaneous component attribution. `plan.json`
records the assembly/source/model/profile identities and the single changed knob.

This remains a **DEVELOPMENT_PARAMETER_COMPARISON** on a Linux partial pipeline.
There is no independent500-case, full-app, Windows/GPU, physical capture/hotkey or
SendInput certification. Initial loading and the recorded Eval-only one-hour
idle override remain separate from production behavior. No further run or
production change follows automatically.

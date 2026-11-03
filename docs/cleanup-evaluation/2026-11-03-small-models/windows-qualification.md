# Windows cleanup performance qualification

The desktop benchmark now supports `--include-cleanup`. It replays public audio
through the actual desktop speech worker, configured cleanup processor, Core
validation and real `SendInput` into its owned Windows EDIT control. It does not
use a microphone or a physical push-to-talk key. Cloud tests of this harness do
not establish a Windows hardware result.

Use a development preview with the pinned speech assets, public `fixtures/jfk.wav`
and a verified **Windows** cleanup bundle. Set `FREEHAND_DATA_DIRECTORY` on the
preview process to a fresh, isolated profile. Its `settings.json` must select the
speech `ModelDirectory` and cleanup `CleanupDirectory`, with `CleanupEnabled`
and `InjectText` true. Disable login startup and update checks in that profile.
The cleanup directory must contain `cleanup-manifest.json` and its complete
verified local assets. The benchmark refuses disabled or unavailable cleanup;
it never downloads a model.

Run the preview with these literal arguments:

```text
Freehand.exe --desktop-delivery-benchmark C:\benchmarks\cleanup-result.json --include-cleanup
```

Keep the benchmark's owned text field in the foreground and leave the machine
idle. The full run includes 50 real-time 10-second recordings, separate warmup,
forced-fresh or prepared-worker observations, repeated-audio 30/60-second
observations, cleanup idle/unload and worker restart checks, plus the existing
speech recovery/retained-audio/unload controls. It can take more than ten minutes.
The cleanup idle observation waits at most two minutes; a longer configured
idle timeout cannot establish unload in this run.

The report records the exact cleanup manifest hash, model/runtime pins,
full actual runtime options, configuration epoch and fingerprint, application
process hash and managed module identity, per-trial cleanup invocation count,
outcome, processing time and
public fixture candidate/selected text. The cached options must match the exact
manifest bytes before measurement. Every provider call and trial checks the
monotonic configuration epoch; bounded manifest hashes are checked outside the
release-to-delivery interval. Selection changes, including A-to-B-to-A reloads,
fail qualification. The benchmark never rehashes model weights per trial.
`desktop`, `speech` and `cleanup`
process roles are sampled together every 10 ms, including cleanup initialization,
retention, restart and reset teardown. Dedicated VRAM and private commit remain
separate; shared GPU allocation counts toward host RAM. Earlier desktop startup
allocations can precede benchmark entry and are explicitly identified in the
report.

Without the flag, the original 650,000,000-byte and 700-ms gates remain. With the
flag, the requested limits are 747,500,000 bytes and 805 ms. Every observed warm
short receipt must remain within 805 ms; cold, long and first-after-idle timings
are retained separately. Warm/prepared/fresh/long p50, p95 and maximum are included.
No fallback, disabled cleanup or missing provider invocation counts as accepted
cleanup. Full qualification also requires complete GPU memory telemetry, no
orphan cleanup process and completed idle/recovery/long diagnostics.

Check `Failures`, `FullCleanupQualificationRequested` and
`CleanupQualificationPassed`, rather than treating a diagnostic or a single
latency number as full acceptance. `--cold-only` and `--ready-only` retain their
separate diagnostic meanings and cannot stand in for the full run. Structural
Core acceptance does not prove semantic fidelity; the model's manually reviewed
quality evaluation remains a separate gate. This short-fixture hardware gate
does not establish an all-length 805-ms deadline.

# CI coverage scope

The 80% new-code coverage gate measures shipping application behavior. Sam approved
this scope for PR #10. All source remains subject to static analysis and existing
build, packaging, regression, and upgrade checks.

Coverage exclusions in `.github/workflows/build.yml` are limited to:

- `tools/**`: evaluation tools, pinned upstream normalization code, and native build
  preparation. The scorer has 44 contract checks; frozen replay results are recorded
  separately in `ACCURACY-HILLCLIMB.md`.
- The three accuracy development and fixture scripts: these prepare optional model
  assets and replay inputs. They are outside the installed application. Fresh-cache
  fixture download and checksum validation were checked locally.
- `GgmlTranscriber.cs` and `SpeechPresenceDetector.cs`: optional GPU-preview native
  integration. Hosted Windows CI lacks the discrete Vulkan hardware used for the
  recorded model, speech-presence, accuracy, and memory verification.
- `DesktopDeliveryBenchmark.cs`, `EngineeringChecks.cs`, and
  `WindowsGpuMemoryReader.cs` and `WindowsDeliveryProbe.cs`: diagnostic measurement and self-test infrastructure.
  The checks still run; their instrumentation is not application coverage.

Worker orchestration, readiness coordination, UI, shared dictation, keyboard hooks,
text delivery, and formatting remain in scope. CI additionally collects the real
desktop executable's lifecycle self-test under the .NET coverage profiler.

## Reviewed static-analysis findings

The two Python command-line tools intentionally read and write paths supplied by
their local operator. They do not accept paths from a server or cross a permission
boundary. S8707 is excluded only for those two files; imposing a fixed directory
would break their documented CLI contracts.

The scorer's S1244 finding is an exact boundary assertion: one deletion in twenty
words must produce the same literal 0.05 used as the strict rejection threshold.
Approximate comparison would weaken that test. Its rule exception is file-specific
so the frozen scorer source and hash remain unchanged.

The four S6640 suppressions cover synchronous native calls using pinned owned audio
and fixed vocabulary buffers with bounded lengths. Buffer lifetime extends through
the call. Required P/Invoke pointer declarations use the same reviewed ABI.
The fixture Git blob identifier uses SHA-1 for upstream identity compatibility,
explicitly with `usedforsecurity=False`; archive integrity uses pinned SHA-256.

Missing cancellation arguments now explicitly opt out where draining or cleanup
must complete. The preparation loop still observes its own cancellation source.
The VAD constructor disposes its model on session-creation failure and transfers
the completed session directly into its readonly owner.

Generated regex state-machine functions are excluded from profiler instrumentation
through `.config/coverage.xml`. Application formatting logic and its tests remain
covered. Two hosted runs exhausted the production 100 ms regex budget under the
profiler and correctly returned unformatted text. This exclusion avoids measuring
generated framework implementation while retaining the production timeout.

The desktop lifecycle replay also applies a missing model directory and a changed
idle timeout, waits for the actual preferences queue, then restores the original
settings in a finally block. Both public CPU and missing-asset GPU profiles run in
CI. This covers preference application and unavailable-model UI without pretending
to verify native GPU inference.

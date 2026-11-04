# Planned selected-candidate N10 resource trial

This began as a file-only plan for the eventual parent-selected V8/interpolation
candidate. The separately authorized fresh standalone build is now complete:
zero warnings/errors,59 source snapshots verified, and eight existing default DLL
pins preserved. See `build-final-verification.json`. The new output root is
logically immutable and the build CPU window has been explicitly released.
No candidate is selected/frozen and no model execution has occurred here.
V8's last parent-reported text-quality result was below495/500;
the fixed interpolation comparisons retain priority. This plan does not consume
or inspect a quality corpus and does not publish a Windows bundle.

## Exact condition

The original IQ4_XS base is211,804,448B with SHA256
`82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174`.
The actual candidate must supply a separately pinned rank8 F32 GGUF LoRA
(184 tensors,12,006,240B), native multiplier1, exact export/training-lineage
receipts and an explicit typed profile matching `plan.json`:

- F16/F16 KV, lookup16/match3, context1024, output512, threads4.
- Batch64/microbatch32, GPU0, repackfalse, literal maskingtrue, cache0/checkpoints0.
- Standard Parakeet110m-int8 ASR, four threads,198B NoSpin config
  SHA256`0d2e1a0192d981a06ec6a6839810bc9f58cbfc7fdeea0c9ae1a708949562f7c9`.
- `DOTNET_TieredPGO=0`, tiered compilation default enabled; current App source
  retains `TieredPGO=false`. All `LLAMA_ARG_*` overrides are removed before
  setting `LLAMA_ARG_DEVICE=none`; accelerated ASR/model-profile and GPU override
  variables are removed. The selected public host/direct-child environment
  entries are retained without dumping unrelated arguments or credentials.

Actual model/base paths come from the future performance input; the same pins
must describe the candidate that was compared. Model paths are not inferred from
an old winner. Text quality is a separate parent-reported fact, and a resource
pass does not become a99% quality or Windows qualification.

## Fresh standalone build

`tools/Freehand.Evaluation/Freehand.Evaluation.csproj` is outside the solution.
The new immutable output root recorded in `plan.json` has now been built once.
The recorded command used Release, no incremental reuse, warnings as errors,
Windows targeting enabled, and the new `--artifacts-path`. Never substitute the
old V6 evaluator or the quality Probe's DLLs. The current body baseline is
`8b059f2`; preparation HEAD`bc89afd` changes documentation only. Exact source
files, dependencies, speech config and App PGO property are hash-pinned; source
bytes must match before/after build, freeze and run, regardless of later doc-only
commits. Actual worker/dependency DLL/runtimeconfig hashes and source snapshots
are retained in a fresh build receipt.

The portable Linux worker runs this newly compiled Evaluation assembly through
the same Speech/Core/Cleanup implementations. The positional APP argument is a
historical pinned reference identity only, not an executed App. Its old source
epoch cannot be represented as this run's worker. The report must identify the
fresh `SpeechWorkerAssembly` and its actual SHA256.

## Deliberately deferred commands

The build command below is retained as the executed recipe; **do not run it again**
into the immutable root. Candidate freeze/run remain deferred until comparisons
end, the parent selects the resource candidate and grants a new resource window:

```sh
python3 work/cleanup-scribekey-training-2026-11-03/performance/v8-selected-native-LoRA-no-pgo/controller.py build --cpu-release-confirmed

# Parent creates a NEW actual-candidate input from performance-input.example.json.
python3 work/cleanup-scribekey-training-2026-11-03/performance/v8-selected-native-LoRA-no-pgo/controller.py freeze \
  --performance-input /PARENT/FROZEN/selected-resource-input.json --cpu-release-confirmed

python3 work/cleanup-scribekey-training-2026-11-03/performance/v8-selected-native-LoRA-no-pgo/controller.py run \
  --cpu-release-confirmed --semantic-priority-cleared
```

Build/freeze/run reject absent explicit release flags. Freeze independently
verifies all declared actual candidate/base/runtime/ASR/audio/worker/source pins,
then creates a candidate-specific cleanup manifest and command freeze. Full model,
native library and audio hashing is deferred to that window. All existing build,
run, report, log and analysis paths are create-only; no automated repeats or
selection of a better cohort occurs.

The integrated preflight correction reads process names/states only. Live
`llama-server`, `llama-bench` and `llama-cli` block in every state exceptZ/X;
deadZ/X entries are recorded and excluded. There is no old-PID whitelist, so PID
reuse cannot hide a live worker. Parent CPU ownership is still required for
training, builds, quantization and other competing workloads; this small native
guard is not a complete machine-idleness detector. No process scan ran during
file-only preparation.

## Measurement and acceptance

Run the existing public10s JFK-derived clip in real time, gain1, exactly10 repeats
with `--include-text --portable-worker`. Retain repeats0..9, including the first.
Initial ASR load and one synthetic cleanup warmup are reported separately;
do not skip warmup, discard an actual trial, add an undocumented warmup, force GC
or retry until a favorable result appears. The existing evaluation-only one-hour
cleanup idle override remains explicit and does not validate production idle
behavior. All100s of recorded audio must be retained.

Every trial must deliver the full transcript once, with Applied/Unchanged
cleanup, no provider failure, fallback, split delivery or truncation. Preserve
raw text, normalized original, provider input/output and final text. The
dictionary-free clip must preserve normalized input words and accepted provider
output; changed words require review and do not count as resource success.

The gate is `CountingInjectorCompleteMilliseconds`, including cleanup and the
counting injector after release. Nearest-rank p95 ofN10 is the maximum:
**all10 must be at most805ms**. Transcript-ready and cleanup-only values are
diagnostics, not substitutes.

Host memory is the maximum coherent simultaneous
evaluator+ASR+cleanup working-set snapshot across the global monitor and every
trial, **at most747,500,000B**. Its three role contributions must sum exactly to
the reported peak. Component maxima remain separate and are never added. The
unchanged100Hz cached`/proc/PID/statm` sampler retains worker-generation identity;
global sampling includes loading/warmup, and trial/global snapshots are merged
after monitors stop. Linux private commit is omitted and shared resident pages
may be counted twice; there is no manufactured sum of unrelated maxima.

Post-run checks bind the actual report/worker, cleanup manifest, environment,
candidate, build/source, runtime and audio artifacts to the frozen condition.
Retain failures/timeouts, logs and source hashes even if either numeric cap fails.
The planned scope is Linux partial pipeline RSS and counting-injector complete
latency. It excludes desktop UI, physical microphone/hotkey/SendInput, visible
delivery, Windows/GPU and population tail-latency claims. No whole-app SLA pass
can be inferred from this research harness.

## Preparation verification

`reference-evidence.json` pins only the small V6 harness/receipt/report metadata
read during preparation. V6's earlier result is historical context, not this
candidate's result. Initial source-only syntax and dead/live-state predicate
assertions passed. The later build-only grant produced a fresh176,128B Evaluation
DLL with SHA256`99da06af6d69adea44e024b037e02154f148a2b2cf8a6a7bafa8ea15b0f4c385`.
Its41 output files and59 source snapshots were independently hash-verified.
The198B speech config matches the NoSpin pin. Evaluation's generated PGO property
is absent, matching V6; App source explicitly sets false, and the actual future
Evaluation run must apply the planned `DOTNET_TieredPGO=0` environment.
No model/audio hashing, native inference, N10 or preview publish occurred.
`readiness.json` records remaining gates and source identities. A future completed
run still requires independent report review.

# Deferred V6 unit native LoRA N10 performance controller

Prepared only. No fresh build, base/adapter/runtime rehash, model loading, replay,
or benchmark execution has occurred in this directory. V6 training owns the CPU.
The new adapter is pending actual completion/export. RTE native export and its
500-case inference take priority. The parent must explicitly release a CPU slot
before either expensive phase below is invoked.

The condition is the original pinned IQ4_XS model (`82ab22ce…`, 211,804,448 bytes)
plus the actual V6 **unmerged F32 native LoRA**, external multiplier **1**. It is
not a prior V4/V5 model, merged derivative, or model-only comparison. No prior
`experiment` or comparator object is inherited. `plan.json` reuses only existing
public JFK/ASR/native artifact pins as metadata until a later complete rehash.

The fresh strict solution build did **not** produce the requested Evaluation
assembly at `/tmp/freehand-native-lora-parser-guard-build/bin/Freehand.Evaluation/release/`.
The controller therefore requires a fresh standalone Evaluation build. It never
labels an older evaluator as supporting current native-adapter options.

After the parent grants the build slot, in an inference-free gap:

```bash
python3 controller.py build --cpu-release-confirmed
```

This runs the exact bounded command recorded in `plan.json`: the Evaluation
project, Release, `--no-incremental -warnaserror`, Windows targeting enabled, and a
new `/tmp/freehand-v6-native-lora-evaluation-build` artifacts root. It checks disk
space first, snapshots and verifies the actual current C# inputs before and after,
and pins all fresh output DLLs/configs. Existing build roots and default DLLs are
not written. Generated runtimeconfig must permit PGO0 and retain tiered compilation;
the actual 198-byte `speech-cpu.config` must match SHA `0d2e1a0192…`.

RTE will provide a small explicit `performance-input.json` after real conversion
verification. Required fields are `base`, `adapter`, `export_receipt` and
`training_receipt` (each with `path`, `bytes`, `sha256`), `external_scale: 1`,
`tensor_precision: "F32"`, and `tensor_count: 184`. No corpus, native500 results,
or semantic-review files are consumed by this controller. When CPU hashing is
released, freeze that exact input:

```bash
python3 controller.py freeze --cpu-release-confirmed --performance-input /absolute/path/performance-input.json
```

Freeze verifies the complete source/build/runtime/speech/audio/base/adapter/export
receipt inventories. It writes a separate cleanup manifest: CPU four threads,
lookup16/match3, context1024, output cap512, batch64/microbatch32, F16 K/V,
no repacking, caches/checkpoints zero, specialist mask and production `trim-v1`
provider. The original base and adapter remain external immutable inputs. The
current App executable is a reference identity only; the fresh Evaluation assembly
executes both portable host and speech worker. This is not an application UI run.

After RTE inference priority is cleared and the parent grants the N10 slot:

```bash
python3 controller.py run --cpu-release-confirmed --semantic-priority-cleared
```

No phase runs automatically. All destinations are exclusive-created; another run
requires a new separately named condition. The run performs complete pre/post
hash verification outside timed release intervals. It clears inherited tiered
compilation overrides, sets `DOTNET_TieredPGO=0`, scopes native CPU device selection,
and records selected public host/child environment values. It rejects competing
native llama workloads. Timeout/cancellation terminates only its own process group.

The replay retains the **first trial and all ten repetitions** of the one public
10-second JFK clip (100 seconds real-time audio). Normal initialization and the
existing synthetic cleanup warmup remain separate; no additional warmup, forced
GC, trial filtering, or short-output success is introduced. Analysis uses
`CountingInjectorCompleteMilliseconds`, including complete delivery to the
counting injector, rather than transcript-ready latency. N10 nearest-rank p95 is
its maximum, not a stable population tail estimate.

The resource gate requires 10 complete single deliveries, accepted cleanup with
no fallback/provider failure, all full input/output text stages, complete word
sequence preservation on this already-clean public clip, and coherent simultaneous
evaluator+speech+cleanup RSS. Changed words are retained for review and do not
qualify as a resource success. It does not sum independent component maxima.
Caps are **747,500,000 bytes and 805 ms**, the requested 15% allowance.

Semantic quality stays **unknown** even when these structural/resource checks
pass. This is Linux partial-pipeline evidence: no Windows, desktop UI, actual
SendInput, microphone/hotkey, GPU, whole-app SLA, or 99% quality qualification.
Actual full text, failure details, initialization, memory attribution and receipts
remain in the generated artifacts for review.

Preparation validation is synthetic only:

```bash
python3 -m unittest discover -s . -p test_controller.py -v
```

# Freehand transcript cleanup handoff

Prepared October 30, 2026. The user asked to stop and transfer this work to a new
agent in an environment with model-download access.

## User's objective and current priority

Implement a Wispr Flow-like final cleanup stage in Freehand. Actually run POCs
for the candidate models, grade output accuracy/fidelity, complete-output latency
and memory relative to the existing path, select the best fit, and finish its
integration into the application.

**Output quality is the primary selection criterion.** The user explicitly
accepts a slower, higher-memory first pass and wants to optimize those costs
after establishing quality. Earlier research's hard RAM/latency rejection gates
are superseded for this first cleanup implementation. Measure all three
variables, but do not choose worse text solely to meet the old limits.

The user wants the implementation/POC to continue in the cloud. A local agent was
only meant to update cloud-environment permissions. Do not delegate the actual
implementation to a local chat unless the user asks again.

## Critical status: implementation exists, model selection does not

- Local cleanup integration, candidate runtime adapter, evaluator, packaging
  preparation and focused tests have been implemented in source.
- **No candidate model weights were downloaded. No actual cleanup-model
  inference or model-quality comparison ran. No winning model was selected.**
- The native llama.cpp runtime was downloaded and verified, and the actual Core
  pipeline was replayed with cleanup disabled.
- The implementation and this handoff are checkpointed on the GitHub branch
  **`codex/transcript-cleanup`** in `samfarls55/freehand`. Fetch that branch to
  recover the code in a different environment. Its starting base was
  `93e555ca57b502dd3b53a44dc6d44ddaaf50a16d`, merge of PR #10.
- No normal installation update, PR, GitHub release or publication occurred.
- The app gracefully continues ordinary dictation when cleanup assets are absent.
  This is not evidence that the requested fully functional selected-model feature
  is finished.

## Recover the checkpoint from GitHub

The original working directory is `/workspace/freehand`. Local file links in the
old chat do not copy files into another environment. The source and this document
are available on the repository branch; a checkout of main alone does not contain
the checkpoint.

In the new environment, inspect and preserve any existing work, then run:

```sh
git fetch origin codex/transcript-cleanup
git switch --track -c codex/transcript-cleanup origin/codex/transcript-cleanup
```

Use a different local branch name if that name already exists. If the existing
local branch already tracks the checkpoint, inspect it instead of recreating it.
Then read `docs/TRANSCRIPT-CLEANUP-HANDOFF.md`. The source can also be inspected at
[the GitHub branch](https://github.com/samfarls55/freehand/tree/codex/transcript-cleanup).

The earlier portable bundle remains an optional backup/evidence transfer. It is
not needed to recover the source from the branch. These artifacts exist only in
the old workspace unless separately downloaded/uploaded:

Artifacts in the old workspace:

- `work/cleanup-handoff/cleanup-source.patch`: the earlier uncommitted source
  snapshot against the starting base above, including the earlier handoff.
- `work/cleanup-handoff/cleanup-handoff.tar.gz`: patch, handoff, transfer metadata
  and available synthetic baseline/bootstrap/test evidence. It excludes model
  weights, native binaries, SDKs, secrets and private recordings.
- `work/cleanup-handoff/transfer-manifest.json`: base commit, branch, file list
  and patch SHA-256.

For optional patch-based recovery only, in a clean checkout of the starting base:

```sh
git fetch origin
git switch -c codex/transcript-cleanup 93e555ca57b502dd3b53a44dc6d44ddaaf50a16d
git apply --check /path/to/cleanup-source.patch
git apply /path/to/cleanup-source.patch
git status --short
```

Do not apply the old patch on top of the fetched checkpoint. If main has advanced,
recover the branch first and reconcile it with current main without discarding
changes.

## Environment blocker and restart

The user had a local agent update the saved environment configuration to allow
Hugging Face. The old running session never adopted it: the final status check
still reported enforced **spec revision 1**, no added allowed hosts, and a normal
request through the inherited proxy to
`https://huggingface.co/api/models/quobi/quill` failed with
`Tunnel connection failed: 403 Forbidden`.

Saved environment configuration ID:
`c3f98934-debe-4bfe-8c40-ae7a28a3fba7~cecfg_6adaa8c2d1b48193aeefd21b2d3e8d4a`.

The requested additions were `huggingface.co`, `*.hf.co` and
`*.huggingface.co`, retaining existing restricted/package-manager access. The new
agent must verify the **active** environment's policy and an actual metadata and
model-download request. Saved configuration alone is insufficient. Follow the
cloud-runtime skill when available. Do not edit the runtime policy snapshot,
disable the proxy, turn off TLS checks or use alternate proxies to bypass policy.

The old cloud chat exposed environment status/diagnostic tools but no environment
editor, and thread listing/reading but no thread creation/sending. The user was
given a local-agent prompt solely for the permission change.

Old execution host: Linux x64, about 17 GiB RAM, no GPU, about 30 GB free workspace
disk; `/tmp` was smaller. .NET SDK 10.0.100 was at `.dotnet/dotnet`, not on PATH.
This is not the user's Windows hardware. Do not label cloud CPU timings as
Windows laptop or whole-app measurements.

## Candidate models and suggested experiment order

Start with a task-specific editor versus a larger general model, then compare
independent families. This order is a research recommendation, not a quality
ranking established by inference.

1. **Quill 4B**, publisher `quobi/quill`, documented filename
   `quill-4b-Q4_K_M.gguf`. Publisher card lists about 2.6 GB; that is not RAM.
   Specifically fine-tuned for dictation cleanup, including spoken corrections.
2. **Qwen3.5-9B**, initially a higher-precision compatible quantization where
   feasible. General-model local quality reference.
3. **Ministral 3 8B Instruct**, an independent-family comparison. The verified
   original checkpoint name is
   `mistralai/Ministral-3-8B-Instruct-2512-BF16`; select and verify an actual
   compatible GGUF artifact and its publisher/revision.
4. **Gemma 4 E4B IT**, another challenger. E4B is not an assumption of only four
   billion stored parameters; reviewed llama.cpp material lists a 7.52B text
   model. Verify artifact access and weight license before packaging.

Optional controls: unfine-tuned Qwen3.5-4B; compact Superwhisper s1-mini after
verifying its upstream card/terms; a larger Qwen3.8-27B or configured hosted model
as a quality reference on suitable compute. No hosted credentials or inference
were configured in this work.

The former official Qwen3.5 repository now redirects to Qwen3.8. The reviewed
release history did not establish a small Qwen3.8 replacement for 4B/9B. Do not
invent artifact names or assume the newest family has a laptop-sized checkpoint.

Quill's own example removes "I think" from a statement, so specialization does
not prove fidelity. Its V4 notes say correction collapse is taught to 2B/4B;
0.8B struggled to select deletion spans. Preserve a specialist's prescribed input
contract before experimenting with extra instructions/examples.

Prior small cleanup probes are recorded in `docs/ACCURACY-VALIDATION.md`:
Qwen3-0.6B was rejected for the old resource gate, not an established quality
failure; TeXlyre/Unbabel T5 probes damaged meaning or paths. Their ignored raw
probe reports were not present in this checkout. Do not turn those summaries
into a fresh benchmark.

Sources and fuller reasoning are in `docs/TRANSCRIPT-CLEANUP-RESEARCH.md`, whose
October 30 section supersedes its clearly labeled historical sections.

## What was implemented

### Core and dictionary behavior

- `src/Freehand.Abstractions/TranscriptPostProcessing.cs`:
  `ITranscriptPostProcessor : IAsyncDisposable`, with
  `ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)`.
- `DictationEngine` accepts an optional processor, a default two-minute cleanup
  deadline and a snapshotted enablement delegate. It processes the complete
  utterance after dictionary correction and English number formatting, before
  the existing single insertion.
- `DictationState.Cleaning`, cleanup outcome/time and original pre-cleanup text
  were added. Failures, rejected output, deadline expiry and late responses keep
  the existing normalized transcript; cleanup failure does not retry ASR or
  automatically insert a second version.
- Original foreground checks and SendInput delivery are preserved. The engine
  owns processor disposal and suppresses overlapping late cleanup jobs.
- `EnglishTextNormalizer.NormalizeWithProtectedRanges` carries dictionary offsets
  through length-changing number formatting without changing dictionary semantics.
- Literal replacements are wrapped with per-job markers, and their content,
  whitespace, order and unique survival must verify before markers are removed.
  Marker form:
  `[[FREEHAND_LITERAL_<randomjobhex>_<index>_START]]literal[[FREEHAND_LITERAL_<same>_<index>_END]]`.
- Strict marker survival can reject a legitimate Backtrack that removes a whole
  superseded clause. Treat that as a reported coverage limitation. Actual Quill
  marker behavior has not been tested with weights.
- Optional original text/outcome/time fields were added to history. Persistence
  still follows the existing history preference; transcript content stays out of
  diagnostics.
- An exposed recording-shutdown cancellation-source ownership race was fixed
  inside the engine's existing synchronization boundary.

### Local runtime

`src/Freehand.Cleanup` is a new .NET 10 project. `LlamaTranscriptPostProcessor`
owns a serialized authenticated loopback llama-server session through an injected
platform launcher. It uses offline mode, bounded context/output, cancellation,
idle unloading and complete-response validation. No runtime model downloading or
silent cloud fallback is implemented.

`LlamaCleanupOptions.LoadManifest(path)` reads `cleanup-manifest.json` with
required fields `runtimePath`, `runtimeSha256`, `modelPath`, `modelSha256`,
`modelId`, `promptStyle`. Paths may be relative to the manifest. Optional
`files: [{path, sha256, size}]` pins the complete bundle, including runtime DLL/SO
files; a provided inventory must include the primary runtime and model.
All listed assets are verified on every worker startup. The executable itself
is a small launcher, so its hash alone is not a full runtime-code pin.

Styles: `QuillChatMl`, `Qwen35`, `Ministral3`, `Gemma4`. Defaults: four CPU
threads, 8192 total context tokens, 2048 maximum output tokens, zero GPU-offload
layers, 60-second startup and idle limits. These are prototype settings, not
measured optimal values.

Quill uses its exact raw ChatML/empty-think prefix with `/completion` and
`--no-jinja`. General models use their embedded templates and
`/v1/chat/completions`. The canonical general instruction is embedded from
`shared/transcript-cleanup-prompt.txt` and shared with the evaluator. Complete
output is required; truncation, generation-limit stops and reasoning leakage
are rejected. Current general configurations disable thinking.

`src/Freehand.Abstractions/CleanupWorker.cs` defines the generic launch request.
`WindowsCleanupWorkerLauncher` is the Windows implementation: hidden process,
literal arguments, per-worker environment key, kill-on-close Job Object and
fixed-buffer output draining without content logging.

### App and packaging

- `CleanupEnabled` defaults true; `CleanupDirectory` optionally selects assets.
- Default bundle: `AppContext.BaseDirectory/models/cleanup/cleanup-manifest.json`.
- Composition lazily loads available configured assets, defers preference changes
  through its existing idle coordinator, and exposes missing/invalid model status.
- Settings has a cleanup toggle, folder selection/reload and status. Processing
  indicators include cleanup, and recording remains disabled while busy.
- History offers `Copy original` when original and final text differ.
- `scripts/prepare-cleanup.ps1` creates/validates an explicit local bundle, copies
  model/runtime licenses, records all file hashes and uses staged replacement.
- `build-release.ps1` accepts `-CleanupSource`, or detects a complete
  `artifacts/cleanup-assets`; it validates/copies the bundle before package-manifest
  creation. `dev.ps1` can use verified assets in the isolated development profile.
- No selected model download manifest/default winner has been added. Complete that
  only after real evaluation and artifact/license verification.

## Runtime already verified

`packaging/cleanup-runtime-manifest.json` records official llama.cpp **b12015**,
source commit `a34de8618b25dfc32ee43749db47d767a9f0a25d`.

- Linux archive: `llama-b12015-bin-ubuntu-x64.tar.gz`, SHA-256
  `25458e07a9eca87791b2c856bf7d1c457dcfda038d6bf2fa2bbb07f11c988ee6`.
- Windows CPU archive: `llama-b12015-bin-win-cpu-x64.zip`, SHA-256
  `f3a0097934526c7c937fbe33b8352ee305aa6605cceef1744427a84686edbc48`.
- Release root: `https://github.com/ggml-org/llama.cpp/releases/download/b12015/`.
- Both archives matched GitHub release digests. Linux `--version`/`--help` worked;
  Windows binaries were not executed. Preserve required DLLs and notices; Windows
  also needs the MSVC runtime.
- Old Linux executable:
  `work/cleanup-poc/runtime/llama-b12015-bin/llama-server`.
- Old Windows bundle:
  `work/cleanup-poc/runtime/windows-b12015-bin/`.

Those ignored binaries may not survive transfer; redownload from the pinned
manifest if needed. `/completion` in this build uses `stop_type` and `truncated`.
Both production and POC parsers were aligned, including Quill stop tokens.

## Evaluator and actual baseline

`tools/Freehand.Cleanup.Evaluation` contains a Python standard-library benchmark,
90 public synthetic fixtures (60 development, 30 held out), configuration example,
grading/import tools and tests. It launches/owns the native server, records
model/runtime/prompt/config hashes and source snapshots, complete-response and
startup time, and sampled process-tree memory. Linux private resident memory and
Windows private commit are separate metrics. This is not whole-app GPU/desktop
profiling.

`tools/Freehand.Cleanup.Probe` feeds those transcripts through the actual Core
dictionary, normalizer, cleanup provider, validation/fallback and single-delivery
orchestration. It uses generated tone/canned ASR/recording injector, not actual
speech recognition or physical text insertion. Its manifest mode invokes the real
cleanup provider; it does not substitute a model response.

The managed no-cleanup baseline completed all 90 cases with one recorded
insertion each. The importer/native baseline used actual Core-normalized inputs,
targets and checks, avoiding credit for already-existing number formatting.
There were 47 normalized example-target matches, 41 expected uncleaned-case
diagnostic failures and two formatting nonmatches. **These are synthetic cleanup
diagnostics, not ASR word accuracy or proof of conversational quality.**

Old artifacts below were selected for the optional handoff bundle. They are
ignored by Git and are not present in a fresh checkout of the branch; rerun the
baseline if the bundle is unavailable:

- `work/cleanup-poc/managed-baseline.json`
- `work/cleanup-poc/managed-baseline-final-scores/`
- `work/cleanup-poc/native-baseline-final/`
- `work/cleanup-poc/runtime/bootstrap-report.json`
- `work/cleanup-poc/script-test-summary.json`

Grade raw candidate output separately from accepted app output and fallback.
Otherwise rejection/bypass can make an inaccurate model appear successful.
Report acceptance and useful-cleanup coverage. Add actual dictionary-replacement
marker cases to the model integration trials before selecting a winner.

## Verification at the stop point

- Full solution strict Release build passed with **zero warnings/errors**:
  `.dotnet/dotnet build Freehand.sln -c Release --no-incremental -warnaserror -p:EnableWindowsTargeting=true -m:1`.
- Full cross-platform test run: **314 passed, 1 failed**, 315 total:
  dictionary 25/25, Core 151/151, cleanup provider 33/33, App 105/106.
- **Unresolved failure:**
  `Freehand.AppTests.HotkeyEditorTests.Long_combinations_wrap_and_survive_a_new_settings_session`,
  `tests/Freehand.App.Tests/HotkeyEditorTests.cs:74`: expected
  `label.Bounds.Height > 20`, actual `0`. Do not declare all tests green or assume
  it is unrelated to the modified Settings layout. Investigate before completion.
- The focused 17 App cleanup integration cases passed separately.
- 20 Python evaluator tests passed, including response-contract parity, timeout
  teardown, normalization import, fallback/coverage grading and real Linux
  process-memory sampling. Fake HTTP tests are not model inference.
- Managed probe Release build and `--selftest` passed; 90 no-cleanup replays passed.
- 55 PowerShell/Pester tests passed (43 existing + 12 new), zero failures/skips.
  Portable PowerShell 7.6.9 and source-built official Pester 6.2.0 were used because
  powershellgallery.com was not allowed. The old helper setup still uses Gallery.
- Windows-targeting compile passed; native Windows launcher tests, published app
  cleanup self-test, microphone/hotkey/foreground delivery and a real selected-model
  package have **not** been validated.
- `git diff --check` passed before handoff writing. Nothing was installed/shipped.

## Resume sequence

1. Fetch the checkpoint branch, read `AGENTS.md` and `docs/DEVELOPMENT.md`, and verify active
   network access in the new environment. Preserve the existing dictation model,
   dictionary contract, clipboard behavior and Windows platform boundary.
2. Resolve the UI test failure above. Rebuild and run the affected tests without
   concurrent shared-output builds. Earlier exploratory Core runs hit a 100 ms
   regex fallback under build load; do not silently raise deadlines or change
   formatting semantics to hide load-related failures.
3. Obtain real candidate metadata, immutable revisions, license texts, artifact
   sizes and SHA-256 values from their publishers. Download weights through the
   permitted network path. Choose verified compatible GGUFs; exact quantized
   artifact names/revisions are still pending. Disk/memory require sequential
   candidate loading. Gated/unavailable artifacts are acquisition limitations,
   not quality failures.
4. Recreate/verify the Core baseline, then configure the native comparison from
   `tools/Freehand.Cleanup.Evaluation/config.example.json`. Use the actual Core
   normalization report. Keep the general prompt canonical and each specialist's
   trained input format intact.
5. Run development comparisons and inspect the actual outputs for meaning and
   readability. Check uncertainty, negation, names/quantities, late corrections,
   intentional repetition, no-edit inputs, paths/URLs and dictated questions.
   Exact target match or verbatim WER alone is insufficient. These initial
   references are synthetic/agent-authored, not user-approved conversational gold.
6. Run the finalists through the managed provider/Core path, including literal
   markers. Record rejected/failed outputs, fallback coverage, complete latency
   and memory alongside raw quality. Freeze model/template/prompt/precision before
   heldout evaluation. If a holdout informs tuning, reserve fresh final examples.
7. Choose the quality leader with performance as descriptive evidence/tie-breaker
   for this first pass. Pin the selected model and prepare the bundle; finish the
   default asset provisioning rather than leaving only a manually configurable
   adapter. Keep source completion, installation and public publication separate.
8. Verify native packaging/startup and end-to-end dictation on Windows as available.
   A source build or synthetic injector cannot establish physical hardware claims.
   Do not install into the normal profile or publish without explicit user request.

Useful commands from the repository root (use installed `dotnet` instead if needed):

```sh
.dotnet/dotnet restore Freehand.CrossPlatform.slnf
.dotnet/dotnet build Freehand.sln -c Release --no-incremental -warnaserror -p:EnableWindowsTargeting=true -m:1
.dotnet/dotnet test Freehand.CrossPlatform.slnf -c Release --no-build --no-restore -m:1
python3 -m unittest discover -s tools/Freehand.Cleanup.Evaluation -p 'test_*.py'
.dotnet/dotnet run --project tools/Freehand.Cleanup.Probe -c Release -- --selftest
.dotnet/dotnet run --project tools/Freehand.Cleanup.Probe -c Release -- \
  --input tools/Freehand.Cleanup.Evaluation/fixtures.json \
  --output work/cleanup-poc/managed-baseline.json
python3 tools/Freehand.Cleanup.Evaluation/benchmark.py \
  --config work/cleanup-config.json \
  --normalization-report work/cleanup-poc/managed-baseline.json \
  --output work/cleanup-poc/native-development --split development
```

For selected-model Core replay add `--manifest /absolute/path/cleanup-manifest.json`
and `--split development` to the managed probe. See both tools' READMEs for the
report schema and `score_probe.py` for separate raw/final/fallback grading.

## Suggested first message to the next agent

> Continue Freehand's cleanup implementation from the GitHub branch
> codex/transcript-cleanup in samfarls55/freehand. Fetch that branch and read
> docs/TRANSCRIPT-CLEANUP-HANDOFF.md first. The user prioritizes
> output quality and accepts a slower/larger first prototype. Verify the new
> environment actually permits Hugging Face downloads, fix the documented UI
> test failure, then run real Quill 4B/Qwen3.5-9B/Ministral/Gemma POCs. Grade
> fidelity, latency and memory honestly, select the best fit, and finish its
> functional app integration and asset provisioning. No real model comparison
> or winner exists yet. Preserve single delivery, dictionary literals, original
> recovery and local processing. Do not install or publish without my request.

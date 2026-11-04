# Cold-start400-case source-graph experiment

These are new controller files only: `source_tag_train400.py` and
`source_tag_runtime400.py`. The597006-parameter graph architecture, source-tag
contract, old48/16 trainer and prior candidate artifacts are unchanged. No
Torch, native client, model, actual cache or corpus was imported/run during
preparation. Tests use small synthetic documents and zero feature files only.

## Frozen inputs and feature profile

The current fixed plan is `scale400-preparation-01/pilot400-plan-v2.compact.json`,
SHA-256 `a709c8d3fdb36ceedfc7cd4430d1e79a75e05b4608d4ffabad84bd992cad793e`.
The earlier pretty7586 plan is preserved separately; root verified the full
objects are identical before selecting this compact artifact.
It retains400 cases,320 train and80 development, with319/320 train golds and
80/80 development golds supported by the held graph contract. The unsupported
training case stays in every status/fit denominator and is skipped only for CE.
Source metadata, old executable labels/programs, precompiled graph labels and
graph vocabulary fingerprints are all checked. Full label arrays/programs are
saved in compact output, alongside their digests.

The plan and cache must both bind the complete new feature-profile SHA. It has
batchSize256 and microBatchSize256; contextSize remains1024. All other fields
match root's declared profile: source-only native embeddings, width1024,
CPU4/4, F16 caches, no repack, no prompt cache/checkpoints, GPU0, pooling none,
no warmup, one parallel slot and no generation speculation. A512-batch profile
is rejected even when individual source text is identical.

Cache metadata stays in the prototype workspace, while `feature_directory`
must name an absolute regular nonsymlink directory under `/dev/shm`.
Every atom feature path is relative to that directory and cannot be absolute,
traverse `..`, escape the root or pass through symlinks. Shape, exact bytes,
source/encoder contract and SHA-256 are verified. The bytes actually loaded into
the source-feature tensor are rehashed to catch a change after initial metadata
verification. Raw little-endian F32 matrices are not copied into candidate
artifacts. The native request accounting must fit the400-case budget, and exact
cache-manifest binding plus explicit process reap/CPU release are mandatory.

## Fixed experiment settings

- New default-copy graph head from random initialization; no previous head or
  base/adapter checkpoint is loaded.
- Same model/contract/vocabulary bytes as the held graph baseline.
- AdamW, learning rate0.001, weight decay0.01, batch4 and seed20261104.
- Hard maximum1000 optimizer updates, two Torch threads and one inter-op thread.
- Worker deadline170seconds, including metadata/feature setup, and at least
 40seconds reserved for inference/reporting. Actual update count is recorded.
- Supervisor hard work timeout180seconds, plus bounded ownership-only cleanup
  of at most two seconds to reap; original interpreter spelling is preserved.

The existing seven graph-loss coefficients and branch masks are reused without
architecture or loss changes. The model receives source atom features and a
right-padding mask only. Gold targets/programs enter label construction and
diagnostics, never model-forward or candidate-decode inputs.

## All-case inference and review artifacts

All80 development rows run first if features/time permit; all320 training rows
follow. Missing features, unsupported golds, rejected graphs, errors and
deadline-stopped rows remain explicit. Every row includes its source, canonical
target, source/target hashes and candidate text or error, with programs and full
traces for accepted results. Attempted/accepted/rejected/error/unavailable/
not-attempted counts are reported against the complete split denominators.
No input fallback receives exact-match or clean-success credit.

Development80 includes16 cases consumed by the earlier experiment and64 new
cases from the same authored training-derived dataset. It is a development
diagnostic, not an independent fresh evaluation. Exact-canonical counts and
manual faithful-and-clean judgments must remain separate. No fresh3 file is
read or used by these controllers.

Large label and casewise inference files use compact JSON without dropping
fields, labels, programs, candidate text or traces. Small config/vocabulary/
metrics/manifest files remain readable. The new head, complete label arrays/programs and complete400-case outputs/traces
live in a fresh exact-granted `/dev/shm` output directory. Small config,
vocabulary, metrics and the candidate manifest live in a separate new metadata
directory under the prototype; owned worker logs and CPU-release evidence are
also written there. The manifest links every large artifact by absolute path
and SHA. The combined experiment is preflighted below50,000,000bytes, reserving
128KB for supervisor/release logs. Oversized writes are rejected before writing;
failed output is never deleted. Features remain in the separately owned external
cache, excluded from the experiment-artifact cap. Only the final tiny head is
saved; no base, adapter or optimizer checkpoint copy is written.

## Grant/launch after root releases CPU

Importing the runtime/settings helpers is standard-library only. Root creates
the explicit grant with operation `copy-editor-source-tag-train400`,
`cpu_granted:true`, `max_wall_seconds:180`, exact source/plan/cache/release pins,
the canonical settings SHA, exact absolute `/dev/shm` output directory and
`metadata_dir` matching the exact absolute prototype metadata directory. Source pins
come from `source_tag_runtime400.required_pins()`. Input pin names are `plan`,
`cache` and `cache_cpu_release`.

```text
ORIGINAL_CONVERSION_ENV_PYTHON source_tag_train400.py \
  --plan scale400-preparation-01/pilot400-plan-v2.compact.json \
  --cache native-cache400-01/cache-manifest.json \
  --cpu-grant GRANT.json --output-dir /dev/shm/NEW_ARTIFACT_DIR \
  --metadata-dir NEW_PROTOTYPE_METADATA_DIR
```

The default CLI plan SHA is frozen above. If root chooses a different serialized
alias, its exact plan/cache/grant/source binding must be frozen and reviewed
before execution; no input is silently substituted. The supervisor prints the
owned PID immediately and writes explicit reap/group-release evidence.

Current pure verification:

```text
python3 -m unittest test_source_tag_train400 -v
```

Six synthetic tests pass; the final duration is recorded with the source freeze. They cover new-profile/external-root binding,
path escape/release rejection, unsupported-row retention, joined deadline rows,
fixed settings/180-second guard, split artifact/metadata path binding, artifact
preflight and source-only cold-start
definitions. No actual400-case preflight, model run, training, native request,
quality result or application-SLA measurement occurred in this preparation.

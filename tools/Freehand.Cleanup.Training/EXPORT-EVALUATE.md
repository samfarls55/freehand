# Export and evaluation of a trained ScribeKey derivative

The production model/runtime, dictionary semantics, Windows capture and delivery,
and dependency pins are unchanged by these research tools. Source model identity
is ScribeKey Fast v1.1 at `c484dad2d815bff83d376e46b25a11dbc820992a`, BF16 weights
SHA-256 `1a9ab3fcd2384f9c4053f4b55d5e0f40de195487853fdd006b1fa810cd69e16a`.

Use the isolated conversion/training Python environment containing PyTorch CPU,
Transformers, safetensors and tokenizer dependencies. No package install or
network access happens during these commands. Run from the repository root and
choose fresh output paths; earlier artifacts are never overwritten.

## Merge and compact export

```sh
PYTHON=work/cleanup-small-models-2026-11-03/scribe-precision-source/conversion-env/bin/python
"$PYTHON" tools/Freehand.Cleanup.Training/export.py \
  --base work/cleanup-small-models-2026-11-03/scribe-precision-source/original-model \
  --adapter work/cleanup-scribekey-training-2026-11-03/RUN \
  --converter work/cleanup-small-models-2026-11-03/scribe-precision-source/llama.cpp-source/convert_hf_to_gguf.py \
  --converter-index work/cleanup-small-models-2026-11-03/scribe-precision-source/converter-source-index.json \
  --quantizer work/cleanup-poc/runtime/llama-b12015/llama-quantize \
  --runtime-inventory work/cleanup-small-models-2026-11-03/runtime-file-index.json \
  --output work/cleanup-scribekey-training-2026-11-03/EXPORTED \
  --temporary-parent /tmp --threads 4
```

This calls `pipeline.py merge` to apply `W + (B @ A) * alpha/rank` to the exact
original checkpoint, rounds back to BF16, and writes a new model in an owned
UUID temporary directory. The existing pinned llama.cpp converter emits F16
there; its matching native quantizer emits a Q4_K_M artifact in the output
directory. There is no Q8-to-Q4 requantization or editing of the base weights.

The default is `--merge-dtype bfloat16`, preserving the original baseline
conversion path. A separately recorded `--merge-dtype float16` experiment avoids
rounding small trained deltas back to BF16 before the F16/GGUF conversion. The
training pipeline records the selected dtype and rounding diagnostics; an FP16
merge is a different model artifact and needs its own native accuracy review.

The isolated tokenizer compatibility edits are the same as the baseline
conversion: `TokenizersBackend` becomes `PreTrainedTokenizerFast`, and the empty
`extra_special_tokens` array becomes an empty object. Vocabulary and special
tokens do not change. Q4/F16 tensor-name, shape and token-byte inventories must
match. All source, adapter, merged, converter, native and output hashes are
retained. Only this invocation's temporary intermediates are removed. On this
workspace `/tmp` is a separate memory-backed mount; its storage consumes RAM.

Every export copies the original inherited notices, including the LFM terms and
the required display attribution **Derived from ScribeKey Fast by ScribeKey**.
Export success establishes conversion, not inference quality or application SLAs.
Development exports can live in a fresh `/tmp` output directory when persistent
disk is tight; preserve their adapters, logs and hashes, and retain the chosen
final Q4 artifact on persistent workspace storage.

The default precision is `--quantization Q4_K_M`; the explicitly allowed
development alternatives are `Q3_K_M`, `Q3_K_S` and `IQ4_XS`. They need their own accuracy
and resource comparisons before selection. `--keep-f16` retains a hard link
when the temporary/output directories share a filesystem, or copies otherwise,
so a controlled precision comparison can reuse that exact merged F16. Its hash
is recorded separately. Do not retain every discarded F16 checkpoint on the
memory-backed mount indefinitely.

## Candidate identity and development replay

The optional deployed native LoRA route uses `freeze --runtime-adapter ADAPTER.gguf
--runtime-adapter-sha256 SHA256 --runtime-adapter-scale 1`. This pins a separate
`runtime_adapter` GGUF artifact; `adapter`/`adapter_config` still describe the
training safetensors lineage. The controlled native route requires the original
IQ4_XS base82ab… and emits manifest fields `adapterPath`, `adapterSha256`,
`adapterScale`. External scale1 preserves the GGUF's embedded alpha/rank factor;
qualification tooling accepts only finite scales in(0,1], preventing accidental
double scaling or applying the adapter again to already merged weights.

Native replay emits `--lora PATH` at scale1, otherwise `--lora-scaled PATH:SCALE`
as one argument, as required by pinned b12015. All adapter paths reject commas:
both native options parse a comma-separated list. Nonunit paths also reject
colons: that parser splits each item at every colon and requires exactly two
parts. In particular,
drive-qualified Windows paths cannot use a nonunit scale with this runtime pin.
The default `--lora PATH` scale1 route retains those paths unchanged.
Core reports must verify both expected and actual base/deployed hashes as typed
strings, plus an explicit finite numeric external scale (a boolean is invalid).
Optional reported byte counts must be integers matching the frozen artifacts.
Semantic
review checks those receipts. A paired original control has no deployed adapter;
its base can equal the selected base because effective model identity includes
the deployed adapter hash and scale. Other profile/source/runtime fields must
still match. Absent deployed adapters keep existing merged-model behavior.
Malformed or missing selected reports and wrong deployed hash/scale metadata
create a failed `runtime-deployment-verification.json` receipt. The control
still runs all500 cases; existing result bytes and case counts are preserved,
while the selected inventory/pair remain ineligible for qualification. Review
continues to require the exact deployed identity and complete verified pair.

Freeze a candidate only after all evaluation/training source files are stable:

```sh
python3 tools/Freehand.Cleanup.Training/evaluate.py freeze \
  --model work/cleanup-scribekey-training-2026-11-03/EXPORTED/ScribeKey-Freehand-trained-Q4_K_M.gguf \
  --runtime work/cleanup-poc/runtime/llama-b12015/llama-server \
  --runtime-inventory work/cleanup-small-models-2026-11-03/runtime-file-index.json \
  --probe tools/Freehand.Cleanup.Probe/bin/Release/net10.0/Freehand.Cleanup.Probe.dll \
  --adapter-config work/cleanup-scribekey-training-2026-11-03/RUN/adapter-config.json \
  --output work/cleanup-scribekey-training-2026-11-03/CANDIDATE-FREEZE.json

python3 tools/Freehand.Cleanup.Training/evaluate.py native \
  --dataset work/cleanup-scribekey-training-2026-11-03/data/development.jsonl \
  --candidate-freeze work/cleanup-scribekey-training-2026-11-03/CANDIDATE-FREEZE.json \
  --dotnet .dotnet/dotnet --phase development --mode both \
  --output work/cleanup-scribekey-training-2026-11-03/DEVELOPMENT-RESULTS
```

The native path first exports production ScribeKey prompts and Core-normalized
references through the managed Probe. It uses literal protocol v3 and exact
token IDs, plus the unchanged context1024/output512/thread4/batch64/micro32,
f16 KV, no-repack, cache0/checkpoints0 and prompt-lookup16/3 profile. Actual
dictionary fixtures therefore receive Core normalization before inference.

`freeze --prompt-lookup-tokens 24` records a separate bounded runtime experiment;
the default remains 16 and the accepted range is 0 through 63, strictly below the
logical batch64. Zero disables speculation. The exact selected length flows
from the frozen profile into both the Core manifest and native replay flags;
all other runtime settings remain fixed. A new profile requires a new freeze
and output-equivalence/performance checks. Choosing24 does not establish any
99% accuracy or whole-app SLA claim by itself.
`--mode core` runs only the integrated Core provider and single-delivery probe;
`--mode native` runs only the raw native replay; `both` preserves both reports.
Native execution refuses concurrent native servers. Coordinate all training,
conversion and measurement CPU windows with the parent task.

The candidate freeze pins the model, full native runtime inventory, six managed
assemblies and all relevant source files. Sources and artifacts are verified
again after inference. A modified adapter, prompt, parser, model, native library
or managed assembly requires a new candidate identity.

Every new freeze also creates a small, create-only
`FREEZE-NAME.source-snapshot.tar.gz` beside its JSON. Each archived source is
verified against the recorded SHA before the freeze is written, and the archive
hash is verified before subsequent evaluation. This preserves the exact source
bytes even if uncommitted tools later change. Earlier546/80-case runs retained
source hashes, model/managed/runtime pins and outputs but had no pre-run source
archive; their source provenance remains honestly hash-only. No snapshot has
been fabricated or retroactively presented as a pre-run artifact for those runs.

## One-time blind qualification and semantic scoring

Development data may guide training. The independent final corpus is opened
only after candidate freeze. For the final run use `--phase blind-final`, its
exact 500-case Probe JSON as `--dataset`, and `--blind-commitment COMMITMENT.json`.
The commitment must contain `corpus_sha256` and `case_count: 500`. A create-only
`.consumed.json` record binds that test to this candidate before reading its
case content. Reusing that consumed test after tuning is rejected; further
training requires a genuinely new independently authored test. A blind path
cannot be passed as development data.

An optional preregistered original control can join the same one-time Core run.
Freeze the original IQ4_XS artifact with `freeze --original-control-provenance
ORIGINAL-CONTROL-EXPORT-REPORT.json`, without an adapter. Its report must pin the
original HF revision/BF16 SHA, original F16 SHA
`f11b2e31506e87e4e270a36a91fabfb7698dde68f942b64b02f6428cdc8f71dc`,
direct IQ4_XS quantization, no adapter, and the independently verified control:
211,804,448 bytes, SHA-256
`82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174`.
Metadata claims cannot substitute different model bytes. Then use:

```sh
python3 tools/Freehand.Cleanup.Training/evaluate.py native \
  --dataset INDEPENDENT-500-CASE-CORPUS.json \
  --blind-commitment COMMITMENT.json --phase blind-final --mode core \
  --candidate-freeze SELECTED-FREEZE.json \
  --paired-baseline-freeze ORIGINAL-CONTROL-FREEZE.json \
  --dotnet .dotnet/dotnet --output FRESH-PAIRED-RESULTS
```

Both artifacts and identical runtime/profile/source/managed assembly identities
are verified before parsing test cases. One preserved consumed lock binds the
two freezes and fixed selected-then-control order. Both full inventories and
role-specific metadata exist before inference. Selected outputs stay at the
root; the control gets `paired-baseline/`. Selected provider failures never skip
the control or shrink either denominator. `paired-completion.json` records both
report hashes/full500-case completeness, followed by verification of both
identities. Each report needs its own complete output-bound semantic review.
Paired review requires its own role-specific metadata, the verified successful
paired completion receipt and the exact captured report hash for that role;
swapped reports, missing metadata and any incomplete candidate are rejected.

The selected score alone determines495/500 qualification. Summaries retain
`semantic_role` and `primary_qualification_candidate`; a passing control has
`selected_primary_quality_gate_passed: false`. A consumed test cannot run a
third model or later tuned candidate under another output directory. Failures
preserve locks/partial reports for explicit documented infrastructure recovery.
This support is prospective: the first consumed500-case run had no paired
control, and that historical deviation remains recorded.

Create a review worksheet from either native `outputs.jsonl` or integrated
`core-results.json`:

```sh
python3 tools/Freehand.Cleanup.Training/evaluate.py review \
  --results RESULTS/core-results.json --output RESULTS/review-worksheet.json

# A named independent reviewer fills the case booleans and explanatory notes.
python3 tools/Freehand.Cleanup.Training/evaluate.py review \
  --results RESULTS/core-results.json --judgments RESULTS/reviewed.json \
  --output RESULTS/semantic-summary.json
```

Each judgment identifies `case_id`, exact `output_sha256`, boolean
`semantic_faithful`, `clean_usable`, `critical_error`, and a reason. The review
must name its reviewer and cover every case from the pre-run case inventory
exactly once. Partial denominators, duplicate cases, changed output bytes and
missing judgments are rejected. Provider failures/fallback and incomplete
delivery do not earn successful model-quality credit.

The requested accuracy is the fraction that is **both faithful and clean/usable**.
The user's current **99%** gate therefore requires at least **495/500** successful cases. Critical
errors count as failed cases and are reported separately, including a separate
zero-critical-errors flag; they are not silently hidden by the aggregate rate.
Exact/normalized target matching and fixed assertions are diagnostics, never
semantic oracles. Keeping already clean text may be correct; retaining cleanup
defects in an edit-needed case is not useful success. Name assistant reviewers
honestly; this is not blinded human sign-off or proven population accuracy.

Candidate freezes, pre-run evaluation metadata and review summaries record the
current minimum and required pass count. Existing runs and their original 98%
summaries are historical evidence and are never overwritten. A new review of
historical outputs uses the current 99% target and records the old run's target
separately; missing/failed cases remain in the full denominator.

Neither this native-only path nor the Core replay measures complete application
RAM, physical microphone/hotkey capture, Windows SendInput completion or GPU
behavior. The actual Windows desktop qualification remains a separate required
measurement against747,500,000 host bytes and805ms.

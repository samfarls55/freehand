# Managed cleanup pipeline probe

This probe feeds text fixtures through the actual `DictationEngine`: dictionary
correction, English number normalization, optional `LlamaTranscriptPostProcessor`,
Core validation/fallback and the single-delivery path. It uses a generated 0.1-second
tone, `FakeTranscriber`, `FakeHotkeySource` and `RecordingTextInjector`. It does not
recognize audio or type into another application. A manifest runs real local model
inference; there is no substituted model response.

Run the normalization baseline without a manifest:

```sh
dotnet run --project tools/Freehand.Cleanup.Probe -c Release -- \
  --input tools/Freehand.Cleanup.Evaluation/fixtures.json \
  --output work/cleanup-poc/managed-baseline.json
```

Run an explicitly prepared local model with the same fixtures:

```sh
dotnet run --project tools/Freehand.Cleanup.Probe -c Release -- \
  --input tools/Freehand.Cleanup.Evaluation/fixtures.json \
  --output work/cleanup-poc/managed-candidate.json \
  --manifest /absolute/path/to/cleanup-manifest.json \
  --split development --cleanup-timeout-seconds 120
```

The manifest uses `LlamaCleanupOptions.LoadManifest`; artifact paths and SHA-256
pins are mandatory. The provider verifies artifacts before starting its worker.
One provider is reused across cases and disposed at the end. The portable launcher
belongs only to this tool, drains/discards native output and kills the child process
tree on disposal. This does not verify the Windows application's Job Object lifetime.

`--split` accepts `development`, `heldout` or `all` (default). Freeze model, precision,
prompt and configuration before evaluating heldout cases. The default cleanup deadline
is 120 seconds; an explicitly changed deadline is recorded in the report. No downloads
occur. The output is atomically checkpointed after each case; `incomplete` stays true
until a run finishes. Exit codes: 0 completed without pipeline failures, 1 at least
one rejected/failed/timed-out case or wrong insertion count, 2 invalid configuration,
130 interrupted. Research fidelity judgments are separate from these exit codes.

## Corpus and report

Input uses the shared corpus's `cases` array, with required string `id` and `input`.
Optional `split`, `targets` and `checks` use the evaluation corpus format. Case IDs
must be unique. An optional case dictionary is an array:

```json
{
  "id": "dictionary-example",
  "input": "send fifty dollars to acme",
  "dictionary": [
    { "kind": "Correction", "hear": "acme", "write": "ACME", "is_enabled": true },
    { "kind": "Term", "write": "Freehand" }
  ]
}
```

The report contains `schema_version`, `metadata`, `incomplete` and `cases`. Each
case includes:

- `normalized_input`: actual dictionary/number-formatted text before cleanup.
- `candidate_text`: the processor's complete returned text before Core validation,
  including protection markers if a dictionary replacement required them; null when
  the provider failed before returning text. It may contain a rejected candidate.
- `output`: actual final Core text, including fallback when cleanup fails validation.
- `cleanup_status`, `error`, `cleanup_time_ms`, `processing_time_ms`, `elapsed_ms`,
  `insertion_count` and `delivered_count`. The two counts both count calls to the
  recording injector and do not establish physical delivery.
- `normalized_targets` and `normalized_checks`: targets and nonliteral assertion
  phrases independently replayed through the same no-cleanup Core pipeline.
  Literal checks remain unchanged. These diagnostic derivatives do not replace
  human-approved references. Their replays happen before the timed candidate case.

Metadata records corpus/manifest and managed assembly hashes, expected and final
independently measured runtime/model hashes, inference settings, runtime/OS/architecture and logical CPU
count. `gc_total_available_memory_bytes` is the runtime's GC memory availability,
not a measured process peak or a guarantee of physical RAM. Model hashes are
independently measured after trials to avoid warming model pages before the first
trial. Candidate and final/fallback quality must be scored separately so rejections
cannot make an inaccurate model appear accurate.

The CLI self-test exercises dictionary correction, number formatting, literal path
and whitespace preservation, and exactly one recorded insertion:

```sh
dotnet run --project tools/Freehand.Cleanup.Probe -c Release -- --selftest
```

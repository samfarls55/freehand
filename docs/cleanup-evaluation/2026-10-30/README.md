# Public cleanup evaluation evidence

These are public synthetic text fixtures and actual experiment results from the
October 30, 2026 continuation. Interpretation, selection and measurement limits
are in [the evaluation report](../../TRANSCRIPT-CLEANUP-EVALUATION.md).
There are no private recordings, model weights, runtime binaries or credentials.

`quill-development` and `qwen-development` preserve the original raw-message
protocol. The three `*-json-screen` directories preserve the common 24-case
development screen. Each includes actual native outputs, source snapshots,
artifact hashes and separate per-case semantic review. These protocol versions
are historical evidence, not the final application configuration.

`qwen-masked-literal-trial` preserves the final adapter's two targeted native
development trials. Its `raw_model_output` is distinct from the provider output
after deterministic restoration of protected literal blocks. Literal contents
restored by code are not credited as model copying successes.

`managed-qwen-*-final.json` files replay the real Core dictionary/number pipeline
and cleanup provider with canned speech text and a counting injector.
`candidate_text` is the complete provider return after protocol parsing and
literal restoration, before Core validation. `output` is Core's accepted result
or original-text fallback. These managed reports do not capture raw rejected
HTTP responses. The accompanying score directories distinguish provider returns,
application results, fallback and accepted coverage; `reviewed-quality.json`
adds agent semantic judgment beyond the automatic diagnostics.

The `*-memory.json` sidecars sample the owned managed-probe/native-worker process
tree. `matched-core-baseline-final` is the matched cleanup-disabled control.
They exclude real speech recognition, desktop UI, capture, observer and physical
delivery. Linux resident pages are not Windows private commit. Synthetic quality
judgments and small-sample tail timings do not establish population accuracy or
Windows hardware performance.

`integrated-pre-heldout-freeze.json` records source, compiled assembly, corpus and
manifest hashes before held-out inspection. `managed-source` preserves the
relevant source and integration fixtures. The selected/runtime acquisition
manifests pin immutable publisher artifacts. The verified bundle manifests and
actual Windows-install report establish full-artifact staging and reuse; the
Windows binaries were not executed on Linux.

`provenance` preserves immutable publisher cards, license texts, templates and
public metadata. Its initial access report predates the full downloads and
inference documented elsewhere here. `validation` retains the final build,
App-test, publish and published-self-test logs as `.txt` files, alongside their
machine-readable summary; original absolute log paths refer to the cloud run.

To regrade a completed managed report from the repository root:

```sh
python3 tools/Freehand.Cleanup.Evaluation/score_probe.py \
  --input docs/cleanup-evaluation/2026-10-30/managed-qwen-development-final.json \
  --candidate-id qwen35-9b-q8_0-v3 --output work/regraded-development
```

Use `--corpus tools/Freehand.Cleanup.Evaluation/integration-fixtures.json` when
grading the dictionary report. Preserve existing reports and use a fresh output
directory for each rerun.

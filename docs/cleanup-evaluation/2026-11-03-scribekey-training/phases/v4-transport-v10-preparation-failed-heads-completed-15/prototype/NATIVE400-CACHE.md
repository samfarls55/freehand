# Separate 400-case native source-feature cache

This preparation adds `native400_client.py` and `native400_cache.py`; the frozen
64-case client, controller, tests, plans and artifacts remain unchanged. No native
server, model, Torch training, feature extraction or build was run to prepare
these files. The tests use mocked HTTP/processes and synthetic data. One test
reads only the explicitly supplied frozen400-plan metadata and forbids access to
case `target`, `target_sha256`, `label` and `tag_label` fields.

The plan is `scale400-preparation-01/pilot400-plan-v2.compact.json`, SHA-256
`a709c8d3fdb36ceedfc7cd4430d1e79a75e05b4608d4ffabad84bd992cad793e`.
Its full JSON object matches the preserved original version; only serialization
changed.
It retains `pilot64-001` through `pilot64-064` with their original48 training and
16 development roles. `scale400-065` through `scale400-336` add272 training rows;
`scale400-337` through `scale400-400` add64 development rows. All400 records remain
in the cache manifest, including unavailable source inputs and extraction errors.
Source-ready cases receive features even when their training target is unsupported.
The fixed denominator is320 training and80 development cases.

The feature profile differs from the64-case profile only in logical batch256 and
physical micro-batch256. It keeps context1024, width1024, four CPU/batch threads,
F16 key/value caches, zero GPU layers, pooling `none`, raw normalization `-1`,
disabled warmup/repacking, one parallel slot, and zero prompt-cache MiB/context
checkpoints. The exact original IQ4 base hash is
`82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174`;
the unmerged F32 adapter hash is
`4d14e22826d039a12444236124459363f02e77de247117b7b8379ccfe257cfb1`.
The controller checks the existing native runtime pin as well. No model/adapter
copy, merge, conversion or re-quantization occurs.

Each ready source uses its frozen official prompt plus separately tokenized
second source copy, exactly one BOS1, and verified native/HF token IDs. A request
over256 input IDs is retained as source-unsupported; it is never truncated or
split into invented feature chunks. All returned rows must be finite, nonzero,
raw1024-wide vectors with the exact input row count. Only the last covering
second-copy BPE row for each source atom reaches a little-endian float32 file.
The controller does not retain full native all-token embedding JSON.

The fixed feature-file cap is50,000,000 bytes. The frozen plan's source metadata
predicts43,159,552 bytes, with at most238 input IDs and78 atoms in a case. Those
counts come from metadata validation; they are not a completed native run. The
controller rejects a whole plan that exceeds the byte cap instead of filtering
cases to fit. At most400 embedding requests may be attempted, including failed
HTTP attempts; there is no hidden embedding retry. Tokenizer requests do not
perform embedding forwards.

Actual execution must wait for ROOT's serial CPU grant after the scheduled V10
worst-case LoRA profile. An estimated150 seconds of400-case work is unverified.
`DEFAULT_WALL_SECONDS=240` is a grant recommendation. The grant must explicitly
provide an integer `max_wall_seconds` from240 through900; an omitted budget is
rejected. The single work deadline covers input pin hashing, model startup,
tokenization and embedding requests, and caps each HTTP timeout to remaining
time. Owned-server TERM/KILL/reap cleanup retains the64-case bounded20-second
grace; actual wall time including cleanup is reported.

The grant operation is `native-copy-editor-cache400`, with `approved: true`,
`authorized_by: "/root"`, schema1, exact plan/client/controller/profile SHA-256
pins, and `max_embedding_requests: 400`. It binds both `output_directory` and
`metadata_output_directory` exactly. The feature directory must be a fresh owned
child of `/dev/shm`; the metadata directory must be a fresh owned child of this
prototype. Both reject traversal, symlink ancestors, existing paths and overlap.
Only F32 blobs go under `/dev/shm`. PID evidence, native logs, per-case results,
`cache-manifest.json` and `cpu-release.json` remain in the metadata directory.
The cache manifest's absolute `feature_directory` plus each case's relative
`atom_features_path` locate the blobs for a later granted trainer.

The intended invocation, after an actual matching ROOT grant exists, is:

```text
python3 native400_cache.py \
  --plan scale400-preparation-01/pilot400-plan-v2.compact.json \
  --grant <ROOT-supplied-grant.json> \
  --output /dev/shm/<ROOT-owned-fresh-feature-directory> \
  --metadata-output /workspace/freehand/work/scribekey-copy-editor-prototype/native-cache400-01
```

The launcher emits its own child PID immediately, verifies its process group and
session, and terminates/reaps only its owned process. CPU release requires both
the child to be reaped and its group to be gone. A deadline, error or failed
release leaves all400 records in an explicit partial/failed manifest.

Only `feature_contract.py`, the dependency actually used for source-offset
selection, is checked against the plan's live `sources` map. Historical
`preparation_sources` remain lineage. The feature cache does not import or pin a
live training pipeline as the historical `8c` source. Additional observer and
source-substitution provenance belongs to the approved outer wrapper.

Pure-code verification is:

```text
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v test_native400_client.py test_native400_cache.py
```

The all400 controller test mocks extraction and writes no feature matrices. A
single-case extraction test writes one4KiB synthetic F32 row. These tests establish
transport, storage and metadata behavior, not model quality, native throughput,
Windows execution, or whole-app memory/latency qualification.

# Source-indexed edit graph: actual first pilot

The new source-indexed model runs and fits its tiny training set, but it has **not demonstrated correction generalization**. The fixed16 training-derived development cases produced3 exact outputs, all three already-clean controls. The other13 outputs failed joint faithful-and-clean review. The earlier dense-slot failure and all its artifacts remain unchanged.

## Contract and verification

Each canonical source atom is a graph node. A virtual BEGIN node starts traversal. The model predicts bounded emission counts, case, anchored morphology, optional finite insertions and an optional next-source pointer. Default edges copy the next remaining source atom. Repair edges permit reordering and at most three visits per source node. END is valid only after every predicted kept/reused atom is consumed. No global output length, target prefix, target padding or learned spacing enters model forward.

Rendering preserves surviving adjacent source gaps and otherwise uses fixed punctuation spacing. Complete source-present letter/number identifiers may be rejoined; unseen recombined identifiers are unsupported. The previous executor validates every lexical/numeric operation and exact once/in-order protected payloads. Source provenance is a structural constraint, not a semantic guarantee: a learned deletion or incorrect role/negation can still change meaning.

All48 stdlib/mock/AST tests passed. Independent source review `77d0dc9e1d44733fff9f4c6167858a703b548131cf9e7892bdf4a13c4ef0726a` binds the held02 sources. The minimal reviewed identity canonicalization makes exact source==target labels copy every original atom, including punctuation. It changes labels only and leaves every gold text unchanged; the first source packet and first unit remain preserved.

The second actual synthetic Torch unit passed in2.624 seconds:597,006 parameters,48 finite gradient tensors, differentiable all-ignored loss0, exact default-copy outputs, strict bitwise checkpoint round-trip and malformed metadata rejection. No optimizer step or candidate was produced by that unit.

Static exact-gold coverage, with every case retained, is2702/2724 old unique training pairs and399/400 new pairs. The23 unsupported canonical targets need finite operations absent from the current inventory. This does not establish a task ceiling: a different faithful source-copy wording may exist. Neither these counts nor successful label execution measure model quality.

## Actual fixed48/16 pilot

The pilot reused the exact64 source feature cache, input-hash selection and split from the dense-slot pilot. It trained all48 eligible cases for300 updates, batch4, learning rate0.001, seed20261104. Model forward received only frozen source features and source padding. It made no native requests and changed no base or adapter weights.

| Observation | Actual result |
| --- | --- |
| Training exact outputs |47/48; the remaining output differs only in initial capitalization |
| Development exact outputs |3/16, all already-clean controls |
| Development structural acceptance |16/16; acceptance receives no cleanup-quality credit |
| Author actual input/output review |8 faithful,3 clean,3 joint; root independent adjudication is separate |
| Worker/supervisor wall time |9.277s /11.901s |
| Checkpoint |2,420,359 bytes; no optimizer/RNG resume state |
| Worker peak memory |413,667,328 bytes; research Torch process, not application qualification |
| Owned worker |PID/PGID/SID190148, exited0, reaped and group released |
| Input preservation |All120 recorded files unchanged across the job, including all prior102 files |

Five nonexact dev outputs preserved meaning but remained unclean through casing, punctuation or repetition. Eight retained canceled actions/attributes or malformed correction bindings. These results show strong training fit and poor generalization on this small split. No fallback received credit, and no99% or SLA claim is made.

## Evidence

- `source-tag-preparation-02/source-held-02.json`: final source/identity-label delta and provenance.
- `source-tag-preparation-02/all64-label-inventory.json`: all64 exact label round-trips.
- `source-tag-preparation-02/independent-source-review.json`: independent source review.
- `source-tag-coverage-03/`: complete approved-training coverage, unsupported rows retained.
- `source-tag-unit-02/`: actual head construction, gradient, checkpoint and ownership proof.
- `source-tag-pilot-01/`: actual head, configuration, labels, all64 inference, all16 joined dev pairs and author casewise review.
- `source-tag-pilot-01-closure/`:120-file preservation and actual CPU release evidence.

Tokenizer-only checks of all400 approved new source inputs found44–238 forced-copy tokens, so all fit256 tokens. Existing512-profile features remain immutable. A future256 profile needs new actual features and quality/resource qualification; its possible memory benefit has not been inherited or measured here. No application integration, new runtime dependency or production model selection was performed.

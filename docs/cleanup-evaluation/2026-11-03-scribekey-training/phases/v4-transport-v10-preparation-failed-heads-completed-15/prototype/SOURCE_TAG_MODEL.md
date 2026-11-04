# Source edit-graph model definitions

`source_tag_model.py` is a new baseline. The failed dense output-slot model and
all held editor-core/head/protection contracts remain unchanged. Only source
definitions and AST checks were prepared here; Torch, native clients, models,
caches and corpora were not imported or run for this task.

## API and architecture

The public API is `TagHeadConfig`, `CopySourceTagHead`,
`source_tag_loss(logits, labels)` and `TAG_LOSS_COEFFICIENTS`. The separately
owned `source_tag_contract.py` provides `TagVocabulary`, graph labels and safe
decode. Root must freeze that contract and the model together before execution.

The default model accepts `features[B,S,1024]` and right-padding bool
`padding[B,S]` only. It rejects an empty source. Canonical source atom i maps to
graph node i+1; node0 is a learned virtual BEGIN node added internally. No target
text, target token, previous output, global learned output queries, global
output length or learned spacing enters `forward()`.

Features project1024→128 with LayerNorm and learned source positions. Two tiny
bidirectional TransformerEncoder layers use four attention heads and feedforward
width256, followed by LayerNorm. `context_layers=0` is an explicit optional
source-aligned projection-only ablation; the default is two. Default dropout is
0.1, max_source_atoms512, max_visits3 and max_insertions4.

An encoded graph node is combined with a learned visit embedding. A learned
insertion-position embedding additionally conditions each finite insertion
slot. Shared per-visit classifiers avoid duplicating the large form/insert
vocabularies three times. Pointer queries/keys use128-dimensional projections
and dot products. Source padding keys receive -inf; key0 is the always-valid
END class, using the contextual BEGIN representation as its key.

| Head | Logit shape, N=S+1 | Classes |
|---|---|---|
| count | `[B,N,4]` |0 delete,1 keep,2/3 reuse; BEGIN ignored |
| case | `[B,N,3,5]` | keep/lower/upper/initial_upper/title |
| form | `[B,N,3,616]` | COPY0 plus finite source-anchored morphology |
| repair | `[B,N,3,2]` | OFF0 implicit next kept source; ON1 explicit pointer |
| pointer | `[B,N,3,N]` | END0 or source node1..S |
| insert_count | `[B,N,3,5]` |0..4 finite post-node/pre-BEGIN operations |
| insert | `[B,N,3,4,V]` | NONE0 plus finite function/case/punctuation classes |

Classifier weights initialize to zero and biases favor exact copy defaults:
count1, casekeep, formCOPY0, repairOFF0, insert_count0, insertNONE0. With the
default positive bias4, each favored class receives+4 and all alternatives-4.
Thus identity argmax is independent of random features/encoder activations.
Pointer logits remain irrelevant until the learned ON gate. This initialization
is a baseline behavior, not a cleanup-success claim: unchanged disfluencies and
grammar still fail a faithful-and-clean gate.

## Parameter budget, not a measurement

At V=150, the explicit arithmetic estimate is597006 parameters, approximately
2.39MB of FP32 parameter payload. The projection/positions/BEGIN/context/norm
portion is462464 parameters; shared visit/insertion embeddings and task heads
make up the rest. The no-context ablation removes264960 parameters. Actual
parameter count, resident memory and compute must be recorded by the separately
granted unit/controller; optimizer/activations/runtime memory are additional.

The source-aligned sequence length is N, rather than256 global output queries.
R=3 and K=4 are fixed representability bounds, not evidence of semantic quality.
Any unsupported gold remains in the full denominator. No model-quality,
training-speed, memory or end-to-end latency result has been established here.

## Gold-branch losses

`source_tag_loss` returns `(total, components)`. Fixed coefficients are count1,
case0.25, form0.5, repair1, pointer1, insert_count0.5 and insert0.5.
The loss clones supplied long labels and applies these gates:

- Count: valid source nodes only; BEGIN always ignored.
- Case/form: source visit indices below each gold count; BEGIN ignored.
- Repair/insert_count: visited sources and BEGIN occurrence0.
- Pointer: only active occurrences whose gold repair isON.
- Insert values: only active finite slots below gold insert_count.

Padding/inapplicable labels use-100. BEGIN occurrence0 becomes active only when
at least one source count is supervised, so an all-ignored batch stays ignored.
An entirely ignored head uses a differentiable empty-view sum. It never computes
`0 * -inf` on masked pointer scores. Counts, gates and targets are labels/loss
inputs only, not model-forward inputs.

## Checkpoints and decode

Config `to_dict/from_dict` preserves all fields and the exact vocabulary SHA.
`checkpoint_payload/from_checkpoint_payload` stores/strictly reconstructs
schema/config/vocabulary/state_dict using plain metadata and tensor weights.
The controller owns file serialization, optimizer/RNG state and source/feature
pins; no base model or native artifact is embedded.

`model.decode_sample(document, logits, sample_index=0)` converts only valid
N graph rows, slices pointer queries and keys, and calls the external
`decode_tag_scores` contract. That contract owns bounded visits, cycles, exact
counts, protected ID order, END handling and final executor validation. The model
cannot certify those constraints itself. Successful graph execution also does
not certify semantic cleanup: polarity, role, deletion, morphology, insertion
and correction-scope choices remain model responsibility. Rejection/fallback
never receives clean-success credit.

## Current checks and required execution

`python3 -m unittest test_source_tag_model_static -v` parses source without
importing Torch/model code. It checks the source-only forward signature, exact
seven-head graph ABI, absence of output-query/length/space heads, fixed loss
coefficients and no eager module-scope model execution.

The separately owned source-tag unit must, after root's CPU grant, instantiate
the real model, verify default-copy graph decode, all output shapes, finite
active/all-ignored gradients (including padding and repair masks), strict
checkpoint rejection and bitwise eval roundtrip. Training must use the frozen64
case feature/split plan and retain unsupported cases in every denominator.

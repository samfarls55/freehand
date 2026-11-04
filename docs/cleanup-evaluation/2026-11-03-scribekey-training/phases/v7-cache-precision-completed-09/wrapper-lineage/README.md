# V7 cache precision diagnostics

This new controller preserves the previous V7 export controllers and all earlier
runs. Root approved three serial Core runs, each with all500 retired development
cases: a SFT F16 bridge under the new source and Probe, then SFT F32 and UL F32.
The expected budget was9–11 minutes, based on the earlier171.1/176.4-second
F16 cohorts, with approximately3–5MB of reports, source snapshots and metadata.
The budget does not justify dropping cases or excluding failures.

All three new model/adapter/source/Probe freezes are created and verified before
any inference. Each run uses the same pinned original IQ4 base82ab…, the exact
unmerged SFT e880… or UL eada… F32 adapter at external scale1, native b12015,
lookup16, context1024, output512, four threads, batch64/micro32, and no repacking.
Only K/V cache precision varies. Flash attention retains the native default
`auto`; a cache-dependent kernel choice may be part of the configuration effect.
The earlier six-case diagnostic with a flash-attention override is not treated
as proof of numerical equivalence for these runs.

The fresh Probe6de0ab… and exact six-DLL receipt d720b6… are required, together
with evaluate.py131d2d… . Root committed the unchanged qualified source bytes as
8b059f2 after the build. Freezes record that actual Git identity; the build
receipt retains its earlier historical HEAD. Runtime metadata must explicitly
report the requested `cache_type_k` and `cache_type_v`. The controller also binds
the manifest SHA and observes the actual owned native worker arguments.

The bridge proof compares exactly13 fields: input, normalized_input,
cleanup_input, candidate_text, output, cleanup_status, error, insertion_count,
delivered_count, delivery_outcome, dictation_outcome, normalized_targets, and
normalized_checks. Only cleanup_input and candidate_text permit normalization
of the32-hex nonce inside exact paired `FREEHAND_LITERAL` markers. The index,
START/END designation, payload and every other byte remain unchanged. Marker
pairs, a consistent nonce per case, and exact payload presence in the original
normalized source input are checked. All other11 fields, including restored
output, are strict. Proofs assign no semantic credit; unexpected differences
require actual review. New code/DLL epoch attribution remains explicit.

Each command uses a dedicated owned process session/group, preserves logs and
command receipts, and stops/reaps that group on timeout or ordinary signal
cancellation. It inspects process names and live group/session identity before
reading only an owned native worker's full arguments. Dead Z/X processes are
ignored; unrelated live workers are never terminated. An external SIGKILL or
machine reset cannot execute Python finally blocks, so any such interruption
still requires recorded infrastructure recovery and preserved partial outputs.
A first-outcome startup exit/deadline stops the diagnostic rather than repeating
500 startup failures; it does not invent an unsupported-cache or OOM cause.

Every complete report retains all500 ordered IDs, model/provider failures,
error/status metadata and delivery counts. Candidates are post-trim-v1 and
literal restoration. There are no training, conversion, weight-copy, broad546,
hard80, performance or fresh-round2 operations in this controller. Accuracy
requires a complete output-bound semantic review. No Windows, whole-app SLA or
99% qualification is claimed by this diagnostic.

The final executed controller is e7f6316…; its earlier audited3fc2286… version is
preserved under historical/audited-three-job-3fc2286c. The final delta only moves
all three freezes before inference. Thirteen small tests cover cache/profile
identity, exact marker handling, strict restored output, live/dead process
ownership, and timeout receipt/cleanup. The independent audit and sequencing
supplement are retained beside this file. This README was written after launch;
it does not pretend to be a pre-run artifact. The actual executed bytes and
pre-run pins are in the fresh output tree and controller log.

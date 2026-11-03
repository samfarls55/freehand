# Bounded prompt-lookup audit

Reviewed pinned llama.cpp source commit
`a34de8618b25dfc32ee43749db47d767a9f0a25d` (b12015), extracted from the
already acquired source archive used by the ScribeKey conversion. The source
file index records complete hashes and immutable upstream URLs. No inference
ran during this source audit.

The optional Freehand configuration selects only `ngram-map-k`. It supplies
`--spec-ngram-map-k-size-n` and `--spec-ngram-map-k-size-m`; it does not enable a
draft model, a persistent n-gram cache, a cache file, extra downloads or network
access. `PromptLookupTokens=0` disables this configuration. Enabled values are
1–64 draft tokens and 1–12 match tokens. The sampled token plus draft must fit
the existing logical batch, so draft length must be less than `BatchSize`.

`common/ngram-map.h` defines a fixed table of 262,144 `uint32_t` entries: 1 MiB
per sequence. Freehand runs one sequence. Additional key records contain token
history indices and bounded counters. They do not contain a corpus of prior
transcript strings or token values. A new key references a current token-history
position; an existing record at that position must match that same current
key, bounding distinct positions by the context window. Vector capacity can
retain a high-water allocation until the worker exits. This does not imply
that total speculative runtime overhead is exactly 1 MiB: draft, sampler,
recurrent rollback/checkpoint and model verification buffers also contribute.
Measure their actual process-memory effect.

`common_speculative_impl_ngram_map_k::begin` invokes
`common_ngram_map_begin` at the start of a generation. The server calls that
after evaluating the new prompt. The map's begin function prunes indices when
history shrinks; it is not a full clear or memory zeroization operation. The
draft function checks matches against the **current** supplied token vector and
copies proposed tokens from that vector. Hash collisions are checked against
current tokens. Retained index/counter state can affect lookup behavior, but
the map does not supply token content from a previous request. Freehand's
`cache_prompt:false`, disabled host prompt cache/context checkpoints, bounded
context and disabled context shifting remain in effect. Existing model/KV
buffers are not a promise of cryptographic erasure either.

The server verifies proposed tokens with the target model's sampler before
acceptance. This makes prompt lookup suitable for a controlled optimization
experiment; it does **not** prove every output bit-identical across batching,
floating-point kernels or sampling configurations. The initial matched short
trial supplied by the parent showed identical outputs and lower median times,
but full development, dictionary and fresh frozen validation are required
before an enabled production selection. Neither source inspection nor worker
speed measurements establish Freehand's whole-application SLA.

Potential debug statements print token IDs. The existing worker retains
`--log-disable`; this option does not add logging or transcript persistence.

Source locations inspected:

- `common/ngram-map.h`: fixed table, index/counter structures and per-map state.
- `common/ngram-map.cpp`: begin/shrink cleanup, current-vector collision checks,
  current-vector draft copying and accepted-token statistics.
- `common/speculative.cpp`: per-sequence map construction and begin/draft hooks.
- `common/arg.cpp`: fixed map-k option names and native integer constraints.
- `tools/server/server-context.cpp`: prompt lifecycle, target verification and
  sampled-plus-draft logical-batch assertion.

# V4-01 Q4 development resource comparison

This is a **development-candidate Linux partial-pipeline comparison**. It does
not qualify the model on the independent 500-case set, or certify Freehand's full
UI, Windows/GPU memory, physical capture/hotkey or SendInput performance.

| Condition | N | Release p50 | Release p95/max | Highest observed simultaneous RSS |
|---|---:|---:|---:|---:|
| ASR/Core baseline |5|364.2637 ms|409.2071 ms|406,310,912 bytes|
| V4-01 Q4, production ASR config |10|684.9547 ms|816.9002 ms|702,046,208 bytes|
| V4-01 Q4, research prepacking-off |1|827.1929 ms|827.1929 ms|650,784,768 bytes|

The exact 15% limits are 747,500,000 bytes and 805 ms. Default Q4 fits the measured
partial RAM cap but misses latency in one of ten trials (the first). That trial
was retained. All 15 baseline/default trials preserved the full 22-word JFK text,
completed once and delivered once. The candidate returned Unchanged on all 10;
there was no fallback. Already-clean copied text is not evidence of useful cleanup.
With nearest-rank percentiles, p95 equals maximum for N5/N10; these small repeated
cohorts do not provide a stable tail estimate or independent quality evidence.

Default Q4's peak components at the same sampled instant were 82,116,608 bytes
host + 322,134,016 bytes ASR + 297,795,584 bytes cleanup. Separate component maxima are not added.
Initial ASR load 1165.8671 ms and cleanup synthetic warmup 694.9373 ms were separate.
The Eval-only one-hour idle override is recorded; production remains 60 seconds.

The one prepacking-off diagnostic added exactly
`SessionConfig.session.disable_prepacking=1` in a separate owned worker copy.
Original ASR threads, 110M weights and native 2.0.0 versions were unchanged.
It preserved all text and delivered once, but did not demonstrate improvement:
the comparable default **first** trial was 816.9002 ms/648,912,896 bytes, so the
variant was 10.2927 ms slower and 1,871,872 bytes higher in this single observation.
Do not compare its N1 peak against the default N10 ramp and claim savings. No
production setting changed and no follow-up sweep was run.

`plan.json` and `prepacking-one-plan.json` preserve exact commands, configurations
and hashes. Eval/Speech were built using an isolated `/tmp` artifacts tree. The
quality-frozen Cleanup/Core/Dictionary/Abstractions DLL bytes were then copied
read-only into that owned worker to keep the tested provider byte-exact; originals
were untouched. The assembly recipe and actual executed hashes are recorded.
Both isolated and quality-bound worker self-tests passed; strict build had zero
warnings/errors. Source is 7da7ad1 with generic-trim-v1 output handling.

`summary.json`, raw cohort JSON/logs and `prepacking-one-result.json` retain full
outputs, outcomes, one-delivery counts, simultaneous component memory, process CPU
and host GC/allocation ramps. No forced GC or accounting adjustment was used.
`post-run-verification.json` confirms 125 frozen files/links and 31 source checks,
including unchanged original quality Probe DLLs and production speech config.

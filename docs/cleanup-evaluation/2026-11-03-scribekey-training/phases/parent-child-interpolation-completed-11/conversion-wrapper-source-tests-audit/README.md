# Fixed parent–child factor derivation evaluation

This work-only controller converts and evaluates exactly three already-derived
adapters: child fractions0.5,0.75 and0.875 between the exact trained V7 UL parent
8855… and V8 child0ad094…. It performs no training, interpolation, optimizer
update, coefficient search, model merge or requantization. The raw derivation
owner completed and independently verified the three artifacts before releasing
CPU. Release9774… binds their exact adapters, configs, DERIVATION receipts,
source guard4baf…, unchanged codec57c5…, notices and both real histories.

DERIVATION metadata and minimal configs remain explicitly zero-new-step factor
derivations. Historical345/405-step training results stay separately labeled and
pinned. Both factors are interpolated: this is not a convex average of effective
LoRA deltas or model outputs, and the derivation receipt retains the cross term.
The wrapper verifies all184 custom F32 names/shapes/payload hashes, exact PEFT
copies and every final GGUF tensor value again for each derived artifact.
Alpha16/rank8 remains embedded2; external native adapter scale stays1.

All three native adapters and source/model/runtime/DLL freezes are completed
before the first inference. Each uses the same original IQ4 base82ab…, Probe
6de0…, six-DLL receipt d720…, evaluator131d…, F16 K/V, lookup16, context1024,
output512, four threads and batch64/micro32. Existing audited owned-process
execution6fe025… provides timeout/cancellation cleanup, dead-state filtering,
and immediate fsynced PID/start/owned-native-argv observations. All derivation,
endpoint, config, source, legal and runtime pins are rechecked after conversion
and Core. Large adapter/PEFT/GGUF files stay under owned /tmp paths.

All three candidates run the same full retired500-case development corpus,
serially and once each. The earlier screen idea was not implemented or run.
Failures, rejected candidates, errors and all500 IDs remain in each denominator;
original fallback receives no model-success credit. Core reports contain actual
post-trim-v1/restored candidates and explicit cache metadata, not pretrim raw
completions. There is no fresh-round2, performance, broad or hard-set action.
Expected CPU/native budget is approximately9 minutes for the three cohorts plus
conversion and verification. New persistent evidence is expected below5MB before
semantic reviews; three native adapters add approximately36MB under /tmp.

Root predeclared selection before inference: highest joint faithful-and-clean
count, then fewer critical errors, higher faithful count, higher clean count,
and finally higher child fraction. The existing V8 baseline492/500 at fraction1
remains in the comparison; a weaker interpolation does not replace it. Output
reviews and resource qualification are separate. Any resource claim must measure
the actual selected artifact. These runs alone establish no99% fresh-test,
Windows or whole-app performance qualification.

After wrapper audit PASS and the derivation owner's explicit CPU release:

```sh
work/cleanup-small-models-2026-11-03/scribe-precision-source/conversion-env/bin/python -B \
  work/cleanup-scribekey-training-2026-11-03/parent-child-conversion-preparation/run.py \
  --output work/cleanup-scribekey-training-2026-11-03/parent-child-interpolation/full500-run-01
```

Every output must be fresh. Keep partial outputs and journals after any reset;
inspect live PID/start identities before considering a retry, so a surviving
original cohort is never duplicated automatically. Original endpoint weights,
training outputs, verifier receipts and old controllers stay untouched.

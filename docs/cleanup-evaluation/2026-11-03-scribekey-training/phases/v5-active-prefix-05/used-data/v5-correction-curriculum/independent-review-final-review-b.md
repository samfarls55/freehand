# Independent curriculum review B

Reviewer: `/root/final_review_b`, Codex GPT-6 assistant. Personally read all **240/240 input/target pairs**, cases `scribe-v5-correction-001` through `scribe-v5-correction-240`, positions `[0,240)`. Review used the input and target only, without author notes or verdicts. No blind-round2 files or metadata were accessed. This is assistant training-data review, not human or population validation.

The reviewed source is `train-240-v2.jsonl`, SHA-256 `29a024e5841c345c11f03a3597a1096c85e831b88f2c54d5bab3e8fc170eb1d2`. Its bytes remain unchanged. Each case judgment binds the exact input and target UTF-8 SHA-256 in `independent-review-final-review-b.json`; the original incremental records remain in `independent-review-final-review-b-manual.jsonl`.

Initial verdict: **239 accepted; 1 requires a target correction.** All 240 targets are clean plain text; case111 loses the speaker's politeness and therefore needs the voice-preservation correction below. No additional quantity, unit, cancellation-scope, unretracted-explanation, independent-instruction, reported-speech or deliberate-repetition issues were found in the other pairs.

## Required-correction overlay

**Case111 — `scribe-v5-correction-111` (zero-based position110)**

Input:

> I have not checked the seal. Please open the drum, cancel that, wait for the supervisor and keep the area clear.

Current target:

> I have not checked the seal. Wait for the supervisor and keep the area clear.

Recommended replacement target:

> I have not checked the seal. Please wait for the supervisor and keep the area clear.

The current target preserves the unchecked-seal fact and final waiting/area-clear requests, but removes “Please.” The frozen policy preserves speaker voice, and carrying this politeness into the replacement request is consistent with other corrected polite imperatives, including cases046, 052, 059 and 061. The replacement does not revive the canceled drum-opening action.

Original target SHA-256: `e865790aa356f6db1287c9827ae10d0a334052fd17f5391239bd3561b71a2485`.

The JSON report contains the same case-specific overlay. It proposes a correction for controller approval without editing the dataset.

## Coverage observations

Cases001–160 were individually checked for correct final value/action, retained independent clauses and explanations, actor relationships, quantity/unit scope, modality, time, uncertainty and politeness. For example, case057 intentionally retains both original-letter retention statements, case106 retains estimate filing while correcting ruler return, and case110 retains timetable sending while correcting the overnight-stop action.

Cases161–240 were individually checked as clean contrasts. Past intentions and reported decision history remain intact; quoted or discussed correction cues are treated as content. Legitimate grammatical repeats such as “can can,” “had had” and “is is” remain, as do deliberate emphatic repeats and substantive words such as “Well,” “Like” and “actually.” Input-target equality was not used as an automatic correctness oracle.

No models, training, application code, corpus content or existing judgments were changed.

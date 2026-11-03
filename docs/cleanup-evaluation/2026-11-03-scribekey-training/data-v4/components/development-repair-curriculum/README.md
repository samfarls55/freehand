# Development repair curriculum: 90 training pairs

`train-90-v1.jsonl` is the complete training input. Its SHA-256 is `1f186a9dd5d796dbb4c61cd453f66669bfcb56ec09df6496ec020453167c981e`. It has 18 individually authored pairs in each of the five requested families, 60 cleanup targets and 30 unchanged controls (33.3%). The comparison family contains 9 unpunctuated comparison cleanups, 3 unambiguous filler-like cleanups and 6 meaningful-like unchanged controls.

All 90 fixed pairs received manual semantic review by an assistant other than their author. The primary reviewer also personally read all 90. No defects or advisories remain: trainable as-is, subject to root's pending opaque overlap checks. Reviews are assistant reviews, not human judgments or model-evaluation results. Casewise notes and exact input/target hash bindings are in `casewise-audit-90-v1.json`.

Authoring used only the parent-reported mismatch-family descriptions. No evaluation corpus or blind case contents were opened for authoring. These are feedback-driven TRAINING examples, never a fresh final test. No model runs or application source changes were performed.

The two source-part JSONL files are preserved authoring artifacts. Do not concatenate them with the complete training input. Three originally comparative boundary-part records were replaced before the combined V1 freeze with parent-authored filler-like contrasts, separately reviewed; their IDs are 060, 063 and 066. The source parts remain unchanged.

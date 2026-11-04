# V8 parent → V9 child factor interpolation — preparation only

This is a separate owned copy of the completed V7→V8 preparation. The old helper,
codec, artifacts and evaluations remain unchanged. Only four endpoint pin
assignments and the helper's descriptive docstring changed. `SOURCE-DIFF.patch`
and `PLAN.json` prove the normalized AST is otherwise identical and reversing
those five source-line changes restores the old file byte for byte.

The unchanged `derive.py` codec is SHA-256
`57c5ff750aed2c5e11cf4a4509274e688084bf0fcd2afde0ca53b8841aecef8f`.
The original nine tiny tests are copied byte-exactly and pass. Only small config,
schema, helper and legal-notice metadata were inspected. **No real adapter/header
was read, no weights were derived, and no conversion, native, compiler, model,
Torch or training run occurred.** Selection awaits root's completed V9 review.

Fixed endpoints:

| Role | Raw adapter SHA-256 | Config SHA-256 |
| --- | --- | --- |
| V8 parent | `0ad09445f70d2547696691511b4a7973bdfe1de4545b83cf76f2b62ca0a8306c` | `2637946ed089eb5c1b53371def45af9b67380c7a2089d40f2bb29cca8ff1cdb9` |
| V9 child | `3de792128cce7469465ca8c42ebef5f769e868415db80198eb036e8cbec05787` | `0b6a1e75f9ab4d2c2ecec1d09dffb254264981316e34f8609542649c78bc3ab8` |

The pinned small configs pass all23 compatibility checks, including the exact
original IQ4 base82ab…, rank8/alpha16/scaling2,184 F32 tensors across92 targets,
native-Q8 activation meaning, KVnone, tokenizer, literal protocol and historical
source8c609…. V9 explicitly identifies these V8 raw/config hashes as its parent.
Training data, objective files and optimizer/RNG histories differ intentionally;
the tool retains each full historical config rather than falsely equating them.

Only child fractions **.5, .75, .875** are accepted by the CLI. The factors are
interpolated in F32 with the same round-products-then-sum implementation:

```
A_t = (1-t) A8 + t A9
B_t = (1-t) B8 + t B9
delta_t = (1-t) delta8 + t delta9
          - 2 t (1-t) (B8-B9) (A8-A9)
```

The cross term is real and disclosed. This is not exact additive-delta or
functional averaging. Shared ancestry does not guarantee improvement, token
agreement or preservation of either endpoint's successful cases.
The equations describe real arithmetic; F32 product/sum rounding adds numerical
differences, and native bit equivalence remains unproved.

Future execution requires root's explicit candidate decision and serial CPU
window. Example for t=.75; the command has **not** run:

```sh
python3 -B work/cleanup-scribekey-training-2026-11-03/v8-v9-factor-average-preparation/derive_parent_child.py \
  --parent work/cleanup-scribekey-training-2026-11-03/pipeline/v8-01 \
  --child work/cleanup-scribekey-training-2026-11-03/pipeline/v9-01 \
  --schema work/cleanup-scribekey-training-2026-11-03/v8-v9-factor-average-preparation/expected-schema.json \
  --notices work/cleanup-scribekey-training-2026-11-03/v8-v9-factor-average-preparation/legal-notice-sources.json \
  --child-fraction .75 --output /tmp/CHOOSE-FRESH-v8-v9-factor075 \
  --evidence work/cleanup-scribekey-training-2026-11-03/CHOOSE-FRESH-v8-v9-factor075-evidence
```

The other fixed fractions require their own fresh paths. Parent bytes are
hash-checked before and after any future derivation; exact shape/key/offset/F32
and finite-value checks, output readback, source/helper/schema identity, legal
notices and ScribeKey credit remain unchanged. Derived configs/receipts declare
zero derivation optimizer steps and omit fabricated optimizer, RNG and training
resume claims. The base stays unmerged, with no requantization and external scale1.

The resulting footprint remains rank8/alpha16,184 tensors,2,998,272 parameters
and11,993,088 raw F32 payload bytes per adapter. Three safetensors plus three
native GGUF payloads need roughly72 MB; optional separate PEFT copies add about
36 MB. These are storage estimates, not memory/latency qualification.

Actual derivation/export source review, native tensor preservation, full
development semantic review and actual resource checks remain required. The
generic evaluator freeze does not recursively validate every derivation parent,
so the future controller must preserve and verify this provenance separately.
No subset screen can establish495/500. No fresh corpus was accessed or modified;
final acceptance still requires a frozen selected candidate and its complete
fresh evaluation. No model default, installation or release changed.

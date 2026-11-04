# Original GGUF to HF causal proof

The original source checkpoint was not modified. No training or fresh blind
evaluation occurred. All recovered/dequantized base weights stayed in memory.

`f16-inverse-proof.json` records an exact comparison for all 148 tensors:
93 F16 and 55 F32 storage tensors match the prescribed casts from the original
BF16 checkpoint, byte for byte. All 10 convolution singleton dimensions were
restored. Names and shapes form a bijection, and there is no generic matrix
transpose. Each recovered HF model verified that its output head and input
embedding share the same underlying weight.

Six fixed, already-consumed production prompts were selected before inference:
the first four rows of the existing 15-case diagnostic export and its final two
unchanged controls. No target fields were copied or used to select outputs.
All 24 native/HF prompt token arrays match exactly.

| Base | Adapter | Exact output/token agreement | Largest first-token top-20 common log-probability difference |
| --- | --- | --- | --- |
| Original F16 | None | 6/6 | 0.00808 |
| Original F16 | V5 F32 unmerged | 6/6 | 0.00765 |
| Original IQ4 | None | 6/6 | 0.37679 |
| Original IQ4 | V5 F32 unmerged | 5/6 | 0.38572 |

Native includes EOS7 in its returned token array; the HF receipt records EOS
separately. Agreement above compares tokens after removing that native EOS.
All 24 first-token argmax IDs agree. The probability evidence is native
normalized top-20 log probabilities, not full native vocabulary logits.

The differing input was:

> Please inspect the hinge and replace the lock, scratch that, lubricate the lock.

Original IQ4 plus unmerged V5 adapter returned:

- Native with production F16 KV: `Please inspect the hinge and lubricate the lock.`
- HF with FP32 dequantized weights and FP32 KV: `Please lubricate the lock.`
- Native with only KV changed to F32: `Please lubricate the lock.`

Changing native KV precision alone therefore changes this editing decision.
This is evidence of rounding sensitivity, not proof that all native/HF IQ4
differences arise from the cache. Native IQ4/Q5_K/Q6_K matmul also dynamically
quantizes activations to Q8_K; HF dense FP32 does not. The larger probability
differences remain relevant even where greedy outputs agree.

## Bounded next experiment, requiring separate authorization

1. First emulate production F16 K/V storage in the HF attention path: cast
   post-RoPE keys and projected values through F16 back to FP32, consistently in
   prefill, decoding, and any eventual teacher-forced loss. Use straight-through
   gradients if training is later authorized. Repeat these same fixed inputs.
2. If a material mismatch remains, emulate native Q8_K activations in the frozen
   quantized-base linear path, preserving the original FP32 input for the
   unmerged LoRA path. Use exact 256-element block scaling and rounding, not a
   generic per-token int8 quantizer. Validate against the pinned native
   quantizer before inference; keep this separately switchable from KV rounding.
3. Compare a small fixed 2x2 inference matrix: FP32/F16 KV rounding, with/without
   Q8_K activation emulation. Select the numerical approximation using native
   agreement, never target-label correctness. No training should precede this
   bounded causal comparison.

Only after that proof should a new adapter phase use the approved full-history
curriculum. Keep the base IQ4 file exact and the adapter unmerged F32. Rank16,
new examples, or direct training on the retired 500 were not performed or
authorized by this proof.

The environment reset killed the first controller after 11 native results.
The owned orphan server was terminated; those results were preserved and only
missing conditions were resumed. `comparison-summary.json` identifies the
per-case receipts, including the one resumed native result in `recovery-01`.
All proof model processes exited before CPU release.

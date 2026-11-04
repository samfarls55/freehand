Independent trainer audit: rank 8 source approved; rank 16 remains blocked

Reviewed pipeline SHA ef07d31f161f97d6fe0a21cc89e57c9b2879d58e9a0fc79c89b017dda67e5daa. Original IQ4 decoding covers all 148 tensors with tied output head; native Q8 hooks cover all 93 quantized matmuls and preserve raw LoRA inputs. Exact recovery binds implementation, base, parent and optional emulation identities. Wrong-base BF16 merges are rejected.

The separately executed 18 focused and 2 resume tests pass. The real model 2×2 comparison remains 5/6 for every mode; Q8/no-KV has the smallest measured first-token discrepancy but no output agreement gain. The real rank-16 initial-logit guard fails despite passing matrix-delta/tiny checks, so the selected control retains rank 8/alpha 16. No tolerance was weakened.

This is source/evidence review for the separate one-epoch 2014-row control, not model qualification or training authorization. No fresh round-two material was accessed. See the JSON for exact hashes, limitations, and evidence attribution.

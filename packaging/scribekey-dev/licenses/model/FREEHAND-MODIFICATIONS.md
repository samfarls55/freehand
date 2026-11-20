# Freehand development derivative

Derived from ScribeKey Fast by ScribeKey, Fast v1.1 revision c484dad2d815bff83d376e46b25a11dbc820992a. Original model terms and notices are retained alongside this file.

Freehand converted the unchanged original weights to F16 and quantized them with llama.cpp b12015 to IQ4_XS. The separate rank-8 F32 adapter interpolates corresponding LoRA factors halfway between Freehand V8 and V9 (alpha16, native external scale1). This is factor interpolation, not exact averaging of model weight deltas. No additional optimizer updates, merge or requantization were performed for the blend.

The 50/50 blend scored495/500 on older consumed development, but462/500 on the subsequent independent test, now retired. It is offered for development testing, not as a99% general-accuracy or Windows performance qualification.

# Future qualified ScribeKey native-LoRA Windows preview

This is an independent source copy of `work/trained-scribe-preview-builder/`.
It prepares a future **isolated, manually supplied preview**, after the parent has
chosen a qualified candidate and released a CPU window. No candidate is selected,
no real bundle was staged, and no application was built or published by this task.
The failed V4 builder, previews, ZIPs and their verification records remain intact.

Native mode keeps the original untrained ScribeKey IQ4_XS base unchanged:

- Base: 211,804,448 bytes, SHA-256
  `82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174`.
- Future selected adapter: 12,006,240 bytes, rank8 GGUF LoRA with F32 parameters.
  Its hash is deliberately unspecified until the qualified candidate is frozen.
- Native `adapterScale: 1` invokes `--lora <path>`. It preserves the GGUF's own
  alpha/rank scaling and supports Windows drive paths. No merge, quantization,
  weight conversion or nonunit colon-delimited `--lora-scaled` route is used.

The runtime manifest uses `modelPath`/`modelSha256` and
`adapterPath`/`adapterSha256`/`adapterScale`, plus a complete plain
`files: [{path,size,sha256}]` inventory. `typed_artifacts` in root evidence labels
the base, native adapter and runtime separately. These extra evidence roles are
not additions to the production runtime schema.

Normal Settings acquisition intentionally rejects an unplanned adapter. This
builder does not change acquisition, the default9B manifest, installation,
normal profiles or normal settings. The app's existing explicit prepared-manifest
loader/provider supports the separately pinned adapter and verifies its inventory.

## Frozen conditions and evidence

The native CPU condition requires threads4, lookup16/match3, context1024,
batch64/microbatch32, explicitly selected f16/f32 KV types, output512, prompt cache0, checkpoints0,
repackfalse, literal maskingtrue, GPU layers0 and 60s startup/idle timeouts.
The candidate must freeze the full typed `cpu_profile`, including both cache types;
the source manifest, root evidence, staged manifest and launcher must agree. The
launcher preserves the separate adapter fields while cloning a fresh manifest.
It retains the existing separate NVIDIA Vulkan experiment; GPU layers999 and
lookup0 are requests, with positive hardware telemetry required for numeric GPU
qualification. Neither backend was executed here.

ASR remains Parakeet110m-int8 with four threads, the 198-byte spinning-disabled
speech config SHA `0d2e1a0192d981a06ec6a6839810bc9f58cbfc7fdeea0c9ae1a708949562f7c9`,
and generated App `TieredPGO=false`, tiered compilation enabled. Publish checks
the source and generated runtime policy. Stage verifies reused ASR pins against
the unchanged speech manifest. Reuse prefers verified hardlinks; cross-device
fallback copies are verified. The source bundle and old preview are never edited.

The future candidate freeze must explicitly record parent selection and at least
495/500 jointly faithful and clean outputs. An aggregate receipt must bind that
result to the same base/adapter pair. This builder checks the parent's pinned
receipt; it does not independently judge semantic quality or open a test corpus.
The required eight provenance roles preserve base/adapter export receipts,
training source freeze, exact executed trainer/exporter code, training config,
lineage and aggregate qualification. Seven legal roles retain base license,
NOTICE, additional terms, modifications, adapter training/conversion notices and
runtime license. Additional existing license files, including runtime dependency
licenses, stay in the complete source-bundle inventory.

Only two explicitly pinned public, already consumed text fixtures are accepted.
No corpus discovery, author discovery or hidden-case packaging occurs.
`candidate-freeze.example.json` has failing selection/qualification fields and
placeholder adapter/source pins, so it cannot stage an accidental candidate.

## Later commands — parent selection and CPU release required

`plan` reads source text and metadata; it does not hash models or build anything.
Use fresh output paths for every operation. A failed stage preserves its partial
owned directory; retry into another new path.

```sh
python3 work/v7-trained-scribe-preview-builder/make_preview.py plan \
  --output work/v7-trained-scribe-preview-builder/NEW-plan.json

# Only after the parent freezes the qualified candidate and releases the CPU:
python3 work/v7-trained-scribe-preview-builder/make_preview.py publish \
  --scratch /tmp/freehand-qualified-lora-publish-NEW

python3 work/v7-trained-scribe-preview-builder/make_preview.py stage \
  --receipt /tmp/freehand-qualified-lora-publish-NEW/build-receipt.json \
  --candidate-freeze /PARENT/FROZEN/qualified-candidate.json \
  --destination /tmp/freehand-qualified-lora-preview-NEW

python3 work/v7-trained-scribe-preview-builder/make_preview.py archive \
  --preview /tmp/freehand-qualified-lora-preview-NEW \
  --output /tmp/freehand-qualified-lora-preview-NEW.zip
```

Publish creates fresh App, Probe and Windows-platform outputs through a separate
`--artifacts-path`, records exact source fingerprints and preserves default DLL
pins. Stage requires this builder's new producer receipt for matching source.
It refuses old App/Cleanup binaries, source-tree destinations, unsafe or
Windows-aliased paths, symlinks, case collisions and incomplete inventories.
Archive requires exact membership, checks every CRC and member SHA, records the
whole ZIP hash, and refuses an existing output. Large hashing, copying,
compression and all publish work remain deferred.

## Verification performed here

`synthetic-tests-cache-profiles-16.log`: 16 Python tests passed using small synthetic model,
adapter, runtime and ASR bytes. They cover pair/profile validation, qualification
and provenance gates, malformed pins, unsafe paths, case collisions, symlink
parents, unchanged sources, hardlink/copy staging and ZIP CRC/hash/coverage.
`synthetic-powershell-cache-profiles-6.log`: launcher parsed and6 function-only checks passed
for clone preservation, unit scale, adapter pin/path, orphan metadata and collision
rejection. The launcher body was never executed.

These latest checks cover the explicit f16/f32 profile change and three independent
review fixes (ZIP output inside preview, `..` preservation bypass, impossible
qualification counts), plus f32 staging and PowerShell cache-field preservation.
They ran at nice19 under the parent's explicit targeted-verification grant. The
PowerShell process remained below 138 MB observed RSS, with a 280 MB stop guard.
The earlier 13-test/6-check logs remain historical. Exact executed source pins,
resource observations and remaining gates are in `ready-gates.json` and
`latest-targeted-verification.json`. No real model or bundle was used.

These tests exercise the work builder and PowerShell clone contract. They do not
execute the C# manifest loader, .NET publish, a native runtime, real weights,
Windows or GPU hardware. Existing C# feature source is recorded separately in
`ready-gates.json`; its unit-scale route was inspected. A real selected candidate,
matched qualification receipts, parent CPU release, fresh cross-publish and final
hash/CRC verification remain gates. Windows/GPU execution is unavailable and must
remain explicitly unqualified in any prepared preview.

# Experimental native recognizer

This builds the Parakeet dictionary-hint adapter for the isolated accuracy
preview. The normal 110M app profile remains separate. Build inputs and official
GGML hashes are pinned in [source-manifest.json](source-manifest.json).

Use PowerShell 7 on Windows x64 with Git, Windows tar, CMake, Ninja, and Visual
Studio C++ Build Tools with the Windows SDK:

```powershell
pwsh -File tools/Freehand.Native/prepare.ps1 `
  -OutputDirectory artifacts/native-cache/transcribe-freehand
```

`-CMake` and `-Ninja` accept executable paths when they are not on PATH.
`-SourceArchive` and `-RuntimeArchive` reuse existing downloads after verifying
their pinned hashes. The script discovers MSVC through vswhere, extracts fresh
source, checks and applies [the patch](parakeet-hints.patch), generates import
libraries from the official DLL exports, and builds with two compiler jobs.

The output directory contains `transcribe.dll`, the unchanged official
`ggml.dll`, `ggml-base.dll`, `ggml-cpu.dll`, and `ggml-vulkan.dll`, plus licenses.
`native-build.json` records the exact source/archive/patch hashes, compiler and
build-tool versions, arguments, and output hashes. Local PE bytes can vary with
toolchains and build paths. Verify that record for a source build; a hash from
another machine is not a reproducible-binary claim. Successful caches are
rehash-verified on reuse. Source and build attempts remain under `_build` for
inspection.

The source is transcribe.cpp v0.4.1 commit
`4d7c1ccefd39e5a9ea36cca5f8fefc6dcc14b99b`, under MIT. The official CUDA/Vulkan
archive is used for its tested CPU/Vulkan subset; the CUDA module and external
CUDA dependencies are not included in the output. The app owns backend
selection, model verification, and performance acceptance.

Pass up to 40 logical phrases through `transcribe_run_params.vocabulary`.
Normalize them to NFC and collapse whitespace at the managed boundary. Native
encoding uses the GGUF's matching SentencePiece BPE pieces, with original-case
and ASCII-lowercase variants. A phrase-prefix graph adds at most 1.5 to a token
score, matching the current hint-score ceiling; an unfinished root prefix gets
0.375. Duplicate phrases do not stack scores. Blank and duration logits remain
unchanged. The graph is rebuilt and reset for each request. Core still owns
literal corrections after joining segments.

The adapter is a bounded greedy hint, so it does not reproduce Sherpa's two-path
search exactly. Its tokenizer's Unicode normalization is approximate; retaining
the existing supported hint character set avoids broadening that contract.
Hints can improve a close decision without guaranteeing a requested spelling.

Native controls compare 5,000 graph rows with an independent suffix matcher and
14 tokenizations with an independent GGUF-score BPE implementation. They cover
multiword continuation, overlap, duplicate hints, blanks, unrelated tokens,
unknown characters, and new-request reset without loading model weights.
`parakeet_hint_controls` and `parakeet_hint_asr` are optional CMake targets in the
patched source. The latter accepts a model and test WAV and is an explicit GPU
recognition test.

The verified no-COOPMAT2 development control produced byte-identical empty-hint
transcripts for all 120 existing recordings against the stock release. Both
scored 118/2461, or 4.79% normalized WER, and 133/2442, or 5.45% literal WER.
In a separate dictionary control, `Manta` and `MANTA` changed `monta` to `Manta`;
an unrelated hint and clearing hints restored the original output in the same
loaded session. Lowercase-only `manta` did not overcome that clip's preference.
Those are capability controls, not a dictionary-assisted accuracy benchmark.
The fresh holdout and complete desktop performance gates remain separate.

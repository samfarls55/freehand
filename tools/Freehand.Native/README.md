# Official native runtime

The accuracy preview uses the unmodified transcribe.cpp 0.4.1 CPU/Vulkan release.
[The runtime manifest](../../packaging/accuracy-runtime-manifest.json) pins its
archive, all 13 DLLs and license. GGML selects the supported CPU backend during
registration, including the generic x64 fallback.

Use PowerShell 7 and Windows tar:

```powershell
pwsh -File tools/Freehand.Native/prepare.ps1 `
  -OutputDirectory artifacts/native-cache/transcribe-0.4.1-cpu-vulkan
```

`-RuntimeArchive` accepts an existing download after verifying its checksum.
Complete caches are rehashed on reuse. An incomplete cache is extracted again
from the verified archive. A checksum mismatch fails before the runtime is used.

Stock and custom 7232 controls produced identical Qwen 0.6 Q6 transcripts for
all 120 existing development clips and identical results in 23 dictionary,
silence, short-speech and quiet-speech cases. Silero accepted all 120 speech
clips in both runtimes with identical probability bits and control decisions.
These controls support replacing the custom build; desktop acceptance and
the separate test set remain part of the app's evaluation.

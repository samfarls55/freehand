# Windows weight reader runtime

The accuracy preview builds transcribe.cpp 0.4.1 with one Windows weight-loading
change. It uses the binary CRT reader for the same tensor offsets, byte counts
and bounded 16 MiB staging buffer. Recognition and decoding code are unchanged.
The small CMake seam links against the official GGML DLLs instead of rebuilding
them. There are no hint, upload or diagnostic patches.

[source-manifest.json](source-manifest.json) pins the upstream source archive and
the combined reader/CMake patch. The [runtime manifest](../../packaging/accuracy-runtime-manifest.json)
pins the official archive, 12 GGML DLLs and all four license files. Its
`transcribe.dll` entry identifies the selected evaluated build. A fresh local
source build may have a different PE hash because of toolchain and build paths.
`native-build.json` records the exact resulting DLL and copied payload hashes.

Fresh preparation needs PowerShell 7, Windows tar, Git, CMake, Ninja and Visual
Studio x64 C++ Build Tools:

```powershell
pwsh -File tools/Freehand.Native/prepare.ps1 `
  -OutputDirectory artifacts/native-cache/transcribe-0.4.1-freehand-read1
```

`-CMake` and `-Ninja` accept explicit executable paths. `-SourceArchive` and
`-RuntimeArchive` accept existing downloads, which are still checksum-verified.
The helper uses fresh attempt directories and builds only `transcribe.dll` with
two jobs. It preserves failed attempts for diagnosis.
Extraction omits one upstream editor-instruction symlink that Windows tar
cannot create; it is unrelated to the native build inputs.

Reuse verifies the source/archive/patch pins and every recorded output before
resolving compiler tools. The official GGML and license hashes must still match
the checked-in pins. Stock `transcribe.dll` is rejected as the reader variant.
Use `-VerifyOnly` to validate an existing cache without building or downloading.

`scripts/dev-accuracy.ps1` requires this record for both its default cache and
an explicit `-RuntimeSource`. It copies the record into the preview and records
the exact packaged DLL hashes and build-record hash in `accuracy-build.json`.
Model accuracy and whole-app performance still require the measured published
executable; a successful source build alone does not establish either gate.

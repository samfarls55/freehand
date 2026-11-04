# Test the selected ScribeKey blend

Training is stopped. The development candidate is the V8/V9 50/50 factor blend,
using the exact original IQ4_XS base and separate F32 adapter. Release defaults
remain unchanged.

## Build from the development branch

Use Windows x64, Git with Git LFS, and PowerShell7. Preserve any local changes
before switching branches; a separate clone is also suitable.

```powershell
git fetch origin
git switch --track origin/codex/scribekey-blend-dev
git lfs install
git lfs pull
pwsh -NoProfile -File ./scripts/setup-dev.ps1
pwsh -NoProfile -File ./scripts/dev-scribekey.ps1
```

For an existing local branch, use `git switch codex/scribekey-blend-dev` and
`git pull --ff-only`. The two LFS files total223,810,688bytes. A GitHub source
ZIP or an unresolved LFS pointer is insufficient; setup rejects incorrect weights.

The command acquires hash-verified Parakeet and llama.cpp assets, publishes a
Release development app, and runs its actual bundled-worker startup self-test.
It prints the output directory under `artifacts/scribekey-dev-*` and opens the
preview. Use `-BuildOnly` to prepare without opening the UI, or `-ModelSource`
to reuse an existing pinned Parakeet directory. Each build preserves earlier
preview folders. No installer or updater runs.

## Download the Windows build

The **ScribeKey development preview** workflow builds this branch on Windows,
runs the strict solution build and regression tests, and runs the published
executable's self-test with the actual base and adapter. After a successful run,
download the **Freehand-ScribeKey-Dev-win-x64** artifact from
[GitHub Actions](https://github.com/samfarls55/freehand/actions/workflows/scribekey-dev.yml).
Extract it completely and double-click **Start Freehand ScribeKey Dev.cmd**.
PowerShell7 is required. Artifacts expire after30days; source builds remain
reproducible from the pinned assets. No GitHub Release is published by this workflow.

## What to test

Quit the installed Freehand from its tray menu. Test Right-Ctrl dictation into
Notepad or your normal applications, including hesitations, corrections,
negation, names and deliberate repetition. Settings/history live in the preview's
separate `profile` directory. Use **Copy original** when cleanup makes a mistake.
The bundled README describes the optional desktop benchmark and its report path.

The blend passed its older development reference at495/500 but scored462/500
on the subsequent independent set. Historical Linux partial-pipeline N10 passed
805ms/747.5MB at780.6206ms and693.90MB; Windows performance and physical delivery
need testing on your machine. Full training history is in
[the research checkpoint](TRANSCRIPT-CLEANUP-SCRIBEKEY-TRAINING.md).

Base SHA256: `82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174`.
Adapter SHA256: `4d14e22826d039a12444236124459363f02e77de247117b7b8379ccfe257cfb1`.

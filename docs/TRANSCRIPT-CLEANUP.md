# Local transcript cleanup

## Status

Cleanup is experimental. The candidate is ScribeKey Fast (IQ4_XS base) with
Freehand's rank-8 adapter, a 50/50 blend of training rounds V8 and V9. On a fresh
500-case test it produced faithful, directly usable text for 462 cases (92.4%),
with 10 critical meaning errors; the original ScribeKey scored 430. Use
**Copy original** when cleanup makes a mistake. Training is stopped. Its history,
datasets and evidence are on the `codex/scribekey-blend-dev` branch.

The installer bundles it. Packaging downloads 248,408,334
bytes from the [`cleanup-model-v1`](https://github.com/samfarls55/freehand/releases/tag/cleanup-model-v1)
release and llama.cpp's own release, pinned in `packaging/cleanup-model-manifest.json`
and `packaging/cleanup-runtime-manifest.json`. That release is a prerelease, so the
app updater ignores it.

## Licensing

The weights are **Derived from ScribeKey Fast by ScribeKey** and inherit the LFM Open
License v1.0 and the ScribeKey Fast Model Terms v1.0. Every place that names the
model, including the manifest's `ModelId` and `DisplayName`, must carry that credit,
and the license, `NOTICE` and modification files must travel with the weights.
Setup installs them under `licenses/model`. The LFM license restricts commercial use
only for organizations with $10 million or more in annual revenue. A new model
release must describe its changes in `FREEHAND-MODIFICATIONS.md`.

## Try the ScribeKey development preview

Use Windows x64, PowerShell 7 and Git LFS. Quit the installed Freehand from its
tray menu, then run from the repository root:

```powershell
git lfs pull
pwsh -NoProfile -File ./scripts/setup-dev.ps1
pwsh -NoProfile -File ./scripts/dev-scribekey.ps1
```

The script verifies the two LFS weights (223,810,688 bytes in total), downloads the
pinned speech model and llama.cpp runtime, publishes a Release build under
`artifacts/scribekey-dev-*`, runs the bundled-worker self-test and opens the
preview. Use `-BuildOnly` to skip opening it. Settings and history stay in the
preview's own `profile` folder. The **ScribeKey development preview** workflow
builds the same preview on GitHub Actions.

The cleanup worker starts loading when you press the dictation key, so loading
overlaps your speech. It stays loaded for five minutes after the last dictation,
like the speech worker. Bundle files are hashed when the worker first starts and
again only after a file's size or timestamp changes.

Base SHA-256: `82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174`.
Adapter SHA-256: `4d14e22826d039a12444236124459363f02e77de247117b7b8379ccfe257cfb1`.

## How cleanup runs

Freehand can run a final local edit after dictionary correction and English number
formatting. The complete result is checked before the existing single insertion.
Failed or incomplete cleanup keeps the original normalized transcript. Dictionary
replacement blocks are hidden from general models behind opaque identifiers;
Freehand restores their exact bytes only after every identifier survives once
and in order. This protects literals without relying on a model to copy whitespace. Settings
can disable cleanup, and history offers **Copy original** when cleanup changed
the text. History persistence still follows the existing preference.

The application never sends dictated text to a remote inference service. It starts an
owned, authenticated loopback worker using the verified local model and runtime, then unloads the idle worker.

## Bundled cleanup

The normal Windows installer includes the speech model and the prepared cleanup
bundle under `models/cleanup`, so cleanup runs on first launch. The worker
verifies the bundle's sizes and SHA-256 hashes before loading it. Ordinary
dictation continues if cleanup assets are missing or damaged. Changing or
disabling cleanup applies through the existing idle preference coordinator.

Installations that ran **Set up cleanup** in an older version keep using that
profile copy until you choose **Use bundled cleanup**. **Set up cleanup** appears
only in builds that ship acquisition metadata, such as the `dev.ps1` preview.
It downloads into the Freehand data profile with progress, cancellation and
retry, and verifies the exact sizes and SHA-256 hashes before making the bundle
active.

**Copy original** retrieves the dictionary-corrected, number-formatted transcript
from before cleanup. With history enabled, it is available beside a saved result
when the two texts differ. With history disabled, the main window offers the
latest result and its original from memory, without saving either version.

## Prepare a development bundle

`dev.ps1` validates and copies setup metadata into the Debug output after a
successful build. You can use **Set up cleanup** in the isolated preview without
automatically downloading weights during the build. An existing selected folder
and an explicit `-CleanupSource` remain selected. The following command is an
alternative for preparing assets before launching the preview.

`get-cleanup-assets.ps1` prepares the selected manifest, including its adapter,
or another manifest passed with `-ManifestPath`. Run from the repository root:

```powershell
pwsh -File ./scripts/get-cleanup-assets.ps1
pwsh -File ./scripts/dev.ps1
```

The first command downloads the selected Windows CPU model, adapter, native
runtime and license texts. It verifies their exact sizes and SHA-256 values, verifies the
runtime executable inside its authenticated archive, and prepares
`artifacts/cleanup-assets`. This can require a multi-gigabyte download and enough
disk for both the download cache and the prepared bundle. The existing bundle
is replaced only after the new bundle verifies. An unrelated output directory
is preserved and rejected.

Downloaded files are cached by their content hashes in
`artifacts/cleanup-downloads`. Later runs verify those cached files rather than
downloading them again. Add `-Offline` to require a complete local cache. A
corrupted cache entry is reported instead of being reused. Its path is named by
the expected hash; remove only that failed cache entry before retrying the
download.

## Package the cleanup bundle

`verify.ps1 -Package` and `build-release.ps1` run `get-cleanup-assets.ps1` for the
selected manifest and embed the prepared bundle under `models/cleanup`. The
download cache makes repeat builds offline.

`-CleanupSource` on `build-release.ps1` selects an already prepared custom Windows
bundle to embed instead. The final installer must remain strictly below 2 GiB to
fit GitHub Releases and the existing updater; oversized bundles fail packaging.

For an explicit baseline package without bundled cleanup assets, run:

```powershell
pwsh -File ./scripts/verify.ps1 -Package -SkipCleanup
```

This prepares a package, not an installed update. Normal installation and public
publication remain separate actions described in [DEVELOPMENT.md](DEVELOPMENT.md).

## Alternate local assets and cloud verification

`prepare-cleanup.ps1` also accepts explicit local runtime, model and license
paths. It copies only the selected executable, its native libraries, allowed
runtime notices, the model and supplied model notices. It creates an inventory
covering every copied file. To validate a prepared bundle without launching it:

```powershell
pwsh -File ./scripts/prepare-cleanup.ps1 -ValidateDirectory artifacts/cleanup-assets
```

For Linux CPU experiments, `get-cleanup-assets.ps1 -Platform linux-x64-cpu`
prepares `artifacts/cleanup-assets-linux`. This uses the same selected model with
the pinned Linux runtime; it does not establish Windows performance or physical
dictation behavior. Windows development launch and packaging reject a Linux bundle.

`-LinkModel` on acquisition or preparation creates a hard link instead of a
second weight-file copy. The cache and bundle must reside on the same filesystem.
Treat both paths as immutable: changing either linked file changes the other,
and subsequent checksum verification will reject the alteration. This option is
useful for cloud experiments with limited disk. It is not required for normal
Windows packaging.

## Selected-model acquisition manifest

The selected manifest uses schema version 1 with these fields:

- `ModelId` and `PromptStyle`: the provider identifier and its trained input
  contract (`QuillChatMl`, `Qwen35`, `Ministral3` or `Gemma4`).
- `Model`: `Source`, immutable 40-character Git `Revision`, `Sha256` and exact
  byte `Size`. Hugging Face download URLs must resolve that exact revision.
- `ModelLicense` and `RuntimeLicense`: `Source`, `Sha256` and byte `Size` for the
  primary license texts.
- `ModelNotices`: optional additional license/model-card records with `Name`,
  `Source`, `Sha256` and byte `Size`. Names must be distinct `.txt` or `.md`
  basenames. These preserve applicable base-model licenses and publisher notices.
- `Inference`: integer `Threads`, `ContextSize`, `MaxOutputTokens`, `GpuLayers`,
  `StartupTimeoutSeconds` and `IdleTimeoutSeconds` values frozen for the selected
  model configuration.

Sources must be HTTPS URLs without credentials, query strings or fragments.
The developer acquisition script accepts no model-account tokens and writes no
request credentials into the bundle. The prepared runtime manifest records
artifact provenance and the inference settings, with relative file paths suitable for packaged startup.

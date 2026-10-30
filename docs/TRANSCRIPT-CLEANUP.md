# Local transcript cleanup

Freehand can run a final local edit after dictionary correction and English number
formatting. The complete result is checked before the existing single insertion.
Failed or incomplete cleanup keeps the original normalized transcript. Dictionary
replacement blocks are hidden from general models behind opaque identifiers;
Freehand restores their exact bytes only after every identifier survives once
and in order. This protects literals without relying on a model to copy whitespace. Settings
can disable cleanup, and history offers **Copy original** when cleanup changed
the text. History persistence still follows the existing preference.

Cleanup setup downloads assets only after an explicit Settings action. The
application never sends dictated text to a remote inference service. It starts an
owned, authenticated loopback worker using the verified local model and runtime, then unloads the idle worker.

## Set up cleanup in the application

The normal Windows installer includes the speech model and the pinned cleanup
acquisition metadata. Cleanup weights and their native runtime are acquired
separately, after you choose **Set up cleanup** in Settings. The app displays
byte progress while downloading and verifies the exact sizes and SHA-256 hashes
before making a prepared bundle active. Downloads contain model/runtime assets
and license texts; they do not send your dictation text to an inference service.

Setup writes into the Freehand data profile rather than the application install
folder. **Cancel setup** stops an active acquisition; a failed or cancelled setup
keeps any previous verified bundle and offers **Retry setup**. Ordinary dictation
continues while cleanup assets are absent. After setup, inference uses only the
local bundle. Changing or disabling cleanup applies through the existing idle
preference coordinator.

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

The selected default is Qwen3.5 9B, Unsloth Q8_0, pinned in
`packaging/cleanup-model-manifest.json`. Its weight file is 9,527,502,048 bytes;
file size is not a RAM measurement. The first implementation prioritizes fidelity
over the historical memory/delay gates. See the [actual model evaluation](TRANSCRIPT-CLEANUP-EVALUATION.md). The
llama.cpp release and complete archive digest are pinned separately in
`packaging/cleanup-runtime-manifest.json`. To acquire assets explicitly for an
isolated development preview, run from the repository root:

```powershell
pwsh -File ./scripts/get-cleanup-assets.ps1
pwsh -File ./scripts/dev.ps1
```

The first command downloads the selected Windows CPU model, native runtime and
license texts. It verifies their exact sizes and SHA-256 values, verifies the
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

## Package setup metadata

`verify.ps1 -Package` and `build-release.ps1` package the validated acquisition
manifests under `models/cleanup-provisioning`. They do not download or embed the
cleanup weights, even when a development bundle exists in the local cache. This
keeps the ordinary CI workspace and installer independent of the cleanup weight
size. The installed application uses those pinned manifests for explicit Settings
setup.

`-CleanupSource` on `build-release.ps1` selects an already prepared custom Windows
bundle to embed instead. The final installer must remain strictly below 2 GiB to
fit GitHub Releases and the existing updater; oversized bundles fail packaging.
Use Settings setup or the isolated development bundle for larger models.

For an explicit baseline package without either cleanup setup metadata or bundled
cleanup assets, run:

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

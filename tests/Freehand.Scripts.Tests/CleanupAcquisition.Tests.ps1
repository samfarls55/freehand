Describe 'Pinned default cleanup acquisition' {
    BeforeAll {
        $script:acquisitionRepository = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        $script:acquisitionFixture = if ($env:FREEHAND_SCRIPT_TEST_ROOT) { $env:FREEHAND_SCRIPT_TEST_ROOT } else { Join-Path $TestDrive 'acquisition-repository' }
        $script:acquisitionScripts = Join-Path $acquisitionFixture 'scripts'
        New-Item -ItemType Directory -Path $acquisitionScripts -Force | Out-Null
        Copy-Item -Path (Join-Path $acquisitionRepository 'scripts/*.ps1') -Destination $acquisitionScripts

        function New-AcquisitionPin([string]$Path, [string]$Source) {
            return @{
                Source = $Source
                Sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
                Size = (Get-Item -LiteralPath $Path).Length
            }
        }
    }

    BeforeEach {
        $script:acquisitionRoot = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $script:acquisitionSources = Join-Path $acquisitionRoot 'sources'
        $script:acquisitionNative = Join-Path $acquisitionSources 'native'
        New-Item -ItemType Directory -Path $acquisitionNative -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $acquisitionNative 'llama-server.exe') -Value 'fixture executable, never launched'
        Set-Content -LiteralPath (Join-Path $acquisitionNative 'llama.dll') -Value 'fixture native dependency'
        Set-Content -LiteralPath (Join-Path $acquisitionNative 'LICENSE-LLVM-OpenMP.txt') -Value 'fixture archive notice'
        $script:acquisitionZip = Join-Path $acquisitionSources 'runtime.zip'
        Compress-Archive -Path $acquisitionNative -DestinationPath $acquisitionZip
        Set-Content -LiteralPath (Join-Path $acquisitionSources 'model.gguf') -Value 'fixture model, never used for inference'
        Set-Content -LiteralPath (Join-Path $acquisitionSources 'model-license.txt') -Value 'fixture model license'
        Set-Content -LiteralPath (Join-Path $acquisitionSources 'runtime-license.txt') -Value 'fixture runtime license'
        Set-Content -LiteralPath (Join-Path $acquisitionSources 'base-license.txt') -Value 'fixture base model license'
        $script:acquisitionModel = New-AcquisitionPin (Join-Path $acquisitionSources 'model.gguf') ('https://huggingface.co/fixture/model/resolve/' + ('a' * 40) + '/model.gguf')
        $acquisitionModel.Revision = 'a' * 40
        $script:acquisitionModelLicense = New-AcquisitionPin (Join-Path $acquisitionSources 'model-license.txt') 'https://example.test/model-license.txt'
        $script:acquisitionRuntimeLicense = New-AcquisitionPin (Join-Path $acquisitionSources 'runtime-license.txt') 'https://example.test/runtime-license.txt'
        $script:acquisitionBaseLicense = New-AcquisitionPin (Join-Path $acquisitionSources 'base-license.txt') 'https://example.test/base-license.txt'
        $acquisitionBaseLicense.Name = 'BASE-LICENSE.txt'
        $script:acquisitionArchive = New-AcquisitionPin $acquisitionZip 'https://example.test/pinned/runtime.zip'
        $script:acquisitionSelected = @{
            SchemaVersion = 1; ModelId = 'fixture-editor'; PromptStyle = 'QuillChatMl'; Model = $acquisitionModel
            ModelLicense = $acquisitionModelLicense; ModelNotices = @($acquisitionBaseLicense); RuntimeLicense = $acquisitionRuntimeLicense
            Inference = @{ Threads = 4; ContextSize = 8192; MaxOutputTokens = 2048; GpuLayers = 0; StartupTimeoutSeconds = 60; IdleTimeoutSeconds = 60 }
        }
        $script:acquisitionRuntime = @{
            SchemaVersion = 1; SourceCommit = 'b' * 40
            Artifacts = @(@{
                Platform = 'win-x64-cpu'; Source = $acquisitionArchive.Source; ArchiveSha256 = $acquisitionArchive.Sha256
                ArchiveSize = $acquisitionArchive.Size; Executable = 'llama-server.exe'
                ExecutableSha256 = (Get-FileHash -LiteralPath (Join-Path $acquisitionNative 'llama-server.exe')).Hash
            })
        }
        $script:acquisitionOptions = @{
            ManifestPath = Join-Path $acquisitionRoot 'model-manifest.json'
            RuntimeManifestPath = Join-Path $acquisitionRoot 'runtime-manifest.json'
            CacheDirectory = Join-Path $acquisitionRoot 'cache'
            OutputDirectory = Join-Path $acquisitionRoot 'prepared'
        }
        $acquisitionSelected | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $acquisitionOptions.ManifestPath
        $acquisitionRuntime | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $acquisitionOptions.RuntimeManifestPath
        $script:acquisitionDownloads = @{
            $acquisitionModel.Source = Join-Path $acquisitionSources 'model.gguf'
            $acquisitionModelLicense.Source = Join-Path $acquisitionSources 'model-license.txt'
            $acquisitionRuntimeLicense.Source = Join-Path $acquisitionSources 'runtime-license.txt'
            $acquisitionBaseLicense.Source = Join-Path $acquisitionSources 'base-license.txt'
            $acquisitionArchive.Source = $acquisitionZip
        }
        Mock Invoke-WebRequest {
            if (-not $acquisitionDownloads.ContainsKey([string]$Uri)) { throw 'Unexpected fixture download.' }
            Copy-Item -LiteralPath $acquisitionDownloads[[string]$Uri] -Destination $OutFile
        }
    }

    It 'downloads the pinned bundle with primary and base licenses, then supports offline cache reuse' {
        $bundle = & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions
        $bundle.ModelId | Should-Be 'fixture-editor'
        $manifest = Get-Content -LiteralPath $bundle.ManifestPath -Raw | ConvertFrom-Json
        $manifest.modelRevision | Should-Be ('a' * 40)
        $manifest.runtimeRevision | Should-Be ('b' * 40)
        $manifest.platform | Should-Be 'win-x64-cpu'
        (Get-Content -LiteralPath (Join-Path $bundle.Directory 'licenses/model/BASE-LICENSE.txt')) | Should-Be 'fixture base model license'
        @($manifest.files | Where-Object { $_.path -eq 'runtime/llama.dll' }).Count | Should-Be 1
        Should-Invoke Invoke-WebRequest -Exactly -Times 5
        $offline = & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions -Offline
        $offline.ModelId | Should-Be 'fixture-editor'
        Should-Invoke Invoke-WebRequest -Exactly -Times 5
    }

    It 'validates selected metadata without downloads, cache directories or bundled weights' {
        $selected = & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions -ValidateManifestOnly
        $selected.ModelId | Should-Be 'fixture-editor'
        $selected.ModelManifestPath | Should-Be $acquisitionOptions.ManifestPath
        $selected.RuntimeManifestPath | Should-Be $acquisitionOptions.RuntimeManifestPath
        (Test-Path -LiteralPath $acquisitionOptions.CacheDirectory) | Should-BeFalse
        (Test-Path -LiteralPath $acquisitionOptions.OutputDirectory) | Should-BeFalse
        Should-NotInvoke Invoke-WebRequest
    }

    It 'rejects a corrupted cached model and preserves the previously prepared bundle' {
        $bundle = & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions
        $previous = Get-Content -LiteralPath $bundle.ManifestPath -Raw
        Set-Content -LiteralPath (Join-Path $acquisitionOptions.CacheDirectory ($acquisitionModel.Sha256 + '.gguf')) -Value 'corrupt cached model'
        { & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions -Offline } | Should-Throw '*verification failed*'
        Get-Content -LiteralPath $bundle.ManifestPath -Raw | Should-Be $previous
        $null = & (Join-Path $acquisitionScripts 'prepare-cleanup.ps1') -ValidateDirectory $bundle.Directory
    }

    It 'rejects a mismatched download without publishing the partial cache file or a bundle' {
        $acquisitionSelected.Model.Sha256 = '0' * 64
        $acquisitionSelected | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $acquisitionOptions.ManifestPath
        { & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions } | Should-Throw '*verification failed*'
        @(Get-ChildItem -LiteralPath $acquisitionOptions.CacheDirectory -File).Count | Should-Be 0
        (Test-Path -LiteralPath $acquisitionOptions.OutputDirectory) | Should-BeFalse
    }

    It 'fails offline before sending a request when a pinned artifact is missing' {
        { & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions -Offline } | Should-Throw '*missing from the offline cache*'
        Should-NotInvoke Invoke-WebRequest
        (Test-Path -LiteralPath $acquisitionOptions.OutputDirectory) | Should-BeFalse
    }

    It 'rejects unsafe model metadata before downloading <Problem>' -ForEach @(
        @{ Problem = 'a moving revision'; Field = 'Revision'; Value = 'main' },
        @{ Problem = 'a token in a URL'; Field = 'Source'; Value = 'https://example.test/model.gguf?token=private' },
        @{ Problem = 'a plain HTTP URL'; Field = 'Source'; Value = 'http://example.test/model.gguf' },
        @{ Problem = 'a negative size'; Field = 'Size'; Value = -1 }
    ) {
        $acquisitionSelected.Model[$Field] = $Value
        $acquisitionSelected | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $acquisitionOptions.ManifestPath
        { & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions } | Should-Throw
        Should-NotInvoke Invoke-WebRequest
        (Test-Path -LiteralPath $acquisitionOptions.CacheDirectory) | Should-BeFalse
    }

    It 'rejects base-license path traversal before downloading' {
        $acquisitionSelected.ModelNotices[0].Name = '../outside.txt'
        $acquisitionSelected | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $acquisitionOptions.ManifestPath
        { & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions } | Should-Throw '*notice names*'
        Should-NotInvoke Invoke-WebRequest
    }

    It 'checks the selected native executable independently of its archive checksum' {
        $acquisitionRuntime.Artifacts[0].ExecutableSha256 = '0' * 64
        $acquisitionRuntime | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $acquisitionOptions.RuntimeManifestPath
        { & (Join-Path $acquisitionScripts 'get-cleanup-assets.ps1') @acquisitionOptions } | Should-Throw '*runtime executable*'
        (Test-Path -LiteralPath $acquisitionOptions.OutputDirectory) | Should-BeFalse
        @(Get-ChildItem -LiteralPath $acquisitionOptions.CacheDirectory -Directory -Filter '.cleanup-extract-*').Count | Should-Be 0
    }
}

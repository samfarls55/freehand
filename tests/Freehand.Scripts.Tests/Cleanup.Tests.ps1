Describe 'Cleanup asset preparation and packaging' {
    BeforeAll {
        $script:cleanupRepositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        $script:cleanupFixtureRoot = if ($env:FREEHAND_SCRIPT_TEST_ROOT) { $env:FREEHAND_SCRIPT_TEST_ROOT } else { Join-Path $TestDrive 'cleanup-repository' }
        $script:cleanupScripts = Join-Path $cleanupFixtureRoot 'scripts'
        New-Item -ItemType Directory -Path $cleanupScripts -Force | Out-Null
        Copy-Item -Path (Join-Path $cleanupRepositoryRoot 'scripts/*.ps1') -Destination $cleanupScripts
        $script:cleanupOriginalLocation = (Get-Location).Path
        $script:cleanupOriginalReleaseVersion = $env:FREEHAND_RELEASE_VERSION

        function Write-CleanupMetadataFixture {
            @{
                SchemaVersion = 1; ModelId = 'fixture-selected-editor'; PromptStyle = 'Qwen35'
                Model = @{ Source = 'https://example.test/pinned/model.gguf'; Revision = 'a' * 40; Sha256 = '1' * 64; Size = [long]9000000000 }
                ModelLicense = @{ Source = 'https://example.test/model-license.txt'; Sha256 = '2' * 64; Size = 500 }
                RuntimeLicense = @{ Source = 'https://example.test/runtime-license.txt'; Sha256 = '3' * 64; Size = 500 }
                Inference = @{ Threads = 4; ContextSize = 8192; MaxOutputTokens = 2048; GpuLayers = 0; StartupTimeoutSeconds = 60; IdleTimeoutSeconds = 60 }
            } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'packaging/cleanup-model-manifest.json')
            @{
                SchemaVersion = 1; SourceCommit = 'b' * 40
                Artifacts = @(@{ Platform = 'win-x64-cpu'; Source = 'https://example.test/pinned/runtime.zip'
                    ArchiveSha256 = '4' * 64; ArchiveSize = 1000; Executable = 'llama-server.exe'; ExecutableSha256 = '5' * 64 })
            } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'packaging/cleanup-runtime-manifest.json')
        }
    }

    BeforeEach {
        Set-Location -LiteralPath $cleanupFixtureRoot
        $env:FREEHAND_RELEASE_VERSION = $null
        $script:cleanupInputs = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
        $script:cleanupRuntime = Join-Path $cleanupInputs 'runtime'
        New-Item -ItemType Directory -Path $cleanupRuntime -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $cleanupRuntime 'llama-server.exe') -Value 'fixture runtime'
        Set-Content -LiteralPath (Join-Path $cleanupRuntime 'llama.dll') -Value 'fixture runtime dependency'
        Set-Content -LiteralPath (Join-Path $cleanupRuntime 'LICENSE-LLVM-OpenMP') -Value 'fixture runtime notice'
        Set-Content -LiteralPath (Join-Path $cleanupRuntime 'credentials.env') -Value 'must not be copied'
        Set-Content -LiteralPath (Join-Path $cleanupRuntime 'LICENSE-private.key') -Value 'must not be copied'
        Set-Content -LiteralPath (Join-Path $cleanupRuntime 'unrelated.exe') -Value 'must not be copied'
        $script:cleanupModel = Join-Path $cleanupInputs 'fixture.gguf'
        $script:cleanupModelLicense = Join-Path $cleanupInputs 'model-license.txt'
        $script:cleanupRuntimeLicense = Join-Path $cleanupInputs 'runtime-license.txt'
        Set-Content -LiteralPath $cleanupModel -Value 'fixture GGUF bytes; never used for inference'
        Set-Content -LiteralPath $cleanupModelLicense -Value 'fixture model license'
        Set-Content -LiteralPath $cleanupRuntimeLicense -Value 'fixture runtime license'
        $script:cleanupDestination = Join-Path $cleanupInputs 'prepared assets'
        $script:cleanupPrepare = @{
            RuntimeDirectory = $cleanupRuntime; ModelPath = $cleanupModel; ModelId = 'fixture-model'
            PromptStyle = 'QuillChatMl'; ModelLicense = $cleanupModelLicense; RuntimeLicense = $cleanupRuntimeLicense
            OutputDirectory = $cleanupDestination; RuntimeRevision = 'fixture-runtime-revision'; ModelRevision = 'fixture-model-revision'
        }
    }

    AfterEach {
        Set-Location -LiteralPath $cleanupOriginalLocation
        $env:FREEHAND_RELEASE_VERSION = $cleanupOriginalReleaseVersion
    }

    It 'prepares only runtime dependencies, one model and license files with verifiable hashes' {
        $bundle = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
        $bundle.Directory | Should-Be $cleanupDestination
        $bundle.ModelId | Should-Be 'fixture-model'
        $manifest = Get-Content -LiteralPath $bundle.ManifestPath -Raw | ConvertFrom-Json
        $manifest.runtimePath | Should-Be 'runtime/llama-server.exe'
        $manifest.modelPath | Should-Be 'model.gguf'
        $manifest.promptStyle | Should-Be 'QuillChatMl'
        $manifest.runtimeRevision | Should-Be 'fixture-runtime-revision'
        $manifest.modelRevision | Should-Be 'fixture-model-revision'
        (Test-Path -LiteralPath (Join-Path $cleanupDestination 'runtime/credentials.env')) | Should-BeFalse
        (Test-Path -LiteralPath (Join-Path $cleanupDestination 'runtime/unrelated.exe')) | Should-BeFalse
        (Test-Path -LiteralPath (Join-Path $cleanupDestination 'licenses/runtime/LICENSE-private.key')) | Should-BeFalse
        $verified = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') -ValidateDirectory $cleanupDestination
        $verified.Files.Count | Should-Be 6
        foreach ($asset in $verified.Files) {
            (Get-FileHash -LiteralPath (Join-Path $cleanupDestination $asset.path)).Hash.ToLowerInvariant() | Should-Be $asset.sha256
        }
    }

    It 'preserves extra model notices and supports a self-contained Linux runtime bundle' {
        Set-Content -LiteralPath (Join-Path $cleanupRuntime 'llama-server') -Value 'fixture Linux runtime'
        Set-Content -LiteralPath (Join-Path $cleanupRuntime 'libllama.so.0') -Value 'fixture Linux shared library'
        $notice = Join-Path $cleanupInputs 'BASE-LICENSE.txt'
        Set-Content -LiteralPath $notice -Value 'fixture base model license'
        $cleanupPrepare.Platform = 'linux-x64-cpu'
        $cleanupPrepare.ModelNotices = @($notice)
        $bundle = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
        $manifest = Get-Content -LiteralPath $bundle.ManifestPath -Raw | ConvertFrom-Json
        $manifest.runtimePath | Should-Be 'runtime/llama-server'
        $manifest.platform | Should-Be 'linux-x64-cpu'
        @($manifest.files | Where-Object { $_.path -eq 'runtime/libllama.so.0' }).Count | Should-Be 1
        Get-Content -LiteralPath (Join-Path $bundle.Directory 'licenses/model/BASE-LICENSE.txt') | Should-Be 'fixture base model license'
        $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') -ValidateDirectory $bundle.Directory
    }

    It 'can prepare the model as a hard link without a second weight-file allocation' {
        $bundle = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare -LinkModel
        Set-Content -LiteralPath $cleanupModel -Value 'changed source proves shared storage'
        Get-Content -LiteralPath (Join-Path $bundle.Directory 'model.gguf') | Should-Be 'changed source proves shared storage'
        { & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') -ValidateDirectory $bundle.Directory } | Should-Throw '*verification failed*'
    }

    It 'rejects a changed <Asset> before packaging' -ForEach @(
        @{ Asset = 'model.gguf' }, @{ Asset = 'runtime/llama-server.exe' }, @{ Asset = 'runtime/llama.dll' }
    ) {
        $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
        Set-Content -LiteralPath (Join-Path $cleanupDestination $Asset) -Value 'damaged asset'
        { & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') -ValidateDirectory $cleanupDestination } |
            Should-Throw '*Cleanup asset verification failed*'
    }

    It 'rejects path traversal and mismatched primary hashes in a manifest' {
        $bundle = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
        $manifest = Get-Content -LiteralPath $bundle.ManifestPath -Raw | ConvertFrom-Json
        $manifest.runtimeSha256 = '0' * 64
        $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $bundle.ManifestPath
        { & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') -ValidateDirectory $cleanupDestination } |
            Should-Throw '*primary hashes disagree*'
        $manifest.files[0].path = '../outside.txt'
        $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $bundle.ManifestPath
        { & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') -ValidateDirectory $cleanupDestination } |
            Should-Throw '*unsafe asset path*'
    }

    It 'requires nonempty license inputs and keeps download credentials out of metadata' {
        Set-Content -LiteralPath $cleanupModelLicense -Value '' -NoNewline
        { & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare } | Should-Throw '*License inputs*'
        Set-Content -LiteralPath $cleanupModelLicense -Value 'fixture model license'
        $cleanupPrepare.ModelSourceUrl = 'https://example.test/model.gguf?token=private'
        { & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare } | Should-Throw '*without credentials*'
        (Test-Path -LiteralPath $cleanupDestination) | Should-BeFalse
    }

    It 'does not replace a directory containing unrelated files' {
        New-Item -ItemType Directory -Path $cleanupDestination | Out-Null
        Set-Content -LiteralPath (Join-Path $cleanupDestination 'notes.txt') -Value 'preserve me'
        { & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare } | Should-Throw '*manifest is missing*'
        Get-Content -LiteralPath (Join-Path $cleanupDestination 'notes.txt') | Should-Be 'preserve me'
    }

    It 'replaces an earlier prepared bundle only after the new bundle is verified' {
        $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
        $cleanupPrepare.ModelId = 'new-fixture-model'
        $bundle = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
        $bundle.ModelId | Should-Be 'new-fixture-model'
        $before = Get-Content -LiteralPath $bundle.ManifestPath -Raw
        Set-Content -LiteralPath (Join-Path $cleanupDestination 'notes.txt') -Value 'preserve me'
        { & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare } | Should-Throw '*outside its cleanup manifest*'
        Get-Content -LiteralPath $bundle.ManifestPath -Raw | Should-Be $before
    }

    Context 'Release and development entry points' {
        BeforeEach {
            $selectedCleanupFixture = Join-Path $cleanupFixtureRoot 'packaging/cleanup-model-manifest.json'
            if (Test-Path -LiteralPath $selectedCleanupFixture) { Remove-Item -LiteralPath $selectedCleanupFixture }
            $debugCleanupMetadata = Join-Path $cleanupFixtureRoot 'src/Freehand.App/bin/Debug/net10.0/models/cleanup-provisioning'
            if (Test-Path -LiteralPath $debugCleanupMetadata) { Remove-Item -LiteralPath $debugCleanupMetadata -Recurse -Force }
            $cachedCleanup = Join-Path $cleanupFixtureRoot 'artifacts/cleanup-assets'
            if (Test-Path -LiteralPath $cachedCleanup) { Remove-Item -LiteralPath $cachedCleanup -Recurse -Force }
            $script:cleanupSdk = Join-Path $cleanupFixtureRoot 'sdk/dotnet.ps1'
            New-Item -ItemType Directory -Path (Split-Path -Parent $cleanupSdk), (Join-Path $cleanupFixtureRoot 'packaging'),
                (Join-Path $cleanupFixtureRoot 'src/Freehand.App/obj'), (Join-Path $cleanupFixtureRoot 'artifacts/model-cache') -Force | Out-Null
            @'
$CliArguments = $args
$global:LASTEXITCODE = 0
if ($CliArguments[0] -eq '--version') { '10.0.100'; return }
if ($CliArguments[0] -eq 'publish') {
    $output = $CliArguments[[array]::IndexOf($CliArguments, '--output') + 1]
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $output 'Freehand.App.exe') -Value 'fixture app'
    Set-Content -LiteralPath (Join-Path $output 'Freehand.Installer.exe') -Value 'fixture installer'
}
'@ | Set-Content -LiteralPath $cleanupSdk
            Set-Content -LiteralPath (Join-Path (Split-Path -Parent $cleanupSdk) 'LICENSE.txt') -Value 'fixture sdk license'
            Set-Content -LiteralPath (Join-Path (Split-Path -Parent $cleanupSdk) 'ThirdPartyNotices.txt') -Value 'fixture sdk notices'
            Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'Version.props') -Value '<Project><PropertyGroup><Version>1.2.3</Version></PropertyGroup></Project>'
            $script:cleanupSpeech = Join-Path $cleanupInputs 'speech'
            New-Item -ItemType Directory -Path $cleanupSpeech -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $cleanupSpeech 'tokens.txt') -Value 'fixture speech model'
            @{ DirectoryName = 'parakeet-110m'; Files = @(@{ Name = 'tokens.txt'; Size = (Get-Item (Join-Path $cleanupSpeech 'tokens.txt')).Length;
                Sha256 = (Get-FileHash (Join-Path $cleanupSpeech 'tokens.txt')).Hash }) } | ConvertTo-Json -Depth 4 |
                Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'packaging/model-manifest.json')
            @{ libraries = @{}; packageFolders = @{ (Split-Path -Parent $cleanupSdk) = @{} } } | ConvertTo-Json -Depth 4 |
                Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'src/Freehand.App/obj/project.assets.json')
            Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'packaging/THIRD-PARTY-NOTICES.txt') -Value 'fixture notices'
            Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'artifacts/model-cache/jfk.wav') -Value 'fixture audio'
            Mock Get-Process { }
            Mock git { $global:LASTEXITCODE = 0; if ($args[0] -eq 'rev-parse') { 'abc1234' } }
            Mock Invoke-WebRequest { throw 'Fixture packaging must not download assets.' }
            Mock Get-FileHash { [pscustomobject]@{ Hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([IO.File]::ReadAllBytes($LiteralPath))) } }
            Mock Get-FileHash { [pscustomobject]@{ Hash = '59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e' } } -ParameterFilter { $LiteralPath -like '*jfk.wav' }
        }

        It 'bundles explicitly supplied cleanup assets before generating the package manifest' {
            $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
            & (Join-Path $cleanupScripts 'build-release.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -CleanupSource $cleanupDestination
            $publish = Join-Path $cleanupFixtureRoot 'artifacts/publish'
            $manifest = Get-Content -LiteralPath (Join-Path $publish 'package-manifest.json') -Raw | ConvertFrom-Json
            @($manifest.Files | Where-Object { $_.Path.Replace('\', '/') -eq 'models/cleanup/cleanup-manifest.json' }).Count | Should-Be 1
            @($manifest.Files | Where-Object { $_.Path.Replace('\', '/') -eq 'models/cleanup/runtime/llama.dll' }).Count | Should-Be 1
            $verified = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') -ValidateDirectory (Join-Path $publish 'models/cleanup')
            $verified.ModelId | Should-Be 'fixture-model'
            Should-NotInvoke Invoke-WebRequest
        }

        It 'packages only pinned setup metadata even when a large-model bundle exists in the local cache' {
            Write-CleanupMetadataFixture
            $cleanupPrepare.OutputDirectory = Join-Path $cleanupFixtureRoot 'artifacts/cleanup-assets'
            $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
            & (Join-Path $cleanupScripts 'build-release.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech
            $publish = Join-Path $cleanupFixtureRoot 'artifacts/publish'
            $package = Get-Content -LiteralPath (Join-Path $publish 'package-manifest.json') -Raw | ConvertFrom-Json
            @($package.Files | Where-Object { $_.Path.Replace('\', '/') -like 'models/cleanup-provisioning/*' }).Count | Should-Be 2
            (Test-Path -LiteralPath (Join-Path $publish 'models/cleanup/model.gguf')) | Should-BeFalse
            (Test-Path -LiteralPath (Join-Path $cleanupPrepare.OutputDirectory 'model.gguf')) | Should-BeTrue
            $selected = Get-Content -LiteralPath (Join-Path $publish 'models/cleanup-provisioning/cleanup-model-manifest.json') -Raw | ConvertFrom-Json
            $selected.Model.Size | Should-Be 9000000000
            $selected.ModelId | Should-Be 'fixture-selected-editor'
            Should-NotInvoke Invoke-WebRequest
        }

        It 'preserves baseline packaging when no cleanup bundle was prepared' {
            & (Join-Path $cleanupScripts 'build-release.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech
            (Test-Path -LiteralPath (Join-Path $cleanupFixtureRoot 'artifacts/publish/models/cleanup')) | Should-BeFalse
            Should-NotInvoke Invoke-WebRequest
        }

        It 'validates selected setup metadata before packaging' {
            Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'packaging/cleanup-model-manifest.json') -Value '{}'
            Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'packaging/cleanup-runtime-manifest.json') -Value '{}'
            { & (Join-Path $cleanupScripts 'build-release.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech } |
                Should-Throw '*immutable source revisions*'
            Should-NotInvoke Invoke-WebRequest
        }

        It 'allows an explicit baseline-only package without provisioning the selected default' {
            Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'packaging/cleanup-model-manifest.json') -Value '{}'
            & (Join-Path $cleanupScripts 'build-release.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -SkipCleanup
            (Test-Path -LiteralPath (Join-Path $cleanupFixtureRoot 'artifacts/publish/models/cleanup')) | Should-BeFalse
            (Test-Path -LiteralPath (Join-Path $cleanupFixtureRoot 'artifacts/publish/models/cleanup-provisioning')) | Should-BeFalse
            Should-NotInvoke Invoke-WebRequest
        }

        It 'rejects a Linux cleanup bundle in a Windows installer' {
            Set-Content -LiteralPath (Join-Path $cleanupRuntime 'llama-server') -Value 'fixture Linux runtime'
            $cleanupPrepare.Platform = 'linux-x64-cpu'
            $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
            { & (Join-Path $cleanupScripts 'build-release.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -CleanupSource $cleanupDestination } |
                Should-Throw '*Windows cleanup bundle*'
            Should-NotInvoke Invoke-WebRequest
        }

        It 'rejects an installer at the 2 GiB release limit before replacing an existing installer' {
            . (Join-Path $cleanupScripts 'common.ps1')
            $payload = Join-Path $cleanupInputs 'payload'
            New-Item -ItemType Directory -Path $payload -Force | Out-Null
            Set-Content -LiteralPath (Join-Path $payload 'small.txt') -Value 'small fixture payload'
            $destination = Join-Path $cleanupInputs 'Setup.exe'
            $zip = $destination + '.payload.zip'
            [IO.Compression.ZipFile]::CreateFromDirectory($payload, $zip, [IO.Compression.CompressionLevel]::Fastest, $false)
            $script:cleanupSimulatedRuntimeSize = 2GB - 48L - (Get-Item -LiteralPath $zip).Length
            Remove-Item -LiteralPath $zip
            Set-Content -LiteralPath $destination -Value 'preserve existing installer'
            $runtime = Join-Path $cleanupRuntime 'llama-server.exe'
            Mock Get-Item { [IO.FileInfo]::new([string]$LiteralPath) }
            Mock Get-Item { [pscustomobject]@{ Length = $cleanupSimulatedRuntimeSize } } -ParameterFilter { $LiteralPath -eq $runtime }
            { New-FreehandInstaller -PublishDirectory $payload -Runtime $runtime -Destination $destination } | Should-Throw '*smaller than 2 GiB*'
            Get-Content -LiteralPath $destination | Should-Be 'preserve existing installer'
            (Test-Path -LiteralPath $zip) | Should-BeFalse
        }

        It 'makes setup available in the isolated preview without downloading weights or replacing its selected folder' {
            Write-CleanupMetadataFixture
            $profile = Join-Path $cleanupFixtureRoot 'artifacts/dev-data'
            New-Item -ItemType Directory -Path $profile -Force | Out-Null
            $selectedFolder = Join-Path $cleanupInputs 'already-selected-cleanup'
            @{ KeepHistory = $false; CleanupDirectory = $selectedFolder } | ConvertTo-Json |
                Set-Content -LiteralPath (Join-Path $profile 'settings.json')
            & (Join-Path $cleanupScripts 'dev.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -BuildOnly
            $metadata = Join-Path $cleanupFixtureRoot 'src/Freehand.App/bin/Debug/net10.0/models/cleanup-provisioning'
            $selected = Get-Content -LiteralPath (Join-Path $metadata 'cleanup-model-manifest.json') -Raw | ConvertFrom-Json
            $selected.ModelId | Should-Be 'fixture-selected-editor'
            $selected.Model.Size | Should-Be 9000000000
            (Test-Path -LiteralPath (Join-Path $metadata 'cleanup-runtime-manifest.json')) | Should-BeTrue
            @(Get-ChildItem -LiteralPath $metadata -File).Count | Should-Be 2
            $settings = Get-Content -LiteralPath (Join-Path $profile 'settings.json') -Raw | ConvertFrom-Json
            $settings.CleanupDirectory | Should-Be $selectedFolder
            $settings.KeepHistory | Should-BeFalse
            Should-NotInvoke Invoke-WebRequest
        }

        It 'rejects invalid preview setup metadata without downloading weights' {
            Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'packaging/cleanup-model-manifest.json') -Value '{}'
            Set-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'packaging/cleanup-runtime-manifest.json') -Value '{}'
            { & (Join-Path $cleanupScripts 'dev.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -BuildOnly } |
                Should-Throw '*immutable source revisions*'
            (Test-Path -LiteralPath (Join-Path $cleanupFixtureRoot 'src/Freehand.App/bin/Debug/net10.0/models/cleanup-provisioning')) | Should-BeFalse
            Should-NotInvoke Invoke-WebRequest
        }

        It 'rejects a valid Linux <SourceMode> bundle before changing Windows development preferences' -ForEach @(
            @{ SourceMode = 'explicit' }, @{ SourceMode = 'cached' }
        ) {
            Set-Content -LiteralPath (Join-Path $cleanupRuntime 'llama-server') -Value 'fixture Linux launcher, never executed'
            $cleanupPrepare.Platform = 'linux-x64-cpu'
            if ($SourceMode -eq 'cached') { $cleanupPrepare.OutputDirectory = Join-Path $cleanupFixtureRoot 'artifacts/cleanup-assets' }
            $bundle = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
            $validated = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') -ValidateDirectory $bundle.Directory
            $manifest = Get-Content -LiteralPath $validated.ManifestPath -Raw | ConvertFrom-Json
            $manifest.runtimePath | Should-Be 'runtime/llama-server'
            (Get-FileHash -LiteralPath (Join-Path $bundle.Directory $manifest.runtimePath)).Hash.ToLowerInvariant() | Should-Be $manifest.runtimeSha256
            $profile = Join-Path $cleanupFixtureRoot 'artifacts/dev-data'
            New-Item -ItemType Directory -Path $profile -Force | Out-Null
            $settingsPath = Join-Path $profile 'settings.json'
            Set-Content -LiteralPath $settingsPath -Value '{ "KeepHistory": false, "StartAtLogin": true, "ModelDirectory": "preserve-existing-speech-folder" }'
            $original = Get-Content -LiteralPath $settingsPath -Raw
            if ($SourceMode -eq 'explicit') {
                { & (Join-Path $cleanupScripts 'dev.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -CleanupSource $bundle.Directory -BuildOnly } |
                    Should-Throw '*Windows cleanup bundle*'
            } else {
                { & (Join-Path $cleanupScripts 'dev.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -BuildOnly } |
                    Should-Throw '*Windows cleanup bundle*'
            }
            Get-Content -LiteralPath $settingsPath -Raw | Should-Be $original
            Should-NotInvoke Invoke-WebRequest
        }

        It 'points the isolated development profile at explicitly verified cleanup assets' {
            Write-CleanupMetadataFixture
            $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
            & (Join-Path $cleanupScripts 'dev.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -CleanupSource $cleanupDestination -BuildOnly
            $settings = Get-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'artifacts/dev-data/settings.json') -Raw | ConvertFrom-Json
            $settings.CleanupDirectory | Should-Be $cleanupDestination
            $settings.StartAtLogin | Should-BeFalse
            (Test-Path -LiteralPath (Join-Path $cleanupFixtureRoot 'src/Freehand.App/bin/Debug/net10.0/models/cleanup-provisioning/cleanup-model-manifest.json')) | Should-BeTrue
            Should-NotInvoke Invoke-WebRequest
        }
    }
}

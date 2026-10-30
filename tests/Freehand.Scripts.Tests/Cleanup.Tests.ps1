Describe 'Cleanup asset preparation and packaging' {
    BeforeAll {
        $script:cleanupRepositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
        $script:cleanupFixtureRoot = if ($env:FREEHAND_SCRIPT_TEST_ROOT) { $env:FREEHAND_SCRIPT_TEST_ROOT } else { Join-Path $TestDrive 'cleanup-repository' }
        $script:cleanupScripts = Join-Path $cleanupFixtureRoot 'scripts'
        New-Item -ItemType Directory -Path $cleanupScripts -Force | Out-Null
        Copy-Item -Path (Join-Path $cleanupRepositoryRoot 'scripts/*.ps1') -Destination $cleanupScripts
        $script:cleanupOriginalLocation = (Get-Location).Path
        $script:cleanupOriginalReleaseVersion = $env:FREEHAND_RELEASE_VERSION
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

        It 'bundles <SourceMode> cleanup assets before generating the package manifest' -ForEach @(
            @{ SourceMode = 'explicit' }, @{ SourceMode = 'cached' }
        ) {
            if ($SourceMode -eq 'cached') {
                $cleanupPrepare.OutputDirectory = Join-Path $cleanupFixtureRoot 'artifacts/cleanup-assets'
                $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
                & (Join-Path $cleanupScripts 'build-release.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech
            } else {
                $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
                & (Join-Path $cleanupScripts 'build-release.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -CleanupSource $cleanupDestination
            }
            $publish = Join-Path $cleanupFixtureRoot 'artifacts/publish'
            $manifest = Get-Content -LiteralPath (Join-Path $publish 'package-manifest.json') -Raw | ConvertFrom-Json
            @($manifest.Files | Where-Object { $_.Path.Replace('\', '/') -eq 'models/cleanup/cleanup-manifest.json' }).Count | Should-Be 1
            @($manifest.Files | Where-Object { $_.Path.Replace('\', '/') -eq 'models/cleanup/runtime/llama.dll' }).Count | Should-Be 1
            $verified = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') -ValidateDirectory (Join-Path $publish 'models/cleanup')
            $verified.ModelId | Should-Be 'fixture-model'
            Should-NotInvoke Invoke-WebRequest
        }

        It 'preserves baseline packaging when no cleanup bundle was prepared' {
            & (Join-Path $cleanupScripts 'build-release.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech
            (Test-Path -LiteralPath (Join-Path $cleanupFixtureRoot 'artifacts/publish/models/cleanup')) | Should-BeFalse
            Should-NotInvoke Invoke-WebRequest
        }

        It 'points the isolated development profile at explicitly verified cleanup assets' {
            $null = & (Join-Path $cleanupScripts 'prepare-cleanup.ps1') @cleanupPrepare
            & (Join-Path $cleanupScripts 'dev.ps1') -Dotnet $cleanupSdk -ModelSource $cleanupSpeech -CleanupSource $cleanupDestination -BuildOnly
            $settings = Get-Content -LiteralPath (Join-Path $cleanupFixtureRoot 'artifacts/dev-data/settings.json') -Raw | ConvertFrom-Json
            $settings.CleanupDirectory | Should-Be $cleanupDestination
            $settings.StartAtLogin | Should-BeFalse
        }
    }
}

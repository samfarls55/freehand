Describe 'Deployment scripts' {
BeforeAll {
    $script:fixtureRoot = $env:FREEHAND_SCRIPT_TEST_ROOT
    $script:scripts = Join-Path $fixtureRoot 'scripts'
    $script:originalLocation = (Get-Location).Path
    $script:originalLocalData = $env:LOCALAPPDATA
    $script:originalProfile = $env:FREEHAND_DATA_DIRECTORY
    $script:sdk = Join-Path $fixtureRoot 'sdk/dotnet.ps1'
    New-Item -ItemType Directory -Path (Split-Path -Parent $sdk) -Force | Out-Null
    @'
$CliArguments = $args
$global:LASTEXITCODE = 0
if ($CliArguments[0] -eq '--version') { '10.0.100'; return }
if ($env:FREEHAND_TEST_FAIL_COMMAND -eq $CliArguments[0]) { $global:LASTEXITCODE = 1; return }
if ($CliArguments[0] -eq 'publish') {
    $output = $CliArguments[[array]::IndexOf($CliArguments, '--output') + 1]
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $output 'Freehand.App.exe') -Value 'fixture app'
    Set-Content -LiteralPath (Join-Path $output 'Freehand.Installer.exe') -Value 'fixture installer'
}
'@ | Set-Content -LiteralPath $sdk
    Set-Content -LiteralPath (Join-Path (Split-Path -Parent $sdk) 'LICENSE.txt') -Value 'fixture license'
    Set-Content -LiteralPath (Join-Path (Split-Path -Parent $sdk) 'ThirdPartyNotices.txt') -Value 'fixture notices'
    . (Join-Path $scripts 'common.ps1')
}

BeforeEach {
    Set-Location -LiteralPath $fixtureRoot
    $env:LOCALAPPDATA = Join-Path $TestDrive ([guid]::NewGuid().ToString('N'))
    $env:FREEHAND_DATA_DIRECTORY = 'previous-profile'
    $env:FREEHAND_TEST_FAIL_COMMAND = $null
    $env:FREEHAND_TEST_SETUP_EXIT = '0'
    $env:FREEHAND_TEST_RUNNING_PATH = $null
    Mock Get-Process { if ($env:FREEHAND_TEST_RUNNING_PATH) { [pscustomobject]@{ Path = $env:FREEHAND_TEST_RUNNING_PATH } } }
    Mock Start-Process { [pscustomobject]@{ ExitCode = [int]$env:FREEHAND_TEST_SETUP_EXIT; Id = 123 } }
    Set-Content -LiteralPath (Join-Path $fixtureRoot 'Version.props') -Value '<Project><PropertyGroup><Version>1.2.3</Version></PropertyGroup></Project>'
    $script:model = Join-Path $TestDrive 'model'
    New-Item -ItemType Directory -Path $model -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $model 'tokens.txt') -Value 'fixture model'
    $script:asset = @{ Name = 'tokens.txt'; Size = (Get-Item (Join-Path $model 'tokens.txt')).Length; Sha256 = (Get-FileHash (Join-Path $model 'tokens.txt')).Hash }
    New-Item -ItemType Directory -Path (Join-Path $fixtureRoot 'packaging'), (Join-Path $fixtureRoot 'src/Freehand.App/obj') -Force | Out-Null
    @{ Version = 'fixture/revision'; Files = @($asset) } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $fixtureRoot 'packaging/model-manifest.json')
    @{ libraries = @{}; packageFolders = @{ (Split-Path -Parent $sdk) = @{} } } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $fixtureRoot 'src/Freehand.App/obj/project.assets.json')
    Set-Content -LiteralPath (Join-Path $fixtureRoot 'packaging/THIRD-PARTY-NOTICES.txt') -Value 'fixture notices'
    $script:installer = Join-Path $TestDrive 'FreehandSetup.exe'
    Set-Content -LiteralPath $installer -Value 'fixture installer'
    ((Get-FileHash $installer).Hash + '  FreehandSetup.exe') | Set-Content -LiteralPath ($installer + '.sha256')
}

AfterEach {
    Set-Location -LiteralPath $originalLocation
    $env:LOCALAPPDATA = $originalLocalData
    $env:FREEHAND_DATA_DIRECTORY = $originalProfile
    $env:FREEHAND_TEST_FAIL_COMMAND = $null
    $env:FREEHAND_TEST_SETUP_EXIT = $null
    $env:FREEHAND_TEST_RUNNING_PATH = $null
}

Describe 'Version and SDK selection' {
    It 'reads the shared package version and rejects malformed versions' {
        Get-FreehandVersion | Should-Be '1.2.3'
        Set-Content -LiteralPath (Join-Path $fixtureRoot 'Version.props') -Value '<Project><PropertyGroup><Version>wrong</Version></PropertyGroup></Project>'
        { Get-FreehandVersion } | Should-Throw '*major.minor.patch*'
    }

    It 'selects a compatible SDK and restores the caller location' {
        Resolve-FreehandDotnet $sdk | Should-Be $sdk
        (Get-Location).Path | Should-Be $fixtureRoot
        { Resolve-FreehandDotnet (Join-Path $TestDrive 'missing.exe') } | Should-Throw '*setup-dev.ps1*'
    }

    It 'finds the pinned model in an explicit directory or the installed package' {
        Find-FreehandModelDirectory $model | Should-Be $model
        $bundled = Join-Path $env:LOCALAPPDATA 'Programs/Freehand/models/parakeet-v2'
        New-Item -ItemType Directory -Path $bundled -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $model 'tokens.txt') -Destination $bundled
        $cache = Join-Path $fixtureRoot 'artifacts/model-cache/parakeet-v2'
        if (Test-Path $cache) { Remove-Item -LiteralPath (Join-Path $cache 'tokens.txt') -Force -ErrorAction SilentlyContinue }
        Find-FreehandModelDirectory | Should-Be $bundled
    }

    It 'restores the data profile after a successful and failed self-test' {
        Invoke-FreehandSelfTest $installer
        $env:FREEHAND_DATA_DIRECTORY | Should-Be 'previous-profile'
        $env:FREEHAND_TEST_SETUP_EXIT = '1'
        { Invoke-FreehandSelfTest $installer } | Should-Throw '*self-test failed*'
        $env:FREEHAND_DATA_DIRECTORY | Should-Be 'previous-profile'
    }
}

Describe 'Development launch' {
    It 'builds with separate preferences and preserves existing development data' {
        $profile = Join-Path $fixtureRoot 'artifacts/dev-data'
        New-Item -ItemType Directory -Path $profile -Force | Out-Null
        @{ KeepHistory = $false } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $profile 'settings.json')
        & (Join-Path $scripts 'dev.ps1') -Dotnet $sdk -ModelSource $model -BuildOnly
        $settings = Get-Content -LiteralPath (Join-Path $profile 'settings.json') -Raw | ConvertFrom-Json
        $settings.StartAtLogin | Should-BeFalse
        $settings.KeepHistory | Should-BeFalse
        $settings.ModelDirectory | Should-Be $model
        $env:FREEHAND_DATA_DIRECTORY | Should-Be 'previous-profile'
    }

    It 'refuses a second hotkey owner and stops after a compiler failure' {
        $env:FREEHAND_TEST_RUNNING_PATH = 'somewhere/Freehand.App.exe'
        { & (Join-Path $scripts 'dev.ps1') -Dotnet $sdk -ModelSource $model } | Should-Throw '*Quit Freehand*'
        $env:FREEHAND_TEST_FAIL_COMMAND = 'build'
        { & (Join-Path $scripts 'dev.ps1') -Dotnet $sdk -ModelSource $model -BuildOnly } | Should-Throw '*Development build failed*'
    }
}

Describe 'Verification failures' {
    It 'stops when <Command> fails' -ForEach @(@{ Command = 'restore'; FailureMessage = 'Restore failed' }, @{ Command = 'build'; FailureMessage = 'Build failed' }, @{ Command = 'test'; FailureMessage = 'Tests failed' }) {
        $env:FREEHAND_TEST_FAIL_COMMAND = $Command
        { & (Join-Path $scripts 'verify.ps1') -Dotnet $sdk } | Should-Throw "*$FailureMessage*"
    }

    It 'completes a successful verification without deploying' {
        & (Join-Path $scripts 'verify.ps1') -Dotnet $sdk
        Should-NotInvoke Start-Process
    }
}

Describe 'Local installation' {
    It 'rejects a checksum mismatch before starting setup' {
        Set-Content -LiteralPath ($installer + '.sha256') -Value ('0' * 64)
        { & (Join-Path $scripts 'deploy-local.ps1') -InstallerPath $installer } | Should-Throw '*checksum mismatch*'
        Should-NotInvoke Start-Process
    }

    It 'previews a verified installer without starting setup or copying a backup' {
        & (Join-Path $scripts 'deploy-local.ps1') -InstallerPath $installer -WhatIf
        Should-NotInvoke Start-Process
    }

    It 'rejects an unpacked app before it changes the installed copy' {
        $env:FREEHAND_TEST_RUNNING_PATH = 'unpacked/Freehand.App.exe'
        { & (Join-Path $scripts 'deploy-local.ps1') -InstallerPath $installer } | Should-Throw '*Quit the development*'
        Should-NotInvoke Start-Process
    }

    It 'saves a rollback installer and starts the verified replacement' {
        $root = Join-Path $env:LOCALAPPDATA 'Programs/Freehand'
        $cache = Join-Path $env:LOCALAPPDATA 'Freehand/installer'
        New-Item -ItemType Directory -Path $root, $cache -Force | Out-Null
        Set-Content -LiteralPath (Join-Path $cache 'FreehandSetup.exe') -Value 'old installer'
        @{ Version = '1.2.3'; Build = 'source-commit' } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'package-manifest.json')
        & (Join-Path $scripts 'deploy-local.ps1') -InstallerPath $installer
        $backups = @(Get-ChildItem -LiteralPath (Join-Path $fixtureRoot 'artifacts/rollback') -Filter FreehandSetup.exe -Recurse)
        $backups.Count | Should-BeGreaterThan 0
        Get-Content -LiteralPath $backups[-1].FullName | Should-Be 'old installer'
        Should-Invoke Start-Process -Exactly -Times 2
        $env:FREEHAND_DATA_DIRECTORY | Should-Be 'previous-profile'
    }

    It 'reports setup failure without launching the app, and restores the profile' {
        $env:FREEHAND_TEST_SETUP_EXIT = '1'
        { & (Join-Path $scripts 'deploy-local.ps1') -InstallerPath $installer } | Should-Throw '*Setup failed*'
        Should-Invoke Start-Process -Exactly -Times 1
        $env:FREEHAND_DATA_DIRECTORY | Should-Be 'previous-profile'
    }
}

Describe 'SDK setup' {
    It 'uses an existing SDK without downloading another one' {
        Mock Get-Command { [pscustomobject]@{ Source = $sdk } } -ParameterFilter { $Name -eq 'dotnet' }
        Mock Invoke-WebRequest { throw 'An existing SDK must not trigger a download.' }
        & (Join-Path $scripts 'setup-dev.ps1')
        Should-NotInvoke Invoke-WebRequest
    }

    It 'bootstraps the SDK when it is missing and reports restore failures' {
        $env:FREEHAND_TEST_BOOTSTRAPPED = $null
        Mock Get-Command { [pscustomobject]@{ Source = $(if ($env:FREEHAND_TEST_BOOTSTRAPPED) { $sdk } else { Join-Path $TestDrive 'missing-sdk.exe' }) } } -ParameterFilter { $Name -eq 'dotnet' }
        Mock Invoke-WebRequest { 'Set-Item Env:FREEHAND_TEST_BOOTSTRAPPED -Value ready' | Set-Content -LiteralPath $OutFile }
        & (Join-Path $scripts 'setup-dev.ps1')
        $env:FREEHAND_TEST_BOOTSTRAPPED | Should-Be 'ready'
        Should-Invoke Invoke-WebRequest -Exactly -Times 1
        $env:FREEHAND_TEST_FAIL_COMMAND = 'restore'
        { & (Join-Path $scripts 'setup-dev.ps1') } | Should-Throw '*Dependency restore failed*'
        $env:FREEHAND_TEST_BOOTSTRAPPED = $null
    }
}

Describe 'Release packaging' {
    It 'verifies the package and checksum through the <Mode> command' -ForEach @(@{ Mode = 'download' }, @{ Mode = 'verification' }, @{ Mode = 'preview' }) {
        Mock git { $global:LASTEXITCODE = 0; if ($args[0] -eq 'rev-parse') { 'abc1234' } else { ' M fixture' } }
        Mock Invoke-WebRequest {
            if ($Uri -like '*huggingface.co*') { Copy-Item -LiteralPath (Join-Path $model 'tokens.txt') -Destination $OutFile }
            else { Set-Content -LiteralPath $OutFile -Value 'fixture speech' }
        }
        Mock Get-FileHash { [pscustomobject]@{ Hash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData([IO.File]::ReadAllBytes($LiteralPath))) } }
        Mock Get-FileHash { [pscustomobject]@{ Hash = '59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e' } } -ParameterFilter { $LiteralPath -like '*jfk.wav' }
        switch ($Mode) {
            'download' {
                $cachedAsset = Join-Path $fixtureRoot 'artifacts/model-cache/parakeet-v2/tokens.txt'
                if (Test-Path -LiteralPath $cachedAsset) { Remove-Item -LiteralPath $cachedAsset }
                & (Join-Path $scripts 'build-release.ps1') -Dotnet $sdk
            }
            'verification' { & (Join-Path $scripts 'verify.ps1') -Dotnet $sdk -ModelSource $model -Package }
            'preview' { & (Join-Path $scripts 'deploy-local.ps1') -Dotnet $sdk -ModelSource $model -WhatIf }
        }
        $package = Get-Content -LiteralPath (Join-Path $fixtureRoot 'artifacts/publish/package-manifest.json') -Raw | ConvertFrom-Json
        $package.Version | Should-Be '1.2.3'
        $package.Build | Should-Be 'abc1234-dirty'
        $output = Join-Path $fixtureRoot 'artifacts/release/Freehand-1.2.3-win-x64-Setup.exe'
        $expected = ((Get-Content -LiteralPath ($output + '.sha256') -Raw).Trim() -split '\s+')[0]
        (Get-FileHash -LiteralPath $output).Hash.ToLowerInvariant() | Should-Be $expected
        if ($Mode -eq 'download') { Should-NotInvoke Start-Process }
        else { Should-Invoke Start-Process -Exactly -Times 1 }
    }

    It 'rejects damaged models before publishing binaries' {
        Mock git { $global:LASTEXITCODE = 0; 'abc1234' }
        Set-Content -LiteralPath (Join-Path $model 'tokens.txt') -Value 'damaged model'
        { & (Join-Path $scripts 'build-release.ps1') -Dotnet $sdk -ModelSource $model } | Should-Throw '*Model verification failed*'
    }
}
}

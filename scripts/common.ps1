# Shared by the development, verification, and packaging commands.
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

function Get-FreehandVersion {
    $version = ([xml](Get-Content -LiteralPath (Join-Path $projectRoot 'Version.props') -Raw)).Project.PropertyGroup.Version
    if ($version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') { throw 'Version.props must contain a major.minor.patch version.' }
    return [string]$version
}

function Resolve-FreehandDotnet([string]$RequestedPath) {
    $candidates = if ($RequestedPath) { @($RequestedPath) } else {
        @((Join-Path $projectRoot '.dotnet/dotnet.exe'), (Get-Command dotnet -ErrorAction SilentlyContinue).Source)
    }
    foreach ($candidate in $candidates) {
        if (-not $candidate -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        Push-Location -LiteralPath $projectRoot
        try {
            $sdk = & $candidate --version 2>$null
            if ($LASTEXITCODE -eq 0 -and $sdk -match '^10\.0\.\d+$') { return (Resolve-Path -LiteralPath $candidate).Path }
        } finally { Pop-Location }
    }
    throw 'A compatible .NET 10 SDK was not found. Run pwsh -File ./scripts/setup-dev.ps1, or supply -Dotnet with its full path.'
}

function Find-FreehandModelDirectory([string]$RequestedPath) {
    if ($RequestedPath) { return (Resolve-Path -LiteralPath $RequestedPath).Path }
    $candidates = @(
        (Join-Path $projectRoot 'artifacts/model-cache/parakeet-v2'),
        (Join-Path $env:LOCALAPPDATA 'Programs/Freehand/models/parakeet-v2'),
        (Join-Path $env:LOCALAPPDATA 'Freehand/models/parakeet-v2'),
        (Join-Path $projectRoot 'artifacts/publish/models/parakeet-v2')
    )
    $manifest = Get-Content -LiteralPath (Join-Path $projectRoot 'packaging/model-manifest.json') -Raw | ConvertFrom-Json
    foreach ($candidate in $candidates) {
        $missing = @($manifest.Files | Where-Object { -not (Test-Path -LiteralPath (Join-Path $candidate $_.Name) -PathType Leaf) })
        if ($missing.Count -eq 0) { return $candidate }
    }
    return $null
}

function Invoke-FreehandSelfTest([string]$Executable) {
    $profile = Join-Path $projectRoot 'artifacts/selftest-data'
    $previous = $env:FREEHAND_DATA_DIRECTORY
    try {
        $env:FREEHAND_DATA_DIRECTORY = $profile
        $check = Start-Process -FilePath $Executable -ArgumentList '--selftest' -Wait -PassThru -WindowStyle Hidden
        if ($check.ExitCode -ne 0) { throw "Published self-test failed with exit code $($check.ExitCode)." }
    } finally { $env:FREEHAND_DATA_DIRECTORY = $previous }
}

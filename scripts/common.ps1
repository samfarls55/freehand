# Shared by the development, verification, and packaging commands.
#Requires -Version 7.0
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

function Get-FreehandVersion {
    $version = if ($env:FREEHAND_RELEASE_VERSION) { $env:FREEHAND_RELEASE_VERSION } else {
        ([xml](Get-Content -LiteralPath (Join-Path $projectRoot 'Version.props') -Raw)).SelectSingleNode('/Project/PropertyGroup/Version[not(@Condition)]').InnerText
    }
    if ($version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') { throw 'Version.props must contain a major.minor.patch version.' }
    return [string]$version
}

function New-FreehandInstaller([string]$PublishDirectory, [string]$Runtime, [string]$Destination) {
    $zip = $Destination + '.payload.zip'
    try {
        [IO.Compression.ZipFile]::CreateFromDirectory($PublishDirectory, $zip, [IO.Compression.CompressionLevel]::Fastest, $false)
        Copy-Item -LiteralPath $Runtime -Destination $Destination -Force
        $archiveStream = [IO.File]::OpenRead($zip)
        $installerStream = [IO.File]::Open($Destination, [IO.FileMode]::Append)
        try {
            $archiveStream.CopyTo($installerStream)
            $installerStream.Write([Convert]::FromHexString((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash))
            $installerStream.Write([BitConverter]::GetBytes([long]$archiveStream.Length))
            $installerStream.Write([Text.Encoding]::ASCII.GetBytes('FREEHD01'))
        } finally { $archiveStream.Dispose(); $installerStream.Dispose() }
        $checksum = (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant()
        ($checksum + '  ' + [IO.Path]::GetFileName($Destination)) | Set-Content -LiteralPath ($Destination + '.sha256')
    } finally { if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force } }
}

function New-FreehandPackageManifest([string]$Directory, [string]$Version, [string]$Build) {
    $files = foreach ($file in Get-ChildItem -LiteralPath $Directory -File -Recurse) {
        if ($file.Name -eq 'package-manifest.json') { continue }
        @{ Path = [IO.Path]::GetRelativePath($Directory, $file.FullName); Size = $file.Length; Sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    }
    @{ Version = $Version; Build = $Build; Files = @($files) } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Directory 'package-manifest.json')
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
    $manifest = Get-Content -LiteralPath (Join-Path $projectRoot 'packaging/model-manifest.json') -Raw | ConvertFrom-Json
    $modelFolder = $manifest.DirectoryName
    $candidates = @(
        (Join-Path $projectRoot "artifacts/model-cache/$modelFolder"),
        (Join-Path $env:LOCALAPPDATA "Programs/Freehand/models/$modelFolder"),
        (Join-Path $env:LOCALAPPDATA "Freehand/models/$modelFolder"),
        (Join-Path $projectRoot "artifacts/publish/models/$modelFolder")
    )
    foreach ($candidate in $candidates) {
        $missing = @($manifest.Files | Where-Object { -not (Test-Path -LiteralPath (Join-Path $candidate $_.Name) -PathType Leaf) })
        if ($missing.Count -eq 0) { return $candidate }
    }
    return $null
}

function Invoke-FreehandSelfTest([string]$Executable) {
    $dataDirectory = Join-Path $projectRoot 'artifacts/selftest-data'
    $previous = $env:FREEHAND_DATA_DIRECTORY
    try {
        $env:FREEHAND_DATA_DIRECTORY = $dataDirectory
        $check = Start-Process -FilePath $Executable -ArgumentList '--selftest' -Wait -PassThru -WindowStyle Hidden
        if ($check.ExitCode -ne 0) { throw "Published self-test failed with exit code $($check.ExitCode)." }
    } finally { $env:FREEHAND_DATA_DIRECTORY = $previous }
}

#Requires -Version 7.0
[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Dotnet,
    [string]$ModelSource,
    [string]$InstallerPath
)
. (Join-Path $PSScriptRoot 'common.ps1')
$installedRoot = Join-Path $env:LOCALAPPDATA 'Programs/Freehand'
if (-not $WhatIfPreference) {
    $installedExe = Join-Path $installedRoot 'Freehand.App.exe'
    foreach ($process in @(Get-Process -Name Freehand.App -ErrorAction SilentlyContinue)) {
        if (-not $process.Path -or -not $process.Path.Equals($installedExe, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Quit the development or unpacked Freehand app before updating the installed copy.'
        }
    }
}
if (-not $InstallerPath) {
    $preview = $WhatIfPreference
    try {
        # Build a real package even when installation is being previewed.
        $WhatIfPreference = $false
        & (Join-Path $PSScriptRoot 'verify.ps1') -Dotnet $Dotnet -ModelSource $ModelSource -Package
    } finally { $WhatIfPreference = $preview }
    $InstallerPath = Join-Path $projectRoot "artifacts/release/Freehand-$(Get-FreehandVersion)-win-x64-Setup.exe"
}
$installer = (Resolve-Path -LiteralPath $InstallerPath).Path
$expected = ((Get-Content -LiteralPath ($installer + '.sha256') -Raw).Trim() -split '\s+')[0]
$actual = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash
if ($expected -notmatch '^[a-fA-F0-9]{64}$' -or $actual -ine $expected) { throw 'Installer checksum mismatch. Installation stopped.' }
if (-not $PSCmdlet.ShouldProcess($installedRoot, "Install verified Freehand package $installer")) { return }
$previousInstaller = Join-Path $env:LOCALAPPDATA 'Freehand/installer/FreehandSetup.exe'
if (Test-Path -LiteralPath $previousInstaller) {
    $backupRoot = Join-Path $projectRoot ('artifacts/rollback/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 6))
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    $backup = Join-Path $backupRoot 'FreehandSetup.exe'
    Copy-Item -LiteralPath $previousInstaller -Destination $backup
    ((Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant() + '  FreehandSetup.exe') | Set-Content -LiteralPath ($backup + '.sha256')
    Write-Output "Rollback installer: $backup"
}
$previousProfile = $env:FREEHAND_DATA_DIRECTORY
try {
    $env:FREEHAND_DATA_DIRECTORY = $null
    $setup = Start-Process -FilePath $installer -ArgumentList '--quiet' -Wait -PassThru -WindowStyle Hidden
    if ($setup.ExitCode -ne 0) { throw "Setup failed with exit code $($setup.ExitCode). See $env:TEMP\Freehand-setup-error.log." }
    $manifest = Get-Content -LiteralPath (Join-Path $installedRoot 'package-manifest.json') -Raw | ConvertFrom-Json
    Start-Process -FilePath (Join-Path $installedRoot 'Freehand.App.exe') -ArgumentList '--tray' -WindowStyle Hidden
    Write-Output "Installed Freehand $($manifest.Version), source $($manifest.Build). The updated app is running in the tray."
} finally { $env:FREEHAND_DATA_DIRECTORY = $previousProfile }

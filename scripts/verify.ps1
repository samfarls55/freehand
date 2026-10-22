#Requires -Version 7.0
param(
    [string]$Dotnet,
    [string]$ModelSource,
    [switch]$Package
)
. (Join-Path $PSScriptRoot 'common.ps1')
$dotnetPath = Resolve-FreehandDotnet $Dotnet
Push-Location -LiteralPath $projectRoot
try {
    & $dotnetPath restore Freehand.sln
    if ($LASTEXITCODE -ne 0) { throw 'Restore failed.' }
    & $dotnetPath build Freehand.sln -c Release --no-restore --no-incremental -warnaserror -bl:artifacts/build.binlog
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
    & $dotnetPath test Freehand.sln -c Release --no-build --logger trx --results-directory artifacts/test-results
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    if ($Package) {
        & (Join-Path $PSScriptRoot 'build-release.ps1') -Dotnet $dotnetPath -ModelSource $ModelSource
        Invoke-FreehandSelfTest (Join-Path $projectRoot 'artifacts/publish/Freehand.App.exe')
    }
} finally { Pop-Location }
Write-Output $(if ($Package) { 'Build, tests, package, and published self-test passed.' } else { 'Build and tests passed.' })

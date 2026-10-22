#Requires -Version 7.0
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'common.ps1')
try {
    $dotnetPath = Resolve-FreehandDotnet
} catch {
    $tools = Join-Path $projectRoot 'artifacts/tools'
    New-Item -ItemType Directory -Force -Path $tools | Out-Null
    $installer = Join-Path $tools 'dotnet-install.ps1'
    Invoke-WebRequest 'https://dot.net/v1/dotnet-install.ps1' -OutFile $installer
    & $installer -JsonFile (Join-Path $projectRoot 'global.json') -InstallDir (Join-Path $projectRoot '.dotnet') -Architecture x64 -NoPath
    $dotnetPath = Resolve-FreehandDotnet
}
Push-Location -LiteralPath $projectRoot
try {
    & $dotnetPath restore Freehand.sln
    if ($LASTEXITCODE -ne 0) { throw 'Dependency restore failed.' }
} finally { Pop-Location }
Write-Output "Development SDK: $dotnetPath"
Write-Output 'Ready. Run pwsh -File ./scripts/dev.ps1 to build and open the development app.'

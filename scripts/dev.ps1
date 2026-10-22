#Requires -Version 7.0
param(
    [string]$Dotnet,
    [string]$ModelSource,
    [switch]$BuildOnly
)
. (Join-Path $PSScriptRoot 'common.ps1')
$dotnetPath = Resolve-FreehandDotnet $Dotnet
if (-not $BuildOnly -and (Get-Process -Name Freehand.App -ErrorAction SilentlyContinue)) {
    throw 'Quit Freehand from its tray menu before opening the development app. Only one copy can own the dictation hotkey.'
}
$model = Find-FreehandModelDirectory $ModelSource
if (-not $model) { throw 'Model files were not found. Run ./scripts/verify.ps1 -Package once, or supply -ModelSource.' }
$dataDirectory = Join-Path $projectRoot 'artifacts/dev-data'
New-Item -ItemType Directory -Force -Path $dataDirectory | Out-Null
$settingsPath = Join-Path $dataDirectory 'settings.json'
$settings = if (Test-Path -LiteralPath $settingsPath) { Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json -AsHashtable } else { @{} }
$settings.ModelDirectory = $model
$settings.StartAtLogin = $false
$settings | ConvertTo-Json | Set-Content -LiteralPath $settingsPath
Push-Location -LiteralPath $projectRoot
try {
    & $dotnetPath build src/Freehand.App/Freehand.App.csproj -c Debug -warnaserror
    if ($LASTEXITCODE -ne 0) { throw 'Development build failed.' }
} finally { Pop-Location }
$exe = Join-Path $projectRoot 'src/Freehand.App/bin/Debug/net10.0/Freehand.App.exe'
Write-Output "Development profile: $dataDirectory"
Write-Output "Model: $model"
if ($BuildOnly) { Write-Output "Built: $exe"; return }
$start = [Diagnostics.ProcessStartInfo]::new($exe)
$start.UseShellExecute = $false
$start.WorkingDirectory = $projectRoot
$start.Environment['FREEHAND_DATA_DIRECTORY'] = $dataDirectory
$start.Environment['DOTNET_ROOT'] = Split-Path -Parent $dotnetPath
$start.Environment['DOTNET_ROOT_X64'] = Split-Path -Parent $dotnetPath
$app = [Diagnostics.Process]::Start($start)
Write-Output "Development app started, process $($app.Id). Quit from the tray before rebuilding or returning to the installed app."

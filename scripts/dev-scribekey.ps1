#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$Dotnet,
    [string]$ModelSource,
    [string]$OutputDirectory,
    [switch]$BuildOnly,
    [switch]$PrepareOnly
)
. (Join-Path $PSScriptRoot 'common.ps1')
. (Join-Path $PSScriptRoot 'scribekey-dev-assets.ps1')
if (-not $PrepareOnly -and -not $IsWindows) { throw 'Build and run this development preview on Windows x64.' }
if (-not $BuildOnly -and -not $PrepareOnly -and (Get-Process -Name Freehand.App -ErrorAction SilentlyContinue)) {
    throw 'Quit Freehand from its tray menu before starting the development preview.'
}
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $projectRoot ('artifacts/scribekey-dev-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8)) }
$output = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $output) { throw 'Choose a fresh output directory; earlier previews are preserved.' }
$assets = Join-Path $projectRoot 'packaging/scribekey-dev'
# Check LFS materialization before downloading or building anything.
Assert-ScribeKeyFile (Join-Path $assets 'assets/base-IQ4_XS.gguf') 211804448 '82ab22cebc8e5a9acc41f0673d69d39ec65812c9872fb91b276137452798b174'
Assert-ScribeKeyFile (Join-Path $assets 'assets/blend-t050-F32.gguf') 12006240 '4d14e22826d039a12444236124459363f02e77de247117b7b8379ccfe257cfb1'
if (-not $PrepareOnly) { $dotnetPath = Resolve-FreehandDotnet $Dotnet }
New-Item -ItemType Directory -Path $output | Out-Null
$app = Join-Path $output 'app'
$cleanup = Join-Path $app 'models/cleanup'
$cache = Join-Path $projectRoot 'artifacts/scribekey-dev-cache'
New-Item -ItemType Directory -Force -Path $cache,$cleanup | Out-Null
$runtimeManifest = Get-Content (Join-Path $projectRoot 'packaging/cleanup-runtime-manifest.json') -Raw | ConvertFrom-Json
$runtime = @($runtimeManifest.Artifacts | Where-Object Platform -CEQ 'win-x64-cpu')[0]
$archive = Join-Path $cache 'llama-b12015-bin-win-cpu-x64.zip'
Get-ScribeKeyDownload $runtime.Source $archive $runtime.ArchiveSha256 $runtime.ArchiveSize
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $cleanup 'runtime')
Assert-ScribeKeyFile (Join-Path $cleanup 'runtime/llama-server.exe') 0 $runtime.ExecutableSha256
foreach ($name in @('base-IQ4_XS.gguf','blend-t050-F32.gguf')) {
    Copy-Item -LiteralPath (Join-Path $assets ('assets/' + $name)) -Destination (Join-Path $cleanup $name)
}
Copy-Item -LiteralPath (Join-Path $assets 'licenses') -Destination $cleanup -Recurse
$manifest = Get-Content (Join-Path $assets 'cleanup-profile.json') -Raw | ConvertFrom-Json -AsHashtable
$manifest.files = @(foreach ($file in Get-ChildItem -LiteralPath $cleanup -File -Recurse | Sort-Object FullName) {
    @{ path = [IO.Path]::GetRelativePath($cleanup,$file.FullName).Replace('\','/'); size = $file.Length
       sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
})
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $cleanup 'cleanup-manifest.json') -Encoding utf8NoBOM
$speechManifest = Get-Content (Join-Path $projectRoot 'packaging/model-manifest.json') -Raw | ConvertFrom-Json
$speech = Join-Path $app ('models/' + $speechManifest.DirectoryName)
New-Item -ItemType Directory -Path $speech | Out-Null
if (-not $ModelSource -and $IsWindows) { $ModelSource = Find-FreehandModelDirectory }
if (-not $ModelSource) {
    $speechArchive = Join-Path $cache 'parakeet-110m.tar.bz2'
    Get-ScribeKeyDownload $speechManifest.Source $speechArchive $speechManifest.ArchiveSha256 0
    $extracted = Join-Path $output 'speech-extraction'
    New-Item -ItemType Directory -Path $extracted | Out-Null
    & tar -xf $speechArchive -C $extracted
    if ($LASTEXITCODE -ne 0) { throw 'Speech model extraction failed.' }
    $ModelSource = Join-Path $extracted $speechManifest.ArchiveDirectory
}
foreach ($file in $speechManifest.Files) {
    $source = Join-Path $ModelSource $file.Name
    Assert-ScribeKeyFile $source $file.Size $file.Sha256
    Copy-Item -LiteralPath $source -Destination (Join-Path $speech $file.Name)
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'packaging/model-manifest.json') -Destination (Join-Path $speech 'manifest.json')
Copy-Item -LiteralPath (Join-Path $assets 'Start Freehand ScribeKey Dev.ps1'),(Join-Path $assets 'Start Freehand ScribeKey Dev.cmd'),(Join-Path $assets 'README.md') -Destination $output
if ($PrepareOnly) { Write-Output "Prepared verified development assets: $output"; return }
Push-Location $projectRoot
try {
    & $dotnetPath publish src/Freehand.App/Freehand.App.csproj -c Release -r win-x64 --self-contained true -warnaserror -p:PublishSingleFile=false --output $app
    if ($LASTEXITCODE -ne 0) { throw 'ScribeKey development publish failed.' }
} finally { Pop-Location }
if (-not (Test-Path (Join-Path $app 'Freehand.Platform.Windows.dll'))) { throw 'Published Windows platform assembly is missing.' }
# The packaged self-test starts the actual bundled cleanup worker and adapter.
& (Join-Path $output 'Start Freehand ScribeKey Dev.ps1') -SelfTest
if ($LASTEXITCODE -ne 0) { throw 'Published ScribeKey development self-test failed.' }
$identity = @{ Commit = (git -C $projectRoot rev-parse HEAD).Trim(); Model = $manifest.modelId
    BaseSha256 = $manifest.modelSha256; AdapterSha256 = $manifest.adapterSha256
    CleanupManifestSha256 = (Get-FileHash (Join-Path $cleanup 'cleanup-manifest.json')).Hash.ToLowerInvariant()
    WindowsSelfTestPassed = $true; PhysicalDictationOrWindowsSlaQualified = $false }
$identity | ConvertTo-Json | Set-Content (Join-Path $output 'build-identity.json') -Encoding utf8NoBOM
Write-Output "Verified development preview: $output"
if (-not $BuildOnly) { & (Join-Path $output 'Start Freehand ScribeKey Dev.ps1') }

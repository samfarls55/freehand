#Requires -Version 7.0
param(
    [string]$Dotnet,
    [string]$ModelSource,
    [string]$CleanupSource
)
. (Join-Path $PSScriptRoot 'common.ps1')
$Dotnet = Resolve-FreehandDotnet $Dotnet
Set-Location -LiteralPath $projectRoot
$cleanupBundle = $null
$cleanupInput = if ($CleanupSource) { $CleanupSource } else { Join-Path $projectRoot 'artifacts/cleanup-assets' }
if ($CleanupSource -or (Test-Path -LiteralPath (Join-Path $cleanupInput 'cleanup-manifest.json') -PathType Leaf)) {
    $cleanupBundle = & (Join-Path $PSScriptRoot 'prepare-cleanup.ps1') -ValidateDirectory $cleanupInput
}
$build = (git rev-parse --short HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Cannot identify the source commit.' }
$changes = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect the source tree.' }
if ($changes) { $build += '-dirty' }
$version = Get-FreehandVersion
$publish = Join-Path $projectRoot 'artifacts/publish'
$compiler = Join-Path $projectRoot 'artifacts/installer-runtime'
$release = Join-Path $projectRoot 'artifacts/release'
$modelInput = Find-FreehandModelDirectory $ModelSource
$manifest = Get-Content -LiteralPath packaging/model-manifest.json -Raw | ConvertFrom-Json
$modelCache = Join-Path $projectRoot ('artifacts/model-cache/' + $manifest.DirectoryName)
New-Item -ItemType Directory -Force -Path $modelCache | Out-Null
foreach ($asset in $manifest.Files) {
    $source = if ($modelInput) { Join-Path $modelInput $asset.Name } else { $null }
    $destination = Join-Path $modelCache $asset.Name
    if ($source -and (Test-Path -LiteralPath $source) -and $source -ne $destination) {
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}
$missing = @($manifest.Files | Where-Object { -not (Test-Path -LiteralPath (Join-Path $modelCache $_.Name)) })
if ($missing.Count -gt 0) {
    $archive = Join-Path $projectRoot ('artifacts/model-cache/' + $manifest.DirectoryName + '.tar.bz2')
    if (-not (Test-Path -LiteralPath $archive)) { Invoke-WebRequest $manifest.Source -OutFile $archive }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ine $manifest.ArchiveSha256) { throw 'Model archive checksum failed.' }
    $extracted = Join-Path $projectRoot ('artifacts/model-cache/' + $manifest.DirectoryName + '-download')
    New-Item -ItemType Directory -Force -Path $extracted | Out-Null
    & tar -xf $archive -C $extracted
    if ($LASTEXITCODE -ne 0) { throw 'Model archive extraction failed.' }
    foreach ($asset in $manifest.Files) {
        $source = Join-Path (Join-Path $extracted $manifest.ArchiveDirectory) $asset.Name
        Copy-Item -LiteralPath $source -Destination (Join-Path $modelCache $asset.Name) -Force
    }
}
foreach ($asset in $manifest.Files) {
    $destination = Join-Path $modelCache $asset.Name
    if ((Get-Item -LiteralPath $destination).Length -ne $asset.Size -or (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $asset.Sha256) { throw "Model verification failed: $($asset.Name)" }
}
foreach ($directory in @($publish, $compiler, $release)) {
    $resolved = [IO.Path]::GetFullPath($directory)
    $allowed = @('publish', 'installer-runtime', 'release') | ForEach-Object { [IO.Path]::GetFullPath((Join-Path $projectRoot "artifacts/$_")) }
    if ($resolved -notin $allowed) { throw "Refusing to clean unexpected output directory: $resolved" }
    foreach ($process in @(Get-Process -Name Freehand.App,Freehand.Installer -ErrorAction SilentlyContinue)) {
        if ($process.Path -and $process.Path.StartsWith($resolved + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Quit the application running from $resolved before packaging."
        }
    }
    if (Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }
    New-Item -ItemType Directory -Path $resolved | Out-Null
}
& $Dotnet publish src/Freehand.App/Freehand.App.csproj -c Release -r win-x64 --self-contained true "-p:Version=$version" -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=false "-p:InformationalVersion=$version+$build" --output $publish
if ($LASTEXITCODE -ne 0) { throw 'Application publish failed' }
$modelTarget = Join-Path $publish ('models/' + $manifest.DirectoryName)
New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
foreach ($asset in $manifest.Files) { Copy-Item -LiteralPath (Join-Path $modelCache $asset.Name) -Destination $modelTarget }
Copy-Item -LiteralPath packaging/model-manifest.json -Destination (Join-Path $modelTarget 'manifest.json') -Force
if ($cleanupBundle) {
    $cleanupTarget = Join-Path $publish 'models/cleanup'
    foreach ($asset in $cleanupBundle.Files) {
        $destination = Join-Path $cleanupTarget $asset.path
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $cleanupBundle.Directory $asset.path) -Destination $destination
    }
    Copy-Item -LiteralPath $cleanupBundle.ManifestPath -Destination (Join-Path $cleanupTarget 'cleanup-manifest.json')
    $null = & (Join-Path $PSScriptRoot 'prepare-cleanup.ps1') -ValidateDirectory $cleanupTarget
}
New-Item -ItemType Directory -Force -Path (Join-Path $publish 'fixtures') | Out-Null
$fixtureCache = Join-Path $projectRoot 'artifacts/model-cache/jfk.wav'
if (-not (Test-Path -LiteralPath $fixtureCache)) {
    Invoke-WebRequest 'https://raw.githubusercontent.com/ggml-org/whisper.cpp/b0a11594aec50892a02cd8d129eee2dfe93a8bb8/samples/jfk.wav' -OutFile $fixtureCache
}
$fixture = Join-Path $publish 'fixtures/jfk.wav'
Copy-Item -LiteralPath $fixtureCache -Destination $fixture
if ((Get-FileHash -LiteralPath $fixture -Algorithm SHA256).Hash -ne '59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e') { throw 'Speech fixture checksum failed' }
Copy-Item -LiteralPath packaging/THIRD-PARTY-NOTICES.txt -Destination $publish -Force
$notices = Join-Path $publish 'licenses'
New-Item -ItemType Directory -Force -Path $notices | Out-Null
# Preserve license texts distributed in every resolved NuGet package.
$assets = Get-Content src/Freehand.App/obj/project.assets.json -Raw | ConvertFrom-Json -AsHashtable
$packageRoot = @($assets.packageFolders.Keys)[0]
$index = [Collections.Generic.List[string]]::new()
foreach ($library in $assets.libraries.GetEnumerator()) {
    if ($library.Value.type -ne 'package') { continue }
    $folder = Join-Path $packageRoot $library.Value.path
    $label = $library.Key.Replace('/', '-')
    $index.Add($library.Key + ' https://www.nuget.org/packages/' + $library.Key)
    foreach ($file in Get-ChildItem -LiteralPath $folder -File -Recurse | Where-Object { $_.Name -match '(?i)^(license|licence|copying|third.?party|notice)' -and $_.Length -lt 2MB }) {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $notices ($label + '-' + $file.Name)) -Force
    }
    $nuspec = Get-ChildItem -LiteralPath $folder -Filter '*.nuspec' | Select-Object -First 1
    if ($nuspec) { Copy-Item -LiteralPath $nuspec.FullName -Destination (Join-Path $notices ($label + '.nuspec')) -Force }
}
$index | Set-Content -LiteralPath (Join-Path $notices 'dependencies.txt')
Copy-Item -LiteralPath (Join-Path (Split-Path $Dotnet) 'LICENSE.txt') -Destination (Join-Path $notices 'dotnet-LICENSE.txt') -Force
Copy-Item -LiteralPath (Join-Path (Split-Path $Dotnet) 'ThirdPartyNotices.txt') -Destination (Join-Path $notices 'dotnet-ThirdPartyNotices.txt') -Force
New-FreehandPackageManifest -Directory $publish -Version $version -Build $build
& $Dotnet publish packaging/Installer/Freehand.Installer.csproj -c Release -r win-x64 --self-contained true "-p:Version=$version" -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true --output $compiler
if ($LASTEXITCODE -ne 0) { throw 'Installer publish failed' }
$installer = Join-Path $release "Freehand-$version-win-x64-Setup.exe"
New-FreehandInstaller -PublishDirectory $publish -Runtime (Join-Path $compiler 'Freehand.Installer.exe') -Destination $installer
Write-Output "Installer: $installer"

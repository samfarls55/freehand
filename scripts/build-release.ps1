param(
    [string]$Dotnet = (Get-Command dotnet -ErrorAction Stop).Source,
    [string]$ModelSource = "$env:LOCALAPPDATA\Freehand\models\parakeet-v2"
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath $Dotnet)) { throw 'Install the SDK pinned in global.json, then supply -Dotnet.' }
$build = (git rev-parse --short HEAD).Trim()
$version = '1.0.0'
$publish = Join-Path $projectRoot 'artifacts/publish'
$compiler = Join-Path $projectRoot 'artifacts/installer-runtime'
$release = Join-Path $projectRoot 'artifacts/release'
foreach ($directory in @($publish, $compiler, $release)) { New-Item -ItemType Directory -Force -Path $directory | Out-Null }
& $Dotnet publish src/Freehand.App/Freehand.App.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=false "-p:InformationalVersion=$version+$build" --output $publish
if ($LASTEXITCODE -ne 0) { throw 'Application publish failed' }
$modelTarget = Join-Path $publish 'models/parakeet-v2'
New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
$manifest = Get-Content -LiteralPath packaging/model-manifest.json -Raw | ConvertFrom-Json
$revision = $manifest.Version.Split('/')[-1]
foreach ($asset in $manifest.Files) {
    $source = Join-Path $ModelSource $asset.Name
    $destination = Join-Path $modelTarget $asset.Name
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $destination -Force }
    else {
        $url = 'https://huggingface.co/csukuangfj/sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-int8/resolve/' + $revision + '/' + $asset.Name
        Invoke-WebRequest $url -OutFile $destination
    }
    if ((Get-Item -LiteralPath $destination).Length -ne $asset.Size -or (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ne $asset.Sha256) { throw "Model verification failed: $($asset.Name)" }
}
Copy-Item -LiteralPath packaging/model-manifest.json -Destination (Join-Path $modelTarget 'manifest.json') -Force
New-Item -ItemType Directory -Force -Path (Join-Path $publish 'fixtures') | Out-Null
$fixture = Join-Path $publish 'fixtures/jfk.wav'
Invoke-WebRequest 'https://raw.githubusercontent.com/ggml-org/whisper.cpp/b0a11594aec50892a02cd8d129eee2dfe93a8bb8/samples/jfk.wav' -OutFile $fixture
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
$files = foreach ($file in Get-ChildItem -LiteralPath $publish -File -Recurse) {
    if ($file.Name -eq 'package-manifest.json') { continue }
    @{ Path = [IO.Path]::GetRelativePath($publish,$file.FullName); Size = $file.Length; Sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
@{ Version=$version; Build=$build; Files=@($files) } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $publish 'package-manifest.json')
& $Dotnet publish packaging/Installer/Freehand.Installer.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true --output $compiler
if ($LASTEXITCODE -ne 0) { throw 'Installer publish failed' }
$zip = Join-Path $release 'payload.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip }
[IO.Compression.ZipFile]::CreateFromDirectory($publish, $zip, [IO.Compression.CompressionLevel]::Fastest, $false)
$installer = Join-Path $release "Freehand-$version-win-x64-Setup.exe"
Copy-Item -LiteralPath (Join-Path $compiler 'Freehand.Installer.exe') -Destination $installer -Force
$archive = [IO.File]::OpenRead($zip)
$output = [IO.File]::Open($installer,[IO.FileMode]::Append)
try {
    $archive.CopyTo($output)
    $hash = [Convert]::FromHexString((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash)
    $output.Write($hash)
    $output.Write([BitConverter]::GetBytes([long]$archive.Length))
    $output.Write([Text.Encoding]::ASCII.GetBytes('FREEHD01'))
} finally { $archive.Dispose(); $output.Dispose() }
$checksum = (Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
($checksum + '  ' + [IO.Path]::GetFileName($installer)) | Set-Content -LiteralPath ($installer + '.sha256')
Write-Output "Installer: $installer"
Write-Output "SHA256: $checksum"

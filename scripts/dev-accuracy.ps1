#Requires -Version 7.0
param(
    [string]$Dotnet,
    [string]$ModelSource,
    [string]$RuntimeSource,
    [switch]$BuildOnly,
    [switch]$Benchmark
)
. (Join-Path $PSScriptRoot 'common.ps1')
$dotnetPath = Resolve-FreehandDotnet $Dotnet
$modelManifest = Get-Content (Join-Path $projectRoot 'packaging/accuracy-model-manifest.json') -Raw | ConvertFrom-Json
$runtimeManifest = Get-Content (Join-Path $projectRoot 'packaging/accuracy-runtime-manifest.json') -Raw | ConvertFrom-Json
$publishDirectory = [IO.Path]::GetFullPath((Join-Path $projectRoot 'artifacts/accuracy-preview'))
$dataDirectory = Join-Path $projectRoot 'artifacts/accuracy-dev-data'
foreach ($existing in @(Get-Process -Name Freehand.App -ErrorAction SilentlyContinue)) {
    if ($existing.Path -and $existing.Path.StartsWith($publishDirectory + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Quit the accuracy preview before rebuilding it.'
    }
    if (-not $BuildOnly) { throw 'Quit the running Freehand copy before starting the accuracy preview.' }
}
$modelCache = Join-Path $projectRoot ('artifacts/model-cache/' + $modelManifest.DirectoryName)
New-Item -ItemType Directory -Force -Path $modelCache,$publishDirectory,$dataDirectory | Out-Null
foreach ($asset in $modelManifest.Files) {
    $destination = Join-Path $modelCache $asset.Name
    $assetSource = if ($asset.PSObject.Properties['Source']) { $asset.Source } else { $null }
    if ($ModelSource) {
        $inputFile = Join-Path (Resolve-Path -LiteralPath $ModelSource).Path $asset.Name
        if (Test-Path -LiteralPath $inputFile) {
            if ($inputFile -ne $destination) { Copy-Item -LiteralPath $inputFile -Destination $destination -Force }
        } elseif (-not $assetSource) { throw "ModelSource is missing $($asset.Name)." }
    }
    if (-not (Test-Path -LiteralPath $destination)) {
        $assetUrl = if ($assetSource) { $assetSource } else { $modelManifest.Source }
        Invoke-WebRequest -Uri $assetUrl -OutFile $destination
    }
    if ((Get-Item -LiteralPath $destination).Length -ne $asset.Size -or
        (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ine $asset.Sha256) {
        throw "Accuracy model checksum failed: $($asset.Name)"
    }
}
if (-not $RuntimeSource) {
    $RuntimeSource = Join-Path $projectRoot 'artifacts/native-cache/transcribe-0.4.1-freehand-read2'
    & (Join-Path $projectRoot 'tools/Freehand.Native/prepare.ps1') -OutputDirectory $RuntimeSource
} else {
    & (Join-Path $projectRoot 'tools/Freehand.Native/prepare.ps1') -OutputDirectory $RuntimeSource -VerifyOnly
}
$runtimeDirectory = (Resolve-Path -LiteralPath $RuntimeSource).Path
# The SDK can reuse composite component images after switching publish modes.
# Regenerate them so every image matches this noncomposite publish.
$appIntermediate = [IO.Path]::GetFullPath((Join-Path $projectRoot 'src/Freehand.App/obj')) + [IO.Path]::DirectorySeparatorChar
$readyToRunCache = [IO.Path]::GetFullPath((Join-Path $appIntermediate 'Release/net10.0/win-x64/R2R'))
if (-not $readyToRunCache.StartsWith($appIntermediate, [StringComparison]::OrdinalIgnoreCase)) { throw 'R2R cache must remain inside the app intermediate directory.' }
if (Test-Path -LiteralPath $readyToRunCache) { Remove-Item -LiteralPath $readyToRunCache -Recurse -Force }
$build = (git -C $projectRoot rev-parse --short HEAD).Trim()
if (git -C $projectRoot status --porcelain) { $build += '-dirty' }
$version = Get-FreehandVersion
& $dotnetPath publish (Join-Path $projectRoot 'src/Freehand.App/Freehand.App.csproj') -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=false -p:PublishReadyToRun=true -p:PublishReadyToRunComposite=false `
    "-p:InformationalVersion=$version-accuracy+$build" --output $publishDirectory
if ($LASTEXITCODE -ne 0) { throw 'Accuracy preview publish failed.' }
Copy-Item -LiteralPath (Join-Path $projectRoot 'src/Freehand.Speech/Assets/parakeet-110m.bpe.vocab'),
    (Join-Path $projectRoot 'src/Freehand.Speech/speech-cpu.config') -Destination $publishDirectory -Force
foreach ($previousNative in Get-ChildItem -LiteralPath $publishDirectory -Filter 'ggml*.dll' -File) {
    if ($previousNative.Name -notin $runtimeManifest.Files.Name) {
        Remove-Item -LiteralPath $previousNative.FullName
    }
}
foreach ($asset in $runtimeManifest.Files) {
    Copy-Item -LiteralPath (Join-Path $runtimeDirectory $asset.Name) -Destination $publishDirectory -Force
}
Copy-Item -LiteralPath (Join-Path $runtimeDirectory 'native-build.json') -Destination $publishDirectory -Force
$oldComposite = Join-Path $publishDirectory 'Freehand.App.r2r.dll'
if (Test-Path -LiteralPath $oldComposite) { Remove-Item -LiteralPath $oldComposite }
$licenses = Join-Path $publishDirectory 'licenses'
New-Item -ItemType Directory -Force -Path $licenses | Out-Null
$nativeNotices = Join-Path $licenses 'transcribe'
New-Item -ItemType Directory -Force -Path $nativeNotices | Out-Null
foreach ($notice in $runtimeManifest.Licenses) {
    $noticeTarget = Join-Path $nativeNotices $notice.Name
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $noticeTarget) | Out-Null
    Copy-Item -LiteralPath (Join-Path $runtimeDirectory ('licenses/' + $notice.Name)) -Destination $noticeTarget -Force
}
foreach ($notice in Get-ChildItem -LiteralPath (Join-Path $projectRoot 'packaging/accuracy-licenses') -File) {
    Copy-Item -LiteralPath $notice.FullName -Destination $licenses -Force
}
Copy-Item -LiteralPath (Join-Path (Split-Path $dotnetPath) 'LICENSE.txt'),(Join-Path (Split-Path $dotnetPath) 'ThirdPartyNotices.txt') -Destination $licenses -Force
$assets = Get-Content (Join-Path $projectRoot 'src/Freehand.App/obj/project.assets.json') -Raw | ConvertFrom-Json -AsHashtable
$packageRoot = @($assets.packageFolders.Keys)[0]
foreach ($library in $assets.libraries.GetEnumerator()) {
    if ($library.Value.type -ne 'package') { continue }
    $folder = Join-Path $packageRoot $library.Value.path
    $label = $library.Key.Replace('/', '-')
    foreach ($notice in Get-ChildItem -LiteralPath $folder -File -Recurse | Where-Object { $_.Name -match '(?i)^(license|licence|copying|third.?party|notice)' -and $_.Length -lt 2MB }) {
        Copy-Item -LiteralPath $notice.FullName -Destination (Join-Path $licenses ($label + '-' + $notice.Name)) -Force
    }
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'packaging/accuracy-NOTICES.txt') -Destination (Join-Path $publishDirectory 'THIRD-PARTY-NOTICES.txt') -Force
$modelTarget = Join-Path $publishDirectory ('models/' + $modelManifest.DirectoryName)
New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
foreach ($asset in $modelManifest.Files) {
    $destination = Join-Path $modelTarget $asset.Name
    Copy-Item -LiteralPath (Join-Path $modelCache $asset.Name) -Destination $destination -Force
    if ((Get-Item -LiteralPath $destination).Length -ne $asset.Size -or
        (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash -ine $asset.Sha256) {
        throw "Published model checksum failed: $($asset.Name)"
    }
}
foreach ($previousModel in Get-ChildItem -LiteralPath $modelTarget -File -Filter '*.gguf') {
    if ($previousModel.Name -notin $modelManifest.Files.Name) { Remove-Item -LiteralPath $previousModel.FullName }
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'packaging/accuracy-model-manifest.json') -Destination (Join-Path $modelTarget 'manifest.json') -Force
$fixtureDirectory = Join-Path $publishDirectory 'fixtures'
New-Item -ItemType Directory -Force -Path $fixtureDirectory | Out-Null
$fixture = Join-Path $fixtureDirectory 'jfk.wav'
Copy-Item -LiteralPath (Join-Path $projectRoot 'artifacts/model-cache/jfk.wav') -Destination $fixture -Force
if ((Get-FileHash -LiteralPath $fixture -Algorithm SHA256).Hash -ine '59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e') { throw 'Fixture checksum failed.' }
$settingsPath = Join-Path $dataDirectory 'settings.json'
$settings = if (Test-Path -LiteralPath $settingsPath) { Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json -AsHashtable } else { @{} }
$settings.ModelDirectory = $modelTarget
$settings.StartAtLogin = $false
$settings | ConvertTo-Json | Set-Content -LiteralPath $settingsPath
$executable = Join-Path $publishDirectory 'Freehand.App.exe'
@"
@echo off
set "FREEHAND_DATA_DIRECTORY=$dataDirectory"
set "FREEHAND_MODEL_PROFILE=accuracy-vulkan"
set "GGML_VK_DISABLE_HOST_VISIBLE_VIDMEM=1"
set "GGML_VK_DISABLE_COOPMAT2=1"
set "GGML_VK_VISIBLE_DEVICES="
start "" "%~dp0Freehand.App.exe"
"@ | Set-Content -LiteralPath (Join-Path $publishDirectory 'Start Freehand Accuracy.cmd') -Encoding ascii
function New-AccuracyProcess {
    $start = [Diagnostics.ProcessStartInfo]::new($executable)
    $start.UseShellExecute = $false
    $start.WorkingDirectory = $publishDirectory
    $start.Environment['FREEHAND_DATA_DIRECTORY'] = $dataDirectory
    $start.Environment['FREEHAND_MODEL_PROFILE'] = 'accuracy-vulkan'
    $start.Environment['GGML_VK_DISABLE_HOST_VISIBLE_VIDMEM'] = '1'
    $start.Environment['GGML_VK_DISABLE_COOPMAT2'] = '1'
    $start.Environment.Remove('GGML_VK_VISIBLE_DEVICES') | Out-Null
    return $start
}
$selftest = New-AccuracyProcess
$selftest.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
$selftest.ArgumentList.Add('--selftest')
$check = [Diagnostics.Process]::Start($selftest)
$check.WaitForExit()
if ($check.ExitCode -ne 0) { throw "Accuracy preview self-test failed: $($check.ExitCode)" }
$check.Dispose()
$identity = [ordered]@{ Build=$build; Model=$modelManifest.Version; Runtime=$runtimeManifest.Version
    NativeBuildSha256=(Get-FileHash -LiteralPath (Join-Path $publishDirectory 'native-build.json')).Hash.ToLowerInvariant(); Files=@(
    foreach ($name in @('Freehand.App.exe') + @($runtimeManifest.Files.Name)) {
        $file = Get-Item -LiteralPath (Join-Path $publishDirectory $name)
        [ordered]@{ Name=$name; Size=$file.Length; Sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
    }
) }
$identity | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $publishDirectory 'accuracy-build.json') -Encoding utf8NoBOM
Write-Output "Verified accuracy preview: $executable"
if ($BuildOnly) { return }
$start = New-AccuracyProcess
if ($Benchmark) {
    $start.ArgumentList.Add('--desktop-delivery-benchmark')
    $start.ArgumentList.Add((Join-Path $projectRoot 'work/desktop-accuracy-preview.json'))
    $start.ArgumentList.Add('--require-gpu-telemetry')
}
$app = [Diagnostics.Process]::Start($start)
Write-Output "Accuracy preview process $($app.Id), profile $dataDirectory"

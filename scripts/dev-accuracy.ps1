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
    $RuntimeSource = Join-Path $projectRoot 'artifacts/native-cache/transcribe-freehand'
    & (Join-Path $projectRoot 'tools/Freehand.Native/prepare.ps1') -OutputDirectory $RuntimeSource
}
$runtimeDirectory = (Resolve-Path -LiteralPath $RuntimeSource).Path
$builtRuntime = $null
$buildRecord = Join-Path $runtimeDirectory 'native-build.json'
if (Test-Path -LiteralPath $buildRecord) {
    $builtRuntime = Get-Content -LiteralPath $buildRecord -Raw | ConvertFrom-Json
    $nativeSpec = Get-Content -LiteralPath (Join-Path $projectRoot 'tools/Freehand.Native/source-manifest.json') -Raw | ConvertFrom-Json
    if ($builtRuntime.SourceRevision -ne $nativeSpec.SourceRevision -or $builtRuntime.PatchSha256 -ine $nativeSpec.PatchSha256 -or
        $builtRuntime.SourceArchiveSha256 -ine $nativeSpec.SourceArchiveSha256 -or $builtRuntime.RuntimeArchiveSha256 -ine $nativeSpec.RuntimeArchiveSha256) {
        throw 'Native build record does not match the pinned source and patch.'
    }
}
foreach ($asset in $runtimeManifest.Files) {
    $sourceFile = Join-Path $runtimeDirectory $asset.Name
    $expected = $asset
    if ($asset.Name -eq 'transcribe.dll' -and $builtRuntime) {
        $nativeDlls = @($builtRuntime.Files | Where-Object Name -eq 'transcribe.dll')
        if ($nativeDlls.Count -ne 1) { throw 'Native build record must identify one transcribe.dll.' }
        $expected = $nativeDlls[0]
    }
    if ((Get-Item -LiteralPath $sourceFile).Length -ne $expected.Size -or
        (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash -ine $expected.Sha256) {
        throw "Accuracy runtime checksum failed: $($asset.Name)"
    }
}
$build = (git -C $projectRoot rev-parse --short HEAD).Trim()
if (git -C $projectRoot status --porcelain) { $build += '-dirty' }
$version = Get-FreehandVersion
& $dotnetPath publish (Join-Path $projectRoot 'src/Freehand.App/Freehand.App.csproj') -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=false "-p:InformationalVersion=$version-accuracy+$build" --output $publishDirectory
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
if ($builtRuntime) { Copy-Item -LiteralPath $buildRecord -Destination $publishDirectory -Force }
$licenses = Join-Path $publishDirectory 'licenses'
New-Item -ItemType Directory -Force -Path $licenses | Out-Null
$nativeNotices = Join-Path $licenses 'transcribe'
New-Item -ItemType Directory -Force -Path $nativeNotices | Out-Null
foreach ($notice in Get-ChildItem -LiteralPath (Join-Path $runtimeDirectory 'licenses') -File) {
    Copy-Item -LiteralPath $notice.FullName -Destination $nativeNotices -Force
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
    Copy-Item -LiteralPath (Join-Path $modelCache $asset.Name) -Destination $modelTarget -Force
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
$identity = [ordered]@{ Build=$build; Model=$modelManifest.Version; Runtime=$runtimeManifest.Version; Files=@(
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

#Requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$OutputDirectory,
    [string]$SourceArchive,
    [string]$RuntimeArchive,
    [string]$CMake = 'cmake',
    [string]$Ninja = 'ninja',
    [switch]$VerifyOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$spec = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'source-manifest.json') -Raw | ConvertFrom-Json
$runtimeSpec = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../../packaging/accuracy-runtime-manifest.json') -Raw | ConvertFrom-Json
if ($spec.Version -ne $runtimeSpec.Version -or $spec.SourceRevision -ne $runtimeSpec.SourceRevision) { throw 'Native source and runtime manifests disagree.' }
$officialFiles = @($runtimeSpec.Files | Where-Object Name -ne 'transcribe.dll') + @($runtimeSpec.Licenses | ForEach-Object {
    [pscustomobject]@{ Name='licenses/' + $_.Name; Size=$_.Size; Sha256=$_.Sha256 }
})
$patch = Join-Path $PSScriptRoot $spec.Patch
if ((Get-FileHash -LiteralPath $patch -Algorithm SHA256).Hash -ine $spec.PatchSha256) {
    throw 'Native source patch checksum failed.'
}
$output = [IO.Path]::TrimEndingDirectorySeparator([IO.Path]::GetFullPath($OutputDirectory))
$buildRecordPath = Join-Path $output 'native-build.json'

# A completed cache is verified without requiring a compiler on every launch.
if (Test-Path -LiteralPath $buildRecordPath) {
    $cached = Get-Content -LiteralPath $buildRecordPath -Raw | ConvertFrom-Json
    if ($cached.Version -ne $spec.Version -or $cached.SourceRevision -ne $spec.SourceRevision -or $cached.PatchSha256 -ine $spec.PatchSha256 -or
        $cached.SourceArchiveSha256 -ine $spec.SourceArchiveSha256 -or $cached.RuntimeArchiveSha256 -ine $runtimeSpec.RuntimeArchiveSha256 -or
        @($cached.Files).Count -ne $officialFiles.Count + 1) {
        throw 'Native cache was built from different inputs. Choose a fresh OutputDirectory.'
    }
    foreach ($file in $officialFiles) {
        $saved = @($cached.Files | Where-Object Name -eq $file.Name)
        if ($saved.Count -ne 1 -or $saved[0].Size -ne $file.Size -or $saved[0].Sha256 -ine $file.Sha256) {
            throw "Native cache record differs from the official payload: $($file.Name)"
        }
        $path = Join-Path $output $file.Name
        if ((Get-Item -LiteralPath $path).Length -ne $file.Size -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $file.Sha256) {
            throw "Native cache checksum failed: $($file.Name)"
        }
    }
    $native = @($cached.Files | Where-Object Name -eq 'transcribe.dll')
    if ($native.Count -ne 1 -or $native[0].Sha256 -ieq $spec.StockTranscribeSha256) {
        throw 'The reader runtime requires a source-built transcribe.dll; stock is not accepted.'
    }
    $path = Join-Path $output 'transcribe.dll'
    if ((Get-Item -LiteralPath $path).Length -ne $native[0].Size -or (Get-FileHash -LiteralPath $path).Hash -ine $native[0].Sha256) {
        throw 'Native cache checksum failed: transcribe.dll'
    }
    Write-Output "Verified reader runtime: $output"
    return
}
if ($VerifyOnly) { throw 'The reader runtime requires a verified native-build.json record.' }
New-Item -ItemType Directory -Path $output -Force | Out-Null

function Resolve-NativeTool([string]$Name) {
    return (Get-Command $Name -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
}
$cmakePath = Resolve-NativeTool $CMake
$ninjaPath = Resolve-NativeTool $Ninja
$gitPath = Resolve-NativeTool 'git'
$tarPath = Resolve-NativeTool 'tar'
$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio/Installer/vswhere.exe'
$installation = & $vswhere -all -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) { throw 'Visual Studio C++ Build Tools for x64 are required for a fresh reader runtime.' }
$installation = $installation.Trim()
$vcvars = Join-Path $installation 'VC/Auxiliary/Build/vcvars64.bat'
$toolDirectory = Get-ChildItem -LiteralPath (Join-Path $installation 'VC/Tools/MSVC') -Directory |
    Sort-Object { [version]$_.Name } -Descending | Select-Object -First 1
$compilerTools = Join-Path $toolDirectory.FullName 'bin/Hostx64/x64'

# Capture vcvars in this process, then invoke tools with PowerShell argument
# arrays. Output/source paths are never interpolated into shell commands.
$compilerEnvironment = & $env:ComSpec /d /c "`"$vcvars`" >nul && set"
if ($LASTEXITCODE -ne 0) { throw 'Visual Studio environment initialization failed.' }
foreach ($line in $compilerEnvironment) {
    if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
}

$downloads = Join-Path $output '_downloads'
New-Item -ItemType Directory -Path $downloads -Force | Out-Null
function Get-VerifiedArchive([string]$Provided, [string]$Url, [string]$Hash, [string]$Name) {
    $path = if ($Provided) { (Resolve-Path -LiteralPath $Provided).Path } else { Join-Path $downloads $Name }
    if (-not (Test-Path -LiteralPath $path)) { Invoke-WebRequest -Uri $Url -OutFile $path }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $Hash) { throw "Native archive checksum failed: $Name" }
    return $path
}
$sourceInput = Get-VerifiedArchive $SourceArchive $spec.SourceArchive $spec.SourceArchiveSha256 'source.tar.gz'
$runtimeInput = Get-VerifiedArchive $RuntimeArchive $runtimeSpec.RuntimeArchive $runtimeSpec.RuntimeArchiveSha256 'runtime.tar.gz'

# Each attempt gets fresh source/build directories. Failed attempts remain for
# diagnosis; no recursive cleanup or changes to an existing checkout occur.
$attempt = Join-Path $output ('_build/' + [guid]::NewGuid().ToString('N'))
$source = Join-Path $attempt 'source'
$runtime = Join-Path $attempt 'runtime'
$imports = Join-Path $attempt 'imports'
$build = Join-Path $attempt 'build'
New-Item -ItemType Directory -Path $source,$runtime,$imports -Force | Out-Null
# Windows tar cannot create this upstream editor-instruction symlink. It is
# unrelated to the native build inputs.
& $tarPath -xzf $sourceInput -C $source --strip-components=1 --exclude '*/ggml/.pi/SYSTEM.md'
if ($LASTEXITCODE -ne 0) { throw 'Native source extraction failed.' }
$runtimePrefix = $runtimeSpec.RuntimePrefix
$runtimeMembers = @($officialFiles | ForEach-Object { "$runtimePrefix/$($_.Name)" })
& $tarPath -xzf $runtimeInput -C $runtime --strip-components=1 @runtimeMembers
if ($LASTEXITCODE -ne 0) { throw 'Official GGML extraction failed.' }
foreach ($file in $officialFiles) {
    $path = Join-Path $runtime $file.Name
    if ((Get-Item -LiteralPath $path).Length -ne $file.Size -or
        (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $file.Sha256) {
        throw "Official GGML payload checksum failed: $($file.Name)"
    }
}

# Absolute --directory confines this trusted, checksum-pinned patch to the
# fresh extracted source, independently of any enclosing Git checkout.
& $gitPath apply --check --unsafe-paths "--directory=$source" $patch
if ($LASTEXITCODE -ne 0) { throw 'Native patch does not match the pinned source.' }
& $gitPath apply --unsafe-paths "--directory=$source" $patch
if ($LASTEXITCODE -ne 0) { throw 'Native patch failed.' }

foreach ($name in @('ggml-base','ggml')) {
    $dump = & (Join-Path $compilerTools 'dumpbin.exe') /exports (Join-Path $runtime "$name.dll")
    if ($LASTEXITCODE -ne 0) { throw "Could not read exports: $name" }
    $exports = foreach ($line in $dump) { if ($line -match '^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(\S+)') { $Matches[1] } }
    if (-not $exports) { throw "No DLL exports found: $name" }
    $definition = Join-Path $imports "$name.def"
    @("LIBRARY $name.dll", 'EXPORTS') + $exports | Set-Content -LiteralPath $definition -Encoding ascii
    & (Join-Path $compilerTools 'lib.exe') /nologo /machine:x64 "/def:$definition" "/out:$(Join-Path $imports "$name.lib")"
    if ($LASTEXITCODE -ne 0) { throw "Import-library generation failed: $name" }
}
$configure = @('-S',$source,'-B',$build,'-G','Ninja',"-DCMAKE_MAKE_PROGRAM=$ninjaPath",'-DCMAKE_BUILD_TYPE=Release',
    '-DTRANSCRIBE_BUILD_SHARED=ON','-DTRANSCRIBE_GGML_BACKEND_DL=ON','-DTRANSCRIBE_BUILD_TESTS=OFF',
    '-DTRANSCRIBE_BUILD_EXAMPLES=OFF','-DTRANSCRIBE_BUILD_TOOLS=OFF','-DTRANSCRIBE_INSTALL=OFF',
    '-DTRANSCRIBE_USE_SYSTEM_BLAS=OFF','-DTRANSCRIBE_USE_OPENMP=OFF','-DTRANSCRIBE_METAL=OFF',
    '-DTRANSCRIBE_VULKAN=OFF','-DTRANSCRIBE_CUDA=OFF',"-DTRANSCRIBE_PREBUILT_GGML_DIR=$runtime", "-DTRANSCRIBE_PREBUILT_IMPLIB_DIR=$imports")
& $cmakePath @configure
if ($LASTEXITCODE -ne 0) { throw 'Native CMake configuration failed.' }
& $cmakePath --build $build --target transcribe --parallel 2
if ($LASTEXITCODE -ne 0) { throw 'Native build failed.' }

Copy-Item -LiteralPath (Join-Path $build 'bin/transcribe.dll') -Destination (Join-Path $output 'transcribe.dll') -Force
foreach ($file in $officialFiles) {
    $destination = Join-Path $output $file.Name
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $runtime $file.Name) -Destination $destination -Force
}
$payloadNames = @('transcribe.dll') + @($officialFiles.Name)
$files = foreach ($name in $payloadNames) {
    $file = Get-Item -LiteralPath (Join-Path $output $name)
    [ordered]@{ Name = $name; Size = $file.Length; Sha256 = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
if ($files[0].Sha256 -ieq $spec.StockTranscribeSha256) { throw 'Source build unexpectedly produced the stock runtime.' }
$record = [ordered]@{
    Version = $spec.Version; SourceRevision = $spec.SourceRevision
    SourceArchiveSha256 = $spec.SourceArchiveSha256; RuntimeArchiveSha256 = $runtimeSpec.RuntimeArchiveSha256
    PatchSha256 = $spec.PatchSha256
    PreparationScriptSha256 = (Get-FileHash -LiteralPath $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant()
    CompilerVersion = (Get-Item -LiteralPath (Join-Path $compilerTools 'cl.exe')).VersionInfo.FileVersion
    VisualStudio = $installation; CMakeVersion = (& $cmakePath --version | Select-Object -First 1)
    NinjaVersion = (& $ninjaPath --version); ConfigureArguments = $configure; Files = @($files)
    BuildPolicy = 'Pinned source build; PE hashes may vary with toolchain and paths. Exact local output hashes are recorded.'
}
$record | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $buildRecordPath -Encoding utf8NoBOM
Write-Output "Prepared reader runtime: $output"

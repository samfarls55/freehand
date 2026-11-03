#Requires -Version 7.0
[CmdletBinding()]
param(
    [string]$ManifestPath,
    [string]$RuntimeManifestPath,
    [ValidateSet('win-x64-cpu', 'win-x64-vulkan', 'linux-x64-cpu')][string]$Platform = 'win-x64-cpu',
    [string]$CacheDirectory,
    [string]$OutputDirectory,
    [switch]$Offline,
    [switch]$ValidateManifestOnly,
    [switch]$LinkModel
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $ManifestPath) { $ManifestPath = Join-Path $repositoryRoot 'packaging/cleanup-model-manifest.json' }
if (-not $RuntimeManifestPath) { $RuntimeManifestPath = Join-Path $repositoryRoot 'packaging/cleanup-runtime-manifest.json' }
if (-not $CacheDirectory) { $CacheDirectory = Join-Path $repositoryRoot 'artifacts/cleanup-downloads' }

function Assert-CleanupDownload($Artifact) {
    $uri = $null
    if (-not [uri]::TryCreate($Artifact.Source, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Query -or $uri.Fragment) {
        throw 'Cleanup artifact sources must use HTTPS without credentials, query strings or fragments.'
    }
    if ($Artifact.Sha256 -notmatch '\A[0-9a-fA-F]{64}\z' -or
        ($Artifact.Size -isnot [int] -and $Artifact.Size -isnot [long]) -or $Artifact.Size -lt 1) {
        throw 'Cleanup downloads require an exact positive byte size and SHA-256.'
    }
}

function Assert-CleanupDownloadFile([string]$Path, $Artifact) {
    if ((Get-Item -LiteralPath $Path).Length -ne $Artifact.Size -or
        (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ine $Artifact.Sha256) {
        throw "Cleanup download verification failed: $([IO.Path]::GetFileName($Path))"
    }
}

function Get-CleanupDownload($Artifact, [string]$Extension) {
    $path = Join-Path $CacheDirectory ($Artifact.Sha256.ToLowerInvariant() + $Extension)
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        Assert-CleanupDownloadFile $path $Artifact
        return $path
    }
    if ($Offline) { throw 'A pinned cleanup artifact is missing from the offline cache.' }
    $partial = $path + '.partial-' + [guid]::NewGuid().ToString('N')
    try {
        Invoke-WebRequest -Uri $Artifact.Source -OutFile $partial -TimeoutSec 1800
        Assert-CleanupDownloadFile $partial $Artifact
        [IO.File]::Move($partial, $path)
        return $path
    } finally {
        if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
    }
}

$selected = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$runtime = Get-Content -LiteralPath $RuntimeManifestPath -Raw | ConvertFrom-Json
if ($null -ne $selected.PSObject.Properties['RuntimePlatform']) {
    if ($selected.RuntimePlatform -isnot [string] -or $selected.RuntimePlatform -cnotin @('win-x64-cpu', 'win-x64-vulkan')) {
        throw 'Cleanup setup requires a supported pinned Windows runtime platform.'
    }
    if (-not $PSBoundParameters.ContainsKey('Platform')) { $Platform = $selected.RuntimePlatform }
}
$Platform = $Platform.ToLowerInvariant()
if (-not $OutputDirectory) {
    $folder = switch ($Platform) { 'win-x64-vulkan' { 'artifacts/cleanup-assets-vulkan' } 'linux-x64-cpu' { 'artifacts/cleanup-assets-linux' } default { 'artifacts/cleanup-assets' } }
    $OutputDirectory = Join-Path $repositoryRoot $folder
}
if ($selected.SchemaVersion -ne 1 -or $runtime.SchemaVersion -ne 1 -or
    [string]::IsNullOrWhiteSpace($selected.ModelId) -or $selected.ModelId.Length -gt 256 -or
    $selected.ModelId -match '[\x00-\x1f]' -or
    $selected.PromptStyle -notin @('QuillChatMl', 'Qwen35', 'Ministral3', 'Gemma4', 'S1Mini', 'HandyEditor', 'HandyEditorUserOnly',
        'Emberon2', 'BitVoiceSmol', 'KuduTinyPolished', 'LocalflowClean', 'SpokenlyCleanup', 'ScribeKeyFast', 'Sotto',
        'GenericChat', 'SmolPostAsr') -or
    $selected.Model.Revision -notmatch '\A[0-9a-fA-F]{40}\z' -or
    $runtime.SourceCommit -notmatch '\A[0-9a-fA-F]{40}\z') {
    throw 'Cleanup acquisition manifests require a selected model, prompt style and immutable source revisions.'
}
$artifacts = @($runtime.Artifacts | Where-Object { $_.Platform -eq $Platform })
if ($artifacts.Count -ne 1) { throw 'Cleanup runtime manifest must select exactly one artifact for the requested platform.' }
$native = $artifacts[0]
$archive = [pscustomobject]@{ Source = $native.Source; Sha256 = $native.ArchiveSha256; Size = $native.ArchiveSize }
foreach ($artifact in @($selected.Model, $selected.ModelLicense, $selected.RuntimeLicense, $archive)) { Assert-CleanupDownload $artifact }
foreach ($artifact in @($selected.ModelNotices)) { if ($null -ne $artifact) { Assert-CleanupDownload $artifact } }
$expectedExecutable = if ($Platform -in @('win-x64-cpu', 'win-x64-vulkan')) { 'llama-server.exe' } else { 'llama-server' }
if ($native.Executable -cne $expectedExecutable -or $native.ExecutableSha256 -notmatch '\A[0-9a-fA-F]{64}\z') {
    throw 'Cleanup runtime manifest does not pin the expected executable.'
}
if ($selected.Model.Source -match '^https://huggingface\.co/' -and
    $selected.Model.Source -notlike "*/resolve/$($selected.Model.Revision)/*") {
    throw 'Hugging Face cleanup downloads must resolve the pinned model revision.'
}
$noticeNames = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($notice in @($selected.ModelNotices)) {
    if ($null -eq $notice) { continue }
    if ($notice.Name -notmatch '^[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:txt|md)$' -or -not $noticeNames.Add($notice.Name)) {
        throw 'Cleanup model notice names must be distinct text filenames without path separators.'
    }
}
$limits = @{
    Threads = @(1, 256); ContextSize = @(256, 1048576); MaxOutputTokens = @(1, 1048575)
    GpuLayers = @(0, 1000); StartupTimeoutSeconds = @(1, 1800); IdleTimeoutSeconds = @(0, 86400)
    BatchSize = @(1, 8192); MicroBatchSize = @(1, 8192); PromptCacheMiB = @(0, 8192); ContextCheckpoints = @(0, 32)
    PromptLookupTokens = @(0, 64); PromptLookupMatchTokens = @(1, 12)
}
$optionalSettings = @{ BatchSize = 128; MicroBatchSize = 128; PromptCacheMiB = 0; ContextCheckpoints = 0
    CacheTypeK = 'f16'; CacheTypeV = 'f16'; Repack = $true; MaskSpecialistLiterals = $false
    PromptLookupTokens = 0; PromptLookupMatchTokens = 3 }
foreach ($name in $optionalSettings.Keys) {
    if ($null -eq $selected.Inference.PSObject.Properties[$name]) {
        $selected.Inference | Add-Member -NotePropertyName $name -NotePropertyValue $optionalSettings[$name]
    }
}
foreach ($name in $limits.Keys) {
    $value = $selected.Inference.$name
    if (($value -isnot [int] -and $value -isnot [long]) -or $value -lt $limits[$name][0] -or $value -gt $limits[$name][1]) {
        throw "Cleanup inference limit is invalid: $name"
    }
}
if ($selected.Inference.MaxOutputTokens -ge $selected.Inference.ContextSize) { throw 'Cleanup maximum output must be smaller than the total context.' }
if ($selected.Inference.MicroBatchSize -gt $selected.Inference.BatchSize) { throw 'Cleanup micro-batch must not exceed the logical batch.' }
if ($selected.Inference.PromptLookupTokens -ge $selected.Inference.BatchSize) { throw 'Cleanup prompt lookup plus its sampled token must fit the logical batch.' }
foreach ($name in @('Repack', 'MaskSpecialistLiterals')) {
    if ($selected.Inference.$name -isnot [bool]) { throw "Cleanup inference switch must be a boolean: $name" }
}
foreach ($name in @('CacheTypeK', 'CacheTypeV')) {
    if ($selected.Inference.$name -isnot [string] -or $selected.Inference.$name -cnotin @('f16', 'q8_0', 'q4_0')) {
        throw "Cleanup cache type is invalid: $name"
    }
}

if ($ValidateManifestOnly) {
    return [pscustomobject]@{
        ModelId = $selected.ModelId; Platform = $Platform
        ModelManifestPath = (Resolve-Path -LiteralPath $ManifestPath).Path
        RuntimeManifestPath = (Resolve-Path -LiteralPath $RuntimeManifestPath).Path
    }
}

$CacheDirectory = [IO.Path]::GetFullPath($CacheDirectory)
New-Item -ItemType Directory -Path $CacheDirectory -Force | Out-Null
$modelPath = Get-CleanupDownload $selected.Model '.gguf'
$modelLicense = Get-CleanupDownload $selected.ModelLicense '.txt'
$runtimeLicense = Get-CleanupDownload $selected.RuntimeLicense '.txt'
$archivePath = Get-CleanupDownload $archive $(if ($Platform -in @('win-x64-cpu', 'win-x64-vulkan')) { '.zip' } else { '.tar.gz' })
$stage = Join-Path $CacheDirectory ('.cleanup-extract-' + [guid]::NewGuid().ToString('N'))
try {
    New-Item -ItemType Directory -Path $stage -Force | Out-Null
    $noticePaths = @()
    foreach ($notice in @($selected.ModelNotices)) {
        if ($null -eq $notice) { continue }
        $noticeInput = Get-CleanupDownload $notice '.txt'
        $noticePath = Join-Path $stage $notice.Name
        Copy-Item -LiteralPath $noticeInput -Destination $noticePath
        $noticePaths += $noticePath
    }
    $extracted = Join-Path $stage 'runtime'
    New-Item -ItemType Directory -Path $extracted -Force | Out-Null
    if ($Platform -in @('win-x64-cpu', 'win-x64-vulkan')) {
        # Authenticate the complete archive before extracting any native code.
        Expand-Archive -LiteralPath $archivePath -DestinationPath $extracted
    } else {
        & tar -xzf $archivePath -C $extracted
        if ($LASTEXITCODE -ne 0) { throw 'Cleanup runtime archive extraction failed.' }
    }
    $executables = @(Get-ChildItem -LiteralPath $extracted -File -Recurse -Filter $expectedExecutable)
    if ($executables.Count -ne 1 -or
        (Get-FileHash -LiteralPath $executables[0].FullName -Algorithm SHA256).Hash -ine $native.ExecutableSha256) {
        throw 'Cleanup runtime executable does not match its pinned manifest.'
    }
    $prepare = @{
        RuntimeDirectory = $executables[0].DirectoryName; ModelPath = $modelPath; ModelId = $selected.ModelId
        PromptStyle = $selected.PromptStyle; ModelLicense = $modelLicense; RuntimeLicense = $runtimeLicense
        ModelNotices = $noticePaths; Platform = $Platform; LinkModel = $LinkModel
        OutputDirectory = $OutputDirectory; ModelSourceUrl = $selected.Model.Source; ModelRevision = $selected.Model.Revision
        RuntimeSourceUrl = $native.Source; RuntimeRevision = $runtime.SourceCommit
    }
    foreach ($name in $limits.Keys) { $prepare[$name] = $selected.Inference.$name }
    foreach ($name in @('CacheTypeK', 'CacheTypeV', 'Repack', 'MaskSpecialistLiterals')) { $prepare[$name] = $selected.Inference.$name }
    return & (Join-Path $PSScriptRoot 'prepare-cleanup.ps1') @prepare
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
}

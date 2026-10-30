#Requires -Version 7.0
[CmdletBinding(DefaultParameterSetName = 'Prepare')]
param(
    [Parameter(Mandatory, ParameterSetName = 'Prepare')][string]$RuntimeDirectory,
    [Parameter(Mandatory, ParameterSetName = 'Prepare')][string]$ModelPath,
    [Parameter(Mandatory, ParameterSetName = 'Prepare')][string]$ModelId,
    [Parameter(Mandatory, ParameterSetName = 'Prepare')]
    [ValidateSet('QuillChatMl', 'Qwen35', 'Ministral3', 'Gemma4')][string]$PromptStyle,
    [Parameter(Mandatory, ParameterSetName = 'Prepare')][string]$ModelLicense,
    [Parameter(Mandatory, ParameterSetName = 'Prepare')][string]$RuntimeLicense,
    [Parameter(ParameterSetName = 'Prepare')][string]$OutputDirectory,
    [Parameter(ParameterSetName = 'Prepare')][string]$ModelSourceUrl,
    [Parameter(ParameterSetName = 'Prepare')][string]$ModelRevision,
    [Parameter(ParameterSetName = 'Prepare')][string]$RuntimeSourceUrl,
    [Parameter(ParameterSetName = 'Prepare')][string]$RuntimeRevision,
    [Parameter(ParameterSetName = 'Prepare')][ValidateRange(1, 256)][int]$Threads = 4,
    [Parameter(ParameterSetName = 'Prepare')][ValidateRange(256, 1048576)][int]$ContextSize = 8192,
    [Parameter(ParameterSetName = 'Prepare')][ValidateRange(1, 1048575)][int]$MaxOutputTokens = 2048,
    [Parameter(ParameterSetName = 'Prepare')][ValidateRange(0, 1000)][int]$GpuLayers = 0,
    [Parameter(ParameterSetName = 'Prepare')][ValidateRange(1, 1800)][int]$StartupTimeoutSeconds = 60,
    [Parameter(ParameterSetName = 'Prepare')][ValidateRange(0, 86400)][int]$IdleTimeoutSeconds = 60,
    [Parameter(Mandatory, ParameterSetName = 'Validate')][string]$ValidateDirectory
)
$ErrorActionPreference = 'Stop'

function Get-CleanupRelativePath([string]$Path) {
    $relative = $Path.Replace('\', '/')
    if ([string]::IsNullOrWhiteSpace($relative) -or $relative -match '[\x00-\x1f:]' -or
        $relative.StartsWith('/') -or @($relative.Split('/') | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0) {
        throw 'Cleanup manifest contains an unsafe asset path.'
    }
    return $relative
}

function Get-CleanupAsset([string]$Directory, [string]$RelativePath) {
    $relative = Get-CleanupRelativePath $RelativePath
    $assetPath = Join-Path $Directory $relative
    if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) { throw "Cleanup asset is missing: $relative" }
    $current = Get-Item -LiteralPath $assetPath -Force
    while ($current -and $current.FullName -ne $Directory) {
        if (($current.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Cleanup assets must not be symbolic links: $relative"
        }
        $current = if ($current -is [IO.DirectoryInfo]) { $current.Parent } else { $current.Directory }
    }
    return Get-Item -LiteralPath $assetPath
}

function Get-PreparedCleanupBundle([string]$Directory) {
    $directoryPath = (Resolve-Path -LiteralPath $Directory).Path
    $manifestPath = Join-Path $directoryPath 'cleanup-manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Cleanup manifest is missing.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.schemaVersion -ne 1 -or [string]::IsNullOrWhiteSpace($manifest.modelId) -or
        $manifest.modelId.Length -gt 256 -or $manifest.modelId -match '[\x00-\x1f]' -or
        $manifest.promptStyle -notin @('QuillChatMl', 'Qwen35', 'Ministral3', 'Gemma4')) {
        throw 'Cleanup manifest model configuration is invalid.'
    }
    foreach ($name in @('threads', 'contextSize', 'maxOutputTokens', 'gpuLayers', 'startupTimeoutSeconds', 'idleTimeoutSeconds')) {
        if ($manifest.$name -isnot [int] -and $manifest.$name -isnot [long]) { throw 'Cleanup manifest inference limits must be integers.' }
    }
    if ($manifest.threads -lt 1 -or $manifest.threads -gt 256 -or $manifest.contextSize -lt 256 -or
        $manifest.maxOutputTokens -lt 1 -or $manifest.maxOutputTokens -ge $manifest.contextSize -or
        $manifest.gpuLayers -lt 0 -or $manifest.startupTimeoutSeconds -lt 1 -or $manifest.startupTimeoutSeconds -gt 1800 -or
        $manifest.idleTimeoutSeconds -lt 0 -or $manifest.idleTimeoutSeconds -gt 86400) {
        throw 'Cleanup manifest inference limits are invalid.'
    }
    $runtime = Get-CleanupRelativePath $manifest.runtimePath
    $model = Get-CleanupRelativePath $manifest.modelPath
    if ($runtime -ine 'runtime/llama-server.exe' -or $model -notmatch '\.gguf$') {
        throw 'Cleanup manifest must select a local llama-server.exe and GGUF model.'
    }
    $known = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $files = @($manifest.files)
    if ($files.Count -lt 4) { throw 'Cleanup manifest must include runtime, model and license assets.' }
    foreach ($file in $files) {
        $relative = Get-CleanupRelativePath $file.path
        $runtimeNotice = $relative -match '^licenses/runtime/(?:LICENSE|LICENCE|NOTICE|COPYING|THIRD[-_ ]?PARTY)[^/]*$' -and
            [IO.Path]::GetExtension($relative) -in @('', '.txt', '.md')
        $allowed = $relative -ieq $runtime -or $relative -ieq $model -or
            $relative -match '^runtime/[^/]+\.dll$' -or
            $relative -match '^licenses/(?:model-LICENSE\.txt|runtime-LICENSE\.txt)$' -or
            $runtimeNotice
        if (-not $allowed -or -not $known.Add($relative)) { throw 'Cleanup manifest contains an unsupported or duplicate asset.' }
        if ($file.sha256 -notmatch '\A[0-9a-fA-F]{64}\z' -or $file.size -lt 1 -or
            ($file.size -isnot [int] -and $file.size -isnot [long])) { throw 'Cleanup manifest asset metadata is invalid.' }
        $asset = Get-CleanupAsset $directoryPath $relative
        if ($asset.Length -ne $file.size -or (Get-FileHash -LiteralPath $asset.FullName -Algorithm SHA256).Hash -ine $file.sha256) {
            throw "Cleanup asset verification failed: $relative"
        }
    }
    foreach ($required in @($runtime, $model, 'licenses/model-LICENSE.txt', 'licenses/runtime-LICENSE.txt')) {
        if (-not $known.Contains($required)) { throw "Cleanup manifest omits a required asset: $required" }
    }
    $runtimeFile = @($files | Where-Object { $_.path.Replace('\', '/') -ieq $runtime })[0]
    $modelFile = @($files | Where-Object { $_.path.Replace('\', '/') -ieq $model })[0]
    if ($manifest.runtimeSha256 -ine $runtimeFile.sha256 -or $manifest.modelSha256 -ine $modelFile.sha256) {
        throw 'Cleanup manifest primary hashes disagree with its asset list.'
    }
    return [pscustomobject]@{ Directory = $directoryPath; ManifestPath = $manifestPath; ModelId = $manifest.modelId; Files = $files }
}

if ($PSCmdlet.ParameterSetName -eq 'Validate') { return Get-PreparedCleanupBundle $ValidateDirectory }

if ($MaxOutputTokens -ge $ContextSize) { throw 'MaxOutputTokens must be smaller than ContextSize.' }
if ([string]::IsNullOrWhiteSpace($ModelId) -or $ModelId.Length -gt 256 -or $ModelId -match '[\x00-\x1f]') {
    throw 'ModelId must contain a printable model identifier.'
}
foreach ($sourceUrl in @($ModelSourceUrl, $RuntimeSourceUrl)) {
    if (-not $sourceUrl) { continue }
    $parsed = $null
    if (-not [uri]::TryCreate($sourceUrl, [UriKind]::Absolute, [ref]$parsed) -or
        $parsed.Scheme -ne 'https' -or $parsed.UserInfo -or $parsed.Query -or $parsed.Fragment) {
        throw 'Source URLs must use HTTPS without credentials, query strings or fragments.'
    }
}
foreach ($revision in @($ModelRevision, $RuntimeRevision)) {
    if ($revision -match '[\x00-\x1f]') { throw 'Artifact revisions must be printable identifiers.' }
}
$runtimeInput = (Resolve-Path -LiteralPath $RuntimeDirectory).Path
$modelInput = (Resolve-Path -LiteralPath $ModelPath).Path
if ([IO.Path]::GetExtension($modelInput) -ine '.gguf') { throw 'ModelPath must select a GGUF file.' }
if (-not (Test-Path -LiteralPath $modelInput -PathType Leaf)) { throw 'ModelPath must select a GGUF file.' }
$serverInput = Join-Path $runtimeInput 'llama-server.exe'
if (-not (Test-Path -LiteralPath $serverInput -PathType Leaf)) { throw 'RuntimeDirectory must contain llama-server.exe.' }
$modelLicenseInput = (Resolve-Path -LiteralPath $ModelLicense).Path
$runtimeLicenseInput = (Resolve-Path -LiteralPath $RuntimeLicense).Path
foreach ($license in @($modelLicenseInput, $runtimeLicenseInput)) {
    $item = Get-Item -LiteralPath $license
    if ($item.PSIsContainer -or $item.Length -lt 1 -or $item.Length -gt 2MB) { throw 'License inputs must be nonempty text files no larger than 2 MiB.' }
}
if (-not $OutputDirectory) { $OutputDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) 'artifacts/cleanup-assets' }
$destination = [IO.Path]::GetFullPath($OutputDirectory)
$parentDirectory = Split-Path -Parent $destination
if (-not $parentDirectory -or $destination -eq [IO.Path]::GetPathRoot($destination)) { throw 'OutputDirectory must be a dedicated cleanup asset directory.' }
foreach ($inputPath in @($runtimeInput, $modelInput, $modelLicenseInput, $runtimeLicenseInput)) {
    if ($inputPath.Equals($destination, [StringComparison]::OrdinalIgnoreCase) -or
        $inputPath.StartsWith($destination + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'OutputDirectory must not contain any input artifacts.'
    }
}

$existingBundle = $null
if (Test-Path -LiteralPath $destination) {
    $existing = @(Get-ChildItem -LiteralPath $destination -Force)
    if ($existing.Count -gt 0) {
        $existingBundle = Get-PreparedCleanupBundle $destination
        $ownedFiles = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        [void]$ownedFiles.Add('cleanup-manifest.json')
        foreach ($file in $existingBundle.Files) { [void]$ownedFiles.Add($file.path.Replace('\', '/')) }
        foreach ($file in Get-ChildItem -LiteralPath $destination -File -Recurse -Force) {
            if (-not $ownedFiles.Contains([IO.Path]::GetRelativePath($destination, $file.FullName).Replace('\', '/'))) {
                throw 'OutputDirectory contains files outside its cleanup manifest; choose another directory.'
            }
        }
    }
}

New-Item -ItemType Directory -Path $parentDirectory -Force | Out-Null
$stage = Join-Path $parentDirectory ('.cleanup-prepare-' + [guid]::NewGuid().ToString('N'))
$backup = $null
$completed = $false
try {
    New-Item -ItemType Directory -Path (Join-Path $stage 'runtime'), (Join-Path $stage 'licenses/runtime') -Force | Out-Null
    Copy-Item -LiteralPath $serverInput -Destination (Join-Path $stage 'runtime/llama-server.exe')
    foreach ($file in Get-ChildItem -LiteralPath $runtimeInput -File -Filter '*.dll') {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $stage 'runtime')
    }
    foreach ($file in Get-ChildItem -LiteralPath $runtimeInput -File | Where-Object {
        $_.Name -match '^(LICENSE|LICENCE|NOTICE|COPYING|THIRD[-_ ]?PARTY)' -and $_.Extension -in @('', '.txt', '.md')
    }) {
        Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $stage 'licenses/runtime')
    }
    Copy-Item -LiteralPath $modelInput -Destination (Join-Path $stage 'model.gguf')
    Copy-Item -LiteralPath $modelLicenseInput -Destination (Join-Path $stage 'licenses/model-LICENSE.txt')
    Copy-Item -LiteralPath $runtimeLicenseInput -Destination (Join-Path $stage 'licenses/runtime-LICENSE.txt')
    $files = @(Get-ChildItem -LiteralPath $stage -File -Recurse | Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = [IO.Path]::GetRelativePath($stage, $_.FullName).Replace('\', '/')
            size = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
    $manifest = [ordered]@{
        schemaVersion = 1
        runtimePath = 'runtime/llama-server.exe'
        runtimeSha256 = (Get-FileHash -LiteralPath (Join-Path $stage 'runtime/llama-server.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
        modelPath = 'model.gguf'
        modelSha256 = (Get-FileHash -LiteralPath (Join-Path $stage 'model.gguf') -Algorithm SHA256).Hash.ToLowerInvariant()
        modelId = $ModelId
        promptStyle = $PromptStyle
        threads = $Threads
        contextSize = $ContextSize
        maxOutputTokens = $MaxOutputTokens
        gpuLayers = $GpuLayers
        startupTimeoutSeconds = $StartupTimeoutSeconds
        idleTimeoutSeconds = $IdleTimeoutSeconds
        modelSourceUrl = $ModelSourceUrl
        modelRevision = $ModelRevision
        runtimeSourceUrl = $RuntimeSourceUrl
        runtimeRevision = $RuntimeRevision
        files = $files
    }
    $temporaryManifest = Join-Path $stage 'cleanup-manifest.json.tmp'
    $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $temporaryManifest -Encoding utf8NoBOM
    [IO.File]::Move($temporaryManifest, (Join-Path $stage 'cleanup-manifest.json'))
    $null = Get-PreparedCleanupBundle $stage
    if (Test-Path -LiteralPath $destination) {
        $backup = Join-Path $parentDirectory ('.cleanup-previous-' + [guid]::NewGuid().ToString('N'))
        [IO.Directory]::Move($destination, $backup)
    }
    try { [IO.Directory]::Move($stage, $destination) }
    catch {
        if ($backup -and -not (Test-Path -LiteralPath $destination)) { [IO.Directory]::Move($backup, $destination); $backup = $null }
        throw
    }
    $result = Get-PreparedCleanupBundle $destination
    $completed = $true
    return $result
} finally {
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    if ($completed -and $backup -and (Test-Path -LiteralPath $backup)) { Remove-Item -LiteralPath $backup -Recurse -Force }
}

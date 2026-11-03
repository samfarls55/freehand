#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$ParseOnly,
    [string]$DeviceListingText,
    [string]$BundleDirectory,
    [string]$EvidenceDirectory,
    [ValidateSet('NvidiaVulkan', 'Cpu')][string]$Execution = 'NvidiaVulkan'
)
$ErrorActionPreference = 'Stop'

function Select-NvidiaVulkanFromListing([string]$Text) {
    $headers = @($Text -split '\r?\n' | Where-Object { $_ -cmatch '^Available devices:\s*$' })
    if ($headers.Count -ne 1) { throw 'Expected exactly one native Available devices section; preview not started.' }
    $afterHeader = $false
    $devices = @()
    foreach ($line in ($Text -split '\r?\n')) {
        if ($line -cmatch '^Available devices:\s*$') { $afterHeader = $true; continue }
        if (-not $afterHeader) { continue }
        if ($line -cmatch '^\s*(?<Device>Vulkan[0-9]+):\s+(?<Description>.+?)\s+\((?<Total>[0-9]+) MiB,\s+(?<Free>[0-9]+) MiB free\)\s*$') {
            $devices += [pscustomobject]@{ Name = $Matches.Device; Description = $Matches.Description
                TotalMiB = [UInt64]$Matches.Total; FreeMiB = [UInt64]$Matches.Free }
        } elseif ($line -match '^\s*Vulkan') {
            throw 'A Vulkan listing line was malformed; preview not started.'
        }
    }
    $uniqueNames = @($devices | Select-Object -ExpandProperty Name -Unique)
    if ($uniqueNames.Count -ne $devices.Count) { throw 'Duplicate Vulkan device names; preview not started.' }
    $nvidiaCandidates = @($devices | Where-Object { $_.Description -match '\bNVIDIA\b' })
    if ($nvidiaCandidates.Count -ne 1) { throw "Expected one NVIDIA Vulkan device, found $($nvidiaCandidates.Count); preview not started." }
    return [pscustomobject]@{ Selected = $nvidiaCandidates[0]; AvailableVulkanDevices = $devices }
}

function New-PreviewSelectionPath([string]$Directory) {
    if (-not $Directory) { return $null }
    New-Item -ItemType Directory -Path $Directory -Force | Out-Null
    $absoluteDirectory = (Resolve-Path -LiteralPath $Directory).ProviderPath
    $path = Join-Path $absoluteDirectory 'run-selection.json'
    if (Test-Path -LiteralPath $path) { throw 'Preserve existing run-selection.json; choose a fresh evidence directory.' }
    return $path
}
function Write-PreviewSelectionRecord($Record, [string]$Path) {
    if (-not $Path) { return }
    $encoding = New-Object Text.UTF8Encoding $false
    $bytes = $encoding.GetBytes(($Record | ConvertTo-Json -Depth 12) + "`n")
    $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}

if ($ParseOnly) {
    $recordPath = New-PreviewSelectionPath $EvidenceDirectory
    $parserRecord = [ordered]@{ Mode = 'ParserOnly'; Status = 'Starting'; DiscoveryStdout = $DeviceListingText
        WindowsNativeExecuted = $false; GpuExecutionProven = $false; SlaProven = $false }
    try {
        if ([string]::IsNullOrWhiteSpace($DeviceListingText)) { throw 'ParseOnly requires literal native-format listing text.' }
        $parserRecord.Parsed = Select-NvidiaVulkanFromListing $DeviceListingText
        $parserRecord.Status = 'Parsed'
        return [pscustomobject]$parserRecord
    } catch { $parserRecord.Status = 'Failed'; $parserRecord.Error = $_.Exception.Message; throw }
    finally { Write-PreviewSelectionRecord $parserRecord $recordPath }
}
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'This native preview discovery step requires Windows; no Windows executable or GPU was run.'
}
if (-not $BundleDirectory -or -not $EvidenceDirectory) { throw 'BundleDirectory and EvidenceDirectory are required.' }
$recordPath = New-PreviewSelectionPath $EvidenceDirectory
$envRemove = @('GGML_VK_VISIBLE_DEVICES', 'LLAMA_ARG_MAIN_GPU', 'LLAMA_ARG_SPLIT_MODE', 'LLAMA_ARG_TENSOR_SPLIT', 'LLAMA_ARG_OVERRIDE_TENSOR')
$record = [ordered]@{ SchemaVersion = 1; Execution = $Execution; Status = 'Starting'
    ScopedEnvironmentRemove = $envRemove; WindowsNativeExecuted = $false; ModelLoaded = $false
    GpuExecutionProven = $false; SlaProven = $false }
try {
    $bundle = (Resolve-Path -LiteralPath $BundleDirectory).Path
    $manifestPath = Join-Path $bundle 'cleanup-manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.platform -cne 'win-x64-vulkan' -or $manifest.runtimePath -cne 'runtime/llama-server.exe') {
        throw 'This discovery script requires a prepared win-x64-vulkan runtime bundle.'
    }
    if (($Execution -eq 'Cpu' -and $manifest.gpuLayers -ne 0) -or
        ($Execution -eq 'NvidiaVulkan' -and $manifest.gpuLayers -le 0)) {
        throw 'Selected execution mode disagrees with its isolated manifest GPU-layer setting.'
    }
    # Caller validates the full isolated bundle; repeat runtime verification before native discovery.
    $runtimeFiles = @($manifest.files | Where-Object { $_.path -cmatch '^runtime/[^/]+\.(?:exe|dll)$' })
    if (@($runtimeFiles | Where-Object path -ceq 'runtime/ggml-vulkan.dll').Count -ne 1) { throw 'Prepared runtime omits ggml-vulkan.dll.' }
    $serverEntries = @($runtimeFiles | Where-Object path -ceq 'runtime/llama-server.exe')
    if ($serverEntries.Count -ne 1 -or $manifest.runtimeSha256 -ine $serverEntries[0].sha256) { throw 'Native launcher hash disagrees with inventory.' }
    foreach ($file in $runtimeFiles) {
        if ($file.path.Contains('..') -or $file.path.Contains(':') -or $file.sha256 -notmatch '^[0-9a-fA-F]{64}$') { throw 'Unsafe runtime inventory entry.' }
        $path = Join-Path $bundle $file.path
        $item = Get-Item -LiteralPath $path -Force
        $current = $item
        while ($current -and $current.FullName -ne $bundle) {
            if (($current.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Runtime inventory traverses a reparse point.' }
            $current = if ($current -is [IO.DirectoryInfo]) { $current.Parent } else { $current.Directory }
        }
        if ($item.Length -ne $file.size -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ine $file.sha256) { throw 'Runtime inventory verification failed.' }
    }
    $record.ManifestSha256 = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $record.RuntimeSha256 = $manifest.runtimeSha256
    $record.ModelSha256 = $manifest.modelSha256
    if ($Execution -eq 'Cpu') {
        $record.SelectedDevice = [ordered]@{ Name = 'none'; Description = 'Vulkan runtime, CPU execution control' }
        $record.ScopedEnvironmentSet = [ordered]@{ LLAMA_ARG_DEVICE = 'none' }
        $record.Status = 'CpuControlSelected'
    } else {
        $start = New-Object Diagnostics.ProcessStartInfo
        $start.FileName = Join-Path $bundle $manifest.runtimePath
        $start.Arguments = '--list-devices'
        $start.WorkingDirectory = Split-Path -Parent $start.FileName
        $start.UseShellExecute = $false
        $start.CreateNoWindow = $true
        $start.RedirectStandardOutput = $true
        $start.RedirectStandardError = $true
        $nativeEncoding = New-Object Text.UTF8Encoding $false
        $start.StandardOutputEncoding = $nativeEncoding
        $start.StandardErrorEncoding = $nativeEncoding
        foreach ($name in ($envRemove + @('LLAMA_ARG_DEVICE'))) { $start.EnvironmentVariables.Remove($name) }
        $process = New-Object Diagnostics.Process
        $process.StartInfo = $start
        $started = $false
        $stdoutTask = $null
        $stderrTask = $null
        try {
            if (-not $process.Start()) { throw 'Native device discovery failed to start.' }
            $started = $true
            $record.WindowsNativeExecuted = $true
            $stdoutTask = $process.StandardOutput.ReadToEndAsync()
            $stderrTask = $process.StandardError.ReadToEndAsync()
            if (-not $process.WaitForExit(30000)) { $process.Kill(); throw 'Native device discovery timed out; preview not started.' }
            $record.DiscoveryExitCode = $process.ExitCode
            $record.DiscoveryStdout = $stdoutTask.GetAwaiter().GetResult()
            $record.DiscoveryStderr = $stderrTask.GetAwaiter().GetResult()
            $record.DiscoveryOutputComplete = $true
            if ($process.ExitCode -ne 0) { throw 'Native device discovery returned a failure; preview not started.' }
            $selection = Select-NvidiaVulkanFromListing $record.DiscoveryStdout
            $record.SelectedDevice = $selection.Selected
            $record.AvailableVulkanDevices = $selection.AvailableVulkanDevices
            $record.ScopedEnvironmentSet = [ordered]@{ LLAMA_ARG_DEVICE = $selection.Selected.Name }
            $record.Status = 'NvidiaVulkanSelected'
        } finally {
            if ($started) {
                if (-not $process.HasExited) { try { $process.Kill(); $null = $process.WaitForExit(5000) } catch { $record.DiscoveryStopError = $_.Exception.Message } }
                foreach ($entry in @(@{ Name = 'DiscoveryStdout'; Task = $stdoutTask }, @{ Name = 'DiscoveryStderr'; Task = $stderrTask })) {
                    if ($entry.Task) {
                        try {
                            if ($entry.Task.Wait(5000)) { $record[$entry.Name] = $entry.Task.GetAwaiter().GetResult() }
                            else { $record.DiscoveryOutputComplete = $false }
                        } catch { $record.DiscoveryReadError = $_.Exception.Message; $record.DiscoveryOutputComplete = $false }
                    }
                }
            }
            $process.Dispose()
        }
    }
    # Caller applies these only to the isolated app process; this script changes no global env.
    return [pscustomobject]$record
} catch {
    $record.Status = 'Failed'
    $record.Error = $_.Exception.Message
    throw
} finally { Write-PreviewSelectionRecord $record $recordPath }

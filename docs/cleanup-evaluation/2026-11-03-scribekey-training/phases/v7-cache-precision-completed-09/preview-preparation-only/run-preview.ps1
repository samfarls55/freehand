#Requires -Version 5.1
[CmdletBinding()]
param(
    [ValidateSet('TrainedScribe')][string]$Model = 'TrainedScribe',
    [ValidateSet('Cpu', 'Vulkan')][string]$Profile = 'Cpu',
    [switch]$Benchmark,
    [switch]$EnablePromptLookup
)
$ErrorActionPreference = 'Stop'

function Write-PreviewJson([string]$Path, $Value) {
    $json = $Value | ConvertTo-Json -Depth 24
    [IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
}

function Get-PreviewHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-PreviewExecutablePin([string]$Root, [string]$Relative) {
    $indexPath = Join-Path $Root 'preview-manifest.json'
    if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) { throw 'The root preview-manifest.json is required before starting any preview executable.' }
    $index = Get-Content -LiteralPath $indexPath -Raw | ConvertFrom-Json
    $entries = @($index.files | Where-Object { $_.path -ceq $Relative })
    if ($entries.Count -ne 1 -or $entries[0].sha256 -notmatch '^[0-9a-fA-F]{64}$' -or
        ($entries[0].size -isnot [int] -and $entries[0].size -isnot [long]) -or $entries[0].size -lt 1) {
        throw "The root preview manifest must pin exactly one executable: $Relative"
    }
    $file = Assert-PreviewRegularFile $Root $Relative
    $hash = Get-PreviewHash $file.FullName
    if ($file.Length -ne $entries[0].size -or $hash -ine $entries[0].sha256) { throw "Preview executable hash/size mismatch: $Relative" }
    return [pscustomobject]@{ Path = $Relative; Size = $file.Length; Sha256 = $hash; PreviewManifestSha256 = Get-PreviewHash $indexPath }
}

function Test-PreviewTrue($Value) { return ($Value -is [bool] -and $Value) }

function Get-PreviewQualification([string]$ReportPath, [string]$ManifestSha256, [bool]$GpuRequired) {
    $reasons = New-Object 'Collections.Generic.List[string]'
    $report = $null
    if (-not (Test-Path -LiteralPath $ReportPath -PathType Leaf)) { $reasons.Add('Desktop report is missing.') }
    else {
        try { $report = Get-Content -LiteralPath $ReportPath -Raw | ConvertFrom-Json }
        catch { $reasons.Add('Desktop report is not valid JSON.') }
    }
    if ($null -ne $report) {
        if (-not (Test-PreviewTrue $report.CleanupQualificationPassed) -or -not (Test-PreviewTrue $report.IncludeCleanup) -or
            -not (Test-PreviewTrue $report.FullCleanupQualificationRequested)) { $reasons.Add('The complete cleanup qualification was not requested and passed.') }
        if ($report.ColdOnly -isnot [bool] -or $report.ColdOnly -or $report.ReadyOnly -isnot [bool] -or $report.ReadyOnly) {
            $reasons.Add('A partial diagnostic is not a full cleanup qualification.')
        }
        if ($ManifestSha256 -notmatch '^[0-9a-fA-F]{64}$' -or $report.CleanupConfiguration.ManifestSha256 -ine $ManifestSha256) {
            $reasons.Add('The desktop report does not identify this run cleanup manifest.')
        }
        if ($report.MemoryLimitBytes -ne 747500000 -or $report.LatencyLimitMilliseconds -ne 805 -or $report.RequestedTolerancePercent -ne 15) {
            $reasons.Add('The desktop report does not use the requested 15 percent numeric limits.')
        }
        if ($GpuRequired) {
            if (-not (Test-PreviewTrue $report.RequireGpuTelemetry) -or -not (Test-PreviewTrue $report.CleanupGpuOffloadRequested) -or
                -not (Test-PreviewTrue $report.WorkerGpuInstanceObserved) -or -not (Test-PreviewTrue $report.CleanupGpuMemoryObserved) -or
                $null -eq $report.GpuTelemetrySamples -or $report.GpuTelemetrySamples -le 0 -or $report.GpuTelemetryMissingSamples -ne 0) {
                $reasons.Add('The required positive cleanup GPU telemetry was not confirmed.')
            }
            $cleanupPeaks = @($report.ProcessMemoryPeaks | Where-Object {
                $_.Role -ceq 'cleanup' -and $_.ProcessId -gt 0 -and (Test-PreviewTrue $_.GpuInstanceObserved) -and
                ($_.DedicatedGpuBytes -gt 0 -or $_.SharedGpuBytes -gt 0 -or $_.GpuCommittedBytes -gt 0)
            })
            if ($cleanupPeaks.Count -eq 0) { $reasons.Add('The desktop report lacks positive GPU memory for an identified cleanup process.') }
        }
    }
    return [pscustomobject]@{ SlaQualificationPassed = ($reasons.Count -eq 0); Reasons = @($reasons.ToArray()) }
}

function Get-PreviewOutcome($Commands, [bool]$BenchmarkRequested, $Qualification) {
    $commands = @($Commands)
    $expectedCount = if ($BenchmarkRequested) { 3 } else { 1 }
    $succeeded = $commands.Count -eq $expectedCount
    foreach ($command in $commands) {
        if ($null -eq $command.ExitCode -or $command.ExitCode -ne 0 -or $command.Error -or
            ($command.ExpectedReport -and -not (Test-PreviewTrue $command.ReportExists))) { $succeeded = $false }
    }
    $sla = $BenchmarkRequested -and $null -ne $Qualification -and (Test-PreviewTrue $Qualification.SlaQualificationPassed)
    $exitCode = 0
    if ($BenchmarkRequested) { if (-not $succeeded -or -not $sla) { $exitCode = 1 } }
    elseif ($commands.Count -ne 1 -or $null -eq $commands[0].ExitCode -or $commands[0].Error) { $exitCode = 1 }
    else { $exitCode = [int]$commands[0].ExitCode }
    return [pscustomobject]@{ AllCommandsSucceeded = $succeeded; SlaQualificationPassed = $sla; WrapperExitCode = $exitCode }
}

function Get-PreviewRelativePath([string]$Value) {
    $value = $Value.Replace('\', '/')
    if ([string]::IsNullOrWhiteSpace($value) -or [IO.Path]::IsPathRooted($value) -or
        $value -match '[\x00-\x1f:]' -or @($value.Split('/') | Where-Object { $_ -in @('', '.', '..') }).Count -gt 0) {
        throw 'Cleanup inventory contains an unsafe relative path.'
    }
    return $value
}

function Assert-PreviewRegularFile([string]$Root, [string]$Relative) {
    $relative = Get-PreviewRelativePath $Relative
    $file = Get-Item -LiteralPath (Join-Path $Root $relative) -Force
    if ($file.PSIsContainer) { throw "Cleanup inventory expects a file: $relative" }
    $item = $file
    while ($null -ne $item) {
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Preview assets must not be symbolic links or reparse points.' }
        if ($item.FullName.Equals($Root, [StringComparison]::OrdinalIgnoreCase)) { break }
        $item = if ($item -is [IO.DirectoryInfo]) { $item.Parent } else { $item.Directory }
    }
    if ($null -eq $item) { throw 'Cleanup asset lies outside its source bundle.' }
    return $file
}

function Copy-VerifiedPreviewBundle([string]$Source, [string]$Destination) {
    if (Test-Path -LiteralPath $Destination) { throw 'The run cleanup directory must be fresh.' }
    $source = (Resolve-Path -LiteralPath $Source).Path
    $manifestPath = Join-Path $source 'cleanup-manifest.json'
    $null = Assert-PreviewRegularFile $source 'cleanup-manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.schemaVersion -ne 1 -or $manifest.platform -cne 'win-x64-vulkan' -or
        $manifest.runtimePath -cne 'runtime/llama-server.exe') { throw 'Expected a verified Windows Vulkan source bundle.' }
    $known = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $files = @($manifest.files)
    if ($files.Count -lt 4) { throw 'Cleanup bundle inventory is incomplete.' }
    foreach ($file in $files) {
        $relative = Get-PreviewRelativePath $file.path
        if (-not $known.Add($relative) -or $relative -ieq 'cleanup-manifest.json' -or
            $file.sha256 -notmatch '^[0-9a-fA-F]{64}$' -or $file.size -lt 1 -or
            ($file.size -isnot [int] -and $file.size -isnot [long])) { throw 'Cleanup inventory entry is invalid or duplicated.' }
        $item = Assert-PreviewRegularFile $source $relative
        if ($item.Length -ne $file.size -or (Get-PreviewHash $item.FullName) -ine $file.sha256) { throw "Source cleanup hash/size mismatch: $relative" }
    }
    $primaries = @(@{ Path = $manifest.runtimePath; Hash = $manifest.runtimeSha256 }, @{ Path = $manifest.modelPath; Hash = $manifest.modelSha256 })
    if ($null -ne $manifest.PSObject.Properties['adapterPath']) {
        $null = Get-PreviewRelativePath $manifest.adapterPath
        if (($manifest.adapterScale -isnot [int] -and $manifest.adapterScale -isnot [long] -and $manifest.adapterScale -isnot [double] -and $manifest.adapterScale -isnot [decimal]) -or
            $manifest.adapterScale -ne 1 -or $manifest.adapterSha256 -notmatch '^[0-9a-fA-F]{64}$') {
            throw 'A portable native adapter requires its full pin and exact unit scale1.'
        }
        $primaries += @{ Path = $manifest.adapterPath; Hash = $manifest.adapterSha256 }
    } elseif ($null -ne $manifest.PSObject.Properties['adapterSha256'] -or $null -ne $manifest.PSObject.Properties['adapterScale']) {
        throw 'An adapter hash/scale without its path is invalid.'
    }
    foreach ($primary in $primaries) {
        $entry = @($files | Where-Object { $_.path -ceq $primary.Path })
        if ($entry.Count -ne 1 -or $entry[0].sha256 -ine $primary.Hash) { throw 'Primary cleanup pins disagree with the complete inventory.' }
    }
    foreach ($required in @('licenses/model-LICENSE.txt', 'licenses/runtime-LICENSE.txt')) {
        if (-not $known.Contains($required)) { throw 'Cleanup bundle is missing a license.' }
    }
    New-Item -ItemType Directory -Path $Destination | Out-Null
    $linked = 0
    $copied = 0
    foreach ($file in $files) {
        $relative = Get-PreviewRelativePath $file.path
        $sourceFile = Join-Path $source $relative
        $target = Join-Path $Destination $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        try { New-Item -ItemType HardLink -Path $target -Target $sourceFile -ErrorAction Stop | Out-Null; $linked++ }
        catch {
            if (Test-Path -LiteralPath $target) { throw 'A failed hard-link operation left an existing run file; refusing to overwrite it.' }
            Copy-Item -LiteralPath $sourceFile -Destination $target -ErrorAction Stop; $copied++
        }
        if ((Get-Item -LiteralPath $target).Length -ne $file.size -or (Get-PreviewHash $target) -ine $file.sha256) {
            throw "Run cleanup copy hash/size mismatch: $relative"
        }
    }
    # The manifest is a separate file because only this fresh copy is customized.
    Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $Destination 'cleanup-manifest.json')
    return [pscustomobject]@{ Manifest = $manifest; SourceManifestSha256 = Get-PreviewHash $manifestPath
        LinkedFiles = $linked; CopiedFiles = $copied; InventoryFiles = $files.Count }
}

function Set-PreviewProperty($Object, [string]$Name, $Value) {
    if ($null -eq $Object.PSObject.Properties[$Name]) { $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value }
    else { $Object.$Name = $Value }
}

function ConvertTo-PreviewArgument([string]$Value) {
    # Windows command-line quoting for ProcessStartInfo.Arguments on .NET Framework.
    $builder = New-Object Text.StringBuilder
    [void]$builder.Append('"')
    $slashes = 0
    foreach ($character in $Value.ToCharArray()) {
        if ($character -eq '\') { $slashes++; continue }
        if ($character -eq '"') { [void]$builder.Append(('\' * (2 * $slashes + 1))).Append('"') }
        else { [void]$builder.Append(('\' * $slashes)).Append($character) }
        $slashes = 0
    }
    [void]$builder.Append(('\' * (2 * $slashes))).Append('"')
    return $builder.ToString()
}

function Invoke-PreviewProcess([string]$Name, [string]$Executable, [string[]]$Arguments,
    [string]$WorkingDirectory, [string]$OutputRoot, $EnvironmentSet, [string[]]$EnvironmentRemove, [string]$ExpectedReport) {
    $record = [ordered]@{ Name = $Name; Executable = $Executable; ExecutableSha256 = Get-PreviewHash $Executable
        Arguments = $Arguments; StartedUtc = [DateTime]::UtcNow.ToString('o'); ExitCode = $null; Error = $null
        ExpectedReport = $ExpectedReport; ReportExists = $false; ReportSha256 = $null }
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $Executable
    $start.Arguments = (@($Arguments | ForEach-Object { ConvertTo-PreviewArgument $_ }) -join ' ')
    $start.WorkingDirectory = $WorkingDirectory
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    foreach ($environmentName in $EnvironmentRemove) { $start.EnvironmentVariables.Remove($environmentName) }
    foreach ($environmentName in $EnvironmentSet.Keys) { $start.EnvironmentVariables[$environmentName] = [string]$EnvironmentSet[$environmentName] }
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'Preview process did not start.' }
        $record.ProcessId = $process.Id
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        $process.WaitForExit()
        $record.ExitCode = $process.ExitCode
        [IO.File]::WriteAllText((Join-Path $OutputRoot ($Name + '.stdout.log')), $stdout.GetAwaiter().GetResult(), (New-Object Text.UTF8Encoding($false)))
        [IO.File]::WriteAllText((Join-Path $OutputRoot ($Name + '.stderr.log')), $stderr.GetAwaiter().GetResult(), (New-Object Text.UTF8Encoding($false)))
    } catch { $record.Error = $_.Exception.Message }
    finally { $process.Dispose(); $record.FinishedUtc = [DateTime]::UtcNow.ToString('o') }
    if ($ExpectedReport -and (Test-Path -LiteralPath $ExpectedReport -PathType Leaf)) {
        $record.ReportExists = $true
        $record.ReportSha256 = Get-PreviewHash $ExpectedReport
    }
    return [pscustomobject]$record
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'This preview launcher requires Windows. No Windows executable or GPU was run.' }
$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
if ($root -eq [IO.Path]::GetPathRoot($root)) { throw 'Extract the preview into a dedicated folder.' }
$app = Join-Path $root 'App/Freehand.App.exe'
$probe = Join-Path $root 'Probe/Freehand.Cleanup.Probe.exe'
$helper = Join-Path $root 'select-preview-device.ps1'
$previewMetadata = Get-Content -LiteralPath (Join-Path $root 'preview-manifest.json') -Raw | ConvertFrom-Json
if ($previewMetadata.specialist_output_normalization -cne 'trim-v1' -or
    $previewMetadata.source.specialist_output_normalization -cne 'trim-v1' -or
    $previewMetadata.trained_model.quantization -cnotin @('Q3_K_S', 'Q3_K_M', 'Q4_K_M', 'IQ4_XS')) {
    throw 'This trained preview requires a new trim-v1 build and an exact frozen Q3/Q4 quantization.'
}
$receiptPath = Join-Path $root 'build-receipt.json'
if ((Get-PreviewHash $receiptPath) -ine $previewMetadata.build_receipt_sha256) { throw 'The new trim-v1 build receipt does not match its root pin.' }
$cpuLookup = $previewMetadata.cpu_profile.promptLookupTokens
if (($cpuLookup -isnot [int] -and $cpuLookup -isnot [long]) -or $cpuLookup -lt 0 -or $cpuLookup -gt 63) {
    throw 'The trained preview must freeze an exact CPU prompt-lookup count from 0 through 63.'
}
if ($previewMetadata.trained_model.artifact_mode -ceq 'native_lora' -and $cpuLookup -ne 16) {
    throw 'The native LoRA CPU condition requires frozen lookup16.'
}
$cacheTypeK = $previewMetadata.cpu_profile.cacheTypeK
$cacheTypeV = $previewMetadata.cpu_profile.cacheTypeV
if ($cacheTypeK -isnot [string] -or $cacheTypeV -isnot [string] -or
    $cacheTypeK -cnotin @('f16', 'f32') -or $cacheTypeV -cnotin @('f16', 'f32')) {
    throw 'The selected preview must explicitly freeze f16/f32 cacheTypeK and cacheTypeV.'
}
$testedSpeechConfig = '0d2e1a0192d981a06ec6a6839810bc9f58cbfc7fdeea0c9ae1a708949562f7c9'
if ($previewMetadata.runtime_policy.tiered_pgo -isnot [bool] -or $previewMetadata.runtime_policy.tiered_pgo -or
    -not (Test-PreviewTrue $previewMetadata.runtime_policy.tiered_compilation) -or
    $previewMetadata.runtime_policy.speech_cpu_config.sha256 -ine $testedSpeechConfig) {
    throw 'The trained preview must record the exact tested PGO and speech spinning policy.'
}
$speechConfigPin = Assert-PreviewExecutablePin $root 'App/speech-cpu.config'
if ($speechConfigPin.Sha256 -ine $testedSpeechConfig) { throw 'Published speech CPU config differs from the exact tested configuration.' }
$modelFolder = 'trained-scribe-vulkan'
$sourceBundle = Join-Path $root ('cleanup/' + $modelFolder)
foreach ($path in @($app, $helper, (Join-Path $sourceBundle 'cleanup-manifest.json'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Preview file is missing: $path" }
}
$executablePins = @((Assert-PreviewExecutablePin $root 'App/Freehand.App.exe'), (Assert-PreviewExecutablePin $root 'Probe/Freehand.Cleanup.Probe.exe'))
if (@(Get-Process -Name Freehand.App -ErrorAction SilentlyContinue).Count -gt 0) { throw 'Quit other Freehand copies from their tray menu before starting this isolated preview. No process was stopped.' }
if ($Benchmark) {
    foreach ($path in @($probe, (Join-Path $root 'fixtures/public-quality.json'), (Join-Path $root 'fixtures/integration10.json'))) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Benchmark file is missing: $path" }
    }
}
$runName = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss', [Globalization.CultureInfo]::InvariantCulture) + '-' + $Model + '-' + $Profile + '-' + [guid]::NewGuid().ToString('N')
$run = Join-Path $root ('runs/' + $runName)
New-Item -ItemType Directory -Path $run | Out-Null
$data = Join-Path $run 'profile'
$outputs = Join-Path $run 'evidence'
New-Item -ItemType Directory -Path $data, $outputs | Out-Null
$manifestPath = Join-Path $run 'cleanup/cleanup-manifest.json'
$summary = [ordered]@{ SchemaVersion = 1; Model = $Model; Profile = $Profile; RunDirectory = $run
    ModelDisplayName = $previewMetadata.trained_model.display_name; Quantization = $previewMetadata.trained_model.quantization
    SpecialistOutputNormalization = 'trim-v1'; BuildReceiptSha256 = $previewMetadata.build_receipt_sha256
    DotNetRuntimePolicy = @{ TieredPGO = $false; TieredCompilation = $true; SpeechCpuConfigSha256 = $speechConfigPin.Sha256 }
    StartedUtc = [DateTime]::UtcNow.ToString('o'); StandardAsrProfile = $true; Benchmark = [bool]$Benchmark
    SourceBundle = $sourceBundle; Commands = @(); Error = $null; SlaProvenByLauncher = $false
    ExecutablePins = $executablePins; AllCommandsSucceeded = $false; SlaQualificationPassed = $false
    SemanticQualityUnverified = $true; WrapperExitCode = 1; QualificationReasons = @()
    Assessment = 'Read each performance and quality artifact. Structural acceptance does not prove semantic fidelity; the launcher does not certify GPU execution or the whole-app SLA.' }
$environmentNames = @('FREEHAND_DATA_DIRECTORY', 'FREEHAND_MODEL_PROFILE', 'FREEHAND_UPDATE_HANDOFF_TEST',
    'DOTNET_TieredPGO', 'DOTNET_TieredCompilation', 'COMPlus_TieredPGO', 'COMPlus_TieredCompilation',
    'LLAMA_ARG_DEVICE', 'GGML_VK_VISIBLE_DEVICES', 'LLAMA_ARG_MAIN_GPU', 'LLAMA_ARG_SPLIT_MODE', 'LLAMA_ARG_TENSOR_SPLIT', 'LLAMA_ARG_OVERRIDE_TENSOR')
$previousEnvironment = @{}
foreach ($name in $environmentNames) { $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    $clone = Copy-VerifiedPreviewBundle $sourceBundle (Join-Path $run 'cleanup')
    $manifest = $clone.Manifest
    if ($previewMetadata.trained_model.artifact_mode -ceq 'native_lora') {
        if ($manifest.adapterSha256 -ine $previewMetadata.trained_model.adapter_sha256 -or $manifest.adapterScale -ne 1 -or
            $manifest.modelSha256 -ine $previewMetadata.trained_model.sha256) { throw 'The exact selected base/adapter pair differs from the root evidence.' }
        $summary.NativeAdapter = @{ Path = $manifest.adapterPath; Sha256 = $manifest.adapterSha256; Scale = $manifest.adapterScale
            Mode = 'unmerged GGUF LoRA, native unit multiplier1'; WindowsExecutionPreviouslyVerified = $false }
    } elseif ($null -ne $manifest.PSObject.Properties['adapterPath']) { throw 'The merged profile contains an unplanned adapter.' }
    $lookup = if ($Profile -eq 'Cpu') { [int]$cpuLookup } elseif ($EnablePromptLookup) { 16 } else { 0 }
    $settings = @{ gpuLayers = $(if ($Profile -eq 'Vulkan') { 999 } else { 0 }); threads = 4
        contextSize = 1024; maxOutputTokens = 512; batchSize = 64; microBatchSize = 32
        promptCacheMiB = 0; contextCheckpoints = 0; cacheTypeK = $cacheTypeK; cacheTypeV = $cacheTypeV
        repack = $false; maskSpecialistLiterals = $true; promptLookupTokens = $lookup; promptLookupMatchTokens = 3 }
    foreach ($name in $settings.Keys) { Set-PreviewProperty $manifest $name $settings[$name] }
    Write-PreviewJson $manifestPath $manifest
    Write-PreviewJson (Join-Path $data 'settings.json') ([ordered]@{ CleanupEnabled = $true; CleanupDirectory = (Join-Path $run 'cleanup')
        ModelDirectory = $null; KeepHistory = $false; StartAtLogin = $false; CheckForUpdates = $false; InjectText = $true })
    $summary.SourceManifestSha256 = $clone.SourceManifestSha256
    $summary.ManifestSha256 = Get-PreviewHash $manifestPath
    $summary.AppSha256 = Get-PreviewHash $app
    $summary.DeviceHelperSha256 = Get-PreviewHash $helper
    $summary.BundleClone = [ordered]@{ InventoryFiles = $clone.InventoryFiles; HardLinked = $clone.LinkedFiles; Copied = $clone.CopiedFiles }
    $summary.Execution = if ($Profile -eq 'Cpu') { 'Vulkan runtime, CPU execution control' } else { 'NVIDIA Vulkan execution requested; positive hardware telemetry required' }
    $summary.PromptLookupTokens = $lookup
    $summary.CacheTypeK = $cacheTypeK
    $summary.CacheTypeV = $cacheTypeV
    $execution = if ($Profile -eq 'Cpu') { 'Cpu' } else { 'NvidiaVulkan' }
    $selection = & $helper -BundleDirectory (Join-Path $run 'cleanup') -EvidenceDirectory $outputs -Execution $execution
    $summary.SelectedDevice = $selection.SelectedDevice
    $environmentSet = @{ FREEHAND_DATA_DIRECTORY = $data; DOTNET_TieredPGO = '0' }
    foreach ($name in $selection.ScopedEnvironmentSet.Keys) { $environmentSet[$name] = $selection.ScopedEnvironmentSet[$name] }
    $environmentRemove = @($selection.ScopedEnvironmentRemove) + @('FREEHAND_MODEL_PROFILE', 'FREEHAND_UPDATE_HANDOFF_TEST',
        'DOTNET_TieredCompilation', 'COMPlus_TieredCompilation', 'COMPlus_TieredPGO')
    Write-Host "Isolated run: $run"
    if ($Benchmark) {
        Write-Host 'Running public text fixtures, then the complete desktop replay. The replay can take well over ten minutes; keep its owned test window available.'
        foreach ($fixture in @(@{ Name = 'quality-text'; Input = 'public-quality.json' }, @{ Name = 'quality-dictionary'; Input = 'integration10.json' })) {
            $report = Join-Path $outputs ($fixture.Name + '.json')
            $arguments = @('--input', (Join-Path $root ('fixtures/' + $fixture.Input)), '--output', $report, '--manifest', $manifestPath, '--split', 'all')
            $summary.Commands += Invoke-PreviewProcess $fixture.Name $probe $arguments (Split-Path -Parent $probe) $outputs $environmentSet $environmentRemove $report
        }
        # Preserve all quality exit codes and still produce the performance artifact.
        $report = Join-Path $outputs 'desktop-delivery.json'
        $arguments = @('--desktop-delivery-benchmark', $report, '--include-cleanup')
        if ($Profile -eq 'Vulkan') { $arguments += '--require-gpu-telemetry' }
        $summary.Commands += Invoke-PreviewProcess 'desktop-delivery' $app $arguments (Split-Path -Parent $app) $outputs $environmentSet $environmentRemove $report
    } else {
        Write-Host 'Opening the isolated preview. Quit it from its tray menu when finished.'
        $summary.Commands += Invoke-PreviewProcess 'interactive-preview' $app @() (Split-Path -Parent $app) $outputs $environmentSet $environmentRemove $null
    }
    $qualification = if ($Benchmark) { Get-PreviewQualification (Join-Path $outputs 'desktop-delivery.json') $summary.ManifestSha256 ($Profile -eq 'Vulkan') } else { $null }
    $outcome = Get-PreviewOutcome $summary.Commands ([bool]$Benchmark) $qualification
    $summary.AllCommandsSucceeded = $outcome.AllCommandsSucceeded
    $summary.SlaQualificationPassed = $outcome.SlaQualificationPassed
    $summary.WrapperExitCode = $outcome.WrapperExitCode
    if ($null -ne $qualification) { $summary.QualificationReasons = $qualification.Reasons }
} catch { $summary.Error = $_.Exception.Message; $summary.WrapperExitCode = 1; throw }
finally {
    foreach ($name in $environmentNames) { [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process') }
    $summary.FinishedUtc = [DateTime]::UtcNow.ToString('o')
    try { $summary.SourceManifestUnchanged = $summary.SourceManifestSha256 -and ((Get-PreviewHash (Join-Path $sourceBundle 'cleanup-manifest.json')) -eq $summary.SourceManifestSha256) }
    catch { $summary.SourceManifestUnchanged = $false; $summary.Error = 'Source cleanup manifest could not be checked after the run.' }
    if (-not $summary.SourceManifestUnchanged -or $summary.Error) { $summary.WrapperExitCode = 1; $summary.AllCommandsSucceeded = $false }
    Write-PreviewJson (Join-Path $run 'run-summary.json') $summary
}
Write-Host "Artifacts: $outputs"
foreach ($command in $summary.Commands) { Write-Host ($command.Name + ': exit=' + $command.ExitCode + ', report=' + $command.ReportExists) }
if ($Benchmark) { Write-Host ('Numeric SLA qualification: ' + $summary.SlaQualificationPassed + '; semantic quality remains unverified.') }
exit ([int]$summary.WrapperExitCode)

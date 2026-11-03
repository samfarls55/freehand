using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using Freehand.Abstractions;
using Freehand.Speech;

namespace Freehand.App;

// Runs the existing real SendInput benchmark with the actual desktop UI present.
// It uses public fixture audio and an owned edit control, never a microphone.
internal static class DesktopDeliveryBenchmark
{
    internal static async Task<int> RunAsync(Composition composition, string output)
    {
        var report = new DesktopDeliveryReport
        {
            IncludeCleanup = Environment.GetCommandLineArgs().Contains("--include-cleanup", StringComparer.Ordinal),
            RequireGpuTelemetry = Environment.GetCommandLineArgs().Contains("--require-gpu-telemetry", StringComparer.Ordinal),
            ColdOnly = Environment.GetCommandLineArgs().Contains("--cold-only", StringComparer.Ordinal),
            ReadyOnly = Environment.GetCommandLineArgs().Contains("--ready-only", StringComparer.Ordinal),
        };
        report.ResidentPolicy = ModelResolver.UsesAcceleratedModel && !report.ColdOnly;
        if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY")))
        {
            report.Failures.Add("Desktop delivery measurement requires an isolated data directory.");
        }
        else if (report.ColdOnly && report.ReadyOnly)
        {
            report.Failures.Add("Choose either forced-fresh or prepared-worker diagnostics.");
        }
        else if (report.ReadyOnly && !report.ResidentPolicy)
        {
            report.Failures.Add("Prepared-worker diagnostics require the accelerated resident profile.");
        }
        else
        {
            using var monitorStop = new CancellationTokenSource();
            var workers = composition.BenchmarkWorkers ?? throw new IOException("The actual desktop worker tracker is unavailable.");
            var cleanupWorkers = composition.BenchmarkCleanupWorkers;
            BenchmarkCleanupReplayContext? cleanupContext = null;
            var memory = PlatformFactory.CreateProcessMemoryReader() ?? throw new IOException("Process memory counters unavailable.");
            using var gpuMemory = PlatformFactory.CreateGpuMemoryReader();
            report.InitializationCompletedBeforeMemorySampling = composition.ReadinessTask.IsCompleted;
            report.MemorySamplingStartedMillisecondsAfterLaunch = Stopwatch.GetElapsedTime(Program.LaunchedAt).TotalMilliseconds;
            report.CleanupWorkersExistedBeforeMemorySampling = cleanupWorkers?.Snapshot().Count > 0;
            var monitor = SampleMemoryAsync(memory, gpuMemory, workers, cleanupWorkers, report, monitorStop.Token);
            try
            {
                await composition.ReadinessTask.ConfigureAwait(false);
                var speech = composition.Speech ?? throw new IOException("The actual desktop speech session is unavailable.");
                if (report.ResidentPolicy && !composition.IsDictationReady)
                    throw new IOException(composition.PreparationError ?? "The desktop did not reach dictation readiness.");
                report.StartupReadinessMilliseconds = composition.ReadinessTime.TotalMilliseconds;
                report.StartupLoadMilliseconds = ModelResolver.UsesAcceleratedModel ? speech.LastLoadTime.TotalMilliseconds : null;
                if (composition.Engine?.TryPrepareForUpdate() != true)
                    throw new IOException("Could not disarm the physical hotkey for fixture replay.");
                if (report.ColdOnly)
                {
                    // Preserve the forced-fresh diagnostic. The actual startup
                    // worker must be gone before another session captures audio.
                    await speech.ResetAsync(CancellationToken.None).ConfigureAwait(false);
                    await speech.DisposeAsync().ConfigureAwait(false);
                    report.StartupWorkerResetForColdDiagnostic = true;
                }
                if (report.IncludeCleanup)
                {
                    if (!report.ValidateCleanupSelection(composition.Settings.Data.CleanupEnabled, composition.Cleanup.IsAvailable))
                        throw new IOException("Cleanup qualification requires the enabled, available configured model.");
                    if (cleanupWorkers is null) throw new IOException("The actual desktop cleanup worker tracker is unavailable.");
                    cleanupContext = new(composition.Cleanup,
                        () => composition.Settings.Data.CleanupEnabled && composition.Cleanup.IsAvailable,
                        cleanupWorkers);
                    var options = cleanupContext.Options;
                    report.CleanupConfiguration = new(options.ModelId, cleanupContext.ManifestPath, cleanupContext.ManifestSha256,
                        options.ModelSha256, options.RuntimeSha256, options.PromptStyle.ToString(), options.Threads,
                        options.ContextSize, options.MaxOutputTokens, options.BatchSize, options.MicroBatchSize,
                        options.MaskSpecialistLiterals, options.Repack, options.IdleTimeout.TotalMilliseconds,
                        cleanupContext.InitialEpoch, cleanupContext.OptionsFingerprint,
                        JsonSerializer.SerializeToElement(options, BenchmarkCleanupJsonContext.Default.LlamaCleanupOptions));
                    report.ApplicationIdentity = await BenchmarkApplicationIdentity.CaptureAsync().ConfigureAwait(false);
                    if (!report.ColdOnly)
                    {
                        var warmupAt = Stopwatch.GetTimestamp();
                        await composition.Cleanup.ProcessAsync("This is a cleanup warmup.", CancellationToken.None).ConfigureAwait(false);
                        report.CleanupStartupWarmupMilliseconds = Stopwatch.GetElapsedTime(warmupAt).TotalMilliseconds;
                        cleanupContext.ValidateConfiguration();
                    }
                }
                var context = new BenchmarkReplayContext(speech, workers, report.ResidentPolicy, report.StartupLoadMilliseconds, cleanupContext);
                report.Replay = await EngineeringChecks.RunDeliveryReplayAsync(deliveryHotkey: composition.DeliveryHotkey,
                    realtimeWarmCapture: true, coldOnly: report.ColdOnly, readyOnly: report.ReadyOnly, context: context).ConfigureAwait(false);
            }
            catch (Exception error) when (error is IOException or InvalidDataException or JsonException or InvalidOperationException or OperationCanceledException or ArgumentException or UnauthorizedAccessException or TimeoutException)
            {
                report.Failures.Add(error.GetType().Name + ": " + error.Message);
            }
            finally
            {
                if (cleanupContext is not null)
                {
                    try
                    {
                        // Release the worker while sampling remains active; keep the
                        // application's configured processor object and selection alive.
                        await cleanupContext.StopAsync().ConfigureAwait(false);
                        report.CleanupTeardownCompleted = cleanupContext.Workers.LiveWorkerIds().Count == 0;
                        await Task.Delay(20).ConfigureAwait(false);
                    }
                    catch (Exception error) when (error is IOException or InvalidDataException or InvalidOperationException or OperationCanceledException or TimeoutException or UnauthorizedAccessException)
                    {
                        report.Failures.Add("Cleanup teardown failed: " + error.GetType().Name);
                    }
                    report.OwnedCleanupWorkers.AddRange(cleanupContext.Workers.Snapshot());
                    report.CleanupOrphanWorkers = report.OwnedCleanupWorkers.Count(worker => !worker.HasExited);
                }
                await monitorStop.CancelAsync().ConfigureAwait(false);
                await monitor.ConfigureAwait(false);
            }
            if (report.Replay is not null) report.ValidateReplayGate(report.Replay);
            report.ValidateMemoryGate();
        }
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(report, DesktopDeliveryJsonContext.Default.DesktopDeliveryReport)).ConfigureAwait(false);
        return report.Failures.Count == 0 ? 0 : 1;
    }

    private static async Task SampleMemoryAsync(IProcessMemoryReader reader, IGpuMemoryReader? gpuReader,
        BenchmarkWorkerLauncher workers, BenchmarkCleanupWorkerLauncher? cleanupWorkers, DesktopDeliveryReport report, CancellationToken token)
    {
        try
        {
            while (true)
            {
                token.ThrowIfCancellationRequested();
                if (!reader.TryRead(Environment.ProcessId, out var host))
                {
                    report.Failures.Add("Could not sample desktop memory.");
                    return;
                }
                var processes = new List<(int Id, string Role, ProcessMemory Memory)> { (Environment.ProcessId, "desktop", host) };
                // Include every live process launched by this actual composition,
                // including startup, reset, recovery and diagnostic transitions.
                var owned = workers.LiveWorkerIds().Select(id => (Id: id, Role: "speech"))
                    .Concat((cleanupWorkers?.LiveWorkerIds() ?? []).Select(id => (Id: id, Role: "cleanup")));
                foreach (var (workerId, role) in owned)
                {
                    if (reader.TryRead(workerId, out var worker)) processes.Add((workerId, role, worker));
                    else if (role == "speech" ? workers.LiveWorkerIds().Contains(workerId) : cleanupWorkers!.LiveWorkerIds().Contains(workerId))
                    {
                        report.Failures.Add("Could not sample native worker memory.");
                        return;
                    }
                }
                var gpu = gpuReader?.Read(processes.Select(process => process.Id).ToArray())
                    ?? new GpuMemorySnapshot([], "GPU memory counters unavailable.");
                report.RecordMemorySample(processes.Select(process => new DesktopProcessMemorySample(process.Id, process.Role, process.Memory,
                    gpu.IsAvailable ? gpu.Processes.Single(value => value.ProcessId == process.Id) : null)).ToArray(), gpu.Error);
                await Task.Delay(10, token).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
    }
}

internal sealed class DesktopDeliveryReport
{
    private static readonly int[] PreparedRecordingSeconds = [1, 3, 8, 10];
    private static readonly int[] LongRecordingSeconds = [30, 60];
    public bool IncludeCleanup { get; set; }
    public BenchmarkCleanupConfiguration? CleanupConfiguration { get; set; }
    public BenchmarkApplicationIdentity? ApplicationIdentity { get; set; }
    public double? CleanupStartupWarmupMilliseconds { get; set; }
    public bool CleanupWorkersExistedBeforeMemorySampling { get; set; }
    public bool CleanupTeardownCompleted { get; set; }
    public int CleanupOrphanWorkers { get; set; }
    public List<BenchmarkWorkerIdentity> OwnedCleanupWorkers { get; } = [];
    public bool FullCleanupQualificationRequested => IncludeCleanup && !ColdOnly && !ReadyOnly;
    public bool CleanupQualificationPassed => FullCleanupQualificationRequested && Failures.Count == 0 && Replay is not null && MemorySamples > 0;
    public bool ColdOnly { get; set; }
    public bool ReadyOnly { get; set; }
    public bool ResidentPolicy { get; set; }
    public double? StartupLoadMilliseconds { get; set; }
    public double? StartupReadinessMilliseconds { get; set; }
    public double MemorySamplingStartedMillisecondsAfterLaunch { get; set; }
    public bool InitializationCompletedBeforeMemorySampling { get; set; }
    public bool StartupWorkerResetForColdDiagnostic { get; set; }
    public string Scope { get; } = "Actual Avalonia composition and all its tracked native workers. Resident acceptance measures prepared-worker recordings after 15 seconds idle, plus 50 warm recordings; model initialization is measured separately before hotkey readiness. Each idle interval begins after a separate one-second drain allowance and records the change in successful native preparation count, which must be zero. Capture starts without awaiting preparation; each prepared-worker trial records successful preparations from just before key press through return to idle, which must be positive. These counts describe native requests, not measured GPU clocks. Forced-fresh and ready-only modes are separate diagnostics. Public audio reaches an owned Windows EDIT control through real SendInput; timestamps measure received characters, not compositor paint. No physical microphone/hotkey test or fresh-worker 700 ms claim. Memory sampling begins on benchmark entry after UI construction, before awaiting readiness; any earlier startup allocation may precede sampling. RAM sums simultaneous desktop and all live owned worker working sets plus shared GPU bytes, conservatively permitting double counting. Dedicated VRAM and private commit remain separate. GPU acceptance requires --require-gpu-telemetry.";
    public string Comparison { get; } = "Provisional limits only. Wispr Flow was not benchmarked.";
    public long OriginalMemoryLimitBytes { get; } = 650_000_000;
    public double OriginalLatencyLimitMilliseconds { get; } = 700;
    public int RequestedTolerancePercent => IncludeCleanup ? 15 : 0;
    public long MemoryLimitBytes => IncludeCleanup ? 747_500_000 : OriginalMemoryLimitBytes;
    public double LatencyLimitMilliseconds => IncludeCleanup ? 805 : OriginalLatencyLimitMilliseconds;
    public string CleanupScope { get; } = "--include-cleanup explicitly executes the configured local processor through Core before the owned Windows EDIT receives real SendInput. Warmup is separate; forced-fresh, first-after-cleanup-idle, restart and repeated-audio 30/60-second observations are separate from 50 warm short recordings. Every qualification trial requires one executed accepted cleanup; fallback is a failure. Core acceptance is structural, not proof of semantic fidelity; repeated public audio tests performance, not cleanup quality. Cleanup memory includes startup, retained workers, restarts and reset teardown. Baseline 650MB/700ms limits remain unchanged without the flag. No physical microphone/hotkey or all-length 805ms claim. Idle diagnostic waits at most two minutes; a longer configured timeout cannot establish idle unload in this run.";
    public long PeakWorkingSetBytes { get; set; }
    public long PeakPrivateBytes { get; set; }
    public bool RequireGpuTelemetry { get; set; }
    public long MemorySamples { get; private set; }
    public long GpuTelemetryMissingSamples { get; private set; }
    public long GpuTelemetrySamples { get; private set; }
    public bool WorkerGpuInstanceObserved { get; private set; }
    public bool CleanupGpuMemoryObserved { get; private set; }
    public bool CleanupGpuOffloadRequested => CleanupConfiguration?.ActualOptions is { ValueKind: JsonValueKind.Object } options
        && options.TryGetProperty("GpuLayers", out var layers) && layers.TryGetInt32(out var count) && count > 0;
    public long? PeakGpuDedicatedBytes => GpuTelemetrySamples == 0 ? null : _peakGpuDedicated;
    public long? PeakGpuSharedBytes => GpuTelemetrySamples == 0 ? null : _peakGpuShared;
    public long? PeakGpuCommittedBytes => GpuTelemetrySamples == 0 ? null : _peakGpuCommitted;
    public long? PeakConservativeRamBytes => GpuTelemetryMissingSamples == 0 ? _peakConservativeRam : null;
    public DesktopMemorySample? MemoryAtPeakConservativeRam { get; private set; }
    public List<DesktopProcessMemoryPeak> ProcessMemoryPeaks { get; } = [];
    public List<string> GpuTelemetryErrors { get; } = [];
    public BenchmarkReport? Replay { get; set; }
    public List<string> Failures { get; } = [];
    private long _peakConservativeRam;
    private long _peakGpuDedicated, _peakGpuShared, _peakGpuCommitted;

    internal bool ValidateCleanupSelection(bool enabled, bool available)
    {
        if (!IncludeCleanup) return true;
        if (enabled && available) return true;
        Failures.Add("Cleanup qualification requires cleanup enabled and a configured available model.");
        return false;
    }

    internal void ValidateReplayGate(BenchmarkReport replay)
    {
        if (replay.Failures.Count != 0 || replay.OrphanWorkers != 0)
            Failures.Add("The native worker and delivery replay failed.");
        if (!ColdOnly && !ReadyOnly)
        {
            if (replay.ReleaseToFullInputMilliseconds.Count != 50)
                Failures.Add("Complete text receipt was not confirmed for every warm trial.");
            if (replay.ReleaseToFullInputMilliseconds.Any(value => value > LatencyLimitMilliseconds))
                Failures.Add("A warm delivery exceeded the requested " + LatencyLimitMilliseconds + " ms limit.");
            if (!replay.WorkerCrashRecoveryPassed || !replay.TimeoutRetentionPassed || replay.UnloadCycles != 20)
                Failures.Add("The complete recovery, retained-audio and unload controls did not pass.");
        }
        if (ResidentPolicy)
        {
            if (!replay.ResidentPolicy || !replay.ReadyRecordingSeconds.SequenceEqual(PreparedRecordingSeconds)
                || replay.ReadyReleaseToFullInputMilliseconds.Count != 4)
                Failures.Add("Complete text receipt was not confirmed for every prepared-worker trial.");
            if (!replay.PreparedWorkerPreserved || replay.ReadyWorkerIds.Count != 4
                || replay.ReadyWorkerIds.Any(id => id != replay.PreparedWorkerId))
                Failures.Add("The actual prepared desktop worker was not preserved.");
            if (replay.ReadyIdleMilliseconds.Count != 4 || replay.ReadyIdleMilliseconds.Any(value => value < 14950))
                Failures.Add("Prepared-worker trials did not follow the required 15-second idle intervals.");
            if (replay.ReadyIdlePreparationCounts.Count != 4 || replay.ReadyIdlePreparationCounts.Any(value => value != 0))
                Failures.Add("Prepared-worker idle intervals did not confirm zero successful native preparations.");
            if (replay.ReadyPreparationCounts.Count != 4 || replay.ReadyPreparationCounts.Any(value => value <= 0))
                Failures.Add("A prepared-worker recording did not confirm a successful native preparation request.");
            if (replay.ReadyReleaseToFullInputMilliseconds.Any(value => value > LatencyLimitMilliseconds))
                Failures.Add("A prepared-worker delivery exceeded the requested " + LatencyLimitMilliseconds + " ms limit.");
            if (replay.ColdRecordingSeconds.Count != 0)
                Failures.Add("Prepared-worker results were mislabeled as forced-fresh recordings.");
        }
        else
        {
            if (replay.ColdReleaseToFullInputMilliseconds.Count != 3)
                Failures.Add("Complete text receipt was not confirmed for every forced-fresh dictation.");
            // The full cleanup gate is ready-state acceptance. Cold initialization
            // remains visible separately; explicit cold-only diagnostics keep a cap.
            if ((!IncludeCleanup || ColdOnly) && replay.ColdReleaseToFullInputMilliseconds.Any(value => value > LatencyLimitMilliseconds))
                Failures.Add("A forced-fresh delivery exceeded the requested " + LatencyLimitMilliseconds + " ms limit.");
        }
        if (IncludeCleanup)
        {
            if (!replay.IncludeCleanup || replay.CleanupTrials.Count == 0
                || replay.CleanupTrials.Any(trial => trial.ProviderCalls != 1 || trial.Outcome is not ("Applied" or "Unchanged")))
                Failures.Add("Cleanup qualification requires an executed accepted cleanup on every replay trial; fallback or disabled cleanup is not a pass.");
            var initialPhase = ResidentPolicy ? "prepared" : "forced-fresh";
            if (replay.CleanupTrials.Count(trial => trial.Phase == initialPhase) != (ResidentPolicy ? 4 : 3))
                Failures.Add("Cleanup execution was not confirmed for every initial replay diagnostic.");
            if (CleanupConfiguration is null || CleanupConfiguration.OptionsFingerprint is not { Length: 64 }
                || CleanupConfiguration.ActualOptions is null || ApplicationIdentity is null
                || CleanupWorkersExistedBeforeMemorySampling || OwnedCleanupWorkers.Count == 0
                || CleanupOrphanWorkers != 0 || !CleanupTeardownCompleted)
                Failures.Add("Cleanup configuration, complete startup sampling and worker teardown were not confirmed.");
            if (FullCleanupQualificationRequested)
            {
                if (replay.CleanupTrials.Count(trial => trial.Phase == "warm") != 50
                    || replay.CleanupWarmups.Count == 0 || replay.CleanupWarmups.Any(warmup => warmup.ProviderCalls != 1))
                    Failures.Add("Cleanup qualification did not execute a separate warmup and all 50 warm recordings.");
                if (!replay.LongRecordingSeconds.SequenceEqual(LongRecordingSeconds) || replay.LongReleaseToFullInputMilliseconds.Count != 2)
                    Failures.Add("Long cleanup delivery diagnostics were not completed.");
                if (replay.CleanupTrials.Count(trial => trial.Phase == "long") != 2
                    || replay.CleanupTrials.Count(trial => trial.Phase == "first-after-cleanup-idle") != 1
                    || replay.CleanupTrials.Count(trial => trial.Phase == "cleanup-worker-recovery") != 1
                    || replay.CleanupTrials.Count(trial => trial.Phase == "speech-worker-recovery") != 1)
                    Failures.Add("Cleanup execution was not confirmed for every long, idle and recovery diagnostic.");
                if (!replay.CleanupIdleUnloadObserved || replay.FirstAfterCleanupIdleFullInputMilliseconds is null
                    || !replay.CleanupCrashRecoveryPassed)
                    Failures.Add("Cleanup first-after-idle and native-worker recovery diagnostics were not completed.");
            }
        }
    }

    internal void RecordMemorySample(IReadOnlyList<DesktopProcessMemorySample> processes, string? gpuError)
    {
        MemorySamples++;
        var working = processes.Sum(process => process.Memory.WorkingSetBytes);
        var committed = processes.Sum(process => process.Memory.PrivateBytes);
        PeakWorkingSetBytes = Math.Max(PeakWorkingSetBytes, working);
        PeakPrivateBytes = Math.Max(PeakPrivateBytes, committed);
        foreach (var process in processes)
        {
            var peak = ProcessMemoryPeaks.SingleOrDefault(value => value.ProcessId == process.ProcessId);
            if (peak is null) { peak = new DesktopProcessMemoryPeak(process.ProcessId, process.Role); ProcessMemoryPeaks.Add(peak); }
            peak.Observe(process);
        }
        if (gpuError is not null)
        {
            GpuTelemetryMissingSamples++;
            if (!GpuTelemetryErrors.Contains(gpuError, StringComparer.Ordinal)) GpuTelemetryErrors.Add(gpuError);
            return;
        }
        var dedicated = processes.Sum(process => process.Gpu!.Value.DedicatedBytes);
        var shared = processes.Sum(process => process.Gpu!.Value.SharedBytes);
        var gpuCommitted = processes.Sum(process => process.Gpu!.Value.CommittedBytes);
        WorkerGpuInstanceObserved |= processes.Any(process => process.Role is "worker" or "speech" or "cleanup" && process.Gpu!.Value.HasInstance);
        CleanupGpuMemoryObserved |= processes.Any(process => process.Role == "cleanup" && process.Gpu!.Value is
            { HasInstance: true } gpu && (gpu.DedicatedBytes > 0 || gpu.SharedBytes > 0 || gpu.CommittedBytes > 0));
        GpuTelemetrySamples++;
        _peakGpuDedicated = Math.Max(_peakGpuDedicated, dedicated);
        _peakGpuShared = Math.Max(_peakGpuShared, shared);
        _peakGpuCommitted = Math.Max(_peakGpuCommitted, gpuCommitted);
        if (working + shared > _peakConservativeRam)
        {
            _peakConservativeRam = working + shared;
            MemoryAtPeakConservativeRam = new(processes, working, committed, dedicated, shared, gpuCommitted, _peakConservativeRam);
        }
    }

    internal void ValidateMemoryGate()
    {
        if (PeakWorkingSetBytes > MemoryLimitBytes || _peakConservativeRam > MemoryLimitBytes)
            Failures.Add("The desktop and native workers exceeded the requested " + MemoryLimitBytes + " byte physical RAM limit.");
        if (GpuTelemetryMissingSamples != 0 || MemorySamples == 0)
            Failures.Add("Physical RAM acceptance requires complete dedicated/shared GPU memory telemetry.");
        if (RequireGpuTelemetry && !WorkerGpuInstanceObserved)
            Failures.Add("GPU acceptance did not observe a native worker GPU counter instance.");
        if (RequireGpuTelemetry && CleanupGpuOffloadRequested && !CleanupGpuMemoryObserved)
            Failures.Add("Cleanup GPU offload acceptance did not observe positive memory counters for the actual cleanup worker.");
    }
}

internal sealed record DesktopProcessMemorySample(int ProcessId, string Role, ProcessMemory Memory, ProcessGpuMemory? Gpu);
internal sealed record DesktopMemorySample(IReadOnlyList<DesktopProcessMemorySample> Processes, long WorkingSetBytes,
    long PrivateCommitBytes, long DedicatedGpuBytes, long SharedGpuBytes, long GpuCommittedBytes, long ConservativeRamBytes);
internal sealed class DesktopProcessMemoryPeak(int processId, string role)
{
    public int ProcessId { get; } = processId;
    public string Role { get; } = role;
    public long WorkingSetBytes { get; private set; }
    public long PrivateCommitBytes { get; private set; }
    public long? DedicatedGpuBytes { get; private set; }
    public long? SharedGpuBytes { get; private set; }
    public long? GpuCommittedBytes { get; private set; }
    public bool GpuInstanceObserved { get; private set; }
    internal void Observe(DesktopProcessMemorySample sample)
    {
        WorkingSetBytes = Math.Max(WorkingSetBytes, sample.Memory.WorkingSetBytes);
        PrivateCommitBytes = Math.Max(PrivateCommitBytes, sample.Memory.PrivateBytes);
        if (sample.Gpu is not { } gpu) return;
        DedicatedGpuBytes = Math.Max(DedicatedGpuBytes ?? 0, gpu.DedicatedBytes);
        SharedGpuBytes = Math.Max(SharedGpuBytes ?? 0, gpu.SharedBytes);
        GpuCommittedBytes = Math.Max(GpuCommittedBytes ?? 0, gpu.CommittedBytes);
        GpuInstanceObserved |= gpu.HasInstance;
    }
}

[JsonSourceGenerationOptions(WriteIndented = true)]
[JsonSerializable(typeof(DesktopDeliveryReport))]
internal sealed partial class DesktopDeliveryJsonContext : JsonSerializerContext;

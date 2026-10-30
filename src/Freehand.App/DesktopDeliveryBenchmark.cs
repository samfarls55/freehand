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
            var memory = PlatformFactory.CreateProcessMemoryReader() ?? throw new IOException("Process memory counters unavailable.");
            using var gpuMemory = PlatformFactory.CreateGpuMemoryReader();
            report.InitializationCompletedBeforeMemorySampling = composition.ReadinessTask.IsCompleted;
            report.MemorySamplingStartedMillisecondsAfterLaunch = Stopwatch.GetElapsedTime(Program.LaunchedAt).TotalMilliseconds;
            var monitor = SampleMemoryAsync(memory, gpuMemory, workers, report, monitorStop.Token);
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
                var context = new BenchmarkReplayContext(speech, workers, report.ResidentPolicy, report.StartupLoadMilliseconds);
                report.Replay = await EngineeringChecks.RunDeliveryReplayAsync(deliveryHotkey: composition.DeliveryHotkey,
                    realtimeWarmCapture: true, coldOnly: report.ColdOnly, readyOnly: report.ReadyOnly, context: context).ConfigureAwait(false);
                report.ValidateReplayGate(report.Replay);
            }
            catch (Exception error) when (error is IOException or JsonException or InvalidOperationException or OperationCanceledException)
            {
                report.Failures.Add(error.GetType().Name + ": " + error.Message);
            }
            finally
            {
                await monitorStop.CancelAsync().ConfigureAwait(false);
                await monitor.ConfigureAwait(false);
            }
            report.ValidateMemoryGate();
        }
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(report, DesktopDeliveryJsonContext.Default.DesktopDeliveryReport)).ConfigureAwait(false);
        return report.Failures.Count == 0 ? 0 : 1;
    }

    private static async Task SampleMemoryAsync(IProcessMemoryReader reader, IGpuMemoryReader? gpuReader,
        BenchmarkWorkerLauncher workers, DesktopDeliveryReport report, CancellationToken token)
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
                foreach (var workerId in workers.LiveWorkerIds())
                {
                    if (reader.TryRead(workerId, out var worker)) processes.Add((workerId, "worker", worker));
                    else if (workers.LiveWorkerIds().Contains(workerId))
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
    public long MemoryLimitBytes { get; } = 650_000_000;
    public double LatencyLimitMilliseconds { get; } = 700;
    public long PeakWorkingSetBytes { get; set; }
    public long PeakPrivateBytes { get; set; }
    public bool RequireGpuTelemetry { get; set; }
    public long MemorySamples { get; private set; }
    public long GpuTelemetryMissingSamples { get; private set; }
    public long GpuTelemetrySamples { get; private set; }
    public bool WorkerGpuInstanceObserved { get; private set; }
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

    internal void ValidateReplayGate(BenchmarkReport replay)
    {
        if (replay.Failures.Count != 0 || replay.OrphanWorkers != 0)
            Failures.Add("The native worker and delivery replay failed.");
        if (!ColdOnly && !ReadyOnly)
        {
            if (replay.ReleaseToFullInputMilliseconds.Count != 50)
                Failures.Add("Complete text receipt was not confirmed for every warm trial.");
            if (replay.ReleaseToFullInputMilliseconds.Any(value => value > LatencyLimitMilliseconds))
                Failures.Add("A warm delivery exceeded the provisional 700 ms limit.");
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
                Failures.Add("A prepared-worker delivery exceeded the provisional 700 ms limit.");
            if (replay.ColdRecordingSeconds.Count != 0)
                Failures.Add("Prepared-worker results were mislabeled as forced-fresh recordings.");
        }
        else
        {
            if (replay.ColdReleaseToFullInputMilliseconds.Count != 3)
                Failures.Add("Complete text receipt was not confirmed for every forced-fresh dictation.");
            if (replay.ColdReleaseToFullInputMilliseconds.Any(value => value > LatencyLimitMilliseconds))
                Failures.Add("A forced-fresh delivery exceeded the provisional 700 ms limit.");
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
        WorkerGpuInstanceObserved |= processes.Any(process => process.Role == "worker" && process.Gpu!.Value.HasInstance);
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
            Failures.Add("The desktop and native worker exceeded the provisional 650 MB physical RAM limit.");
        if (GpuTelemetryMissingSamples != 0 || MemorySamples == 0)
            Failures.Add("Physical RAM acceptance requires complete dedicated/shared GPU memory telemetry.");
        if (RequireGpuTelemetry && !WorkerGpuInstanceObserved)
            Failures.Add("GPU acceptance did not observe a native worker GPU counter instance.");
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

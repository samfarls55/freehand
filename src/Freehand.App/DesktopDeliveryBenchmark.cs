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
        };
        if (string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY")))
        {
            report.Failures.Add("Desktop delivery measurement requires an isolated data directory.");
        }
        else if (composition.Engine?.TryPrepareForUpdate() != true)
        {
            report.Failures.Add("Could not disarm the physical hotkey for fixture replay.");
        }
        else
        {
            // The normal engine stays idle, with its hotkey disarmed. The benchmark
            // exercises the same engine and worker through its scripted capture source.
            using var monitorStop = new CancellationTokenSource();
            SpeechWorkerClient? observedSession = null;
            var memory = PlatformFactory.CreateProcessMemoryReader() ?? throw new IOException("Process memory counters unavailable.");
            using var gpuMemory = PlatformFactory.CreateGpuMemoryReader();
            var monitor = SampleMemoryAsync(memory, gpuMemory, () => Volatile.Read(ref observedSession), report, monitorStop.Token);
            try
            {
                report.Replay = await EngineeringChecks.RunDeliveryReplayAsync(session => Volatile.Write(ref observedSession, session),
                    composition.DeliveryHotkey, realtimeWarmCapture: true, coldOnly: report.ColdOnly).ConfigureAwait(false);
                if (report.Replay.Failures.Count != 0 || report.Replay.OrphanWorkers != 0)
                    report.Failures.Add("The native worker and delivery replay failed.");
                else if (!report.ColdOnly && report.Replay.ReleaseToFullInputMilliseconds.Count != 50)
                    report.Failures.Add("Complete text receipt was not confirmed for every warm trial.");
                else if (!report.ColdOnly && report.Replay.ReleaseToFullInputMilliseconds.Any(value => value > report.LatencyLimitMilliseconds))
                    report.Failures.Add("A warm delivery exceeded the provisional 700 ms limit.");
                if (report.Replay.ColdReleaseToFullInputMilliseconds.Count != 3)
                    report.Failures.Add("Complete text receipt was not confirmed for every cold dictation.");
                else if (report.Replay.ColdReleaseToFullInputMilliseconds.Any(value => value > report.LatencyLimitMilliseconds))
                    report.Failures.Add("A cold delivery exceeded the provisional 700 ms limit.");
            }
            catch (Exception error) when (error is IOException or JsonException)
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
        Func<SpeechWorkerClient?> session, DesktopDeliveryReport report, CancellationToken token)
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
                // Read counters for the actual worker directly. Walking loaded modules
                // at every sample adds substantial observer CPU and allocation overhead.
                if (session()?.WorkerId is { } workerId)
                {
                    if (reader.TryRead(workerId, out var worker)) processes.Add((workerId, "worker", worker));
                    else if (session()?.WorkerId == workerId)
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
    public bool ColdOnly { get; set; }
    public string Scope { get; } = "Constructed Avalonia desktop plus native speech worker, including worker startup and teardown; public audio replay into an owned Windows EDIT control. Input timestamps measure received characters, not compositor paint. No physical microphone or hotkey test. RAM uses simultaneous summed working sets plus shared GPU bytes, conservatively allowing double counting. Dedicated VRAM and private commit are separate diagnostics; WDDM GPU backing-store commit is not physical host RAM. GPU acceptance requires --require-gpu-telemetry.";
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

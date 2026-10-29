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
        var report = new DesktopDeliveryReport();
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
            var monitor = SampleMemoryAsync(memory, () => Volatile.Read(ref observedSession), report, monitorStop.Token);
            try
            {
                report.Replay = await EngineeringChecks.RunDeliveryReplayAsync(session => Volatile.Write(ref observedSession, session),
                    composition.DeliveryHotkey).ConfigureAwait(false);
                if (report.Replay.Failures.Count != 0 || report.Replay.OrphanWorkers != 0)
                    report.Failures.Add("The native worker and delivery replay failed.");
                else if (report.Replay.ReleaseToFullInputMilliseconds.Count != 50)
                    report.Failures.Add("Complete text receipt was not confirmed for every warm trial.");
                else if (report.Replay.ReleaseToFullInputMilliseconds.Any(value => value > report.LatencyLimitMilliseconds))
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
            if (report.PeakWorkingSetBytes > report.MemoryLimitBytes || report.PeakPrivateBytes > report.MemoryLimitBytes)
                report.Failures.Add("The desktop and native worker exceeded the provisional 650 MB limit.");
        }
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(report, DesktopDeliveryJsonContext.Default.DesktopDeliveryReport)).ConfigureAwait(false);
        return report.Failures.Count == 0 ? 0 : 1;
    }

    private static async Task SampleMemoryAsync(IProcessMemoryReader reader, Func<SpeechWorkerClient?> session, DesktopDeliveryReport report, CancellationToken token)
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
                long working = host.WorkingSetBytes, committed = host.PrivateBytes;
                // Read counters for the actual worker directly. Walking loaded modules
                // at every sample adds substantial observer CPU and allocation overhead.
                if (session()?.WorkerId is { } workerId && reader.TryRead(workerId, out var worker))
                {
                    working += worker.WorkingSetBytes;
                    committed += worker.PrivateBytes;
                }
                report.PeakWorkingSetBytes = Math.Max(report.PeakWorkingSetBytes, working);
                report.PeakPrivateBytes = Math.Max(report.PeakPrivateBytes, committed);
                await Task.Delay(10, token).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
    }
}

internal sealed class DesktopDeliveryReport
{
    public string Scope { get; } = "Constructed Avalonia desktop plus native speech worker, including worker startup and teardown; public audio replay into an owned Windows EDIT control. Input timestamps measure received characters, not compositor paint. No physical microphone or hotkey test. Summed working sets may count shared pages twice.";
    public string Comparison { get; } = "Provisional limits only. Wispr Flow was not benchmarked.";
    public long MemoryLimitBytes { get; } = 650_000_000;
    public double LatencyLimitMilliseconds { get; } = 700;
    public long PeakWorkingSetBytes { get; set; }
    public long PeakPrivateBytes { get; set; }
    public BenchmarkReport? Replay { get; set; }
    public List<string> Failures { get; } = [];
}

[JsonSourceGenerationOptions(WriteIndented = true)]
[JsonSerializable(typeof(DesktopDeliveryReport))]
internal sealed partial class DesktopDeliveryJsonContext : JsonSerializerContext;

using Freehand.App;
using Xunit;

namespace Freehand.AppTests;

public sealed class DesktopDeliveryReplayGateTests
{
    [Fact]
    public void Full_resident_acceptance_requires_all_prepared_and_warm_receipts_at_or_below_the_cap()
    {
        var replay = CreateResidentReplay();
        for (var index = 0; index < replay.ReadyReleaseToFullInputMilliseconds.Count; index++)
            replay.ReadyReleaseToFullInputMilliseconds[index] = 700;
        for (var index = 0; index < replay.ReleaseToFullInputMilliseconds.Count; index++)
            replay.ReleaseToFullInputMilliseconds[index] = 700;
        var report = new DesktopDeliveryReport { ResidentPolicy = true };

        report.ValidateReplayGate(replay);

        Assert.Empty(report.Failures);
        Assert.Empty(replay.ColdRecordingSeconds);
    }

    [Theory]
    [InlineData("ready-latency")]
    [InlineData("worker-replaced")]
    [InlineData("worker-unloaded")]
    [InlineData("idle-too-short")]
    [InlineData("missing-ready-receipt")]
    [InlineData("warm-latency")]
    [InlineData("missing-warm-receipt")]
    [InlineData("orphan")]
    [InlineData("recovery")]
    [InlineData("retained-audio")]
    [InlineData("unload-cycles")]
    [InlineData("ready-labeled-cold")]
    public void Full_resident_acceptance_rejects_an_unmet_requirement(string failure)
    {
        var replay = CreateResidentReplay();
        switch (failure)
        {
            case "ready-latency": replay.ReadyReleaseToFullInputMilliseconds[2] = 700.1; break;
            case "worker-replaced": replay.ReadyWorkerIds[2]++; break;
            case "worker-unloaded": replay.PreparedWorkerPreserved = false; break;
            case "idle-too-short": replay.ReadyIdleMilliseconds[2] = 14000; break;
            case "missing-ready-receipt": replay.ReadyReleaseToFullInputMilliseconds.RemoveAt(2); break;
            case "warm-latency": replay.ReleaseToFullInputMilliseconds[^1] = 700.1; break;
            case "missing-warm-receipt": replay.ReleaseToFullInputMilliseconds.RemoveAt(49); break;
            case "orphan": replay.OrphanWorkers = 1; break;
            case "recovery": replay.WorkerCrashRecoveryPassed = false; break;
            case "retained-audio": replay.TimeoutRetentionPassed = false; break;
            case "unload-cycles": replay.UnloadCycles = 19; break;
            case "ready-labeled-cold": replay.ColdRecordingSeconds.Add(1); break;
            default: throw new ArgumentOutOfRangeException(nameof(failure));
        }
        var report = new DesktopDeliveryReport { ResidentPolicy = true };

        report.ValidateReplayGate(replay);

        Assert.NotEmpty(report.Failures);
    }

    [Fact]
    public void Ready_only_diagnostic_pass_cannot_stand_in_for_full_acceptance()
    {
        var replay = CreateResidentReplay();
        replay.ReleaseToFullInputMilliseconds.Clear();
        replay.WorkerCrashRecoveryPassed = false;
        replay.TimeoutRetentionPassed = false;
        replay.UnloadCycles = 0;
        var diagnostic = new DesktopDeliveryReport { ResidentPolicy = true, ReadyOnly = true };
        var full = new DesktopDeliveryReport { ResidentPolicy = true };

        diagnostic.ValidateReplayGate(replay);
        full.ValidateReplayGate(replay);

        Assert.Empty(diagnostic.Failures);
        Assert.NotEmpty(full.Failures);
    }

    [Fact]
    public void Forced_fresh_diagnostic_keeps_separate_cold_results_and_checks_its_own_latency()
    {
        var replay = new BenchmarkReport();
        replay.ColdReleaseToFullInputMilliseconds.AddRange([250, 400, 700]);
        var diagnostic = new DesktopDeliveryReport { ColdOnly = true };
        diagnostic.ValidateReplayGate(replay);
        Assert.Empty(diagnostic.Failures);
        Assert.False(diagnostic.ResidentPolicy);
        Assert.Empty(replay.ReadyRecordingSeconds);

        replay.ColdReleaseToFullInputMilliseconds[0] = 700.1;
        var failed = new DesktopDeliveryReport { ColdOnly = true };
        failed.ValidateReplayGate(replay);
        Assert.NotEmpty(failed.Failures);
    }

    private static BenchmarkReport CreateResidentReplay()
    {
        var replay = new BenchmarkReport
        {
            ResidentPolicy = true,
            PreparedWorkerId = 123,
            PreparedWorkerPreserved = true,
            WorkerCrashRecoveryPassed = true,
            TimeoutRetentionPassed = true,
            UnloadCycles = 20,
        };
        replay.ReadyRecordingSeconds.AddRange([1, 3, 8, 10]);
        replay.ReadyWorkerIds.AddRange([123, 123, 123, 123]);
        replay.ReadyIdleMilliseconds.AddRange([15000, 15000, 15000, 15000]);
        replay.ReadyReleaseToFullInputMilliseconds.AddRange([250, 350, 600, 450]);
        replay.ReleaseToFullInputMilliseconds.AddRange(Enumerable.Repeat(450d, 50));
        return replay;
    }
}

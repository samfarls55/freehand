using Freehand.Abstractions;
using Xunit;

namespace Freehand.AppTests;

public sealed class DesktopMemoryTests
{
    [Fact]
    public void Physical_gate_uses_simultaneous_working_sets_and_shared_gpu_bytes()
    {
        var report = new App.DesktopDeliveryReport { RequireGpuTelemetry = true };
        report.RecordMemorySample([Process(1, "desktop", 500_000_000, 900_000_000, 0, 10_000_000),
            Process(2, "worker", 50_000_000, 1_100_000_000, 600_000_000, 20_000_000)], null);
        report.RecordMemorySample([Process(1, "desktop", 50_000_000, 900_000_000, 0, 10_000_000),
            Process(2, "worker", 500_000_000, 1_100_000_000, 600_000_000, 20_000_000)], null);
        report.ValidateMemoryGate();
        Assert.Empty(report.Failures);
        Assert.Equal(550_000_000, report.PeakWorkingSetBytes);
        Assert.Equal(580_000_000, report.PeakConservativeRamBytes);
        Assert.Equal(2_000_000_000, report.PeakPrivateBytes);
        Assert.Equal(600_000_000, report.PeakGpuDedicatedBytes);
        Assert.Equal(580_000_000, report.MemoryAtPeakConservativeRam!.ConservativeRamBytes);
    }

    [Fact]
    public void Shared_gpu_memory_can_fail_the_cap_while_working_sets_alone_pass()
    {
        var report = new App.DesktopDeliveryReport { RequireGpuTelemetry = true };
        report.RecordMemorySample([Process(1, "desktop", 120_000_000, 200_000_000, 0, 10_000_000),
            Process(2, "worker", 490_000_000, 1_000_000_000, 600_000_000, 50_000_000)], null);
        report.ValidateMemoryGate();
        Assert.Equal(670_000_000, report.PeakConservativeRamBytes);
        Assert.Contains(report.Failures, error => error.Contains("physical RAM", StringComparison.Ordinal));
    }

    [Fact]
    public void Missing_gpu_telemetry_is_explicit_and_fails_gpu_acceptance()
    {
        var report = new App.DesktopDeliveryReport { RequireGpuTelemetry = true };
        report.RecordMemorySample([new(1, "desktop", new(100, 200), null), new(2, "worker", new(300, 400), null)], "PDH unavailable");
        report.ValidateMemoryGate();
        Assert.Null(report.PeakConservativeRamBytes);
        Assert.Equal(400, report.PeakWorkingSetBytes);
        Assert.Single(report.GpuTelemetryErrors);
        Assert.Null(report.ProcessMemoryPeaks[0].SharedGpuBytes);
        Assert.Null(report.PeakGpuSharedBytes);
        Assert.Contains(report.Failures, error => error.Contains("complete", StringComparison.Ordinal));
    }

    [Fact]
    public void Cpu_worker_with_valid_zero_activity_can_pass_without_gpu_worker_acceptance()
    {
        var report = new App.DesktopDeliveryReport();
        report.RecordMemorySample([new(1, "desktop", new(100, 200), new(1, 0, 0, 0, false)),
            new(2, "worker", new(300, 400), new(2, 0, 0, 0, false))], null);
        report.ValidateMemoryGate();
        Assert.Empty(report.Failures);
        Assert.Equal(0, report.PeakGpuSharedBytes);
        Assert.False(report.WorkerGpuInstanceObserved);
    }

    [Fact]
    public void Valid_zero_gpu_activity_does_not_establish_gpu_worker_acceptance()
    {
        var report = new App.DesktopDeliveryReport { RequireGpuTelemetry = true };
        report.RecordMemorySample([new(1, "desktop", new(100, 200), new(1, 0, 0, 0, false)),
            new(2, "worker", new(300, 400), new(2, 0, 0, 0, false))], null);
        report.ValidateMemoryGate();
        Assert.Equal(400, report.PeakConservativeRamBytes);
        Assert.Contains(report.Failures, error => error.Contains("worker GPU counter", StringComparison.Ordinal));
    }

    private static App.DesktopProcessMemorySample Process(int id, string role, long working, long committed, long dedicated, long shared) =>
        new(id, role, new(working, committed), new(id, dedicated, shared, dedicated + shared, true));
}

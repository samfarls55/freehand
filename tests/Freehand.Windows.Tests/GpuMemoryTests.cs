using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class GpuMemoryTests
{
    [Fact]
    public void Sums_adapters_for_each_requested_process_without_matching_similar_process_ids()
    {
        var samples = GaugeSet("pid_12_luid_a", 10, 2, 12)
            .Concat(GaugeSet("pid_12_luid_b", 20, 3, 23))
            .Concat(GaugeSet("pid_123_luid_a", 100, 40, 140)).ToArray();
        var snapshot = WindowsGpuMemoryReader.Aggregate([12, 123, 9], samples);
        Assert.True(snapshot.IsAvailable);
        Assert.Equal(new Freehand.Abstractions.ProcessGpuMemory(12, 30, 5, 35, true), snapshot.Processes[0]);
        Assert.Equal(new Freehand.Abstractions.ProcessGpuMemory(123, 100, 40, 140, true), snapshot.Processes[1]);
        Assert.Equal(new Freehand.Abstractions.ProcessGpuMemory(9, 0, 0, 0, false), snapshot.Processes[2]);
    }

    [Fact]
    public void Missing_one_adapter_gauge_is_unavailable_instead_of_zero()
    {
        var samples = GaugeSet("pid_12_luid_a", 10, 2, 12)
            .Append(new(GpuCounterKind.Dedicated, "pid_12_luid_b", 20, 0)).ToArray();
        var snapshot = WindowsGpuMemoryReader.Aggregate([12], samples);
        Assert.False(snapshot.IsAvailable);
        Assert.Empty(snapshot.Processes);
        Assert.Contains("Incomplete", snapshot.Error, StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(0x800007D1u, 10)]
    [InlineData(0u, -1)]
    public void Invalid_matching_gauges_fail_without_hiding_unrelated_invalid_instances(uint status, long bytes)
    {
        var samples = GaugeSet("pid_12_luid_a", 10, 2, 12)
            .Append(new(GpuCounterKind.Dedicated, "pid_99_luid_b", bytes, status)).ToArray();
        Assert.True(WindowsGpuMemoryReader.Aggregate([12], samples).IsAvailable);
        Assert.False(WindowsGpuMemoryReader.Aggregate([99], samples).IsAvailable);
    }

    private static GpuCounterValue[] GaugeSet(string name, long dedicated, long shared, long committed) =>
    [
        new(GpuCounterKind.Dedicated, name, dedicated, 0),
        new(GpuCounterKind.Shared, name, shared, 1),
        new(GpuCounterKind.Committed, name, committed, 0),
    ];
}

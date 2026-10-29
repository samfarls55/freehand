using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class ProcessMemoryTests
{
    [Fact]
    public void Reads_live_process_counters_and_rejects_an_invalid_process()
    {
        var reader = new WindowsProcessMemoryReader();
        Assert.True(reader.TryRead(Environment.ProcessId, out var memory));
        Assert.True(memory.WorkingSetBytes > 0);
        Assert.True(memory.PrivateBytes > 0);
        Assert.False(reader.TryRead(-1, out _));
    }
}

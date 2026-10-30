using System.Diagnostics;
using Freehand.Abstractions;
using Freehand.App;
using Xunit;

namespace Freehand.AppTests;

public sealed class BenchmarkWorkerOwnershipTests
{
    [Fact]
    public async Task Exited_owned_worker_is_not_confused_with_another_live_owner_using_the_same_executable()
    {
        using var firstOwner = new BenchmarkWorkerLauncher(new WaitingProcessLauncher());
        using var otherOwner = new BenchmarkWorkerLauncher(new WaitingProcessLauncher());
        await using var first = firstOwner.Launch("unused", "unused");
        await using var unrelated = otherOwner.Launch("unused", "unused");
        var originalIdentity = Assert.Single(firstOwner.Snapshot());
        Assert.Equal(first.Id, originalIdentity.ProcessId);
        Assert.False(originalIdentity.HasExited);
        Assert.False(Assert.Single(otherOwner.Snapshot()).HasExited);

        await first.DisposeAsync();

        // The other owner's process is still live at the same executable path.
        // A path-wide orphan check fails here, even though our worker exited.
        using var stillLive = Process.GetProcessById(unrelated.Id);
        Assert.False(stillLive.HasExited);
        var ended = Assert.Single(firstOwner.Snapshot());
        Assert.Equal(originalIdentity.ProcessId, ended.ProcessId);
        Assert.Equal(originalIdentity.StartTimeUtc, ended.StartTimeUtc);
        Assert.True(ended.HasExited);
        Assert.DoesNotContain(firstOwner.Snapshot(), worker => !worker.HasExited);
        Assert.False(Assert.Single(otherOwner.Snapshot()).HasExited);

        await unrelated.DisposeAsync();
        Assert.All(otherOwner.Snapshot(), worker => Assert.True(worker.HasExited));
    }

    private sealed class WaitingProcessLauncher : IWorkerLauncher
    {
        public IWorkerProcess Launch(string pipeName, string secret)
        {
            var start = new ProcessStartInfo(OperatingSystem.IsWindows() ? "cmd.exe" : "/bin/sh")
            {
                UseShellExecute = false, CreateNoWindow = true, RedirectStandardInput = true,
                RedirectStandardOutput = true, RedirectStandardError = true,
            };
            if (OperatingSystem.IsWindows())
            {
                start.ArgumentList.Add("/d"); start.ArgumentList.Add("/c");
                start.ArgumentList.Add("set /p FREEHAND_BENCHMARK_TEST_INPUT=");
            }
            else
            {
                start.ArgumentList.Add("-c"); start.ArgumentList.Add("read FREEHAND_BENCHMARK_TEST_INPUT");
            }
            return new WaitingProcess(Process.Start(start) ?? throw new IOException("Test child failed to start"));
        }
    }

    private sealed class WaitingProcess(Process process) : IWorkerProcess
    {
        private bool _disposed;
        public int Id { get; } = process.Id;
        public bool HasExited => _disposed || process.HasExited;
        public Task WaitForExitAsync(CancellationToken cancellationToken) => process.WaitForExitAsync(cancellationToken);
        public void Terminate() { if (!process.HasExited) process.Kill(true); }
        public async ValueTask DisposeAsync()
        {
            if (_disposed) return;
            process.StandardInput.Close();
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            await process.WaitForExitAsync(deadline.Token);
            _disposed = true;
            process.Dispose();
        }
    }
}

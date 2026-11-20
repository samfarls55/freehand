using System.Diagnostics;
using Freehand.Abstractions;
using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class CleanupWorkerTests
{
    [Fact]
    public void A_relative_executable_is_rejected_before_launch()
    {
        var launcher = new WindowsCleanupWorkerLauncher();
        Assert.Throws<ArgumentException>(() => launcher.Launch(new CleanupWorkerStartInfo(
            "llama-server.exe", [], new Dictionary<string, string>())));
    }

    [Fact]
    public async Task Verbose_output_is_drained_and_disposal_terminates_the_worker()
    {
        var directory = Path.Combine(Path.GetTempPath(), "Freehand cleanup worker " + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var script = Path.Combine(directory, "verbose-worker.cmd");
        var completed = Path.Combine(directory, "output completed.txt");
        await File.WriteAllTextAsync(script, """
            @echo off
            for /L %%i in (1,1,20000) do (
              echo discarded stdout output
              echo discarded stderr output 1>&2
            )
            echo complete > "%FREEHAND_CLEANUP_TEST_MARKER%"
            ping -n 60 127.0.0.1 >nul
            """);
        try
        {
            var launcher = new WindowsCleanupWorkerLauncher();
            var executable = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe");
            var worker = launcher.Launch(new CleanupWorkerStartInfo(executable, ["/D", "/C", script],
                new Dictionary<string, string> { ["FREEHAND_CLEANUP_TEST_MARKER"] = completed }));
            try
            {
                using var process = Process.GetProcessById(worker.Id);
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                while (!File.Exists(completed)) await Task.Delay(20, deadline.Token);
                Assert.False(worker.HasExited);
                // Cancelling one caller's wait must not terminate an active runtime.
                using var cancelled = new CancellationTokenSource();
                cancelled.Cancel();
                await Assert.ThrowsAnyAsync<OperationCanceledException>(() => worker.WaitForExitAsync(cancelled.Token));
                Assert.False(worker.HasExited);

                await worker.DisposeAsync();
                Assert.True(worker.HasExited);
                await process.WaitForExitAsync().WaitAsync(TimeSpan.FromSeconds(5));
                await worker.WaitForExitAsync(CancellationToken.None);
                worker.Terminate();
                await worker.DisposeAsync();
            }
            finally { await worker.DisposeAsync(); }
        }
        finally { Directory.Delete(directory, recursive: true); }
    }

    [Fact]
    public async Task Termination_closes_the_job_and_allows_a_waiting_caller_to_finish()
    {
        var executable = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "cmd.exe");
        var worker = new WindowsCleanupWorkerLauncher().Launch(new CleanupWorkerStartInfo(executable,
            ["/D", "/C", "for /L %i in (1,1,100000000) do @rem waiting"], new Dictionary<string, string>()));
        await using (worker)
        {
            var exited = worker.WaitForExitAsync(CancellationToken.None);
            worker.Terminate();
            await exited.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.True(worker.HasExited);
        }
    }
}

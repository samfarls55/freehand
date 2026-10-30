using System.Diagnostics;
using Freehand.Abstractions;

namespace Freehand.Cleanup.Probe;

// Evaluation-only launcher. Windows application process ownership stays in the
// platform project; this executable needs a portable launcher for Linux probes.
internal sealed class ProbeCleanupWorkerLauncher : ICleanupWorkerLauncher
{
    public IWorkerProcess Launch(CleanupWorkerStartInfo startInfo)
    {
        ArgumentNullException.ThrowIfNull(startInfo);
        var start = new ProcessStartInfo(startInfo.ExecutablePath)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            WorkingDirectory = Path.GetDirectoryName(startInfo.ExecutablePath)!,
        };
        foreach (var argument in startInfo.Arguments) start.ArgumentList.Add(argument);
        foreach (var pair in startInfo.EnvironmentVariables) start.Environment[pair.Key] = pair.Value;
        return new ProbeWorker(Process.Start(start) ?? throw new IOException("Cleanup worker did not start."));
    }

    private sealed class ProbeWorker : IWorkerProcess
    {
        private readonly Process _process;
        private readonly Task _stdout;
        private readonly Task _stderr;
        private int _disposed;

        internal ProbeWorker(Process process)
        {
            _process = process;
            // Drain native output without retaining or printing transcript content.
            _stdout = process.StandardOutput.BaseStream.CopyToAsync(Stream.Null);
            _stderr = process.StandardError.BaseStream.CopyToAsync(Stream.Null);
        }

        public int Id => _process.Id;
        public bool HasExited => _process.HasExited;
        public Task WaitForExitAsync(CancellationToken cancellationToken) => _process.WaitForExitAsync(cancellationToken);

        public void Terminate()
        {
            try { if (!_process.HasExited) _process.Kill(entireProcessTree: true); }
            catch (InvalidOperationException) when (_process.HasExited) { }
        }

        public async ValueTask DisposeAsync()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
            try
            {
                Terminate();
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
                await _process.WaitForExitAsync(deadline.Token).ConfigureAwait(false);
                await Task.WhenAll(_stdout, _stderr).WaitAsync(deadline.Token).ConfigureAwait(false);
            }
            finally { _process.Dispose(); }
        }
    }
}

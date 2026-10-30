using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Freehand.Abstractions;
using Microsoft.Win32.SafeHandles;

namespace Freehand.Platform.Windows;

/// <summary>Starts a hidden local cleanup runtime owned by a kill-on-close Windows Job Object.</summary>
public sealed class WindowsCleanupWorkerLauncher : ICleanupWorkerLauncher
{
    /// <inheritdoc />
    public IWorkerProcess Launch(CleanupWorkerStartInfo startInfo)
    {
        ArgumentNullException.ThrowIfNull(startInfo);
        if (!Path.IsPathFullyQualified(startInfo.ExecutablePath))
            throw new ArgumentException("The cleanup runtime path must be absolute.", nameof(startInfo));

        var start = new ProcessStartInfo(startInfo.ExecutablePath)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            WorkingDirectory = Path.GetDirectoryName(startInfo.ExecutablePath)!,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var argument in startInfo.Arguments) start.ArgumentList.Add(argument);
        foreach (var variable in startInfo.EnvironmentVariables) start.Environment[variable.Key] = variable.Value;

        var job = CreateJobObject(IntPtr.Zero, null);
        if (job.IsInvalid) { job.Dispose(); throw new Win32Exception(Marshal.GetLastWin32Error()); }
        Process? process = null;
        try
        {
            var limits = new ExtendedLimits { Basic = new BasicLimits { Flags = 0x2000 } };
            if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<ExtendedLimits>()))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            process = Process.Start(start) ?? throw new InvalidOperationException("Cleanup runtime did not start.");
            if (!AssignProcessToJobObject(job, process.Handle)) throw new Win32Exception(Marshal.GetLastWin32Error());
            return new OwnedCleanupWorker(process, job);
        }
        catch
        {
            // Arguments and output can contain a per-worker API key or transcript content.
            // Deliberately attach neither to exceptions or diagnostic messages.
            job.Dispose();
            if (process is not null)
            {
                try { if (!process.HasExited) process.Kill(entireProcessTree: true); }
                catch (InvalidOperationException) { }
                finally { process.Dispose(); }
            }
            throw;
        }
    }

    private sealed class OwnedCleanupWorker : IWorkerProcess
    {
        private readonly object _sync = new();
        private readonly Process _process;
        private readonly SafeFileHandle _job;
        private readonly Task _exited;
        private readonly Task _output;
        private readonly Task _error;
        private readonly CancellationTokenSource _drainCancellation = new();
        private Task? _disposeTask;
        private bool _disposed;

        internal OwnedCleanupWorker(Process process, SafeFileHandle job)
        {
            _process = process; _job = job; Id = process.Id;
            _output = DrainAsync(process.StandardOutput, _drainCancellation.Token);
            _error = DrainAsync(process.StandardError, _drainCancellation.Token);
            _exited = process.WaitForExitAsync();
        }

        public int Id { get; }

        public bool HasExited
        {
            get
            {
                lock (_sync) return _disposed || _process.HasExited;
            }
        }

        public Task WaitForExitAsync(CancellationToken cancellationToken) => _exited.WaitAsync(cancellationToken);

        public void Terminate()
        {
            // Closing the job also terminates any descendants that inherited output handles.
            lock (_sync) if (!_disposed) _job.Dispose();
        }

        public ValueTask DisposeAsync()
        {
            lock (_sync) return new ValueTask(_disposeTask ??= DisposeCoreAsync());
        }

        private async Task DisposeCoreAsync()
        {
            try
            {
                _job.Dispose();
                await _exited.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
            }
            finally
            {
                await _drainCancellation.CancelAsync().ConfigureAwait(false);
                try { await Task.WhenAll(_output, _error).WaitAsync(TimeSpan.FromSeconds(2)).ConfigureAwait(false); }
                finally
                {
                    lock (_sync) { _disposed = true; _process.Dispose(); }
                    _drainCancellation.Dispose();
                }
            }
        }

        private static async Task DrainAsync(StreamReader reader, CancellationToken cancellationToken)
        {
            // Fixed buffers prevent verbose native output from blocking the worker or
            // accumulating in memory. Content is discarded rather than logged.
            var buffer = new char[4096];
            try
            {
                while (await reader.ReadAsync(buffer.AsMemory(), cancellationToken).ConfigureAwait(false) != 0) { }
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { }
            catch (IOException) { }
            catch (ObjectDisposedException) { }
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct BasicLimits
    {
        internal long ProcessTime, JobTime;
        internal uint Flags;
        internal nuint MinWorkingSet, MaxWorkingSet;
        internal uint ActiveProcesses;
        internal nuint Affinity;
        internal uint Priority, Scheduling;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct IoCounters { internal ulong Read, Write, Other, ReadBytes, WriteBytes, OtherBytes; }

    [StructLayout(LayoutKind.Sequential)]
    private struct ExtendedLimits
    {
        internal BasicLimits Basic;
        internal IoCounters Io;
        internal nuint ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }

    [DllImport("kernel32.dll", EntryPoint = "CreateJobObjectW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateJobObject(IntPtr attributes, string? name);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetInformationJobObject(SafeFileHandle job, int infoClass, ref ExtendedLimits info, uint length);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AssignProcessToJobObject(SafeFileHandle job, IntPtr process);
}

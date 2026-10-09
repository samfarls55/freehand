using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

/// <summary>Owns child processes through a kill-on-close Windows Job Object.</summary>
public sealed class WindowsWorkerLauncher : IWorkerLauncher
{
    /// <inheritdoc />
    public IWorkerProcess Launch(string pipeName, string secret)
    {
        var start = new ProcessStartInfo(Environment.ProcessPath ?? throw new InvalidOperationException("Executable path unavailable"))
            { UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden };
        if (Path.GetFileNameWithoutExtension(start.FileName).Equals("dotnet", StringComparison.OrdinalIgnoreCase))
            start.ArgumentList.Add(Environment.GetCommandLineArgs()[0]);
        start.ArgumentList.Add("--speech-worker"); start.ArgumentList.Add(pipeName); start.ArgumentList.Add(secret);
        using var parent = Process.GetCurrentProcess();
        start.ArgumentList.Add(Environment.ProcessId.ToString(CultureInfo.InvariantCulture));
        start.ArgumentList.Add(parent.StartTime.ToUniversalTime().Ticks.ToString(CultureInfo.InvariantCulture));
        var job = CreateJobObject(IntPtr.Zero, null);
        if (job.IsInvalid) { job.Dispose(); throw new Win32Exception(Marshal.GetLastWin32Error()); }
        Process? process = null;
        try
        {
            var limits = new ExtendedLimits { Basic = new BasicLimits { Flags = 0x2000 } };
            if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf<ExtendedLimits>())) throw new Win32Exception(Marshal.GetLastWin32Error());
            process = Process.Start(start) ?? throw new InvalidOperationException("Worker did not start");
            if (!AssignProcessToJobObject(job, process.Handle)) throw new Win32Exception(Marshal.GetLastWin32Error());
            return new OwnedWorker(process, job);
        }
        catch
        {
            if (process is not null) { if (!process.HasExited) process.Kill(true); process.Dispose(); }
            job.Dispose(); throw;
        }
    }
    private sealed class OwnedWorker(Process process, SafeFileHandle job) : IWorkerProcess
    {
        private readonly int _id = process.Id;
        private volatile bool _disposed;
        public int Id => _id;
        public bool HasExited
        {
            get
            {
                if (_disposed) return true;
                try { return process.HasExited; }
                catch (InvalidOperationException) when (_disposed) { return true; }
            }
        }
        public Task WaitForExitAsync(CancellationToken cancellationToken) => process.WaitForExitAsync(cancellationToken);
        public void Terminate() { if (!process.HasExited) process.Kill(true); }
        public async ValueTask DisposeAsync()
        {
            job.Dispose();
            if (!process.HasExited) { using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5)); await process.WaitForExitAsync(deadline.Token).ConfigureAwait(false); }
            _disposed = true;
            process.Dispose();
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

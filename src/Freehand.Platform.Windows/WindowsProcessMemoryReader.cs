using System.Runtime.InteropServices;
using Freehand.Abstractions;
using Microsoft.Win32.SafeHandles;

namespace Freehand.Platform.Windows;

/// <summary>Queries only the named process through Windows memory counters.</summary>
public sealed class WindowsProcessMemoryReader : IProcessMemoryReader
{
    /// <inheritdoc />
    public bool TryRead(int processId, out ProcessMemory memory)
    {
        memory = default;
        using var process = OpenProcess(0x1000, false, processId);
        if (process.IsInvalid) return false;
        var counters = new MemoryCounters { Size = (uint)Marshal.SizeOf<MemoryCounters>() };
        if (!GetProcessMemoryInfo(process, ref counters, counters.Size)) return false;
        memory = new ProcessMemory((long)counters.WorkingSet, (long)counters.PrivateUsage);
        return true;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MemoryCounters
    {
        internal uint Size, PageFaults;
        internal nuint PeakWorkingSet, WorkingSet, PeakPagedPool, PagedPool,
            PeakNonPagedPool, NonPagedPool, Pagefile, PeakPagefile, PrivateUsage;
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern SafeProcessHandle OpenProcess(uint access, [MarshalAs(UnmanagedType.Bool)] bool inherit, int processId);

    [DllImport("kernel32.dll", EntryPoint = "K32GetProcessMemoryInfo", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetProcessMemoryInfo(SafeProcessHandle process, ref MemoryCounters counters, uint size);
}

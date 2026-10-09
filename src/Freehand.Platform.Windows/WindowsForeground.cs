using System.Runtime.InteropServices;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

internal static class WindowsForeground
{
    internal static ForegroundTarget Capture()
    {
        var window = GetForegroundWindow();
        return GetWindowThreadProcessId(window, out var pid) == 0 ? default : new ForegroundTarget(window, checked((int)pid));
    }
    internal static bool IsCurrent(ForegroundTarget target) => target.Window != 0 && Capture() == target;
    [DllImport("user32.dll")] private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint window, out uint pid);
}

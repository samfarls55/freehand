using System.Runtime.InteropServices;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

internal static class WindowsForeground
{
    internal static ForegroundTarget Capture()
    {
        var window = GetForegroundWindow();
        var thread = GetWindowThreadProcessId(window, out var pid);
        return thread == 0 ? default : new ForegroundTarget(window, checked((int)pid)) { FocusedControl = FocusedWindow(thread) };
    }
    internal static bool IsCurrent(ForegroundTarget target)
    {
        if (target.Window == 0 || GetForegroundWindow() != target.Window) return false;
        var thread = GetWindowThreadProcessId(target.Window, out var pid);
        return thread != 0 && pid == (uint)target.ProcessId &&
            (target.FocusedControl == 0 || FocusedWindow(thread) == target.FocusedControl);
    }

    internal static nint FocusedWindow(ForegroundTarget target) => FocusedWindow(GetWindowThreadProcessId(target.Window, out _));

    private static nint FocusedWindow(uint thread)
    {
        var info = new GuiThreadInfo { Size = Marshal.SizeOf<GuiThreadInfo>() };
        return thread != 0 && GetGUIThreadInfo(thread, ref info) ? info.Focus : 0;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct GuiThreadInfo
    {
        internal int Size, Flags;
        internal nint Active, Focus, Capture, MenuOwner, MoveSize, Caret;
        internal int Left, Top, Right, Bottom;
    }

    [DllImport("user32.dll")] private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint window, out uint pid);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetGUIThreadInfo(uint thread, ref GuiThreadInfo info);
}

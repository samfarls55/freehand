using System.Diagnostics;
using System.Runtime.InteropServices;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

internal sealed class WindowsClipboardPaste : IDisposable
{
    private const uint UnicodeText = 13;
    private const uint Bitmap = 2;
    private const uint Palette = 9;
    private const uint RenderFormat = 0x0305;
    private const uint RenderAllFormats = 0x0306;
    private static readonly TimeSpan ModifierTimeout = TimeSpan.FromSeconds(1);
    private static readonly TimeSpan RestoreTimeout = TimeSpan.FromSeconds(5);
    private static readonly uint PrivacyFormat = RegisterClipboardFormat("ExcludeClipboardContentFromMonitorProcessing");
    // OLE's clipboard bookkeeping only describes OLE's own ownership. The content formats
    // beside it are restored; these would point the next OleGetClipboard at a stale owner.
    private static readonly uint[] OleOwnership = [RegisterClipboardFormat("DataObject"), RegisterClipboardFormat("Ole Private Data")];

    private readonly ForegroundTarget _target;
    private readonly WindowProcedure _procedure;
    private readonly List<(uint Format, nint Handle)> _original = [];
    private readonly nint _window;
    private readonly nint _defaultProcedure;
    private nint _transcript;
    private long _readAt;
    private bool _shortcutStarted;

    internal WindowsClipboardPaste(ForegroundTarget target)
    {
        _target = target;
        _procedure = HandleMessage;
        _window = CreateWindow(0, "STATIC", "", 0, 0, 0, 0, 0, new nint(-3), 0, 0, 0);
        if (_window != 0) _defaultProcedure = SetWindowLongPtr(_window, -4, Marshal.GetFunctionPointerForDelegate(_procedure));
    }

    // A null outcome allows keyboard fallback. It is used only before a shortcut can reach the target.
    internal DeliveryOutcome? Deliver(string text, CancellationToken token)
    {
        if (_defaultProcedure == 0 || PrivacyFormat == 0) return null;
        var (useInsert, restoreDelay) = ClipboardPasteTextInjector.PasteBehavior(_target.ProcessId);
        var started = Stopwatch.GetTimestamp();
        while (SendInputTextInjector.ModifiersHeld())
        {
            token.ThrowIfCancellationRequested();
            if (!TargetHasFocus()) return DeliveryOutcome.TargetChanged;
            if (Stopwatch.GetElapsedTime(started) >= ModifierTimeout) return DeliveryOutcome.PartialOrUncertain;
            Thread.Sleep(5);
        }

        if (!TargetHasFocus()) return DeliveryOutcome.TargetChanged;
        if (!Prepare(text)) return TargetHasFocus() ? null : DeliveryOutcome.TargetChanged;

        try
        {
            token.ThrowIfCancellationRequested();
            if (!TargetHasFocus()) return DeliveryOutcome.TargetChanged;
            if (GetClipboardOwner() != _window || SendInputTextInjector.ModifiersHeld()) return DeliveryOutcome.PartialOrUncertain;

            _shortcutStarted = true;
            if (!SendInputTextInjector.SendPasteShortcut(useInsert)) return DeliveryOutcome.PartialOrUncertain;

            started = Stopwatch.GetTimestamp();
            while (GetClipboardOwner() == _window)
            {
                token.ThrowIfCancellationRequested();
                PumpMessages();
                if (_readAt != 0)
                {
                    if (Stopwatch.GetElapsedTime(_readAt) >= restoreDelay) return DeliveryOutcome.Delivered;
                }
                else
                {
                    if (!TargetHasFocus()) return DeliveryOutcome.PartialOrUncertain;
                    // The target ignored the paste. Freehand keeps the transcript for Copy;
                    // the user's own clipboard must come back.
                    if (Stopwatch.GetElapsedTime(started) >= restoreDelay + TimeSpan.FromSeconds(1)) return DeliveryOutcome.PartialOrUncertain;
                }
                Thread.Sleep(5);
            }

            return _readAt == 0 ? DeliveryOutcome.PartialOrUncertain : DeliveryOutcome.Delivered;
        }
        finally
        {
            Restore();
        }
    }

    private bool TargetHasFocus() => WindowsForeground.IsCurrent(_target);

    private bool Prepare(string text)
    {
        var normalized = text.Replace("\r\n", "\n", StringComparison.Ordinal).Replace('\r', '\n').Replace("\n", "\r\n", StringComparison.Ordinal);
        _transcript = Allocate(checked((nuint)(normalized.Length + 1) * sizeof(char)));
        var privacy = Allocate(sizeof(uint));
        try
        {
            if (_transcript == 0 || privacy == 0) return false;
            var pointer = GlobalLock(_transcript);
            if (pointer == 0) return false;
            Marshal.Copy(normalized.ToCharArray(), 0, pointer, normalized.Length);
            _ = GlobalUnlock(_transcript);
            if (!OpenClipboard(_window)) return false;
            try
            {
                // Copy every format before replacing the clipboard. Data that can't be copied stays with its owner.
                for (uint format = 0; ;)
                {
                    format = EnumClipboardFormats(format);
                    if (format == 0)
                    {
                        if (Marshal.GetLastPInvokeError() != 0) return false;
                        break;
                    }
                    if (OleOwnership.Contains(format)) continue;
                    var handle = GetClipboardData(format);
                    if (handle == 0) return false;
                    var copy = OleDuplicateData(handle, (ushort)format, 0);
                    if (copy == 0) return false;
                    _original.Add((format, copy));
                }

                if (!TargetHasFocus() || !EmptyClipboard()) return false;
                if (SetClipboardData(PrivacyFormat, privacy) != 0)
                {
                    privacy = 0;
                    _ = SetClipboardData(UnicodeText, 0);
                    if (IsClipboardFormatAvailable(UnicodeText)) return true;
                }

                RestoreOpenClipboard();
                return false;
            }
            finally { _ = CloseClipboard(); }
        }
        finally { if (privacy != 0) _ = GlobalFree(privacy); }
    }

    private void Restore()
    {
        var started = Stopwatch.GetTimestamp();
        // Another app may hold the clipboard open briefly; the saved copy is freed after this.
        while (GetClipboardOwner() == _window && Stopwatch.GetElapsedTime(started) < RestoreTimeout)
        {
            if (OpenClipboard(_window))
            {
                try { if (GetClipboardOwner() == _window) RestoreOpenClipboard(); }
                finally { _ = CloseClipboard(); }
                return;
            }
            PumpMessages();
            Thread.Sleep(5);
        }
    }

    private void RestoreOpenClipboard()
    {
        if (!EmptyClipboard()) return;
        for (var i = 0; i < _original.Count; i++)
        {
            var (format, handle) = _original[i];
            if (SetClipboardData(format, handle) != 0) _original[i] = (format, 0);
        }
    }

    private nint HandleMessage(nint window, uint message, nuint wParam, nint lParam)
    {
        if (message == RenderFormat && wParam == UnicodeText)
        {
            var reader = GetOpenClipboardWindow();
            if (!_shortcutStarted || !TargetHasFocus() ||
                (reader != 0 && GetWindowThreadProcessId(reader, out var pid) != 0 && pid != (uint)_target.ProcessId)) return 0;
            if (RenderTranscript()) _readAt = Stopwatch.GetTimestamp();
            return 0;
        }

        if (message == RenderAllFormats && _transcript != 0 && OpenClipboard(window))
        {
            try { if (GetClipboardOwner() == window) _ = RenderTranscript(); }
            finally { _ = CloseClipboard(); }
            return 0;
        }

        return CallWindowProc(_defaultProcedure, window, message, wParam, lParam);
    }

    private bool RenderTranscript()
    {
        if (_transcript == 0 || SetClipboardData(UnicodeText, _transcript) == 0) return false;
        _transcript = 0;
        return true;
    }

    private static nint Allocate(nuint size) => GlobalAlloc(0x42, size); // movable, zero-initialized

    private static void PumpMessages()
    {
        while (PeekMessage(out var message, 0, 0, 0, 1)) _ = DispatchMessage(ref message);
    }

    public void Dispose()
    {
        if (_window != 0) _ = DestroyWindow(_window);
        GC.KeepAlive(_procedure);
        if (_transcript != 0) _ = GlobalFree(_transcript);
        foreach (var (format, handle) in _original)
        {
            if (handle == 0) continue;
            if (format is Bitmap or Palette) _ = DeleteObject(handle);
            else _ = GlobalFree(handle);
        }
    }

    private delegate nint WindowProcedure(nint window, uint message, nuint wParam, nint lParam);
    [StructLayout(LayoutKind.Sequential)]
    private struct Message { internal nint Window; internal uint Id; internal nuint WParam; internal nint LParam; internal uint Time; internal int X, Y; internal uint Private; }

    [DllImport("user32.dll", EntryPoint = "CreateWindowExW", CharSet = CharSet.Unicode)] private static extern nint CreateWindow(uint ex, string cls, string title, uint style, int x, int y, int width, int height, nint parent, nint menu, nint instance, nint param);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] private static extern nint SetWindowLongPtr(nint window, int index, nint value);
    [DllImport("user32.dll", EntryPoint = "CallWindowProcW")] private static extern nint CallWindowProc(nint proc, nint window, uint message, nuint wParam, nint lParam);
    [DllImport("user32.dll", EntryPoint = "PeekMessageW")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool PeekMessage(out Message message, nint window, uint min, uint max, uint flags);
    [DllImport("user32.dll", EntryPoint = "DispatchMessageW")] private static extern nint DispatchMessage(ref Message message);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool DestroyWindow(nint window);
    [DllImport("user32.dll", EntryPoint = "RegisterClipboardFormatW", CharSet = CharSet.Unicode)] private static extern uint RegisterClipboardFormat(string name);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool OpenClipboard(nint window);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CloseClipboard();
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool EmptyClipboard();
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool IsClipboardFormatAvailable(uint format);
    [DllImport("user32.dll", SetLastError = true)] private static extern uint EnumClipboardFormats(uint format);
    [DllImport("user32.dll")] private static extern nint GetClipboardData(uint format);
    [DllImport("user32.dll")] private static extern nint SetClipboardData(uint format, nint memory);
    [DllImport("user32.dll")] private static extern nint GetClipboardOwner();
    [DllImport("user32.dll")] private static extern nint GetOpenClipboardWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint window, out uint pid);
    [DllImport("kernel32.dll")] private static extern nint GlobalAlloc(uint flags, nuint size);
    [DllImport("kernel32.dll")] private static extern nint GlobalLock(nint memory);
    [DllImport("kernel32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GlobalUnlock(nint memory);
    [DllImport("kernel32.dll")] private static extern nint GlobalFree(nint memory);
    [DllImport("ole32.dll")] private static extern nint OleDuplicateData(nint source, ushort format, uint flags);
    [DllImport("gdi32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool DeleteObject(nint handle);
}

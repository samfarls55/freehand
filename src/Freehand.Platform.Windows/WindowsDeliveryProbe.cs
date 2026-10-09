using System.Diagnostics;
using System.Runtime.InteropServices;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

/// <summary>Real SendInput validation against an owned Windows EDIT control.</summary>
public sealed class WindowsDeliveryProbe : ITextDeliveryProbe
{
    private readonly Thread _thread;
    private readonly ManualResetEventSlim _ready = new();
    private readonly ManualResetEventSlim _trial = new();
    private readonly WindowProcedure _procedure;
    private nint _window, _edit, _original;
    private uint _threadId;
    private long _first;
    /// <inheritdoc />
    public long FirstInputTimestamp => Interlocked.Read(ref _first);
    /// <summary>Creates a visible engineering test field on its own message thread.</summary>
    public WindowsDeliveryProbe()
    {
        _procedure = EditCallback;
        _thread = new Thread(Run) { IsBackground = true, Name = "Freehand delivery benchmark" };
        _thread.SetApartmentState(ApartmentState.STA); _thread.Start();
        if (!_ready.Wait(TimeSpan.FromSeconds(5)) || _window == 0) throw new InvalidOperationException("Could not create foreground test field");
    }
    private void Run()
    {
        _threadId = GetCurrentThreadId();
        _window = CreateWindowEx(0, "STATIC", "Freehand delivery benchmark", 0x10CF0000, 100, 100, 600, 240, 0, 0, 0, 0);
        _edit = CreateWindowEx(0, "EDIT", "", 0x50801004, 12, 12, 550, 150, _window, 0, 0, 0);
        _original = SetWindowLongPtr(_edit, -4, Marshal.GetFunctionPointerForDelegate(_procedure));
        _ready.Set();
        try
        {
            while (GetMessage(out var message, 0, 0, 0) > 0)
            {
                if (message.Id == 0x8001)
                {
                    SendMessage(_edit, 0x000C, 0, "");
                    Interlocked.Exchange(ref _first, 0);
                    ShowWindow(_window, 5); SetForegroundWindow(_window); SetFocus(_edit); _trial.Set();
                }
                else { TranslateMessage(ref message); DispatchMessage(ref message); }
            }
        }
        finally { DestroyWindow(_window); }
    }
    private nint EditCallback(nint window, uint message, nuint wParam, nint lParam)
    {
        var result = CallWindowProc(_original, window, message, wParam, lParam);
        if (message == 0x0102) Interlocked.CompareExchange(ref _first, Stopwatch.GetTimestamp(), 0);
        return result;
    }
    /// <inheritdoc />
    public ForegroundTarget BeginTrial()
    {
        _trial.Reset();
        if (!PostThreadMessage(_threadId, 0x8001, 0, 0) || !_trial.Wait(TimeSpan.FromSeconds(5))) throw new InvalidOperationException("Test field did not respond");
        var target = new ForegroundTarget(_window, Environment.ProcessId);
        if (GetForegroundWindow() != _window) throw new InvalidOperationException("Windows did not allow the test field to become foreground");
        return target;
    }
    /// <inheritdoc />
    public string ReadText()
    {
        var text = new char[32768]; var count = GetWindowText(_edit, text, text.Length); return new string(text, 0, count);
    }
    /// <inheritdoc />
    public void Dispose()
    {
        PostThreadMessage(_threadId, 0x0012, 0, 0); _thread.Join(TimeSpan.FromSeconds(3));
        _ready.Dispose(); _trial.Dispose();
    }
    private delegate nint WindowProcedure(nint window, uint message, nuint wParam, nint lParam);
    [StructLayout(LayoutKind.Sequential)] private struct Message { internal nint Window; internal uint Id; internal nuint WParam; internal nint LParam; internal uint Time; internal int X, Y; internal uint Private; }
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", EntryPoint = "CreateWindowExW", CharSet = CharSet.Unicode)] private static extern nint CreateWindowEx(uint ex, string cls, string title, uint style, int x, int y, int width, int height, nint parent, nint menu, nint instance, nint param);
    [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] private static extern nint SetWindowLongPtr(nint window, int index, nint value);
    [DllImport("user32.dll", EntryPoint = "CallWindowProcW")] private static extern nint CallWindowProc(nint proc, nint window, uint message, nuint wParam, nint lParam);
    [DllImport("user32.dll", EntryPoint = "GetMessageW")] private static extern int GetMessage(out Message message, nint window, uint min, uint max);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool TranslateMessage(ref Message message);
    [DllImport("user32.dll", EntryPoint = "DispatchMessageW")] private static extern nint DispatchMessage(ref Message message);
    [DllImport("user32.dll", EntryPoint = "PostThreadMessageW")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool PostThreadMessage(uint thread, uint message, nuint wParam, nint lParam);
    [DllImport("user32.dll", EntryPoint = "SendMessageW", CharSet = CharSet.Unicode)] private static extern nint SendMessage(nint window, uint message, nuint wParam, string text);
    [DllImport("user32.dll", EntryPoint = "GetWindowTextW", CharSet = CharSet.Unicode)] private static extern int GetWindowText(nint window, [Out] char[] text, int count);
    [DllImport("user32.dll")] private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool SetForegroundWindow(nint window);
    [DllImport("user32.dll")] private static extern nint SetFocus(nint window);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool ShowWindow(nint window, int command);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool DestroyWindow(nint window);
}

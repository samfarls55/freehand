using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

/// <summary>Per-user desktop ownership, startup, focus and Windows recovery notifications.</summary>
public sealed class WindowsDesktopIntegration : IDesktopIntegration
{
    private Mutex? _instance;
    private EventWaitHandle? _activate;
    private RegisteredWaitHandle? _activationWait;
    private EventWaitHandle? _quit;
    private RegisteredWaitHandle? _quitWait;
    private Thread? _notifications;
    private uint _threadId;
    private readonly WindowProcedure _procedure;
    private readonly string _className = "Freehand.Notifications." + Guid.NewGuid().ToString("N");
    /// <inheritdoc />
    public event EventHandler? ActivationRequested;
    /// <inheritdoc />
    public event EventHandler? ShutdownRequested;
    private static string InstanceName()
    {
        using var identity = WindowsIdentity.GetCurrent();
        var owner = identity.User!.Value;
        // Only the explicit headless packaging probe gets separate ownership. Ordinary
        // development profiles still share the installed hotkey owner's identity.
        if (Environment.GetEnvironmentVariable("FREEHAND_UPDATE_HANDOFF_TEST") == "1"
            && Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY") is { Length: > 0 } profile)
            owner += "|update-test|" + Path.GetFullPath(profile).ToUpperInvariant();
        return "Local\\Freehand.Desktop." + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(owner)));
    }
    /// <inheritdoc />
    public void RequestExistingShutdown()
    {
        try { using var signal = EventWaitHandle.OpenExisting(InstanceName() + ".Quit"); signal.Set(); }
        catch (WaitHandleCannotBeOpenedException) { }
    }
    /// <inheritdoc />
    public event EventHandler? ReadinessInvalidated;
    /// <summary>Creates integration without claiming ownership.</summary>
    public WindowsDesktopIntegration() => _procedure = WindowCallback;
    /// <inheritdoc />
    public bool ClaimInstance()
    {
        var name = InstanceName();
        _instance = new Mutex(false, name, out var created);
        _activate = new EventWaitHandle(false, EventResetMode.AutoReset, name + ".Activate");
        if (!created) { _activate.Set(); Dispose(); return false; }
        Marshal.ThrowExceptionForHR(SetCurrentProcessExplicitAppUserModelID("Sam.Freehand.Windows"));
        _quit = new EventWaitHandle(false, EventResetMode.AutoReset, name + ".Quit");
        return true;
    }
    /// <inheritdoc />
    public void StartNotifications()
    {
        if (_activate is null || _quit is null || _activationWait is not null) return;
        // Named events retain startup requests until the UI has subscribed.
        _activationWait = ThreadPool.RegisterWaitForSingleObject(_activate, (_, timedOut) =>
        {
            if (!timedOut) ActivationRequested?.Invoke(this, EventArgs.Empty);
        }, null, Timeout.Infinite, false);
        _quitWait = ThreadPool.RegisterWaitForSingleObject(_quit, (_, timedOut) =>
        {
            if (!timedOut) ShutdownRequested?.Invoke(this, EventArgs.Empty);
        }, null, Timeout.Infinite, false);
        _notifications = new Thread(NotificationLoop) { IsBackground = true, Name = "Freehand Windows notifications" };
        _notifications.Start();
    }
    /// <inheritdoc />
    public ForegroundTarget Capture()
    {
        return WindowsForeground.Capture();
    }
    /// <inheritdoc />
    public bool IsCurrent(ForegroundTarget target) => WindowsForeground.IsCurrent(target);
    /// <inheritdoc />
    public void SetLoginStartup(bool enabled)
    {
        // A development or verification profile must not change the installed app's login entry.
        if (Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY") is { Length: > 0 }) return;
        using var key = Registry.CurrentUser.CreateSubKey("Software\\Microsoft\\Windows\\CurrentVersion\\Run");
        if (enabled) key.SetValue("Freehand", "\"" + Environment.ProcessPath + "\" --tray", RegistryValueKind.String);
        else key.DeleteValue("Freehand", false);
    }
    /// <inheritdoc />
    public (uint Style, uint ExtendedStyle) GetNonActivatingStyles(uint style, uint extendedStyle) =>
        // WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, without WS_EX_APPWINDOW.
        (style, (extendedStyle | 0x08000000u | 0x00000080u) & ~0x00040000u);
    /// <inheritdoc />
    public (int X, int Y)? GetPointerPosition() => GetCursorPos(out var point) ? (point.X, point.Y) : null;
    /// <inheritdoc />
    public void Open(string path) => Process.Start(new ProcessStartInfo(path) { UseShellExecute = true });
    private void NotificationLoop()
    {
        _threadId = GetCurrentThreadId();
        var cls = new WindowClass { Size = (uint)Marshal.SizeOf<WindowClass>(), Procedure = _procedure, ClassName = _className };
        if (RegisterClassEx(ref cls) == 0) return;
        var window = CreateWindowEx(0, _className, "", 0, 0, 0, 0, 0, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
        try { while (GetMessage(out var message, IntPtr.Zero, 0, 0) > 0) { TranslateMessage(ref message); DispatchMessage(ref message); } }
        finally { if (window != 0) DestroyWindow(window); UnregisterClass(_className, IntPtr.Zero); }
    }
    private nint WindowCallback(nint window, uint message, nuint wParam, nint lParam)
    {
        if (message == 0x0219 || (message == 0x0218 && wParam is 7 or 18)) ReadinessInvalidated?.Invoke(this, EventArgs.Empty);
        return DefWindowProc(window, message, wParam, lParam);
    }
    /// <inheritdoc />
    public void Dispose()
    {
        _activationWait?.Unregister(null); _activationWait = null;
        _quitWait?.Unregister(null); _quitWait = null; _quit?.Dispose(); _quit = null;
        _activate?.Dispose(); _activate = null; _instance?.Dispose(); _instance = null;
        if (_threadId != 0) PostThreadMessage(_threadId, 0x0012, 0, 0);
        _notifications?.Join(TimeSpan.FromSeconds(2)); _notifications = null;
    }
    private delegate nint WindowProcedure(nint window, uint message, nuint wParam, nint lParam);
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct WindowClass
    {
        internal uint Size, Style;
        internal WindowProcedure Procedure;
        internal int ClassExtra, WindowExtra;
        internal nint Instance, Icon, Cursor, Background;
        internal string? MenuName;
        internal string ClassName;
        internal nint SmallIcon;
    }
    [StructLayout(LayoutKind.Sequential)]
    private struct Message { internal nint Window; internal uint Id; internal nuint WParam; internal nint LParam; internal uint Time; internal int X, Y; internal uint Private; }
    [StructLayout(LayoutKind.Sequential)]
    private struct ScreenPoint { internal int X, Y; }
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetCursorPos(out ScreenPoint point);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)] private static extern int SetCurrentProcessExplicitAppUserModelID(string id);
    [DllImport("kernel32.dll")] private static extern uint GetCurrentThreadId();
    [DllImport("user32.dll", EntryPoint = "RegisterClassExW", CharSet = CharSet.Unicode)] private static extern ushort RegisterClassEx(ref WindowClass cls);
    [DllImport("user32.dll", EntryPoint = "CreateWindowExW", CharSet = CharSet.Unicode)] private static extern nint CreateWindowEx(uint exStyle, string cls, string title, uint style, int x, int y, int width, int height, nint parent, nint menu, nint instance, nint param);
    [DllImport("user32.dll", EntryPoint = "DefWindowProcW")] private static extern nint DefWindowProc(nint window, uint message, nuint wParam, nint lParam);
    [DllImport("user32.dll", EntryPoint = "GetMessageW")] private static extern int GetMessage(out Message message, nint window, uint min, uint max);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool TranslateMessage(ref Message message);
    [DllImport("user32.dll", EntryPoint = "DispatchMessageW")] private static extern nint DispatchMessage(ref Message message);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool DestroyWindow(nint window);
    [DllImport("user32.dll", EntryPoint = "UnregisterClassW", CharSet = CharSet.Unicode)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool UnregisterClass(string cls, nint instance);
    [DllImport("user32.dll", EntryPoint = "PostThreadMessageW")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool PostThreadMessage(uint threadId, uint message, nuint wParam, nint lParam);
}

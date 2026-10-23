using System.Runtime.InteropServices;
using System.Threading.Channels;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

/// <summary>
/// Detects press and release of a held keyboard combination globally.
/// </summary>
/// <remarks>
/// <para>
/// <b>Why not <c>RegisterHotKey</c>:</b> it has no key-up notification at all — the API
/// delivers exactly one <c>WM_HOTKEY</c> on press — and its modifier masks are qualifiers
/// rather than triggers, with no left/right distinction. Neither limitation can be worked
/// around. It is the right API for "Ctrl+Shift+D toggles something" and the wrong one for
/// hold-to-talk.
/// </para>
/// <para>
/// <b>Why a dedicated thread:</b> Microsoft's guidance is explicit — low-level hooks should
/// run on their own thread that hands work off and returns immediately. If the hook procedure
/// exceeds <c>LowLevelHooksTimeout</c> (capped at 1000 ms since Windows 10 1709) the system
/// <b>silently removes the hook, with no way for the application to know</b>. A hook on the
/// UI thread dies the first time the app does a slow layout pass.
/// </para>
/// <para>
/// <b>Why the key is never swallowed:</b> the macOS build consumes Right Option because on
/// macOS that key types characters. Here, suppression buys nothing and risks something much
/// worse — if the key-down is swallowed but the key-up escapes (the hook timed out
/// mid-gesture, or focus crossed into an elevated window), the target application believes
/// the modifier is held down forever.
/// </para>
/// </remarks>
public sealed class PushToTalkHook : IHotkeySource, IHotkeyRecorder
{
    private const int WH_KEYBOARD_LL = 13;
    private const int HC_ACTION = 0;

    private const int WM_KEYDOWN = 0x0100;
    private const int WM_KEYUP = 0x0101;
    private const int WM_SYSKEYDOWN = 0x0104;
    private const int WM_SYSKEYUP = 0x0105;
    private const uint WM_QUIT = 0x0012;

    private const uint LLKHF_EXTENDED = 0x01;

    private const int VK_SHIFT = 0x10;
    private const int VK_CONTROL = 0x11;
    private const int VK_MENU = 0x12;
    private const int VK_LSHIFT = 0xA0;
    private const int VK_RSHIFT = 0xA1;
    private const int VK_LCONTROL = 0xA2;
    private const int VK_RCONTROL = 0xA3;
    private const int VK_LMENU = 0xA4;
    private const int VK_RMENU = 0xA5;

    private const int ScanCodeRightShift = 0x36;

    /// <summary>
    /// Stamped into <c>dwExtraInfo</c> so injected text cannot trigger dictation.
    /// </summary>
    public static readonly IntPtr InjectedTag = unchecked((IntPtr)0x4D524D52); // 'MRMR'

    [StructLayout(LayoutKind.Sequential)]
    private struct KBDLLHOOKSTRUCT
    {
        public uint VirtualKey;
        public uint ScanCode;
        public uint Flags;
        public uint Time;
        public IntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MSG
    {
        public IntPtr Window;
        public uint Message;
        public IntPtr WParam;
        public IntPtr LParam;
        public uint Time;
        public int X;
        public int Y;
    }

    private delegate IntPtr HookProc(int code, IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll", EntryPoint = "SetWindowsHookExW", SetLastError = true)]
    private static extern IntPtr SetWindowsHookEx(int idHook, HookProc callback, IntPtr module, uint threadId);

    [DllImport("user32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnhookWindowsHookEx(IntPtr hook);

    [DllImport("user32.dll")]
    private static extern IntPtr CallNextHookEx(IntPtr hook, int code, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll", EntryPoint = "GetModuleHandleW", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr GetModuleHandle(string? name);

    [DllImport("user32.dll", EntryPoint = "GetMessageW")]
    private static extern int GetMessage(out MSG message, IntPtr window, uint filterMin, uint filterMax);

    [DllImport("user32.dll", EntryPoint = "PostThreadMessageW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool PostThreadMessage(uint threadId, uint message, IntPtr wParam, IntPtr lParam);

    [DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    /// <summary>
    /// Roots the delegate for the lifetime of the hook.
    /// </summary>
    /// <remarks>
    /// Microsoft: "you must ensure the callback is not moved around by the garbage collector,
    /// otherwise your app will crash with an ExecutionEngineException." A local variable here
    /// produces a crash minutes or hours later, at random, with no useful stack.
    /// </remarks>
    private HookProc? _callback;

    private IntPtr _hook;
    private Thread? _thread;
    private uint _threadId;
    private readonly object _sync = new();
    private readonly HotkeyState _keys;
    private Recording? _recording;
    private long _generation;
    private bool _disposed;
    private readonly Channel<Notification> _events = Channel.CreateUnbounded<Notification>(
        new UnboundedChannelOptions { SingleReader = true, SingleWriter = true });

    /// <summary>Dispatches ordered notifications outside the Windows hook thread.</summary>
    public PushToTalkHook() : this([0xA3]) { }

    /// <summary>Observes any combination of Windows virtual keys.</summary>
    public PushToTalkHook(int[] keys)
    {
        ArgumentNullException.ThrowIfNull(keys);
        if (keys.Length == 0 || keys.Any(key => key is not (0x03 or >= 0x08 and <= 0xFE))) throw new ArgumentOutOfRangeException(nameof(keys));
        _keys = new HotkeyState(keys);
        _ = DispatchAsync();
    }

    private sealed record Recording(IProgress<IReadOnlyList<int>> Progress)
    {
        internal TaskCompletionSource<IReadOnlyList<int>?> Result { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    private readonly record struct Notification(long Generation, KeyUpdate Update, Recording? Recording);

    private async Task DispatchAsync()
    {
        await foreach (var notification in _events.Reader.ReadAllAsync().ConfigureAwait(false))
        {
            if (notification.Generation != Interlocked.Read(ref _generation)) continue;
            try
            {
                if (notification.Recording is { } recording && notification.Update.CapturedKeys is { } keys)
                {
                    if (recording.Result.Task.IsCompleted) continue;
                    try { recording.Progress.Report(keys); }
                    finally { if (notification.Update.Complete) recording.Result.TrySetResult(keys); }
                }
                else if (notification.Update.Active is { } down)
                {
                    if (down) Pressed?.Invoke(this, EventArgs.Empty);
                    else Released?.Invoke(this, EventArgs.Empty);
                }
            }
            catch (Exception) { /* Subscriber failure must not terminate key dispatch. */ }
        }
    }

    /// <inheritdoc />
    public async Task<IReadOnlyList<int>?> RecordAsync(IProgress<IReadOnlyList<int>> progress, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(progress);
        cancellationToken.ThrowIfCancellationRequested();
        var recording = new Recording(progress);
        lock (_sync)
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            if (_recording is not null) return null;
            Interlocked.Increment(ref _generation);
            _recording = recording; _keys.BeginCapture();
        }
        using var registration = cancellationToken.Register(() => recording.Result.TrySetCanceled(cancellationToken));
        try { return await recording.Result.Task.ConfigureAwait(false); }
        finally
        {
            lock (_sync)
            {
                _recording = null; _keys.EndCapture();
                Interlocked.Increment(ref _generation);
            }
        }
    }

    /// <inheritdoc />
    public event EventHandler? Pressed;

    /// <inheritdoc />
    public event EventHandler? Released;

    /// <inheritdoc />
    public bool Start()
    {
        ObjectDisposedException.ThrowIf(_disposed, this);
        StopListening();

        using var ready = new ManualResetEventSlim(false);
        var installed = false;

        _thread = new Thread(() =>
        {
            _threadId = GetCurrentThreadId();
            _callback = Callback;

            // Pass the running module's handle. IntPtr.Zero is documented as possibly
            // failing when threadId is 0, which is exactly the global case.
            _hook = SetWindowsHookEx(WH_KEYBOARD_LL, _callback, GetModuleHandle(null), 0);
            installed = _hook != IntPtr.Zero;

            // ReSharper disable once AccessToDisposedClosure
            ready.Set();
            if (!installed) return;

            // Required. The system delivers hook callbacks by *sending a message* to this
            // thread, so without a pump the hook is installed but never invoked.
            while (GetMessage(out var message, IntPtr.Zero, 0, 0) > 0)
            {
                // No TranslateMessage/DispatchMessage: this thread owns no windows, and the
                // only message it cares about is the WM_QUIT that ends the loop.
            }

            if (_hook != IntPtr.Zero)
            {
                UnhookWindowsHookEx(_hook);
                _hook = IntPtr.Zero;
            }
        })
        {
            IsBackground = true,
            Name = "Freehand push-to-talk hook",
            // Stay ahead of the 1000 ms timeout that silently removes the hook.
            Priority = ThreadPriority.AboveNormal,
        };

        _thread.SetApartmentState(ApartmentState.STA);
        _thread.Start();
        ready.Wait(TimeSpan.FromSeconds(3));

        return installed;
    }

    /// <inheritdoc />
    public void StopListening()
    {
        Interlocked.Increment(ref _generation);
        lock (_sync) { _keys.Reset(); _recording?.Result.TrySetCanceled(); }
        if (_thread is null) return;

        if (_threadId != 0) PostThreadMessage(_threadId, WM_QUIT, IntPtr.Zero, IntPtr.Zero);
        _thread.Join(TimeSpan.FromSeconds(2));

        _thread = null;
        _threadId = 0;
        _callback = null;
    }

    /// <summary>Rooted for the lifetime of this hook. Keep the body short.</summary>
    private IntPtr Callback(int code, IntPtr wParam, IntPtr lParam)
    {
        if (code != HC_ACTION) return CallNextHookEx(IntPtr.Zero, code, wParam, lParam);

        try
        {
            Handle(wParam, lParam);
        }
        catch (Exception)
        {
            // An exception escaping into the hook chain would take the process down from a
            // thread with no useful context. Swallow and keep the chain intact.
        }

        // Always chain. Microsoft: otherwise "other applications that have installed
        // WH_KEYBOARD_LL hooks will not receive hook notifications and may behave
        // incorrectly as a result."
        return CallNextHookEx(IntPtr.Zero, code, wParam, lParam);
    }

    private void Handle(IntPtr wParam, IntPtr lParam)
    {
        var e = Marshal.PtrToStructure<KBDLLHOOKSTRUCT>(lParam);

        // Ignore anything this app injected itself.
        if (e.ExtraInfo == InjectedTag) return;

        // ToInt32 rather than a cast: since .NET 7 an explicit (int)IntPtr conversion
        // silently truncates instead of throwing, which CA2020 flags. Window messages are
        // always small, so the checked conversion is free and states the intent.
        var message = wParam.ToInt32();
        var isDown = message is WM_KEYDOWN or WM_SYSKEYDOWN;
        var isUp = message is WM_KEYUP or WM_SYSKEYUP;
        if (!isDown && !isUp) return;

        ProcessKey((int)e.VirtualKey, (int)e.ScanCode, e.Flags, isDown, e.ExtraInfo);
    }

    internal void ProcessKey(int virtualKey, int scanCode, uint flags, bool down, nint extraInfo = default)
    {
        if (extraInfo == InjectedTag) return;
        var raw = new KBDLLHOOKSTRUCT { VirtualKey = (uint)virtualKey, ScanCode = (uint)scanCode, Flags = flags };
        lock (_sync)
        {
            var update = _keys.Update(Normalize(raw), down);
            if (update != default) _events.Writer.TryWrite(new(Interlocked.Read(ref _generation), update, _recording));
        }
    }

    /// <summary>
    /// Collapses the side-agnostic <c>VK_SHIFT</c>/<c>VK_CONTROL</c>/<c>VK_MENU</c> codes into
    /// left/right-specific ones.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Physical keys normally arrive already specific, but input injected by another app via
    /// <c>keybd_event</c> or <c>SendInput</c> often uses the neutral form. AutoHotkey — the
    /// most battle-tested low-level keyboard hook in existence — translates defensively for
    /// exactly this reason, and so does this.
    /// </para>
    /// <para>
    /// Right Shift is the awkward one: Microsoft's keyboard-input documentation states it is
    /// <i>not</i> an extended key and is identified by scan code <c>0x36</c>, while
    /// AutoHotkey's source insists it must be treated as extended "or there will be problems".
    /// Both signals are accepted here.
    /// </para>
    /// </remarks>
    private static int Normalize(in KBDLLHOOKSTRUCT e)
    {
        var key = (int)e.VirtualKey;
        var scan = (int)(e.ScanCode & 0xFF);
        var extended = (e.Flags & LLKHF_EXTENDED) != 0;

        return key switch
        {
            VK_CONTROL => extended ? VK_RCONTROL : VK_LCONTROL,
            VK_MENU => extended ? VK_RMENU : VK_LMENU,
            VK_SHIFT => scan == ScanCodeRightShift || extended ? VK_RSHIFT : VK_LSHIFT,
            _ => key,
        };
    }

    /// <inheritdoc />
    public void Dispose()
    {
        StopListening();
        lock (_sync) _disposed = true;
        _events.Writer.TryComplete();
    }
}

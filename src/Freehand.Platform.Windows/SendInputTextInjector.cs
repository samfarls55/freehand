using System.Runtime.InteropServices;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

/// <summary>
/// Types text into whatever application has focus.
/// </summary>
/// <remarks>
/// <para>
/// <b>UI Automation is not an option here.</b> On macOS the Accessibility API can write text
/// directly; Windows has no counterpart. <c>TextPattern</c> is documented as providing no
/// means to insert or modify text, and <c>ValuePattern</c> replaces an entire field rather
/// than inserting at the caret — and multi-line controls do not support it at all. Microsoft's
/// own sample code says plainly: "text input must be simulated."
/// </para>
/// <para>
/// Text uses the target's keyboard layout where possible. Unicode-only characters
/// are sent one scalar at a time, rather than flooding text services with VK_PACKET.
/// The original foreground is checked throughout; the clipboard remains untouched.
/// </para>
/// </remarks>
public sealed class SendInputTextInjector : ITargetedTextInjector
{
    /// <summary>Layout-mapped characters per <c>SendInput</c> call.</summary>
    private const int ChunkSize = 32;

    /// <summary>Pause between chunks, so slower targets keep up.</summary>
    private static readonly TimeSpan ChunkGap = TimeSpan.FromMilliseconds(4);
    private static readonly TimeSpan UnicodeGap = TimeSpan.FromMilliseconds(1);
    private static readonly TimeSpan ModifierWait = TimeSpan.FromSeconds(1);
    private readonly Func<ForegroundTarget, bool> _isCurrent;
    private readonly Func<bool> _modifiersHeld;
    private readonly Func<INPUT[], uint> _send;
    private readonly Action<TimeSpan> _pause;
    private readonly Func<char, ForegroundTarget, INPUT?> _mapKey;

    /// <summary>Creates a foreground-checked Windows keyboard injector.</summary>
    public SendInputTextInjector() : this(WindowsForeground.IsCurrent, ModifiersHeld,
        inputs => SendInput((uint)inputs.Length, inputs, InputSize), Thread.Sleep, MapTextKey) { }

    internal SendInputTextInjector(Func<ForegroundTarget, bool> isCurrent, Func<bool> modifiersHeld,
        Func<INPUT[], uint> send, Action<TimeSpan> pause, Func<char, ForegroundTarget, INPUT?>? mapKey = null)
    {
        _isCurrent = isCurrent; _modifiersHeld = modifiersHeld; _send = send; _pause = pause;
        _mapKey = mapKey ?? ((_, _) => null);
    }

    private const uint INPUT_KEYBOARD = 1;
    private const uint KEYEVENTF_EXTENDEDKEY = 0x0001;
    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const uint KEYEVENTF_UNICODE = 0x0004;
    private const uint KEYEVENTF_SCANCODE = 0x0008;

    private const int VK_RETURN = 0x0D;
    // Unassigned by Windows. Unlike Ctrl or Escape, this has no normal shortcut action.
    private const int VK_MENU_MASK = 0xE8;

    private const uint MAPVK_VK_TO_VSC = 0;

    [StructLayout(LayoutKind.Sequential)]
    internal struct MOUSEINPUT
    {
        public int X, Y;
        public uint Data, Flags, Time;
        public IntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct KEYBDINPUT
    {
        public ushort VirtualKey;
        public ushort ScanCode;
        public uint Flags;
        public uint Time;
        public IntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct HARDWAREINPUT
    {
        public uint Message;
        public ushort ParamL, ParamH;
    }

    [StructLayout(LayoutKind.Explicit)]
    internal struct InputUnion
    {
        [FieldOffset(0)] public MOUSEINPUT Mouse;
        [FieldOffset(0)] public KEYBDINPUT Keyboard;
        [FieldOffset(0)] public HARDWAREINPUT Hardware;
    }

    [StructLayout(LayoutKind.Sequential)]
    internal struct INPUT
    {
        public uint Type;
        public InputUnion Union;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, INPUT[] inputs, int size);

    [DllImport("user32.dll", EntryPoint = "MapVirtualKeyW")]
    private static extern uint MapVirtualKey(uint code, uint mapType);

    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int virtualKey);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(nint window, out uint processId);

    [DllImport("user32.dll")]
    private static extern nint GetKeyboardLayout(uint threadId);

    [DllImport("user32.dll", EntryPoint = "VkKeyScanExW", CharSet = CharSet.Unicode)]
    private static extern short VkKeyScanEx(char character, nint layout);

    [DllImport("user32.dll", EntryPoint = "MapVirtualKeyExW")]
    private static extern uint MapVirtualKeyEx(uint code, uint mapType, nint layout);

    [DllImport("user32.dll")]
    private static extern short GetKeyState(int virtualKey);

    [DllImport("user32.dll", EntryPoint = "ToUnicodeEx", CharSet = CharSet.Unicode)]
    private static extern int ToUnicodeEx(uint virtualKey, uint scanCode, byte[] state,
        [Out] char[] characters, int capacity, uint flags, nint layout);

    internal static INPUT? MapTextKey(char character, ForegroundTarget target)
    {
        // Do not synthesize Shift/AltGr chords or disturb a dead-key composition.
        // Control characters and non-ASCII text take the paced Unicode route.
        if (character is < ' ' or > '~' || (GetKeyState(0x14) & 1) != 0) return null;
        var thread = GetWindowThreadProcessId(target.Window, out _);
        if (thread == 0) return null;
        var layout = GetKeyboardLayout(thread);
        var key = VkKeyScanEx(character, layout);
        if (key < 0 || (key & 0xFF00) != 0) return null;
        var virtualKey = (uint)(key & 0xFF);
        var scan = MapVirtualKeyEx(virtualKey, 4, layout); // MAPVK_VK_TO_VSC_EX
        if (scan == 0) return null;
        var state = new byte[256];
        state[virtualKey] = 0x80;
        var result = new char[2];
        // Flag4 checks the translation without mutating Windows' dead-key buffer.
        if (ToUnicodeEx(virtualKey, scan & 0xFF, state, result, result.Length, 4, layout) != 1 || result[0] != character)
            return null;
        return new INPUT
        {
            Type = INPUT_KEYBOARD,
            Union = new InputUnion
            {
                Keyboard = new KEYBDINPUT
                {
                    ScanCode = (ushort)(scan & 0xFF),
                    Flags = KEYEVENTF_SCANCODE | ((scan & 0xFF00) == 0xE000 ? KEYEVENTF_EXTENDEDKEY : 0),
                    ExtraInfo = PushToTalkHook.InjectedTag,
                },
            },
        };
    }

    private static bool ModifiersHeld() =>
        (GetAsyncKeyState(0x10) & 0x8000) != 0 || (GetAsyncKeyState(0x11) & 0x8000) != 0 ||
        (GetAsyncKeyState(0x12) & 0x8000) != 0 || (GetAsyncKeyState(0x5B) & 0x8000) != 0 ||
        (GetAsyncKeyState(0x5C) & 0x8000) != 0;

    private static readonly int InputSize = Marshal.SizeOf<INPUT>();

    /// <summary>Prevents held Windows/Alt keys from opening menus on release.</summary>
    internal static void MaskModifierMenu()
    {
        INPUT[] inputs = [KeyInput(VK_MENU_MASK, up: false), KeyInput(VK_MENU_MASK, up: true)];
        _ = SendInput((uint)inputs.Length, inputs, InputSize);
    }

    /// <inheritdoc />
    public async ValueTask<bool> InjectAsync(string text, CancellationToken cancellationToken) =>
        await InjectAsync(text, WindowsForeground.Capture(), cancellationToken).ConfigureAwait(false) == DeliveryOutcome.Delivered;

    /// <inheritdoc />
    public ValueTask<DeliveryOutcome> InjectAsync(string text, ForegroundTarget target, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!_isCurrent(target)) return ValueTask.FromResult(DeliveryOutcome.TargetChanged);
        // SendInput does not reset physical keyboard state. A failed hotkey pause
        // is not permission to type through a held Ctrl/Alt/Shift/Windows key.
        var deadline = System.Diagnostics.Stopwatch.StartNew();
        while (_modifiersHeld())
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!_isCurrent(target)) return ValueTask.FromResult(DeliveryOutcome.TargetChanged);
            if (deadline.Elapsed >= ModifierWait) return ValueTask.FromResult(DeliveryOutcome.PartialOrUncertain);
            _pause(ChunkGap);
        }
        return ValueTask.FromResult(TypeWithNewlines(text, target, cancellationToken)
            ? DeliveryOutcome.Delivered : DeliveryOutcome.PartialOrUncertain);
    }
    /// <summary>Types layout-mapped keys and individually paced Unicode scalars.</summary>
    /// <remarks>
    /// <para>
    /// The Unicode fallback sends UTF-16 code units. A non-BMP character — an
    /// emoji, some CJK extensions — is two surrogate halves, and each is sent as its own
    /// event; Unicode-aware controls recombine them. The 16-bit <c>ScanCode</c> field cannot
    /// carry a full 21-bit code point.
    /// </para>
    /// <para>
    /// <b>Failure here is silent.</b> <c>SendInput</c> is subject to UIPI, and Microsoft
    /// documents that when it is blocked "neither GetLastError nor the return value will
    /// indicate the failure was caused by UIPI blocking." Injecting into an elevated window
    /// from a normal process can return success and do nothing.
    /// </para>
    /// </remarks>
    private bool TypeText(string text, ForegroundTarget target, CancellationToken token)
    {
        for (var offset = 0; offset < text.Length;)
        {
            token.ThrowIfCancellationRequested();
            if (!_isCurrent(target) || _modifiersHeld()) return false;
            var inputs = new List<INPUT>(ChunkSize * 2);
            var length = 0;
            while (offset + length < text.Length && length < ChunkSize && _mapKey(text[offset + length], target) is { } mapped)
            {
                inputs.Add(mapped);
                mapped.Union.Keyboard.Flags |= KEYEVENTF_KEYUP;
                inputs.Add(mapped);
                length++;
            }
            var unicode = length == 0;
            if (unicode)
            {
                length = char.IsHighSurrogate(text[offset]) && offset + 1 < text.Length && char.IsLowSurrogate(text[offset + 1]) ? 2 : 1;
                for (var i = 0; i < length; i++)
                {
                    inputs.Add(UnicodeInput(text[offset + i], up: false));
                    inputs.Add(UnicodeInput(text[offset + i], up: true));
                }
            }
            if (!SendBalanced([.. inputs])) return false;
            offset += length;
            if (offset < text.Length) _pause(unicode ? UnicodeGap : ChunkGap);
        }

        return true;
    }

    /// <summary>Types text, sending a real Return for each newline.</summary>
    private bool TypeWithNewlines(string text, ForegroundTarget target, CancellationToken token)
    {
        var lines = text.Replace("\r\n", "\n", StringComparison.Ordinal).Replace('\r', '\n').Split('\n');

        for (var i = 0; i < lines.Length; i++)
        {
            token.ThrowIfCancellationRequested();
            if (!_isCurrent(target) || _modifiersHeld()) return false;
            if (lines[i].Length > 0 && !TypeText(lines[i], target, token)) return false;

            if (i < lines.Length - 1)
            {
                INPUT[] enter = [KeyInput(VK_RETURN, up: false), KeyInput(VK_RETURN, up: true)];
                if (!_isCurrent(target) || _modifiersHeld() || !SendBalanced(enter)) return false;
            }
        }

        return true;
    }

    private bool SendBalanced(INPUT[] inputs)
    {
        var sent = _send(inputs);
        if (sent == inputs.Length) return true;
        // A short write can end on key-down. Release only that injected key;
        // never resend the text prefix or leave Return/VK_PACKET pressed.
        if (sent < inputs.Length && (sent & 1) != 0) _ = _send([inputs[sent]]);
        return false;
    }

    private static INPUT UnicodeInput(ushort codeUnit, bool up) => new()
    {
        Type = INPUT_KEYBOARD,
        Union = new InputUnion
        {
            Keyboard = new KEYBDINPUT
            {
                VirtualKey = 0,   // must be 0 for KEYEVENTF_UNICODE
                ScanCode = codeUnit,
                Flags = KEYEVENTF_UNICODE | (up ? KEYEVENTF_KEYUP : 0),
                Time = 0,
                ExtraInfo = PushToTalkHook.InjectedTag,
            },
        },
    };

    private static INPUT KeyInput(int virtualKey, bool up)
    {
        var flags = up ? KEYEVENTF_KEYUP : 0;
        if (IsExtendedKey(virtualKey)) flags |= KEYEVENTF_EXTENDEDKEY;

        return new INPUT
        {
            Type = INPUT_KEYBOARD,
            Union = new InputUnion
            {
                Keyboard = new KEYBDINPUT
                {
                    VirtualKey = (ushort)virtualKey,
                    ScanCode = (ushort)MapVirtualKey((uint)virtualKey, MAPVK_VK_TO_VSC),
                    Flags = flags,
                    Time = 0,
                    // Tagged so our own hook ignores it and doesn't re-trigger dictation.
                    ExtraInfo = PushToTalkHook.InjectedTag,
                },
            },
        };
    }

    private static bool IsExtendedKey(int virtualKey) => virtualKey is
        0xA3 or 0xA5 or 0x5B or 0x5C or   // right ctrl/alt, both Windows keys
        0x2D or 0x2E or 0x24 or 0x23 or   // insert, delete, home, end
        0x21 or 0x22 or                   // page up/down
        0x25 or 0x26 or 0x27 or 0x28;     // arrows
}

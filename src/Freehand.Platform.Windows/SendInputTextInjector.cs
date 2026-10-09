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
/// Text is delivered as Unicode packets in paced blocks, checking the original foreground
/// target before each block. The clipboard stays available for explicit Copy.
/// </para>
/// </remarks>
public sealed class SendInputTextInjector : ITargetedTextInjector
{
    /// <summary>Characters per <c>SendInput</c> call when typing.</summary>
    private const int ChunkSize = 40;

    /// <summary>Pause between chunks, so slower targets keep up.</summary>
    private static readonly TimeSpan ChunkGap = TimeSpan.FromMilliseconds(4);

    private const uint INPUT_KEYBOARD = 1;
    private const uint KEYEVENTF_EXTENDEDKEY = 0x0001;
    private const uint KEYEVENTF_KEYUP = 0x0002;
    private const uint KEYEVENTF_UNICODE = 0x0004;

    private const int VK_RETURN = 0x0D;

    private const uint MAPVK_VK_TO_VSC = 0;

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT
    {
        public int X, Y;
        public uint Data, Flags, Time;
        public IntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT
    {
        public ushort VirtualKey;
        public ushort ScanCode;
        public uint Flags;
        public uint Time;
        public IntPtr ExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct HARDWAREINPUT
    {
        public uint Message;
        public ushort ParamL, ParamH;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion
    {
        [FieldOffset(0)] public MOUSEINPUT Mouse;
        [FieldOffset(0)] public KEYBDINPUT Keyboard;
        [FieldOffset(0)] public HARDWAREINPUT Hardware;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT
    {
        public uint Type;
        public InputUnion Union;
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern uint SendInput(uint count, INPUT[] inputs, int size);

    [DllImport("user32.dll", EntryPoint = "MapVirtualKeyW")]
    private static extern uint MapVirtualKey(uint code, uint mapType);

    private static readonly int InputSize = Marshal.SizeOf<INPUT>();

    /// <inheritdoc />
    public async ValueTask<bool> InjectAsync(string text, CancellationToken cancellationToken) =>
        await InjectAsync(text, WindowsForeground.Capture(), cancellationToken).ConfigureAwait(false) == DeliveryOutcome.Delivered;

    /// <inheritdoc />
    public ValueTask<DeliveryOutcome> InjectAsync(string text, ForegroundTarget target, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!WindowsForeground.IsCurrent(target)) return ValueTask.FromResult(DeliveryOutcome.TargetChanged);
        return ValueTask.FromResult(TypeWithNewlines(text, target, cancellationToken)
            ? DeliveryOutcome.Delivered : DeliveryOutcome.PartialOrUncertain);
    }
    /// <summary>Types arbitrary text as Unicode packets.</summary>
    /// <remarks>
    /// <para>
    /// Iterating by UTF-16 code unit is correct and intentional. A non-BMP character — an
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
    private static bool TypeUnicode(string text, ForegroundTarget target, CancellationToken token)
    {
        for (var offset = 0; offset < text.Length;)
        {
            token.ThrowIfCancellationRequested();
            if (!WindowsForeground.IsCurrent(target)) return false;
            var length = Math.Min(ChunkSize, text.Length - offset);

            // Never split a surrogate pair across two SendInput calls.
            if (offset + length < text.Length && char.IsHighSurrogate(text[offset + length - 1])) length++;

            var inputs = new INPUT[length * 2];
            for (var i = 0; i < length; i++)
            {
                var unit = text[offset + i];
                inputs[i * 2] = UnicodeInput(unit, up: false);
                inputs[(i * 2) + 1] = UnicodeInput(unit, up: true);
            }

            if (SendInput((uint)inputs.Length, inputs, InputSize) != inputs.Length) return false;
            offset += length;
            if (offset < text.Length) Thread.Sleep(ChunkGap);
        }

        return true;
    }

    /// <summary>Types text, sending a real Return for each newline.</summary>
    private static bool TypeWithNewlines(string text, ForegroundTarget target, CancellationToken token)
    {
        var lines = text.Replace("\r\n", "\n", StringComparison.Ordinal).Split('\n');

        for (var i = 0; i < lines.Length; i++)
        {
            token.ThrowIfCancellationRequested();
            if (!WindowsForeground.IsCurrent(target)) return false;
            if (lines[i].Length > 0 && !TypeUnicode(lines[i], target, token)) return false;

            if (i < lines.Length - 1)
            {
                INPUT[] enter = [KeyInput(VK_RETURN, up: false), KeyInput(VK_RETURN, up: true)];
                if (SendInput(2, enter, InputSize) != 2) return false;
            }
        }

        return true;
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

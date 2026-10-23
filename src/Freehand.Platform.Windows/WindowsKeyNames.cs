using System.Runtime.InteropServices;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

/// <summary>Resolves printable key names without altering keyboard or dead-key state.</summary>
public sealed class WindowsKeyNames : IKeyNameProvider
{
    /// <inheritdoc />
    public string? GetKeyName(int virtualKey) => GetKeyName(virtualKey, GetKeyboardLayout(0));

    internal static string? GetKeyName(int virtualKey, nint layout)
    {
        // MAPVK_VK_TO_CHAR returns the unshifted character. Its high bit marks dead keys;
        // unlike ToUnicodeEx, querying it cannot consume a pending dead-key composition.
        var character = MapVirtualKeyEx((uint)virtualKey, 2, layout) & 0x7FFFFFFF;
        return character is >= 0x20 and <= 0xFFFF ? char.ToUpperInvariant((char)character).ToString() : null;
    }

    [DllImport("user32.dll")] private static extern nint GetKeyboardLayout(uint threadId);
    [DllImport("user32.dll", EntryPoint = "MapVirtualKeyExW")]
    private static extern uint MapVirtualKeyEx(uint code, uint mapType, nint layout);
}

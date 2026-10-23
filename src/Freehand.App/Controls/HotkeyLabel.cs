using System.Globalization;

namespace Freehand.App.Controls;

internal static class HotkeyLabel
{
    internal static string Format(IReadOnlyList<int> keys) => string.Join(" + ", keys.OrderBy(Order).ThenBy(key => key).Select(KeyName));

    private static int Order(int key) => key switch
    {
        0x11 or 0xA2 or 0xA3 => 0,
        0x10 or 0xA0 or 0xA1 => 1,
        0x12 or 0xA4 or 0xA5 => 2,
        0x5B or 0x5C => 3,
        _ => 4,
    };

    internal static string KeyName(int key) => key switch
    {
        >= 0x30 and <= 0x39 or >= 0x41 and <= 0x5A => ((char)key).ToString(),
        >= 0x70 and <= 0x87 => "F" + (key - 0x6F).ToString(CultureInfo.InvariantCulture),
        >= 0x60 and <= 0x69 => "Num " + (key - 0x60).ToString(CultureInfo.InvariantCulture),
        0x03 => "Break", 0x08 => "Backspace", 0x09 => "Tab", 0x0C => "Clear", 0x0D => "Enter",
        0x10 => "Shift", 0x11 => "Ctrl", 0x12 => "Alt", 0x13 => "Pause", 0x14 => "Caps Lock",
        0x1B => "Escape", 0x20 => "Space", 0x21 => "Page Up", 0x22 => "Page Down",
        0x23 => "End", 0x24 => "Home", 0x25 => "Left", 0x26 => "Up", 0x27 => "Right", 0x28 => "Down",
        0x2C => "Print Screen", 0x2D => "Insert", 0x2E => "Delete", 0x5B => "Left Win", 0x5C => "Right Win", 0x5D => "Menu",
        0x6A => "Num *", 0x6B => "Num +", 0x6C => "Num separator", 0x6D => "Num -", 0x6E => "Num .", 0x6F => "Num /",
        0x90 => "Num Lock", 0x91 => "Scroll Lock", 0xA0 => "Left Shift", 0xA1 => "Right Shift",
        0xA2 => "Left Ctrl", 0xA3 => "Right Ctrl", 0xA4 => "Left Alt", 0xA5 => "Right Alt",
        0xA6 => "Browser back", 0xA7 => "Browser forward", 0xA8 => "Browser refresh", 0xA9 => "Browser stop",
        0xAA => "Browser search", 0xAB => "Browser favorites", 0xAC => "Browser home",
        0xAD => "Mute", 0xAE => "Volume down", 0xAF => "Volume up", 0xB0 => "Next track", 0xB1 => "Previous track",
        0xB2 => "Stop media", 0xB3 => "Play/pause", 0xB4 => "Mail", 0xB5 => "Media", 0xB6 => "App 1", 0xB7 => "App 2",
        0xBA => ";", 0xBB => "=", 0xBC => ",", 0xBD => "-", 0xBE => ".", 0xBF => "/", 0xC0 => "`",
        0xDB => "[", 0xDC => "\\", 0xDD => "]", 0xDE => "'", 0xE2 => "OEM 102",
        _ => string.Create(CultureInfo.InvariantCulture, $"Key 0x{key:X2}"),
    };
}

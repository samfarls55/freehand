using Freehand.Abstractions;
using Freehand.App.Controls;
using Shouldly;
using Xunit;

namespace Freehand.AppTests;

public sealed class HotkeyLabelTests
{
    [Fact]
    public void Oem_keys_use_the_layout_provider_in_settings_and_shortcut_labels()
    {
        var german = new GermanNames();
        HotkeyLabel.KeyName(0xBA, german).ShouldBe("Ö");
        HotkeyLabel.Format([0xBA, 0xA3], german).ShouldBe("Right Ctrl + Ö");
        HotkeyLabel.Format([0xDE, 0xA2], german).ShouldBe("Left Ctrl + Ä");
        HotkeyLabel.KeyName(0xE2, german).ShouldBe("<");
        HotkeyLabel.KeyName(0xDB, german).ShouldBe("Key 0xDB");
    }

    [Fact]
    public void Modifiers_have_a_stable_order_and_preserve_their_sides()
    {
        HotkeyLabel.Format([0x42, 0x5C, 0xA5, 0xA1, 0xA3, 0x41])
            .ShouldBe("Right Ctrl + Right Shift + Right Alt + Right Win + A + B");
        HotkeyLabel.Format([0x12, 0x10, 0x11]).ShouldBe("Ctrl + Shift + Alt");
        HotkeyLabel.Format([0x5B, 0xA4, 0xA0, 0xA2]).ShouldBe("Left Ctrl + Left Shift + Left Alt + Left Win");
    }

    [Theory]
    [InlineData(0x30, "0")]
    [InlineData(0x5A, "Z")]
    [InlineData(0x60, "Num 0")]
    [InlineData(0x69, "Num 9")]
    [InlineData(0x70, "F1")]
    [InlineData(0x87, "F24")]
    [InlineData(0x03, "Break")]
    [InlineData(0x08, "Backspace")]
    [InlineData(0x09, "Tab")]
    [InlineData(0x0D, "Enter")]
    [InlineData(0x1B, "Escape")]
    [InlineData(0x20, "Space")]
    [InlineData(0x25, "Left")]
    [InlineData(0x2E, "Delete")]
    [InlineData(0x6B, "Num +")]
    [InlineData(0x90, "Num Lock")]
    [InlineData(0xA6, "Browser back")]
    [InlineData(0xAD, "Mute")]
    [InlineData(0xB3, "Play/pause")]
    [InlineData(0xFE, "Key 0xFE")]
    public void Key_categories_keep_recognizable_names(int key, string expected) => HotkeyLabel.KeyName(key).ShouldBe(expected);

    private sealed class GermanNames : IKeyNameProvider
    {
        public string? GetKeyName(int virtualKey) => virtualKey switch { 0xBA => "Ö", 0xDE => "Ä", 0xE2 => "<", _ => null };
    }
}

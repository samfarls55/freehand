using System.Runtime.InteropServices;
using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

public sealed class KeyNameTests
{
    [Fact]
    public void Current_layout_names_printable_keys_but_not_modifiers()
    {
        var names = new WindowsKeyNames();
        Assert.Equal("A", names.GetKeyName(0x41));
        Assert.Null(names.GetKeyName(0xA3));
    }

    [Fact]
    public void German_layout_names_oem_keys_without_switching_the_active_layout()
    {
        var german = LoadKeyboardLayout("00000407", 0);
        Assert.NotEqual(0, german);
        try
        {
            Assert.Equal("Ü", WindowsKeyNames.GetKeyName(0xBA, german));
            Assert.Equal("Ö", WindowsKeyNames.GetKeyName(0xC0, german));
            Assert.Equal("Ä", WindowsKeyNames.GetKeyName(0xDE, german));
            Assert.Equal("ß", WindowsKeyNames.GetKeyName(0xDB, german));
            Assert.Equal("<", WindowsKeyNames.GetKeyName(0xE2, german));
            Assert.Null(WindowsKeyNames.GetKeyName(0xA3, german));
            Assert.Null(WindowsKeyNames.GetKeyName(0, german));
        }
        finally { UnloadKeyboardLayout(german); }
    }

    [DllImport("user32.dll", EntryPoint = "LoadKeyboardLayoutW", CharSet = CharSet.Unicode)]
    private static extern nint LoadKeyboardLayout(string identifier, uint flags);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool UnloadKeyboardLayout(nint layout);
}

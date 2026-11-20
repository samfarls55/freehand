using System.Runtime.InteropServices;
using System.Text;
using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

[Collection("Native text delivery")]
public sealed class ClipboardPasteTests
{
    [Fact]
    public void Ole_and_app_specific_clipboard_formats_take_the_paste_route_and_come_back()
    {
        // Avalonia, WinForms and Office copy through OLE, which adds its ownership formats.
        var custom = RegisterClipboardFormat("Freehand.Tests.AppSpecific");
        uint[] ole = [RegisterClipboardFormat("DataObject"), RegisterClipboardFormat("Ole Private Data")];
        byte[] payload = [1, 2, 3, 250];
        Assert.True(OpenClipboard(0));
        try
        {
            Assert.True(EmptyClipboard());
            Assert.NotEqual(0, SetClipboardData(13, Global(Encoding.Unicode.GetBytes("copied before\0"))));
            Assert.NotEqual(0, SetClipboardData(custom, Global(payload)));
            foreach (var format in ole) Assert.NotEqual(0, SetClipboardData(format, Global([0, 0, 0, 0])));
        }
        finally { CloseClipboard(); }

        using var field = new WindowsDeliveryProbe();
        var target = field.BeginTrial();
        using (var paste = new WindowsClipboardPaste(target))
        {
            // Null is the "can't preserve the clipboard" answer that sends the text through per-key typing.
            Assert.NotNull(paste.Deliver("Pasted, not typed.", CancellationToken.None));
        }

        Assert.True(OpenClipboard(0));
        try
        {
            Assert.Equal("copied before", Encoding.Unicode.GetString(Read(13)).Split('\0')[0]);
            Assert.Equal(payload, Read(custom)[..payload.Length]); // GlobalSize may round up
            foreach (var format in ole) Assert.False(IsClipboardFormatAvailable(format));
        }
        finally { CloseClipboard(); }
    }

    private static nint Global(byte[] bytes)
    {
        var memory = GlobalAlloc(0x42, (nuint)bytes.Length);
        Marshal.Copy(bytes, 0, GlobalLock(memory), bytes.Length);
        _ = GlobalUnlock(memory);
        return memory;
    }

    private static byte[] Read(uint format)
    {
        var memory = GetClipboardData(format);
        Assert.NotEqual(0, memory);
        var bytes = new byte[checked((int)GlobalSize(memory))];
        Marshal.Copy(GlobalLock(memory), bytes, 0, bytes.Length);
        _ = GlobalUnlock(memory);
        return bytes;
    }

    [DllImport("user32.dll", EntryPoint = "RegisterClipboardFormatW", CharSet = CharSet.Unicode)] private static extern uint RegisterClipboardFormat(string name);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool OpenClipboard(nint window);
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CloseClipboard();
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool EmptyClipboard();
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool IsClipboardFormatAvailable(uint format);
    [DllImport("user32.dll")] private static extern nint SetClipboardData(uint format, nint memory);
    [DllImport("user32.dll")] private static extern nint GetClipboardData(uint format);
    [DllImport("kernel32.dll")] private static extern nint GlobalAlloc(uint flags, nuint size);
    [DllImport("kernel32.dll")] private static extern nint GlobalLock(nint memory);
    [DllImport("kernel32.dll")] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GlobalUnlock(nint memory);
    [DllImport("kernel32.dll")] private static extern nuint GlobalSize(nint memory);
}

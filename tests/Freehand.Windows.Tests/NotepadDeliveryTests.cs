using System.Diagnostics;
using System.Runtime.InteropServices;
using Freehand.Abstractions;
using Freehand.Platform.Windows;
using Xunit;

namespace Freehand.Windows.Tests;

[Collection("Native text delivery")]
public sealed class NotepadDeliveryTests
{
    [Theory]
    [InlineData("Testing, testing, testing, this is an interesting thing and I really want to see if it works and I really hope that it's best.")]
    [InlineData("Trying one more time, I know sometimes the first dictation might not always be perfect.")]
    public async Task The_reported_transcript_arrives_unchanged_in_an_actual_Notepad_process(string text)
    {
        var path = Path.Combine(Path.GetTempPath(), "freehand-notepad-" + Guid.NewGuid().ToString("N") + ".txt");
        File.WriteAllText(path, string.Empty);
        var start = new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "notepad.exe"))
        { UseShellExecute = false };
        start.ArgumentList.Add(path);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Could not start Notepad");
        try
        {
            Assert.True(process.WaitForInputIdle(10000));
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            nint window = 0;
            while (window == 0 && !deadline.IsCancellationRequested && !process.HasExited)
            {
                process.Refresh(); window = process.MainWindowHandle;
                if (window == 0) await Task.Delay(20);
            }
            Assert.NotEqual(0, window);
            _ = GetWindowThreadProcessId(window, out var owner);
            Assert.Equal((uint)process.Id, owner);
            nint edit = 0;
            EnumChildWindows(window, (child, _) =>
            {
                var buffer = new char[256];
                var length = GetClassName(child, buffer, buffer.Length);
                var name = new string(buffer, 0, length);
                if (name.Equals("Edit", StringComparison.OrdinalIgnoreCase) ||
                    name.StartsWith("RichEdit", StringComparison.OrdinalIgnoreCase)) edit = child;
                return edit == 0;
            }, 0);
            Assert.NotEqual(0, edit);
            if (GetForegroundWindow() != window) Assert.True(SetForegroundWindow(window));
            Assert.Equal(window, GetForegroundWindow());
            var injector = new SendInputTextInjector();
            Assert.Equal(DeliveryOutcome.Delivered,
                await injector.InjectAsync(text, new ForegroundTarget(window, process.Id), deadline.Token));
            var received = ReadText(edit);
            while (received != text && !deadline.IsCancellationRequested)
            {
                await Task.Delay(20); received = ReadText(edit);
            }
            Assert.Equal(text, received);
        }
        finally
        {
            // Only terminate the exact process created above, never an existing editor.
            if (!process.HasExited) { process.Kill(entireProcessTree: true); process.WaitForExit(5000); }
            File.Delete(path);
        }
    }

    private static string ReadText(nint edit)
    {
        var buffer = new char[32768];
        if (SendMessageTimeout(edit, 0x000D, (nuint)buffer.Length, buffer, 2, 1000, out var count) == 0)
            throw new TimeoutException("Notepad did not respond to the test text readback");
        return new string(buffer, 0, checked((int)count));
    }

    private delegate bool ChildCallback(nint window, nint parameter);
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool EnumChildWindows(nint window, ChildCallback callback, nint parameter);
    [DllImport("user32.dll", EntryPoint = "GetClassNameW", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(nint window, [Out] char[] name, int count);
    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(nint window, out uint processId);
    [DllImport("user32.dll")]
    private static extern nint GetForegroundWindow();
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool SetForegroundWindow(nint window);
    [DllImport("user32.dll", EntryPoint = "SendMessageTimeoutW", CharSet = CharSet.Unicode)]
    private static extern nint SendMessageTimeout(nint window, uint message, nuint count,
        [Out] char[] text, uint flags, uint timeout, out nuint result);
}

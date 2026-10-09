using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

namespace Freehand.Installer;

internal static class Shortcut
{
    internal static void Create(string path, string executable)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var link = (IShellLink)(object)new ShellLink();
        try
        {
            link.SetPath(executable); link.SetWorkingDirectory(Path.GetDirectoryName(executable)!);
            link.SetDescription("Freehand local dictation"); link.SetIconLocation(executable, 0);
            var store = (IPropertyStore)link;
            var key = new PropertyKey { Format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), Id = 5 };
            var value = new PropertyValue { Type = 31, Pointer = Marshal.StringToCoTaskMemUni("Sam.Freehand.Windows") };
            try { store.SetValue(ref key, ref value); store.Commit(); } finally { Marshal.FreeCoTaskMem(value.Pointer); }
            ((IPersistFile)link).Save(path, true);
        }
        finally { Marshal.FinalReleaseComObject(link); }
    }
    [ComImport, Guid("00021401-0000-0000-C000-000000000046")] private sealed class ShellLink;
    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShellLink
    {
        void GetPath(nint file, int count, nint data, uint flags);
        void GetIDList(out nint item);
        void SetIDList(nint item);
        void GetDescription(nint text, int count);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string text);
        void GetWorkingDirectory(nint text, int count);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string path);
        void GetArguments(nint text, int count);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string arguments);
        void GetHotkey(out short key);
        void SetHotkey(short key);
        void GetShowCmd(out int command);
        void SetShowCmd(int command);
        void GetIconLocation(nint path, int count, out int index);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
        void Resolve(nint window, uint flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string path);
    }
    [StructLayout(LayoutKind.Sequential)] private struct PropertyKey { internal Guid Format; internal uint Id; }
    [StructLayout(LayoutKind.Explicit, Size = 24)] private struct PropertyValue { [FieldOffset(0)] internal ushort Type; [FieldOffset(8)] internal nint Pointer; }
    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropertyValue value);
        void SetValue(ref PropertyKey key, ref PropertyValue value);
        void Commit();
    }
}

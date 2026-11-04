using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;
using SherpaOnnx;

namespace Freehand.Speech;

// The pinned .NET wrapper omits CreateOfflineStreamWithHotwords. Use the public
// C ABI with its public config struct, without reflecting into wrapper handles.
internal sealed class ParakeetRecognizer : IDisposable
{
    private readonly RecognizerHandle _handle;

    internal ParakeetRecognizer(OfflineRecognizerConfig config)
    {
        _handle = CreateRecognizer(ref config);
        if (_handle.IsInvalid) { _handle.Dispose(); throw new InvalidOperationException("Recognizer creation failed"); }
    }

    internal string Transcribe(float[] samples, string hotwords)
    {
        var encoded = Marshal.StringToCoTaskMemUTF8(hotwords);
        IntPtr pointer;
        try { pointer = hotwords.Length == 0 ? CreateStream(_handle) : CreateStreamWithHotwords(_handle, encoded); }
        finally { Marshal.FreeCoTaskMem(encoded); }
        if (pointer == IntPtr.Zero) throw new InvalidOperationException("Recognition stream creation failed");
        using var stream = new OfflineStream(pointer);
        stream.AcceptWaveform(16000, samples);
        Decode(_handle, stream.Handle);
        return stream.Result.Text?.Trim() ?? string.Empty;
    }

    public void Dispose() => _handle.Dispose();

    private sealed class RecognizerHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        public RecognizerHandle() : base(true) { }
        protected override bool ReleaseHandle() { DestroyRecognizer(handle); return true; }
    }

    [DllImport("sherpa-onnx-c-api", EntryPoint = "SherpaOnnxCreateOfflineRecognizer")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.SafeDirectories)]
    private static extern RecognizerHandle CreateRecognizer(ref OfflineRecognizerConfig config);

    [DllImport("sherpa-onnx-c-api", EntryPoint = "SherpaOnnxDestroyOfflineRecognizer")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.SafeDirectories)]
    private static extern void DestroyRecognizer(IntPtr handle);

    [DllImport("sherpa-onnx-c-api", EntryPoint = "SherpaOnnxCreateOfflineStream")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.SafeDirectories)]
    private static extern IntPtr CreateStream(RecognizerHandle handle);

    [DllImport("sherpa-onnx-c-api", EntryPoint = "SherpaOnnxCreateOfflineStreamWithHotwords")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.SafeDirectories)]
    private static extern IntPtr CreateStreamWithHotwords(RecognizerHandle handle, IntPtr hotwords);

    [DllImport("sherpa-onnx-c-api", EntryPoint = "SherpaOnnxDecodeOfflineStream")]
    [DefaultDllImportSearchPaths(DllImportSearchPath.SafeDirectories)]
    private static extern void Decode(RecognizerHandle handle, IntPtr stream);
}

using System.Runtime.InteropServices;
using System.Text;
using Freehand.Abstractions;
using Microsoft.Win32.SafeHandles;

[assembly: DefaultDllImportSearchPaths(DllImportSearchPath.SafeDirectories)]

namespace Freehand.Speech;

// The pinned transcribe.cpp v0.4.1 ABI. One worker owns one sequential session.
internal sealed class GgmlTranscriber(string modelDirectory) : ITranscriber
{
    private SessionHandle? _session;
    private ParakeetHotwords? _hotwords;
    private SpeechPresenceDetector? _speechPresence;
    public bool IsReady => _session is { IsInvalid: false, IsClosed: false };

    public ValueTask<bool> LoadAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (IsReady) return ValueTask.FromResult(true);
        var modelPath = Path.Combine(modelDirectory, ModelResolver.RequiredFiles[0]);
        if (!File.Exists(modelPath)) return ValueTask.FromResult(false);
        Native.BackendParamsInit(out var backends);
        backends.AllowedBackends = 5; // CPU and Vulkan only.
        Check(Native.InitBackends(ref backends));
        Native.LoadParamsInit(out var load);
        // AUTO probes discrete devices first within the allowed Vulkan/CPU
        // backends. Querying every adapter's live free-memory counter first
        // unnecessarily initializes the integrated GPU on this laptop.
        load.Backend = 0;
        Native.SessionParamsInit(out var session);
        session.Threads = 4;
        session.Context = ModelResolver.DecoderContext;
        var encodedPath = Marshal.StringToCoTaskMemUTF8(modelPath);
        IntPtr pointer;
        try { Check(Native.Open(encodedPath, ref load, ref session, out pointer)); }
        finally { Marshal.FreeCoTaskMem(encodedPath); }
        _session = new SessionHandle(pointer);
        Native.DeviceInfoInit(out var info);
        Check(Native.DeviceGetInfo(Native.ModelDevice(Native.GetModel(_session)), ref info));
        if (info.DeviceType != 1 || Marshal.PtrToStringUTF8(info.Kind) != "vulkan")
        {
            _session.Dispose(); _session = null;
            throw new InvalidOperationException("A discrete Vulkan GPU is required for this development candidate.");
        }
        // Keep the existing hint character boundary. Native token IDs come from
        // the selected GGUF's tokenizer, never from this validator.
        _hotwords = new ParakeetHotwords(Path.Combine(AppContext.BaseDirectory, ParakeetHotwords.VocabularyFile));
        if (ModelResolver.VoiceActivityModel is { } detectorModel)
            _speechPresence = new SpeechPresenceDetector(Path.Combine(modelDirectory, detectorModel));
        // Prepare encoder/decoder graphs while loading can overlap recording.
        // Run directly: the speech-presence guard correctly rejects this input.
        // The result stays inside initialization; every user request resets state.
        _ = RunNative(_session, new float[ModelResolver.PreferredMaxSegmentSeconds * AudioChunk.SampleRate], [], cancellationToken);
        return ValueTask.FromResult(true);
    }

    public bool SupportsBiasPhrase(string phrase) => _hotwords?.Supports(phrase) == true;

    public ValueTask<string> TranscribeAsync(ReadOnlyMemory<float> samples,
        IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken)
    {
        if (_session is null || samples.IsEmpty) return ValueTask.FromResult(string.Empty);
        cancellationToken.ThrowIfCancellationRequested();
        if (_speechPresence?.ContainsSpeech(samples) == false) return ValueTask.FromResult(string.Empty);
        return ValueTask.FromResult(RunNative(_session, samples, biasPhrases, cancellationToken));
    }

    private static unsafe string RunNative(SessionHandle session, ReadOnlyMemory<float> samples,
        IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken)
    {
        Native.RunParamsInit(out var run);
        run.Timestamps = 0;
        var phrases = new IntPtr[biasPhrases.Count];
        try
        {
            for (var i = 0; i < phrases.Length; i++)
            {
                var phrase = string.Join(' ', biasPhrases[i].Normalize(NormalizationForm.FormC)
                    .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));
                phrases[i] = Marshal.StringToCoTaskMemUTF8(phrase);
            }
            using var pcm = samples.Pin();
            fixed (IntPtr* vocabulary = phrases)
            fixed (byte* language = "en\0"u8)
            {
                run.Vocabulary = (IntPtr)vocabulary;
                run.VocabularyCount = phrases.Length;
                run.Language = (IntPtr)language;
                Check(Native.Run(session, pcm.Pointer, samples.Length, ref run));
            }
            cancellationToken.ThrowIfCancellationRequested();
            return Marshal.PtrToStringUTF8(Native.FullText(session))?.Trim() ?? string.Empty;
        }
        finally { foreach (var phrase in phrases) Marshal.FreeCoTaskMem(phrase); }
    }

    public ValueTask DisposeAsync()
    {
        _speechPresence?.Dispose();
        _speechPresence = null;
        _session?.Dispose();
        _session = null;
        _hotwords = null;
        return ValueTask.CompletedTask;
    }

    private static void Check(int status)
    {
        if (status != 0) throw new InvalidOperationException("Native recognition failed: " + Marshal.PtrToStringUTF8(Native.StatusString(status)));
    }

    private sealed class SessionHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        internal SessionHandle(IntPtr pointer) : base(true) => SetHandle(pointer);
        protected override bool ReleaseHandle() { Native.SessionFree(handle); return true; }
    }

    private static class Native
    {
        private const string Library = "transcribe";
        [StructLayout(LayoutKind.Sequential)] internal struct BackendParams { internal ulong Size; internal IntPtr ArtifactDirectory; internal uint AllowedBackends; }
        [StructLayout(LayoutKind.Sequential)] internal struct LoadParams { internal ulong Size; internal int Backend; internal IntPtr Device; internal byte NoMmap; }
        [StructLayout(LayoutKind.Sequential)] internal struct SessionParams { internal ulong Size; internal int Threads, KvType, Context; }
        [StructLayout(LayoutKind.Sequential)] internal struct DeviceInfo { internal ulong Size; internal IntPtr Name, Description, Kind, Id; internal ulong Total, Free; internal int DeviceType; }
        [StructLayout(LayoutKind.Sequential)] internal struct RunParams
        {
            internal ulong Size;
            internal int Task, Timestamps, Pnc, Itn, Diarize;
            internal IntPtr Language, TargetLanguage;
            internal byte KeepSpecialTags;
            internal IntPtr Family;
            internal int Drafts;
            internal IntPtr Vocabulary;
            internal int VocabularyCount;
            internal IntPtr Prompt, Prefix;
        }
        [DllImport(Library, EntryPoint = "transcribe_backend_init_params_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void BackendParamsInit(out BackendParams p);
        [DllImport(Library, EntryPoint = "transcribe_init_backends_ex", CallingConvention = CallingConvention.Cdecl)] internal static extern int InitBackends(ref BackendParams p);
        [DllImport(Library, EntryPoint = "transcribe_model_load_params_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void LoadParamsInit(out LoadParams p);
        [DllImport(Library, EntryPoint = "transcribe_session_params_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void SessionParamsInit(out SessionParams p);
        [DllImport(Library, EntryPoint = "transcribe_run_params_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void RunParamsInit(out RunParams p);
        [DllImport(Library, EntryPoint = "transcribe_device_info_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void DeviceInfoInit(out DeviceInfo p);
        [DllImport(Library, EntryPoint = "transcribe_device_get_info", CallingConvention = CallingConvention.Cdecl)] internal static extern int DeviceGetInfo(IntPtr device, ref DeviceInfo info);
        [DllImport(Library, EntryPoint = "transcribe_get_model", CallingConvention = CallingConvention.Cdecl)] internal static extern IntPtr GetModel(SessionHandle session);
        [DllImport(Library, EntryPoint = "transcribe_model_device", CallingConvention = CallingConvention.Cdecl)] internal static extern IntPtr ModelDevice(IntPtr model);
        [DllImport(Library, EntryPoint = "transcribe_open", CallingConvention = CallingConvention.Cdecl)] internal static extern int Open(IntPtr path, ref LoadParams load, ref SessionParams session, out IntPtr result);
        [DllImport(Library, EntryPoint = "transcribe_run", CallingConvention = CallingConvention.Cdecl)] internal static extern unsafe int Run(SessionHandle session, void* samples, int count, ref RunParams p);
        [DllImport(Library, EntryPoint = "transcribe_full_text", CallingConvention = CallingConvention.Cdecl)] internal static extern IntPtr FullText(SessionHandle session);
        [DllImport(Library, EntryPoint = "transcribe_session_free", CallingConvention = CallingConvention.Cdecl)] internal static extern void SessionFree(IntPtr session);
        [DllImport(Library, EntryPoint = "transcribe_status_string", CallingConvention = CallingConvention.Cdecl)] internal static extern IntPtr StatusString(int status);
    }
}

using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace Freehand.Speech;

// The sequential worker initializes the native backends before this CPU-only
// session. Valid owned PCM arrives through WorkerProtocol; normalization uses
// only a bounded copy, leaving the complete ASR input unchanged.
internal sealed class SpeechPresenceDetector : IDisposable
{
    private readonly ModelHandle _model;
    private readonly SessionHandle _session;
    private readonly float[] _normalized = new float[WorkerProtocol.MaxSamples];

    internal SpeechPresenceDetector(string modelPath)
    {
        Native.LoadParamsInit(out var load);
        load.Backend = 1; // Explicit CPU, independent of the ASR model device.
        var encoded = Marshal.StringToCoTaskMemUTF8(modelPath);
        IntPtr pointer;
        try { Check(Native.ModelLoad(encoded, ref load, out pointer)); }
        finally { Marshal.FreeCoTaskMem(encoded); }
        ModelHandle? model = new(pointer);
        SessionHandle? session = null;
        try
        {
            Native.InfoInit(out var info);
            Check(Native.GetInfo(model, ref info));
            if (info.SampleRate != 16000 || info.FrameSamples != 512)
                throw new InvalidDataException("The pinned speech detector requires 16 kHz, 512-sample frames.");
            Native.SessionParamsInit(out var options);
            options.Threads = 1;
            Check(Native.SessionInit(model, ref options, out pointer));
            session = new SessionHandle(pointer, model);
            _model = model;
            _session = session;
            model = null;
            session = null;
        }
        finally { session?.Dispose(); model?.Dispose(); }
    }

    internal unsafe bool ContainsSpeech(ReadOnlyMemory<float> samples)
    {
        var source = samples.Span;
        double energy = 0, peak = 0;
        foreach (var value in source)
        {
            energy += (double)value * value;
            peak = Math.Max(peak, Math.Abs((double)value));
        }
        if (peak == 0) return false;
        var rms = Math.Sqrt(energy / source.Length);
        var gain = Math.Min(0.05 / rms, 1 / peak);
        var normalized = _normalized.AsSpan(0, source.Length);
        for (var index = 0; index < source.Length; index++) normalized[index] = (float)(source[index] * gain);
        Native.ParamsInit(out var options);
        options.MinimumSpeechMilliseconds = 0; // Retain short yes/no utterances.
        // A whole-clip run resets recurrent state before every request.
        fixed (float* input = normalized) Check(Native.Run(_session, input, normalized.Length, ref options));
        Native.ResultInit(out var result);
        Check(Native.GetResult(_session, ref result));
        return result.SegmentCount > 0;
    }

    public void Dispose()
    {
        _session.Dispose();
        _model.Dispose();
    }

    private static void Check(int status)
    {
        if (status != 0) throw new InvalidOperationException("Native speech detection failed: " + Marshal.PtrToStringUTF8(Native.StatusString(status)));
    }

    private sealed class ModelHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        internal ModelHandle(IntPtr pointer) : base(true) => SetHandle(pointer);
        protected override bool ReleaseHandle() { Native.ModelFree(handle); return true; }
    }

    private sealed class SessionHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        private readonly ModelHandle _model;
        private readonly bool _modelReferenceHeld;
        internal SessionHandle(IntPtr pointer, ModelHandle model) : base(true)
        {
            _model = model;
            var held = false;
            model.DangerousAddRef(ref held);
            _modelReferenceHeld = held;
            SetHandle(pointer);
        }
        protected override bool ReleaseHandle()
        {
            Native.SessionFree(handle);
            if (_modelReferenceHeld) _model.DangerousRelease();
            return true;
        }
    }

    private static class Native
    {
        private const string Library = "transcribe";
        [StructLayout(LayoutKind.Sequential)] internal struct LoadParams { internal ulong Size; internal int Backend; internal IntPtr Device; internal byte NoMmap; }
        [StructLayout(LayoutKind.Sequential)] internal struct Info { internal ulong Size; internal int SampleRate, FrameSamples; }
        [StructLayout(LayoutKind.Sequential)] internal struct SessionParams { internal ulong Size; internal int Threads; }
        [StructLayout(LayoutKind.Sequential)] internal struct Params { internal ulong Size; internal double Threshold, NegativeThreshold; internal int MinimumSpeechMilliseconds, MinimumSilenceMilliseconds, PaddingMilliseconds, MaximumSpeechMilliseconds; }
        [StructLayout(LayoutKind.Sequential)] internal struct Result { internal ulong Size; internal int ProbabilityCount; internal long FirstFrame; internal int SegmentCount; }
        [DllImport(Library, EntryPoint = "transcribe_model_load_params_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void LoadParamsInit(out LoadParams value);
        [DllImport(Library, EntryPoint = "transcribe_model_load_file", CallingConvention = CallingConvention.Cdecl)] internal static extern int ModelLoad(IntPtr path, ref LoadParams options, out IntPtr model);
        [DllImport(Library, EntryPoint = "transcribe_model_free", CallingConvention = CallingConvention.Cdecl)] internal static extern void ModelFree(IntPtr model);
        [DllImport(Library, EntryPoint = "transcribe_vad_info_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void InfoInit(out Info value);
        [DllImport(Library, EntryPoint = "transcribe_vad_get_info", CallingConvention = CallingConvention.Cdecl)] internal static extern int GetInfo(ModelHandle model, ref Info value);
        [DllImport(Library, EntryPoint = "transcribe_vad_session_params_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void SessionParamsInit(out SessionParams value);
        [DllImport(Library, EntryPoint = "transcribe_vad_session_init", CallingConvention = CallingConvention.Cdecl)] internal static extern int SessionInit(ModelHandle model, ref SessionParams options, out IntPtr session);
        [DllImport(Library, EntryPoint = "transcribe_vad_session_free", CallingConvention = CallingConvention.Cdecl)] internal static extern void SessionFree(IntPtr session);
        [DllImport(Library, EntryPoint = "transcribe_vad_params_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void ParamsInit(out Params value);
        [DllImport(Library, EntryPoint = "transcribe_vad_run", CallingConvention = CallingConvention.Cdecl)] internal static extern unsafe int Run(SessionHandle session, float* samples, int count, ref Params options);
        [DllImport(Library, EntryPoint = "transcribe_vad_result_init", CallingConvention = CallingConvention.Cdecl)] internal static extern void ResultInit(out Result value);
        [DllImport(Library, EntryPoint = "transcribe_vad_get_result", CallingConvention = CallingConvention.Cdecl)] internal static extern int GetResult(SessionHandle session, ref Result value);
        [DllImport(Library, EntryPoint = "transcribe_status_string", CallingConvention = CallingConvention.Cdecl)] internal static extern IntPtr StatusString(int status);
    }
}

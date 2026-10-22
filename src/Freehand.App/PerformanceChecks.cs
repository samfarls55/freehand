using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Speech;

namespace Freehand.App;

/// <summary>Replays public fixture audio at microphone speed without capturing or typing.</summary>
internal static class PerformanceChecks
{
    internal static async Task<int> RunAsync(string output)
    {
        var report = new PerformanceReport();
        try
        {
            var fixture = EngineeringChecks.ReadFixture();
            using var models = new ModelResolver();
            var speech = new SpeechWorkerClient(PlatformFactory.CreateWorkerLauncher()
                ?? throw new InvalidOperationException("Worker launcher unavailable"), models);
            await using (speech.ConfigureAwait(false))
            {
                await speech.BeginWorkAsync(CancellationToken.None).ConfigureAwait(false);
                if (!await speech.LoadAsync(CancellationToken.None).ConfigureAwait(false)) throw new IOException("Model unavailable");
                report.ColdLoadMilliseconds = speech.LastLoadTime.TotalMilliseconds;
                var observed = new ObservedTranscriber(speech);
                var key = new ScriptedKey();
                var capture = new ReplayCapture(fixture);
                var injector = new CountingInjector();
                await using (var engine = new DictationEngine(capture, key, observed, injector, () => []))
                {
                    foreach (var seconds in new[] { 10, 30, 60, 10 })
                    {
                        var trial = new PerformanceTrial { AudioSeconds = seconds };
                        capture.Prepare(seconds);
                        var completedBefore = injector.Deliveries;
                        var samplesBefore = observed.CompletedSamples;
                        using var monitorStop = new CancellationTokenSource();
                        var monitor = SampleMemoryAsync(speech, trial, monitorStop.Token);
                        try
                        {
                            key.Press();
                            await capture.Ready.Task.WaitAsync(TimeSpan.FromSeconds(seconds + 15)).ConfigureAwait(false);
                            trial.DecodedSecondsBeforeRelease = (double)(observed.CompletedSamples - samplesBefore) / AudioChunk.SampleRate;
                            if (injector.Deliveries != completedBefore) throw new IOException("Text delivered before release");
                            key.Release();
                            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(60));
                            while (engine.State != DictationState.Idle) await Task.Delay(5, deadline.Token).ConfigureAwait(false);
                            var result = engine.LastResult ?? throw new IOException("Missing transcript");
                            if (result.AudioDuration.TotalSeconds != seconds || !result.Text.Contains("fellow americans", StringComparison.OrdinalIgnoreCase)
                                || !result.Text.Contains("country", StringComparison.OrdinalIgnoreCase) || injector.Deliveries != completedBefore + 1)
                                throw new IOException("Fixture correctness or delivery count failed");
                            trial.ReleaseToTranscriptMilliseconds = result.TranscriptTime.TotalMilliseconds;
                            trial.ReleaseToInjectorCompleteMilliseconds = result.ProcessingTime.TotalMilliseconds;
                            using var worker = Process.GetProcessById(speech.WorkerId!.Value);
                            trial.RetainedWorkerPrivateBytes = worker.PrivateMemorySize64;
                            trial.RetainedWorkerWorkingSetBytes = worker.WorkingSet64;
                            report.Trials.Add(trial);
                        }
                        finally
                        {
                            await monitorStop.CancelAsync().ConfigureAwait(false);
                            await monitor.ConfigureAwait(false);
                        }
                    }
                }
            }
        }
        catch (Exception e) { report.Failures.Add(e.GetType().Name + ": " + e.Message); }
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(report, PerformanceJsonContext.Default.PerformanceReport)).ConfigureAwait(false);
        return report.Failures.Count == 0 ? 0 : 1;
    }

    private static async Task SampleMemoryAsync(SpeechWorkerClient speech, PerformanceTrial trial, CancellationToken token)
    {
        try
        {
            while (true)
            {
                token.ThrowIfCancellationRequested();
                if (speech.WorkerId is { } id)
                {
                    using var worker = Process.GetProcessById(id);
                    trial.PeakWorkerPrivateBytes = Math.Max(trial.PeakWorkerPrivateBytes, worker.PrivateMemorySize64);
                    trial.PeakWorkerWorkingSetBytes = Math.Max(trial.PeakWorkerWorkingSetBytes, worker.WorkingSet64);
                }
                using var host = Process.GetCurrentProcess();
                trial.PeakHostPrivateBytes = Math.Max(trial.PeakHostPrivateBytes, host.PrivateMemorySize64);
                await Task.Delay(10, token).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { }
    }

    private sealed class ObservedTranscriber(ITranscriber inner) : ITranscriber
    {
        private long _completedSamples;
        internal long CompletedSamples => Interlocked.Read(ref _completedSamples);
        public bool IsReady => inner.IsReady;
        public ValueTask<bool> LoadAsync(CancellationToken cancellationToken) => inner.LoadAsync(cancellationToken);
        public async ValueTask<string> TranscribeAsync(ReadOnlyMemory<float> samples, IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken)
        {
            var text = await inner.TranscribeAsync(samples, biasPhrases, cancellationToken).ConfigureAwait(false);
            Interlocked.Add(ref _completedSamples, samples.Length);
            return text;
        }
        // The benchmark owns the real session through the enclosing await using.
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private sealed class ScriptedKey : IHotkeySource
    {
        public event EventHandler? Pressed;
        public event EventHandler? Released;
        public bool Start() => true;
        public void StopListening() { }
        public void Dispose() { }
        internal void Press() => Pressed?.Invoke(this, EventArgs.Empty);
        internal void Release() => Released?.Invoke(this, EventArgs.Empty);
    }

    private sealed class CountingInjector : ITextInjector
    {
        private int _deliveries;
        internal int Deliveries => Volatile.Read(ref _deliveries);
        public ValueTask<bool> InjectAsync(string text, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Interlocked.Increment(ref _deliveries);
            return ValueTask.FromResult(true);
        }
    }

    private sealed class ReplayCapture(float[] fixture) : IAudioCapture
    {
        private int _seconds;
        internal TaskCompletionSource Ready { get; private set; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal void Prepare(int seconds) { _seconds = seconds; Ready = new(TaskCreationOptions.RunContinuationsAsynchronously); }
        public bool IsCapturing { get; private set; }
        public async IAsyncEnumerable<AudioChunk> CaptureAsync([EnumeratorCancellation] CancellationToken cancellationToken)
        {
            IsCapturing = true;
            var clock = Stopwatch.StartNew();
            try
            {
                const int chunkSize = AudioChunk.SampleRate / 10;
                for (var offset = 0; offset < _seconds * AudioChunk.SampleRate; offset += chunkSize)
                {
                    var delay = TimeSpan.FromSeconds((double)(offset + chunkSize) / AudioChunk.SampleRate) - clock.Elapsed;
                    if (delay > TimeSpan.Zero) await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
                    var chunk = new float[chunkSize];
                    for (var i = 0; i < chunk.Length; i++) chunk[i] = fixture[(offset + i) % fixture.Length];
                    yield return new AudioChunk(chunk);
                }
                Ready.TrySetResult();
                await Task.Delay(Timeout.Infinite, cancellationToken).ConfigureAwait(false);
            }
            finally { IsCapturing = false; }
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}

internal sealed class PerformanceReport
{
    public string ModelVersion { get; } = ModelResolver.Version;
    public string Runtime { get; } = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription;
    public int LogicalProcessors { get; } = Environment.ProcessorCount;
    public double ColdLoadMilliseconds { get; set; }
    public List<PerformanceTrial> Trials { get; } = [];
    public List<string> Failures { get; } = [];
}

internal sealed class PerformanceTrial
{
    public int AudioSeconds { get; init; }
    public double DecodedSecondsBeforeRelease { get; set; }
    public double ReleaseToTranscriptMilliseconds { get; set; }
    public double ReleaseToInjectorCompleteMilliseconds { get; set; }
    public long PeakWorkerPrivateBytes { get; set; }
    public long PeakWorkerWorkingSetBytes { get; set; }
    public long PeakHostPrivateBytes { get; set; }
    public long RetainedWorkerPrivateBytes { get; set; }
    public long RetainedWorkerWorkingSetBytes { get; set; }
}

[JsonSourceGenerationOptions(WriteIndented = true)]
[JsonSerializable(typeof(PerformanceReport))]
internal sealed partial class PerformanceJsonContext : JsonSerializerContext;

using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Speech;

namespace Freehand.App;

internal static class EngineeringChecks
{
    internal static async Task<int> MeasureDesktopAsync(Composition composition, string output)
    {
        var report = new DesktopBenchmarkReport();
        try
        {
            var speech = composition.Speech ?? throw new IOException("Speech session unavailable");
            if (composition.Settings.Data.IdleModelMinutes != 5) throw new IOException("The isolated profile did not receive the five-minute default");
            await composition.Models.VerifyAsync(CancellationToken.None).ConfigureAwait(false);
            await Task.Delay(2000).ConfigureAwait(false);
            if (speech.WorkerId is not null) throw new IOException("Startup loaded a worker");
            var before = Memory(speech);
            report.BeforePrivateBytes = before.Private; report.BeforeWorkingSet = before.Working;
            using var process = Process.GetCurrentProcess();
            var cpuBefore = process.TotalProcessorTime; var sampleAt = Stopwatch.GetTimestamp();
            await Task.Delay(TimeSpan.FromMinutes(1)).ConfigureAwait(false);
            process.Refresh();
            report.IdleCpuPercent = 100 * (process.TotalProcessorTime - cpuBefore).TotalSeconds
                / Stopwatch.GetElapsedTime(sampleAt).TotalSeconds / Environment.ProcessorCount;
            await speech.BeginWorkAsync(CancellationToken.None).ConfigureAwait(false);
            if (!await speech.LoadAsync(CancellationToken.None).ConfigureAwait(false)) throw new IOException("Model failed to load");
            CheckFixtureText(await speech.TranscribeAsync(ReadFixture(), [], CancellationToken.None).ConfigureAwait(false));
            var loaded = Memory(speech); report.LoadedPrivateBytes = loaded.Private; report.LoadedWorkingSet = loaded.Working;
            // Exercise the actual five-minute default, without shortened test policy.
            speech.SetIdleTimeout(TimeSpan.FromMinutes(5));
            var idleAt = Stopwatch.GetTimestamp(); speech.FinishWork();
            await WaitAsync(() => speech.WorkerId is null, TimeSpan.FromMinutes(5) + TimeSpan.FromSeconds(7)).ConfigureAwait(false);
            report.IdleExitMilliseconds = Stopwatch.GetElapsedTime(idleAt).TotalMilliseconds;
            if (report.IdleExitMilliseconds < 299950 || report.IdleExitMilliseconds > 305000)
                throw new IOException("Worker exit did not follow the five-minute idle policy");
            var after = Memory(speech); report.AfterPrivateBytes = after.Private; report.AfterWorkingSet = after.Working;
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            after = Memory(speech); report.AfterCollectionPrivateBytes = after.Private; report.AfterCollectionWorkingSet = after.Working;
            report.WorkersAfterUnload = speech.WorkerId is null ? 0 : 1;
        }
        catch (Exception e) { report.Failures.Add(e.GetType().Name + ": " + e.Message); }
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(report, BenchmarkJsonContext.Default.DesktopBenchmarkReport)).ConfigureAwait(false);
        return report.Failures.Count == 0 ? 0 : 1;
    }
    internal static async Task<int> CheckDesktopAsync()
    {
        try
        {
            using var owner = PlatformFactory.CreateDesktopIntegration() ?? throw new InvalidOperationException("Desktop unavailable");
            if (!owner.ClaimInstance()) throw new InvalidOperationException("Close Freehand before this check");
            using (var second = PlatformFactory.CreateDesktopIntegration()!)
                if (second.ClaimInstance()) throw new IOException("Two instances claimed ownership");
            var activated = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            owner.ActivationRequested += (_, _) => activated.TrySetResult();
            owner.StartNotifications();
            await activated.Task.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
            using var hook = PlatformFactory.CreateHotkeySource(0xA3) ?? throw new IOException("Hook unavailable");
            for (var cycle = 0; cycle < 10; cycle++)
            {
                if (!hook.Start()) throw new IOException("Hook failed to rearm");
                hook.StopListening();
            }
            Console.WriteLine("  [ok] single instance, activation retained during startup, ten hook rearm cycles");
            return 0;
        }
        catch (Exception e) { Console.Error.WriteLine("Desktop check failed: " + e); return 1; }
    }
    internal static async Task<int> CheckSpeechAsync()
    {
        try
        {
            var audio = ReadFixture();
            using var models = new ModelResolver();
            await using var speech = new SpeechWorkerClient(PlatformFactory.CreateWorkerLauncher() ?? throw new InvalidOperationException("Worker launcher unavailable"), models);
            for (var run = 0; run < 2; run++)
            {
                await speech.BeginWorkAsync(CancellationToken.None).ConfigureAwait(false);
                if (!await speech.LoadAsync(CancellationToken.None).ConfigureAwait(false)) throw new IOException("Bundled model invalid");
                if (ModelResolver.UsesAcceleratedModel && run == 0)
                {
                    // Prepare the GPU's shader variants with public voiced audio;
                    // a speech detector correctly skips all-zero warmups.
                    var preparation = Stopwatch.GetTimestamp();
                    foreach (var seconds in new[] { 15, 8, 4, 1 })
                    {
                        var preparationAudio = new float[seconds * AudioChunk.SampleRate];
                        for (var sample = 0; sample < preparationAudio.Length; sample++) preparationAudio[sample] = audio[sample % audio.Length];
                        if (string.IsNullOrWhiteSpace(await speech.TranscribeAsync(preparationAudio, [], CancellationToken.None).ConfigureAwait(false)))
                            throw new InvalidDataException("GPU preparation speech produced no transcript");
                    }
                    Console.WriteLine(FormattableString.Invariant($"  GPU shader preparation: {Stopwatch.GetElapsedTime(preparation).TotalMilliseconds:F0} ms"));
                }
                var text = await speech.TranscribeAsync(audio, [], CancellationToken.None).ConfigureAwait(false);
                CheckFixtureText(text);
                CheckFixtureText(await speech.TranscribeAsync(audio, ["fellow Americans", "country"], CancellationToken.None).ConfigureAwait(false));
                CheckFixtureText(await speech.TranscribeAsync(audio, [], CancellationToken.None).ConfigureAwait(false));
                // The old NeMo hard log floor returned no words at this level.
                // Exercise the packaged feature extractor without changing microphone gain.
                var quiet = audio.Select(sample => sample * 0.001f).ToArray();
                CheckFixtureText(await speech.TranscribeAsync(quiet, [], CancellationToken.None).ConfigureAwait(false));
                if (!string.IsNullOrWhiteSpace(await speech.TranscribeAsync(new float[audio.Length], [], CancellationToken.None).ConfigureAwait(false)))
                    throw new InvalidDataException("Silent fixture produced a transcript");
                speech.FinishWork(); await speech.ResetAsync(CancellationToken.None).ConfigureAwait(false);
                if (speech.WorkerId is not null) throw new IOException("Worker did not stop");
            }
            Console.WriteLine("  [ok] bundled model, known and quiet speech, silence, per-recording hotwords, worker stop and restart");
            return 0;
        }
        catch (Exception e) { Console.Error.WriteLine("Speech check failed: " + e); return 1; }
    }
    internal static async Task<int> BenchmarkAsync(string output)
    {
        var report = await RunDeliveryReplayAsync().ConfigureAwait(false);
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(report, BenchmarkJsonContext.Default.BenchmarkReport)).ConfigureAwait(false);
        return report.Failures.Count == 0 && report.OrphanWorkers == 0 ? 0 : 1;
    }
    internal static async Task<BenchmarkReport> RunDeliveryReplayAsync(Action<SpeechWorkerClient>? observeSession = null,
        ITextDeliveryHotkeySource? deliveryHotkey = null, bool realtimeWarmCapture = false, bool coldOnly = false)
    {
        var report = new BenchmarkReport { RealtimeWarmCapture = realtimeWarmCapture };
        BenchmarkWorkerLauncher? trackedLauncher = null;
        try
        {
            var audio = ReadFixture();
            report.ClipSeconds = (double)audio.Length / AudioChunk.SampleRate;
            using var models = new ModelResolver();
            using var desktop = PlatformFactory.CreateDesktopIntegration() ?? throw new InvalidOperationException("Windows unavailable");
            using var deliveryProbe = PlatformFactory.CreateDeliveryProbe();
            ITextDeliveryProbe? probe = deliveryProbe;
            void PrepareTrial()
            {
                if (probe is null) return;
                try { probe.BeginTrial(); }
                catch (InvalidOperationException e) { report.DeliveryLimitation = e.Message; probe = null; }
            }
            if (probe is null) report.DeliveryLimitation = "Foreground test field unavailable";
            PrepareTrial();
            var launcher = trackedLauncher = new BenchmarkWorkerLauncher(PlatformFactory.CreateWorkerLauncher()
                ?? throw new InvalidOperationException("Worker launcher unavailable"));
            var injector = PlatformFactory.CreateTextInjector() ?? throw new InvalidOperationException("Injector unavailable");
            var speech = new SpeechWorkerClient(launcher, models, new WorkerOptions { IdleTimeout = TimeSpan.FromMilliseconds(100) });
            observeSession?.Invoke(speech);
            var baseline = Memory(speech); report.BaselinePrivateBytes = baseline.Private; report.BaselineWorkingSet = baseline.Working;
            var capture = new FixtureCapture(audio);
            var key = new ScriptedKey(deliveryHotkey);
            await using (var engine = new DictationEngine(capture, key, speech, injector, () => [], foreground: desktop, injectEnabled: () => probe is not null,
                options: new DictationOptions { MaxSegmentSeconds = ModelResolver.PreferredMaxSegmentSeconds }))
            {
                var completed = 0;
                engine.Completed += (_, _) => completed++;
                // Start with an unloaded worker, replaying at recording speed so
                // loading overlaps the actual utterance rather than a preload.
                foreach (var seconds in new[] { 1, 3, 10 })
                {
                    await speech.ResetAsync(CancellationToken.None).ConfigureAwait(false);
                    PrepareTrial(); capture.Prepare(realtime: true, seconds: seconds); key.Press();
                    await capture.Started.Task.WaitAsync(TimeSpan.FromSeconds(seconds + 15)).ConfigureAwait(false);
                    var released = Stopwatch.GetTimestamp(); key.Release();
                    await WaitAsync(() => engine.State == DictationState.Idle, TimeSpan.FromSeconds(30)).ConfigureAwait(false);
                    var result = engine.LastResult ?? throw new IOException("Cold dictation produced no transcript");
                    if (completed != report.ColdRecordingSeconds.Count + 1) throw new IOException("Cold dictation did not complete exactly once");
                    report.ColdRecordingSeconds.Add(seconds);
                    report.ColdDictationLoadMilliseconds.Add(speech.LastLoadTime.TotalMilliseconds);
                    report.ColdInferenceMilliseconds.Add(speech.LastInferenceTime.TotalMilliseconds);
                    report.ColdReleaseToTranscriptMilliseconds.Add(result.TranscriptTime.TotalMilliseconds);
                    if (probe is not null)
                    {
                        if (result.Delivery != DeliveryOutcome.Delivered) throw new IOException("Cold delivery outcome: " + result.Delivery);
                        await WaitAsync(() => probe.ReadText() == result.Text + " ", TimeSpan.FromSeconds(2)).ConfigureAwait(false);
                        report.ColdReleaseToFullInputMilliseconds.Add(Stopwatch.GetElapsedTime(released, probe.LastInputTimestamp).TotalMilliseconds);
                    }
                }
                if (coldOnly) return report;
                var warmStarted = completed;
                // Warm dictations should keep the worker for the full sequence.
                speech.SetIdleTimeout(TimeSpan.FromMinutes(5));
                await speech.BeginWorkAsync(CancellationToken.None).ConfigureAwait(false);
                await speech.LoadAsync(CancellationToken.None).ConfigureAwait(false);
                speech.FinishWork();
                var warmWorker = speech.WorkerId;
                for (var run = 0; run < 50; run++)
                {
                    PrepareTrial(); capture.Prepare(realtime: realtimeWarmCapture); key.Press();
                    var trialTarget = desktop.Capture();
                    await capture.Started.Task.WaitAsync(TimeSpan.FromSeconds(realtimeWarmCapture ? 15 : 5)).ConfigureAwait(false);
                    var released = Stopwatch.GetTimestamp(); key.Release();
                    await WaitAsync(() => engine.State == DictationState.Idle, TimeSpan.FromSeconds(30)).ConfigureAwait(false);
                    var result = engine.LastResult ?? throw new IOException("Missing transcript");
                    CheckFixtureText(result.Text);
                    var insertedText = result.Text + " ";
                    if (probe is not null)
                    {
                        try
                        {
                            if (result.Delivery != DeliveryOutcome.Delivered) throw new IOException("Delivery outcome: " + result.Delivery);
                            await WaitAsync(() => probe.ReadText() == insertedText, TimeSpan.FromSeconds(2)).ConfigureAwait(false);
                            if (probe.FirstInputTimestamp == 0) throw new IOException("First input was not observed");
                            report.ReleaseToFirstInputMilliseconds.Add(Stopwatch.GetElapsedTime(released, probe.FirstInputTimestamp).TotalMilliseconds);
                            report.ReleaseToFullInputMilliseconds.Add(Stopwatch.GetElapsedTime(released, probe.LastInputTimestamp).TotalMilliseconds);
                        }
                        catch (Exception e) when (e is IOException or OperationCanceledException)
                        {
                            if (!desktop.IsCurrent(trialTarget) || result.Delivery == DeliveryOutcome.TargetChanged)
                                report.DeliveryLimitation = "Focus changed during delivery; remaining inference checks ran without insertion.";
                            else report.Failures.Add($"Foreground delivery could not be confirmed: outcome={result.Delivery}, expected={insertedText.Length}, received={probe.ReadText().Length}");
                            probe = null;
                        }
                    }
                    if (completed != warmStarted + run + 1) throw new IOException("Duplicate completion");
                    if (speech.WorkerId != warmWorker) throw new IOException("Worker was not reused");
                    report.TranscriptCharacters = result.Text.Length;
                    report.ReleaseToTranscriptMilliseconds.Add(result.TranscriptTime.TotalMilliseconds);
                    report.LoadedPrivateBytes = Math.Max(report.LoadedPrivateBytes, Memory(speech).Private);
                    report.LoadedWorkingSet = Math.Max(report.LoadedWorkingSet, Memory(speech).Working);
                }
                report.SequentialDictations = completed - warmStarted;
                // Kill a real worker after capturing audio, before releasing it.
                PrepareTrial(); capture.Prepare(); key.Press();
                await capture.Started.Task.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false);
                using (var child = Process.GetProcessById(speech.WorkerId!.Value)) { child.Kill(); await child.WaitForExitAsync().ConfigureAwait(false); }
                var recovery = Stopwatch.GetTimestamp(); key.Release();
                await WaitAsync(() => engine.State == DictationState.Idle, TimeSpan.FromSeconds(45)).ConfigureAwait(false);
                report.RecoveryMilliseconds = Stopwatch.GetElapsedTime(recovery).TotalMilliseconds;
                var recovered = engine.LastResult;
                if (completed != warmStarted + 51 || recovered is null || (probe is not null && recovered.Delivery != DeliveryOutcome.Delivered))
                    throw new IOException("Worker recovery lost audio or repeated delivery");
                if (probe is not null)
                    await WaitAsync(() => probe.ReadText() == recovered.Text + " ", TimeSpan.FromSeconds(2)).ConfigureAwait(false);
                report.WorkerCrashRecoveryPassed = true;
                speech.SetIdleTimeout(TimeSpan.FromMilliseconds(100));
                await WaitAsync(() => speech.WorkerId is null, TimeSpan.FromSeconds(7)).ConfigureAwait(false);
            }
            // An actual native-worker deadline must retain one unresolved recording.
            var timeoutSpeech = new SpeechWorkerClient(launcher, models, new WorkerOptions { InferenceTimeout = TimeSpan.FromTicks(1) });
            observeSession?.Invoke(timeoutSpeech);
            capture = new FixtureCapture(audio); key = new ScriptedKey(deliveryHotkey);
            await using (var engine = new DictationEngine(capture, key, timeoutSpeech, injector, () => [], injectEnabled: () => false,
                options: new DictationOptions { MaxSegmentSeconds = ModelResolver.PreferredMaxSegmentSeconds }))
            {
                capture.Prepare(); key.Press(); await capture.Started.Task.WaitAsync(TimeSpan.FromSeconds(5)).ConfigureAwait(false); key.Release();
                await WaitAsync(() => engine.State == DictationState.AwaitingRetry, TimeSpan.FromSeconds(90)).ConfigureAwait(false);
                if (engine.LastResult is not null || !engine.HasPendingAudio) throw new IOException("Timeout lost recoverable audio");
                engine.Discard();
                if (engine.State != DictationState.Idle || engine.HasPendingAudio) throw new IOException("Discard did not release recording");
                report.TimeoutRetentionPassed = true;
            }
            // Keep delivery checks close to creation of the foreground test field.
            // Cold-load cycles do not require focus and can run afterwards.
            speech = new SpeechWorkerClient(launcher, models, new WorkerOptions { IdleTimeout = TimeSpan.FromMilliseconds(100) });
            observeSession?.Invoke(speech);
            await using (speech)
            {
                for (var run = 0; run < 20; run++)
                {
                    await speech.BeginWorkAsync(CancellationToken.None).ConfigureAwait(false);
                    if (!await speech.LoadAsync(CancellationToken.None).ConfigureAwait(false)) throw new IOException("Model not verified");
                    report.ColdLoadMilliseconds.Add(speech.LastLoadTime.TotalMilliseconds);
                    report.LoadedPrivateBytes = Math.Max(report.LoadedPrivateBytes, Memory(speech).Private);
                    report.LoadedWorkingSet = Math.Max(report.LoadedWorkingSet, Memory(speech).Working);
                    speech.FinishWork();
                    await WaitAsync(() => speech.WorkerId is null, TimeSpan.FromSeconds(7)).ConfigureAwait(false);
                    report.UnloadCycles++;
                }
            }
            GC.Collect(); GC.WaitForPendingFinalizers(); GC.Collect();
            var after = Memory(speech); report.AfterUnloadPrivateBytes = after.Private; report.AfterUnloadWorkingSet = after.Working;
        }
        catch (Exception e) { report.Failures.Add(e.GetType().Name + ": " + e.Message); }
        finally
        {
            if (trackedLauncher is not null)
            {
                report.OwnedWorkers.AddRange(trackedLauncher.Snapshot());
                report.OrphanWorkers = report.OwnedWorkers.Count(worker => !worker.HasExited);
                trackedLauncher.Dispose();
            }
        }
        return report;
    }
    private static (long Private, long Working) Memory(SpeechWorkerClient client)
    {
        using var process = Process.GetCurrentProcess(); process.Refresh();
        var memory = process.PrivateMemorySize64; var working = process.WorkingSet64;
        if (client.WorkerId is { } pid) { using var child = Process.GetProcessById(pid); memory += child.PrivateMemorySize64; working += child.WorkingSet64; }
        return (memory, working);
    }
    private static async Task WaitAsync(Func<bool> predicate, TimeSpan timeout)
    {
        using var deadline = new CancellationTokenSource(timeout);
        while (!predicate()) await Task.Delay(10, deadline.Token).ConfigureAwait(false);
    }
    private static void CheckFixtureText(string text)
    {
        if (!text.Contains("fellow americans", StringComparison.OrdinalIgnoreCase) || !text.Contains("country", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Known speech fixture produced an unexpected transcript");
    }
    internal static float[] ReadFixture()
    {
        using var reader = new BinaryReader(File.OpenRead(Path.Combine(AppContext.BaseDirectory, "fixtures", "jfk.wav")));
        if (reader.ReadUInt32() != 0x46464952) throw new InvalidDataException("Not WAV");
        reader.ReadUInt32(); if (reader.ReadUInt32() != 0x45564157) throw new InvalidDataException("Not WAV");
        while (reader.BaseStream.Position < reader.BaseStream.Length)
        {
            var kind = reader.ReadUInt32(); var size = reader.ReadInt32(); var next = reader.BaseStream.Position + size + (size & 1);
            if (kind == 0x20746D66)
            {
                if (reader.ReadUInt16() != 1 || reader.ReadUInt16() != 1 || reader.ReadInt32() != 16000) throw new InvalidDataException("Fixture must be 16kHz mono PCM");
                reader.ReadInt32(); reader.ReadUInt16(); if (reader.ReadUInt16() != 16) throw new InvalidDataException("Fixture must be PCM16");
            }
            if (kind == 0x61746164)
            {
                var count = Math.Min(size / 2, 10 * AudioChunk.SampleRate);
                var audio = new float[count]; for (var i = 0; i < count; i++) audio[i] = reader.ReadInt16() / 32768f;
                return audio;
            }
            reader.BaseStream.Position = next;
        }
        throw new InvalidDataException("Fixture audio missing");
    }
    private sealed class ScriptedKey(ITextDeliveryHotkeySource? deliveryHotkey = null) : ITextDeliveryHotkeySource
    {
        public event EventHandler? Pressed;
        public event EventHandler? Released;
        public bool Start() => deliveryHotkey?.Start() ?? true;
        public ValueTask<bool> TryPauseForDeliveryAsync(CancellationToken cancellationToken) =>
            deliveryHotkey?.TryPauseForDeliveryAsync(cancellationToken) ?? ValueTask.FromResult(false);
        public void StopListening() { }
        public void Dispose() { }
        internal void Press() => Pressed?.Invoke(this, EventArgs.Empty);
        internal void Release() => Released?.Invoke(this, EventArgs.Empty);
    }
    private sealed class FixtureCapture(float[] audio) : IAudioCapture
    {
        private bool _realtime;
        private int _samples = audio.Length;
        internal TaskCompletionSource Started { get; private set; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        internal void Prepare(bool realtime = false, int seconds = 10)
        {
            _realtime = realtime; _samples = Math.Min(audio.Length, seconds * AudioChunk.SampleRate);
            Started = new(TaskCreationOptions.RunContinuationsAsynchronously);
        }
        public bool IsCapturing { get; private set; }
        public async IAsyncEnumerable<AudioChunk> CaptureAsync([EnumeratorCancellation] CancellationToken cancellationToken)
        {
            IsCapturing = true;
            var clock = Stopwatch.StartNew();
            var chunkSize = _realtime ? AudioChunk.SampleRate / 20 : _samples;
            for (var offset = 0; offset < _samples; offset += chunkSize)
            {
                var count = Math.Min(chunkSize, _samples - offset);
                if (_realtime)
                {
                    var delay = TimeSpan.FromSeconds((double)(offset + count) / AudioChunk.SampleRate) - clock.Elapsed;
                    if (delay > TimeSpan.Zero) await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
                }
                yield return new AudioChunk(audio.AsSpan(offset, count).ToArray());
            }
            Started.TrySetResult();
            try { await Task.Delay(Timeout.Infinite, cancellationToken).ConfigureAwait(false); } catch (OperationCanceledException) { }
            IsCapturing = false;
        }
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}
// Retain handles to the benchmark's exact processes until teardown has been
// checked. Other sessions can use the same executable, and PIDs can be reused.
internal sealed class BenchmarkWorkerLauncher(IWorkerLauncher inner) : IWorkerLauncher, IDisposable
{
    private readonly List<(Process Process, int Id, DateTime StartedUtc)> _workers = [];

    public IWorkerProcess Launch(string pipeName, string secret)
    {
        var worker = inner.Launch(pipeName, secret);
        var process = Process.GetProcessById(worker.Id);
        _ = process.Handle;
        _workers.Add((process, worker.Id, process.StartTime.ToUniversalTime()));
        return worker;
    }

    internal IReadOnlyList<BenchmarkWorkerIdentity> Snapshot() => _workers.Select(worker =>
        new BenchmarkWorkerIdentity(worker.Id, worker.StartedUtc, worker.Process.HasExited)).ToArray();

    public void Dispose()
    {
        foreach (var worker in _workers) worker.Process.Dispose();
    }
}

internal sealed record BenchmarkWorkerIdentity(int ProcessId, DateTime StartTimeUtc, bool HasExited);

internal sealed class BenchmarkReport
{
    public bool RealtimeWarmCapture { get; set; }
    public string ModelName { get; init; } = ModelResolver.DisplayName;
    public string ModelVersion { get; init; } = ModelResolver.Version;
    public string Runtime { get; init; } = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription;
    public int LogicalProcessors { get; init; } = Environment.ProcessorCount;
    public double ClipSeconds { get; set; }
    public int TranscriptCharacters { get; set; }
    public List<double> ColdLoadMilliseconds { get; } = [];
    public List<double> ReleaseToFirstInputMilliseconds { get; } = [];
    public List<double> ReleaseToFullInputMilliseconds { get; } = [];
    public List<int> ColdRecordingSeconds { get; } = [];
    public List<double> ColdDictationLoadMilliseconds { get; } = [];
    public List<double> ColdInferenceMilliseconds { get; } = [];
    public List<double> ColdReleaseToTranscriptMilliseconds { get; } = [];
    public List<double> ColdReleaseToFullInputMilliseconds { get; } = [];
    public List<double> ReleaseToTranscriptMilliseconds { get; } = [];
    public string? DeliveryLimitation { get; set; }
    public long BaselinePrivateBytes { get; set; }
    public long BaselineWorkingSet { get; set; }
    public long LoadedPrivateBytes { get; set; }
    public long LoadedWorkingSet { get; set; }
    public long AfterUnloadPrivateBytes { get; set; }
    public long AfterUnloadWorkingSet { get; set; }
    public int UnloadCycles { get; set; }
    public int SequentialDictations { get; set; }
    public double RecoveryMilliseconds { get; set; }
    public bool WorkerCrashRecoveryPassed { get; set; }
    public bool TimeoutRetentionPassed { get; set; }
    public int OrphanWorkers { get; set; }
    public List<BenchmarkWorkerIdentity> OwnedWorkers { get; } = [];
    public List<string> Failures { get; } = [];
}
internal sealed class DesktopBenchmarkReport
{
    public long BeforePrivateBytes { get; set; }
    public long BeforeWorkingSet { get; set; }
    public double IdleCpuPercent { get; set; }
    public long LoadedPrivateBytes { get; set; }
    public long LoadedWorkingSet { get; set; }
    public double IdleExitMilliseconds { get; set; }
    public long AfterPrivateBytes { get; set; }
    public long AfterWorkingSet { get; set; }
    public long AfterCollectionPrivateBytes { get; set; }
    public long AfterCollectionWorkingSet { get; set; }
    public int WorkersAfterUnload { get; set; }
    public List<string> Failures { get; } = [];
}
[JsonSourceGenerationOptions(WriteIndented = true)]
[JsonSerializable(typeof(BenchmarkReport))]
[JsonSerializable(typeof(DesktopBenchmarkReport))]
internal sealed partial class BenchmarkJsonContext : JsonSerializerContext;

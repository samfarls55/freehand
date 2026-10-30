using System.Buffers.Binary;
using System.Diagnostics;
using System.Globalization;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Speech;

namespace Freehand.Evaluation;

internal static partial class Program
{
    private static async Task<int> Main(string[] args)
    {
        if (args is ["--selftest"])
        {
            var cases = new[]
            {
                ("one two", "one two", new WordScore(2, 0, 0, 0)),
                ("one two", "one three", new WordScore(2, 1, 0, 0)),
                ("one two three", "one", new WordScore(3, 0, 2, 0)),
                ("one", "one two three", new WordScore(1, 0, 0, 2)),
                ("Don't use C-sharp, again.", "dont use c sharp again", new WordScore(5, 0, 0, 0)),
                ("one two", "", new WordScore(2, 0, 2, 0)),
            };
            foreach (var (reference, actual, expected) in cases)
                if (Score(reference, actual) != expected) throw new InvalidDataException("Word scoring self-test failed.");
            Console.WriteLine("Word scoring self-test passed: equality, substitutions, deletions, insertions, normalization, empty output.");
            foreach (var waitForCancellation in new[] { false, true })
            {
                var failingSpeech = new SelfTestTranscriber(waitForCancellation);
                var key = new ScriptedKey();
                var capture = new ReplayCapture(Enumerable.Repeat(0.1f, 1600).ToArray(), realtime: false);
                var completed = new TaskCompletionSource<DictationResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                await using var engine = new DictationEngine(capture, key, failingSpeech, new CountingInjector(), () => []);
                engine.Completed += (_, result) => completed.TrySetResult(result);
                key.Press();
                await capture.Ready.Task.WaitAsync(TimeSpan.FromSeconds(1)).ConfigureAwait(false);
                key.Release();
                var outcome = await WaitForCompletionAsync(engine, completed.Task, TimeSpan.FromMilliseconds(waitForCancellation ? 25 : 1000)).ConfigureAwait(false);
                var expected = waitForCancellation ? "CompletionDeadline" : "ModelFailure";
                if (outcome.Result is not null || outcome.Failure != expected || (!waitForCancellation && failingSpeech.Calls != 2))
                    throw new InvalidDataException("Evaluator completion failure self-test failed.");
            }
            Console.WriteLine("Completion self-test passed: two real engine ASR failures stop at AwaitingRetry; stalled recognition stops at the deadline and cancels on disposal.");
            return 0;
        }
        if (args.Length < 4)
        {
            Console.Error.WriteLine("Usage: Freehand.Evaluation APP MODEL MANIFEST OUTPUT [--repeat N] [--gains 1,0.02] [--realtime] [--cold] [--include-text] [--completion-timeout-seconds N]");
            return 2;
        }
        var executable = Path.GetFullPath(args[0]);
        var modelDirectory = Path.GetFullPath(args[1]);
        var manifestPath = Path.GetFullPath(args[2]);
        var output = Path.GetFullPath(args[3]);
        var repeats = 1;
        var gains = new[] { 1f };
        var realtime = false;
        var cold = false;
        var includeText = false;
        var completionTimeoutSeconds = 180;
        for (var index = 4; index < args.Length; index++)
        {
            switch (args[index])
            {
                case "--repeat": repeats = int.Parse(args[++index], CultureInfo.InvariantCulture); break;
                case "--gains": gains = args[++index].Split(',').Select(value => float.Parse(value, CultureInfo.InvariantCulture)).ToArray(); break;
                case "--realtime": realtime = true; break;
                case "--cold": cold = true; break;
                case "--include-text": includeText = true; break;
                case "--completion-timeout-seconds": completionTimeoutSeconds = int.Parse(args[++index], CultureInfo.InvariantCulture); break;
                default: throw new ArgumentException("Unknown evaluation option: " + args[index]);
            }
        }
        if (repeats is < 1 or > 20 || gains.Length == 0 || gains.Any(gain => !float.IsFinite(gain) || gain is <= 0 or > 1))
            throw new ArgumentException("Repeat must be 1-20 and gains must be finite in (0,1].");
        if (completionTimeoutSeconds is < 1 or > 300) throw new ArgumentException("Completion timeout must be 1-300 seconds.");
        if (!File.Exists(executable)) throw new FileNotFoundException("Worker executable missing", executable);
        var outputDirectory = Path.GetDirectoryName(output)!;
        Directory.CreateDirectory(outputDirectory);
        using var manifestDocument = JsonDocument.Parse(await File.ReadAllTextAsync(manifestPath).ConfigureAwait(false));
        var clips = ReadManifest(manifestDocument.RootElement, Path.GetDirectoryName(manifestPath)!);
        var trials = new List<Trial>();
        var failures = new List<string>();
        using var models = new ModelResolver(modelDirectory, cacheDirectory: Path.Combine(outputDirectory, "verification"));
        await using var speech = new SpeechWorkerClient(new ExecutableLauncher(executable, Path.Combine(outputDirectory, "worker-profile")), models,
            new WorkerOptions { PrepareWhileActive = ModelResolver.UsesAcceleratedModel });
        speech.SetIdleTimeout(Timeout.InfiniteTimeSpan);
        using var totalMonitorStop = new CancellationTokenSource();
        var totalPeak = new MemoryPeak();
        var totalMonitor = MonitorAsync(speech, totalPeak, totalMonitorStop.Token);
        var started = Stopwatch.GetTimestamp();
        if (!await speech.LoadAsync(CancellationToken.None).ConfigureAwait(false)) throw new IOException("Model verification failed.");
        var initialLoadMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        foreach (var gain in gains)
        {
            foreach (var clip in clips)
            {
                var source = ReadWave(clip.AudioPath);
                for (var repeat = 0; repeat < repeats; repeat++)
                {
                    var samples = source.Select(sample => sample * gain).ToArray();
                    var rms = Math.Sqrt(samples.Sum(sample => (double)sample * sample) / samples.Length);
                    var loadMilliseconds = 0d;
                    if (cold)
                    {
                        await speech.ResetAsync(CancellationToken.None).ConfigureAwait(false);
                        var loadAt = Stopwatch.GetTimestamp();
                        if (!await speech.LoadAsync(CancellationToken.None).ConfigureAwait(false)) throw new IOException("Cold load failed.");
                        loadMilliseconds = Stopwatch.GetElapsedTime(loadAt).TotalMilliseconds;
                    }
                    var observed = new ObservedTranscriber(speech);
                    var key = new ScriptedKey();
                    var capture = new ReplayCapture(samples, realtime);
                    var injector = new CountingInjector();
                    var completed = new TaskCompletionSource<DictationResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                    await using var engine = new DictationEngine(capture, key, observed, injector, () => [],
                        options: new DictationOptions { MaxSegmentSeconds = ModelResolver.PreferredMaxSegmentSeconds });
                    engine.Completed += (_, result) => completed.TrySetResult(result);
                    using var monitorStop = new CancellationTokenSource();
                    var peak = new MemoryPeak();
                    var monitor = MonitorAsync(speech, peak, monitorStop.Token);
                    key.Press();
                    await capture.Ready.Task.WaitAsync(TimeSpan.FromMinutes(11)).ConfigureAwait(false);
                    key.Release();
                    var outcome = await WaitForCompletionAsync(engine, completed.Task, TimeSpan.FromSeconds(completionTimeoutSeconds)).ConfigureAwait(false);
                    var result = outcome.Result;
                    if (outcome.Failure == "CompletionDeadline") await engine.DisposeAsync().ConfigureAwait(false);
                    await monitorStop.CancelAsync().ConfigureAwait(false);
                    await monitor.ConfigureAwait(false);
                    var raw = string.Join(' ', observed.Pieces);
                    var final = result?.Text ?? string.Empty;
                    if (outcome.Failure is not null) failures.Add(clip.Id + ": " + outcome.Failure);
                    if (result is not null && injector.Count != 1) failures.Add(clip.Id + ": wrong delivery count");
                    var rawScore = Score(clip.Reference, raw);
                    var formattedScore = Score(clip.Reference, final);
                    trials.Add(new Trial(clip.Id, repeat, gain, rms > 0 ? 20 * Math.Log10(rms) : null, samples.Length / 16000d,
                        rawScore, formattedScore, result?.TranscriptTime.TotalMilliseconds,
                        result?.ProcessingTime.TotalMilliseconds, loadMilliseconds, peak.Snapshot(),
                        capture.ElapsedMilliseconds, realtime ? capture.ElapsedMilliseconds - samples.Length / 16d : null,
                        rms < 0.00001, raw.Length == 0, includeText ? clip.Reference : null, includeText ? raw : null, includeText ? final : null));
                }
            }
        }
        await totalMonitorStop.CancelAsync().ConfigureAwait(false);
        await totalMonitor.ConfigureAwait(false);
        var summaries = trials.GroupBy(trial => trial.Gain).Select(group => new Summary(group.Key, group.Count(),
            Aggregate(group.Select(trial => trial.Raw)), Aggregate(group.Select(trial => trial.Formatted)),
            Percentile(group.Where(trial => trial.TranscriptMilliseconds.HasValue).Select(trial => trial.TranscriptMilliseconds!.Value), .5),
            Percentile(group.Where(trial => trial.TranscriptMilliseconds.HasValue).Select(trial => trial.TranscriptMilliseconds!.Value), .95))).ToArray();
        var runtimeHashes = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var name in new[] { "sherpa-onnx-c-api.dll", "onnxruntime.dll" })
        {
            var library = Path.Combine(Path.GetDirectoryName(executable)!, name);
            if (File.Exists(library))
            {
                using var libraryStream = File.OpenRead(library);
                runtimeHashes.Add(name, Convert.ToHexString(SHA256.HashData(libraryStream)));
            }
        }
        var report = new Report(DateTimeOffset.UtcNow, executable, Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(executable).ConfigureAwait(false))), runtimeHashes,
            manifestPath, Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(manifestPath).ConfigureAwait(false))), realtime ? "realtime audio replay" : "accelerated accuracy replay", cold,
            "Memory includes evaluator and worker, excludes desktop UI. Injector counts calls and does not type. Cold mode measures loading separately before recording. No visible-delivery or Wispr parity claim.",
            initialLoadMilliseconds, totalPeak.Snapshot(), summaries, trials.ToArray(), failures.ToArray());
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(report, EvaluationJsonContext.Default.Report)).ConfigureAwait(false);
        foreach (var summary in summaries)
            Console.WriteLine(string.Create(CultureInfo.InvariantCulture, $"gain={summary.Gain} trials={summary.Trials} raw WER={summary.Raw.WordErrorRate:P2} S/D/I={summary.Raw.Substitutions}/{summary.Raw.Deletions}/{summary.Raw.Insertions} p50={summary.TranscriptP50Milliseconds:F1}ms p95={summary.TranscriptP95Milliseconds:F1}ms"));
        Console.WriteLine("Report: " + output);
        return failures.Count == 0 ? 0 : 1;
    }

    private static async Task<(DictationResult? Result, string? Failure)> WaitForCompletionAsync(
        DictationEngine engine, Task<DictationResult> completed, TimeSpan timeout)
    {
        var released = Stopwatch.GetTimestamp();
        while (!completed.IsCompleted && engine.State is not (DictationState.Idle or DictationState.AwaitingRetry or DictationState.Stopping))
        {
            if (Stopwatch.GetElapsedTime(released) >= timeout) return (null, "CompletionDeadline");
            await Task.Delay(2).ConfigureAwait(false);
        }
        if (completed.IsCompletedSuccessfully) return (await completed.ConfigureAwait(false), null);
        return (null, engine.Feedback?.Outcome == DictationOutcome.EmptySpeech ? null
            : engine.Feedback?.Outcome.ToString() ?? engine.State.ToString());
    }

    private static Clip[] ReadManifest(JsonElement document, string directory)
    {
        var ids = new HashSet<string>(StringComparer.Ordinal);
        return document.GetProperty("clips").EnumerateArray().Select(element =>
        {
            var id = element.GetProperty("id").GetString()!;
            var reference = element.GetProperty("reference").GetString()!;
            var path = Path.GetFullPath(Path.Combine(directory, element.GetProperty("audioPath").GetString()!));
            if (string.IsNullOrWhiteSpace(id) || reference is null || !ids.Add(id))
                throw new InvalidDataException("Each recording needs a unique ID and a string reference. Use an empty reference for silence.");
            if (element.TryGetProperty("sha256", out var expected))
            {
                using var stream = File.OpenRead(path);
                if (!Convert.ToHexString(SHA256.HashData(stream)).Equals(expected.GetString(), StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("Recording checksum mismatch: " + id);
            }
            return new Clip(id, path, reference);
        }).ToArray();
    }

    private static float[] ReadWave(string path)
    {
        var bytes = File.ReadAllBytes(path);
        if (bytes.Length < 44 || !bytes.AsSpan(0, 4).SequenceEqual("RIFF"u8) || !bytes.AsSpan(8, 4).SequenceEqual("WAVE"u8))
            throw new InvalidDataException("Expected RIFF WAVE audio: " + path);
        ushort format = 0, channels = 0, bits = 0;
        var rate = 0;
        ReadOnlySpan<byte> data = default;
        for (var at = 12; at + 8 <= bytes.Length;)
        {
            var size = BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(at + 4));
            if (size < 0 || size > bytes.Length - at - 8) throw new InvalidDataException("Truncated WAVE chunk.");
            if (bytes.AsSpan(at, 4).SequenceEqual("fmt "u8) && size >= 16)
            {
                format = BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(at + 8));
                channels = BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(at + 10));
                rate = BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(at + 12));
                bits = BinaryPrimitives.ReadUInt16LittleEndian(bytes.AsSpan(at + 22));
            }
            if (bytes.AsSpan(at, 4).SequenceEqual("data"u8)) data = bytes.AsSpan(at + 8, size);
            at = checked(at + 8 + size + (size & 1));
        }
        if (rate != 16000 || channels != 1 || data.IsEmpty || !(format == 1 && bits == 16 || format == 3 && bits == 32))
            throw new InvalidDataException("Use 16 kHz mono PCM16 or float32 WAVE audio.");
        var width = bits / 8;
        if (data.Length % width != 0) throw new InvalidDataException("Incomplete WAVE sample.");
        var samples = new float[data.Length / width];
        for (var index = 0; index < samples.Length; index++)
            samples[index] = format == 1 ? BinaryPrimitives.ReadInt16LittleEndian(data[(index * width)..]) / 32768f
                : BinaryPrimitives.ReadSingleLittleEndian(data[(index * width)..]);
        if (samples.Any(sample => !float.IsFinite(sample) || sample is < -1 or > 1)) throw new InvalidDataException("WAVE samples outside [-1,1].");
        return samples;
    }

    [GeneratedRegex(@"[^\p{L}\p{N}]+", RegexOptions.CultureInvariant)]
    private static partial Regex NonWords();
    private static string[] Words(string text) => NonWords().Replace(text.Normalize(NormalizationForm.FormC).ToLowerInvariant().Replace("'", string.Empty, StringComparison.Ordinal).Replace("’", string.Empty, StringComparison.Ordinal), " ").Split(' ', StringSplitOptions.RemoveEmptyEntries);
    private static WordScore Score(string reference, string actual)
    {
        var expected = Words(reference);
        var observed = Words(actual);
        var costs = new (int Errors, int Substitutions, int Deletions, int Insertions)[expected.Length + 1, observed.Length + 1];
        for (var row = 1; row <= expected.Length; row++) costs[row, 0] = (row, 0, row, 0);
        for (var column = 1; column <= observed.Length; column++) costs[0, column] = (column, 0, 0, column);
        for (var row = 1; row <= expected.Length; row++)
            for (var column = 1; column <= observed.Length; column++)
            {
                var replace = costs[row - 1, column - 1];
                if (expected[row - 1] != observed[column - 1]) { replace.Errors++; replace.Substitutions++; }
                var delete = costs[row - 1, column]; delete.Errors++; delete.Deletions++;
                var insert = costs[row, column - 1]; insert.Errors++; insert.Insertions++;
                costs[row, column] = replace.Errors <= delete.Errors && replace.Errors <= insert.Errors ? replace : delete.Errors <= insert.Errors ? delete : insert;
            }
        var result = costs[expected.Length, observed.Length];
        return new WordScore(expected.Length, result.Substitutions, result.Deletions, result.Insertions);
    }
    private static WordScore Aggregate(IEnumerable<WordScore> scores) => scores.Aggregate(new WordScore(0, 0, 0, 0), (sum, value) => new WordScore(sum.ReferenceWords + value.ReferenceWords, sum.Substitutions + value.Substitutions, sum.Deletions + value.Deletions, sum.Insertions + value.Insertions));
    private static double? Percentile(IEnumerable<double> samples, double fraction)
    {
        var sorted = samples.Order().ToArray();
        return sorted.Length == 0 ? null : sorted[Math.Max(0, (int)Math.Ceiling(sorted.Length * fraction) - 1)];
    }
    private static async Task MonitorAsync(SpeechWorkerClient speech, MemoryPeak peak, CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            using var host = Process.GetCurrentProcess();
            var working = host.WorkingSet64;
            var commit = host.PrivateMemorySize64;
            if (speech.WorkerId is { } id)
            {
                // A sampled child can exit while cold-mode reset replaces it.
                try
                {
                    using var worker = Process.GetProcessById(id);
                    working += worker.WorkingSet64; commit += worker.PrivateMemorySize64;
                }
                catch (ArgumentException) { }
                catch (InvalidOperationException) { }
            }
            peak.Observe(working, commit);
            await Task.Delay(5, CancellationToken.None).ConfigureAwait(false);
        }
    }
}

internal sealed record Clip(string Id, string AudioPath, string Reference);
internal sealed record WordScore(int ReferenceWords, int Substitutions, int Deletions, int Insertions)
{
    public double? WordErrorRate => ReferenceWords == 0 ? null : (Substitutions + Deletions + Insertions) / (double)ReferenceWords;
}
internal sealed record MemorySample(long PeakSummedWorkingSetBytes, long PeakSummedPrivateCommitBytes);
internal sealed record Trial(string Id, int Repeat, float Gain, double? RmsDbfs, double AudioSeconds, WordScore Raw, WordScore Formatted, double? TranscriptMilliseconds, double? CountingInjectorCompleteMilliseconds, double SeparateColdLoadMilliseconds, MemorySample Memory, double CaptureMilliseconds, double? CaptureDriftMilliseconds, bool BelowEngineSilenceThreshold, bool RawOutputEmpty, string? Reference, string? RawText, string? FinalText);
internal sealed record Summary(float Gain, int Trials, WordScore Raw, WordScore Formatted, double? TranscriptP50Milliseconds, double? TranscriptP95Milliseconds);
internal sealed record Report(DateTimeOffset At, string Executable, string ExecutableSha256, Dictionary<string, string> RuntimeSha256, string Manifest, string ManifestSha256, string ReplayMode, bool ColdLoadsBeforeRecording, string Limitations, double InitialLoadMilliseconds, MemorySample Memory, Summary[] Summaries, Trial[] Trials, string[] Failures);
[JsonSerializable(typeof(Report))]
[JsonSourceGenerationOptions(WriteIndented = true, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
internal sealed partial class EvaluationJsonContext : JsonSerializerContext;

internal sealed class MemoryPeak
{
    private long _working, _commit;
    internal void Observe(long working, long commit) { _working = Math.Max(_working, working); _commit = Math.Max(_commit, commit); }
    internal MemorySample Snapshot() => new(_working, _commit);
}

internal sealed class ObservedTranscriber(SpeechWorkerClient speech) : ISpeechSession
{
    internal List<string> Pieces { get; } = [];
    public ModelState State => speech.State;
    public event EventHandler? Changed { add => speech.Changed += value; remove => speech.Changed -= value; }
    public bool IsReady => speech.IsReady;
    public bool SupportsBiasPhrase(string phrase) => speech.SupportsBiasPhrase(phrase);
    public ValueTask BeginWorkAsync(CancellationToken cancellationToken) => speech.BeginWorkAsync(cancellationToken);
    public void FinishWork() => speech.FinishWork();
    public void SetIdleTimeout(TimeSpan timeout) => speech.SetIdleTimeout(timeout);
    public ValueTask ResetAsync(CancellationToken cancellationToken) { Pieces.Clear(); return speech.ResetAsync(cancellationToken); }
    public ValueTask<bool> LoadAsync(CancellationToken cancellationToken) => speech.LoadAsync(cancellationToken);
    public async ValueTask<string> TranscribeAsync(ReadOnlyMemory<float> samples, IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken)
    {
        var text = await speech.TranscribeAsync(samples, biasPhrases, cancellationToken).ConfigureAwait(false);
        Pieces.Add(text);
        return text;
    }
    public ValueTask DisposeAsync() => ValueTask.CompletedTask;
}

internal sealed class ScriptedKey : IHotkeySource
{
    public event EventHandler? Pressed;
    public event EventHandler? Released;
    public bool Start() => true;
    public void StopListening() { }
    public void Dispose() { }
    internal void Press() => Pressed?.Invoke(this, EventArgs.Empty);
    internal void Release() => Released?.Invoke(this, EventArgs.Empty);
}

internal sealed class ReplayCapture(float[] samples, bool realtime) : IAudioCapture
{
    internal TaskCompletionSource Ready { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
    internal double ElapsedMilliseconds { get; private set; }
    public bool IsCapturing { get; private set; }
    public async IAsyncEnumerable<AudioChunk> CaptureAsync([EnumeratorCancellation] CancellationToken cancellationToken)
    {
        IsCapturing = true;
        var started = Stopwatch.GetTimestamp();
        for (var offset = 0; offset < samples.Length; offset += 800)
        {
            var count = Math.Min(800, samples.Length - offset);
            yield return new AudioChunk(samples.AsSpan(offset, count).ToArray());
            if (realtime)
            {
                var due = TimeSpan.FromSeconds((offset + count) / 16000d);
                var delay = due - Stopwatch.GetElapsedTime(started);
                if (delay > TimeSpan.Zero) await Task.Delay(delay, cancellationToken).ConfigureAwait(false);
            }
            else await Task.Yield();
        }
        ElapsedMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        Ready.TrySetResult();
        while (!cancellationToken.IsCancellationRequested) await Task.Delay(1, CancellationToken.None).ConfigureAwait(false);
        IsCapturing = false;
    }
    public ValueTask DisposeAsync() => ValueTask.CompletedTask;
}

internal sealed class CountingInjector : ITextInjector
{
    internal int Count { get; private set; }
    public ValueTask<bool> InjectAsync(string text, CancellationToken cancellationToken) { Count++; return ValueTask.FromResult(true); }
}

internal sealed class SelfTestTranscriber(bool waitForCancellation) : ITranscriber
{
    internal int Calls { get; private set; }
    public bool IsReady => true;
    public ValueTask<bool> LoadAsync(CancellationToken cancellationToken) => ValueTask.FromResult(true);
    public async ValueTask<string> TranscribeAsync(ReadOnlyMemory<float> samples, IReadOnlyList<string> biasPhrases, CancellationToken cancellationToken)
    {
        Calls++;
        if (!waitForCancellation) throw new IOException("Expected evaluator self-test inference failure.");
        await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken).ConfigureAwait(false);
        return string.Empty;
    }
    public ValueTask DisposeAsync() => ValueTask.CompletedTask;
}

internal sealed class ExecutableLauncher(string executable, string dataDirectory) : IWorkerLauncher
{
    public IWorkerProcess Launch(string pipeName, string secret)
    {
        using var parent = Process.GetCurrentProcess();
        var start = new ProcessStartInfo(executable) { UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden };
        start.Environment["FREEHAND_DATA_DIRECTORY"] = dataDirectory;
        foreach (var argument in new[] { "--speech-worker", pipeName, secret, Environment.ProcessId.ToString(CultureInfo.InvariantCulture), parent.StartTime.ToUniversalTime().Ticks.ToString(CultureInfo.InvariantCulture) }) start.ArgumentList.Add(argument);
        return new EvaluationWorker(Process.Start(start) ?? throw new IOException("Worker did not start."));
    }
    private sealed class EvaluationWorker(Process process) : IWorkerProcess
    {
        public int Id => process.Id;
        public bool HasExited => process.HasExited;
        public Task WaitForExitAsync(CancellationToken cancellationToken) => process.WaitForExitAsync(cancellationToken);
        public void Terminate() { if (!process.HasExited) process.Kill(entireProcessTree: true); }
        public async ValueTask DisposeAsync()
        {
            if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync().ConfigureAwait(false); }
            process.Dispose();
        }
    }
}

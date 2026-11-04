using System.Buffers.Binary;
using System.Buffers.Text;
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
using Freehand.Cleanup;
using Freehand.Speech;
using Microsoft.Win32.SafeHandles;

namespace Freehand.Evaluation;

internal static partial class Program
{
    // Portable research worker mode deliberately requires this framework-dependent
    // tool's loose assembly, rather than relying on Assembly.Location in a bundle.
    internal static string ResearchWorkerAssemblyPath => Path.Combine(AppContext.BaseDirectory, "Freehand.Evaluation.dll");
    private static async Task<int> Main(string[] args)
    {
        if (args.Length == 5 && args[0] is "--speech-worker" or "--portable-speech-worker")
        {
            var parentId = int.Parse(args[3], CultureInfo.InvariantCulture);
            var expectedTicks = long.Parse(args[4], CultureInfo.InvariantCulture);
            using var parent = Process.GetProcessById(parentId);
            var observedTicks = parent.StartTime.ToUniversalTime().Ticks;
            var portable = args[0] == "--portable-speech-worker";
            if (portable && !OperatingSystem.IsLinux()) throw new PlatformNotSupportedException("Portable research worker mode is Linux-only.");
            Console.Error.WriteLine(string.Create(CultureInfo.InvariantCulture,
                $"Research worker parent-start diagnostic: expected={expectedTicks} observed={observedTicks} deltaTicks={observedTicks - expectedTicks} portable={portable}"));
            // Linux can derive slightly different wall-clock boot-time offsets in separate
            // managed processes. Bound the discrepancy, then use this child's observation
            // for the real worker's exact parent-handle check. This is research-only; the
            // application's Windows entry point and ownership check remain unchanged.
            if (portable && (expectedTicks < observedTicks - TimeSpan.FromSeconds(2).Ticks
                || expectedTicks > observedTicks + TimeSpan.FromSeconds(2).Ticks)) return 2;
            return await SpeechWorker.RunAsync(args[1], args[2], parentId, portable ? observedTicks : expectedTicks).ConfigureAwait(false);
        }
        if (args is ["--selftest"])
        {
            var peak = new MemoryPeak();
            peak.Observe(100, 200, 0, 10);
            peak.Observe(50, 60, 250, 20);
            peak.Observe(500, 0, 0, 30);
            var memory = peak.Snapshot();
            if (memory.PeakSummedWorkingSetBytes != 500 || memory.PeakHostWorkingSetBytes != 500
                || memory.PeakSpeechWorkingSetBytes != 200 || memory.PeakCleanupWorkingSetBytes != 250
                || memory.AtSummedWorkingSetPeak != new MemoryBreakdown(500, 0, 0))
                throw new InvalidDataException("Simultaneous memory-peak attribution self-test failed.");
            var independentlyPhased = new MemoryPeak();
            independentlyPhased.Observe(200, 400, 100, 50);
            peak.IncludeObserved(independentlyPhased.Snapshot());
            var combined = peak.Snapshot();
            if (combined.PeakSummedWorkingSetBytes != 700 || combined.AtSummedWorkingSetPeak != new MemoryBreakdown(200, 400, 100)
                || combined.PeakHostWorkingSetBytes != 500 || combined.PeakSpeechWorkingSetBytes != 400 || combined.PeakCleanupWorkingSetBytes != 250)
                throw new InvalidDataException("Observed memory-snapshot aggregation self-test failed.");
            Console.WriteLine("Memory attribution self-test passed: component maxima remain separate from the simultaneous sum peak.");
            if (OperatingSystem.IsLinux())
            {
                using var resident = new LinuxResidentReader();
                var cached = resident.Read(Environment.ProcessId, 1);
                using var process = Process.GetCurrentProcess();
                var reference = process.WorkingSet64;
                var tolerance = 1024L * Environment.SystemPageSize;
                if (cached <= 0 || Math.Abs(cached - reference) > tolerance
                    || resident.Read(null, 2) != 0 || resident.Read(int.MaxValue, 3) != 0)
                    throw new InvalidDataException("Cached Linux resident-memory counter self-test failed.");
                Console.WriteLine(string.Create(CultureInfo.InvariantCulture,
                    $"Linux resident counter self-test passed: statm={cached} Process.WorkingSet64={reference} delta={Math.Abs(cached - reference)} tolerance={tolerance} bytes; missing/replaced identity yields zero."));
            }
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
            Console.Error.WriteLine("Usage: Freehand.Evaluation APP MODEL MANIFEST OUTPUT [--repeat N] [--gains 1,0.02] [--realtime] [--cold] [--include-text] [--completion-timeout-seconds N] [--cleanup-manifest PATH] [--skip-cleanup-warmup] [--portable-worker]");
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
        string? cleanupManifestPath = null;
        var skipCleanupWarmup = false;
        var portableWorker = false;
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
                case "--cleanup-manifest": cleanupManifestPath = Path.GetFullPath(args[++index]); break;
                case "--skip-cleanup-warmup": skipCleanupWarmup = true; break;
                case "--portable-worker": portableWorker = true; break;
                default: throw new ArgumentException("Unknown evaluation option: " + args[index]);
            }
        }
        if (repeats is < 1 or > 20 || gains.Length == 0 || gains.Any(gain => !float.IsFinite(gain) || gain is <= 0 or > 1))
            throw new ArgumentException("Repeat must be 1-20 and gains must be finite in (0,1].");
        if (completionTimeoutSeconds is < 1 or > 300) throw new ArgumentException("Completion timeout must be 1-300 seconds.");
        if (portableWorker && !OperatingSystem.IsLinux()) throw new PlatformNotSupportedException("Portable research worker mode is Linux-only.");
        if (portableWorker && !File.Exists(ResearchWorkerAssemblyPath))
            throw new FileNotFoundException("Portable research worker mode requires the framework-dependent evaluator DLL.", ResearchWorkerAssemblyPath);
        if (!File.Exists(executable)) throw new FileNotFoundException("Worker executable missing", executable);
        var outputDirectory = Path.GetDirectoryName(output)!;
        Directory.CreateDirectory(outputDirectory);
        using var manifestDocument = JsonDocument.Parse(await File.ReadAllTextAsync(manifestPath).ConfigureAwait(false));
        var clips = ReadManifest(manifestDocument.RootElement, Path.GetDirectoryName(manifestPath)!);
        var trials = new List<Trial>();
        var failures = new List<string>();
        using var models = new ModelResolver(modelDirectory, cacheDirectory: Path.Combine(outputDirectory, "verification"));
        var speechLauncher = new ExecutableLauncher(executable, Path.Combine(outputDirectory, "worker-profile"), portableWorker);
        await using var speech = new SpeechWorkerClient(speechLauncher, models,
            new WorkerOptions { PrepareWhileActive = ModelResolver.UsesAcceleratedModel });
        speech.SetIdleTimeout(Timeout.InfiniteTimeSpan);
        var cleanupLauncher = new EvaluationCleanupLauncher();
        var cleanupOptions = cleanupManifestPath is null ? null : LlamaCleanupOptions.LoadManifest(cleanupManifestPath);
        // A ready-state replay keeps the worker resident across recording durations.
        // Report this evaluation-only policy explicitly; it is not an app idle-policy result.
        await using var cleanup = cleanupOptions is null ? null : new LlamaTranscriptPostProcessor(
            cleanupOptions with { IdleTimeout = TimeSpan.FromHours(1) }, cleanupLauncher);
        using var totalMonitorStop = new CancellationTokenSource();
        var totalPeak = new MemoryPeak();
        var totalMonitor = MonitorAsync(speech, speechLauncher, cleanupLauncher, totalPeak, totalMonitorStop.Token);
        var started = Stopwatch.GetTimestamp();
        if (!await speech.LoadAsync(CancellationToken.None).ConfigureAwait(false)) throw new IOException("Model verification failed.");
        var initialLoadMilliseconds = Stopwatch.GetElapsedTime(started).TotalMilliseconds;
        var initialCleanupWarmupMilliseconds = 0d;
        if (cleanup is not null && !skipCleanupWarmup)
        {
            var warmupAt = Stopwatch.GetTimestamp();
            await cleanup.ProcessAsync("This is a cleanup warmup.", CancellationToken.None).ConfigureAwait(false);
            initialCleanupWarmupMilliseconds = Stopwatch.GetElapsedTime(warmupAt).TotalMilliseconds;
        }
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
                    var observedCleanup = cleanup is null ? null : new ObservedCleanup(cleanup,
                        () => speech.WorkerId, () => cleanupLauncher.WorkerId);
                    var key = new ScriptedKey();
                    var capture = new ReplayCapture(samples, realtime);
                    var injector = new CountingInjector();
                    var completed = new TaskCompletionSource<DictationResult>(TaskCreationOptions.RunContinuationsAsynchronously);
                    await using var engine = new DictationEngine(capture, key, observed, injector, () => [],
                        options: new DictationOptions { MaxSegmentSeconds = ModelResolver.PreferredMaxSegmentSeconds },
                        transcriptPostProcessor: observedCleanup);
                    engine.Completed += (_, result) => completed.TrySetResult(result);
                    using var monitorStop = new CancellationTokenSource();
                    var peak = new MemoryPeak();
                    var monitor = MonitorAsync(speech, speechLauncher, cleanupLauncher, peak, monitorStop.Token);
                    var allocatedBefore = GC.GetTotalAllocatedBytes();
                    var gen0Before = GC.CollectionCount(0); var gen1Before = GC.CollectionCount(1); var gen2Before = GC.CollectionCount(2);
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
                        rms < 0.00001, raw.Length == 0, includeText ? clip.Reference : null, includeText ? raw : null, includeText ? final : null)
                    {
                        CleanupOutcome = result?.CleanupOutcome.ToString(), CleanupMilliseconds = result?.CleanupTime.TotalMilliseconds,
                        NormalizedOriginalText = includeText ? result?.OriginalText : null,
                        ProviderInput = includeText ? observedCleanup?.Input : null, ProviderOutput = includeText ? observedCleanup?.Output : null,
                        DeliveryCalls = injector.Count,
                        SpeechCpuDuringCleanupMilliseconds = observedCleanup?.SpeechCpuMilliseconds,
                        CleanupWorkerCpuDuringCleanupMilliseconds = observedCleanup?.CleanupWorkerCpuMilliseconds,
                        HostCpuDuringCleanupMilliseconds = observedCleanup?.HostCpuMilliseconds,
                        ProviderFailureCode = observedCleanup?.FailureCode,
                        HostAllocatedBytesDuringTrial = GC.GetTotalAllocatedBytes() - allocatedBefore,
                        HostManagedHeapBytesAfterTrial = GC.GetTotalMemory(forceFullCollection: false),
                        HostGcCommittedBytesAtLastCollection = GC.GetGCMemoryInfo().TotalCommittedBytes,
                        HostGen0CollectionsDuringTrial = GC.CollectionCount(0) - gen0Before,
                        HostGen1CollectionsDuringTrial = GC.CollectionCount(1) - gen1Before,
                        HostGen2CollectionsDuringTrial = GC.CollectionCount(2) - gen2Before,
                    });
                }
            }
        }
        await totalMonitorStop.CancelAsync().ConfigureAwait(false);
        await totalMonitor.ConfigureAwait(false);
        // The trial monitor may catch a short peak between global samples. Merge
        // complete observed snapshots after both monitors stop, never independent
        // component maxima or observations concurrently with a sampler update.
        foreach (var trial in trials) totalPeak.IncludeObserved(trial.Memory);
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
            "Memory includes simultaneous evaluator, ASR worker and optional cleanup worker sums, excludes desktop UI. Working sets can double-count shared pages. Linux private commit is undefined and omitted. Injector counts calls and does not type. Cold ASR mode measures loading separately before recording. Cleanup uses an evaluation-only one-hour idle timeout; initial synthetic warmup is separate unless skipped. No Windows, microphone, physical hotkey, visible-delivery or whole-app SLA claim.",
            initialLoadMilliseconds, totalPeak.Snapshot(), summaries, trials.ToArray(), failures.ToArray())
        {
            CleanupManifest = cleanupManifestPath,
            CleanupManifestSha256 = cleanupManifestPath is null ? null : Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(cleanupManifestPath).ConfigureAwait(false))),
            InitialCleanupWarmupMilliseconds = cleanup is null || skipCleanupWarmup ? null : initialCleanupWarmupMilliseconds,
            CleanupWarmupSkipped = cleanup is null ? null : skipCleanupWarmup,
            CleanupIdleTimeoutOverrideSeconds = cleanup is null ? null : 3600,
            SpeechWorkerMode = portableWorker ? "portable-linux-research-worker; APP argument is reference-only" : "application-worker",
            SpeechWorkerAssembly = portableWorker ? ResearchWorkerAssemblyPath : null,
            SpeechWorkerAssemblySha256 = portableWorker ? Convert.ToHexString(SHA256.HashData(await File.ReadAllBytesAsync(ResearchWorkerAssemblyPath).ConfigureAwait(false))) : null,
            MemoryObserverProfile = OperatingSystem.IsLinux()
                ? "100Hz cached /proc/PID/statm handles with worker-generation identity; low-allocation resident counters; CPU reads only around cleanup"
                : "200Hz System.Diagnostics.Process working set and private commit",
        };
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
    private static async Task MonitorAsync(SpeechWorkerClient speech, ExecutableLauncher speechLauncher,
        EvaluationCleanupLauncher cleanup, MemoryPeak peak, CancellationToken token)
    {
        var linux = OperatingSystem.IsLinux();
        using var hostResident = linux ? new LinuxResidentReader() : null;
        using var speechResident = linux ? new LinuxResidentReader() : null;
        using var cleanupResident = linux ? new LinuxResidentReader() : null;
        while (!token.IsCancellationRequested)
        {
            if (linux)
            {
                peak.Observe(hostResident!.Read(Environment.ProcessId, 1),
                    speechResident!.Read(speech.WorkerId, speechLauncher.Generation),
                    cleanupResident!.Read(cleanup.WorkerId, cleanup.Generation), 0);
            }
            else
            {
                using var host = Process.GetCurrentProcess();
                var commit = OperatingSystem.IsWindows() ? host.PrivateMemorySize64 : 0;
                var speechMemory = ProcessMetrics.ReadMemory(speech.WorkerId);
                var cleanupMemory = ProcessMetrics.ReadMemory(cleanup.WorkerId);
                commit += speechMemory.Commit + cleanupMemory.Commit;
                peak.Observe(host.WorkingSet64, speechMemory.Working, cleanupMemory.Working, commit);
            }
            await Task.Delay(linux ? 10 : 5, CancellationToken.None).ConfigureAwait(false);
        }
    }
}

internal sealed record Clip(string Id, string AudioPath, string Reference);
internal sealed record WordScore(int ReferenceWords, int Substitutions, int Deletions, int Insertions)
{
    public double? WordErrorRate => ReferenceWords == 0 ? null : (Substitutions + Deletions + Insertions) / (double)ReferenceWords;
}
internal sealed record MemoryBreakdown(long HostWorkingSetBytes, long SpeechWorkingSetBytes, long CleanupWorkingSetBytes);
internal sealed record MemorySample(long PeakSummedWorkingSetBytes, long? PeakSummedPrivateCommitBytes)
{
    public long PeakHostWorkingSetBytes { get; init; }
    public long PeakSpeechWorkingSetBytes { get; init; }
    public long PeakCleanupWorkingSetBytes { get; init; }
    public MemoryBreakdown? AtSummedWorkingSetPeak { get; init; }
}
internal sealed record Trial(string Id, int Repeat, float Gain, double? RmsDbfs, double AudioSeconds, WordScore Raw, WordScore Formatted, double? TranscriptMilliseconds, double? CountingInjectorCompleteMilliseconds, double SeparateColdLoadMilliseconds, MemorySample Memory, double CaptureMilliseconds, double? CaptureDriftMilliseconds, bool BelowEngineSilenceThreshold, bool RawOutputEmpty, string? Reference, string? RawText, string? FinalText)
{
    public string? CleanupOutcome { get; init; }
    public double? CleanupMilliseconds { get; init; }
    public string? NormalizedOriginalText { get; init; }
    public string? ProviderInput { get; init; }
    public string? ProviderOutput { get; init; }
    public int DeliveryCalls { get; init; }
    public double? SpeechCpuDuringCleanupMilliseconds { get; init; }
    public double? CleanupWorkerCpuDuringCleanupMilliseconds { get; init; }
    public double? HostCpuDuringCleanupMilliseconds { get; init; }
    public string? ProviderFailureCode { get; init; }
    public long HostAllocatedBytesDuringTrial { get; init; }
    public long HostManagedHeapBytesAfterTrial { get; init; }
    public long HostGcCommittedBytesAtLastCollection { get; init; }
    public int HostGen0CollectionsDuringTrial { get; init; }
    public int HostGen1CollectionsDuringTrial { get; init; }
    public int HostGen2CollectionsDuringTrial { get; init; }
}
internal sealed record Summary(float Gain, int Trials, WordScore Raw, WordScore Formatted, double? TranscriptP50Milliseconds, double? TranscriptP95Milliseconds);
internal sealed record Report(DateTimeOffset At, string Executable, string ExecutableSha256, Dictionary<string, string> RuntimeSha256, string Manifest, string ManifestSha256, string ReplayMode, bool ColdLoadsBeforeRecording, string Limitations, double InitialLoadMilliseconds, MemorySample Memory, Summary[] Summaries, Trial[] Trials, string[] Failures)
{
    public string? CleanupManifest { get; init; }
    public string? CleanupManifestSha256 { get; init; }
    public double? InitialCleanupWarmupMilliseconds { get; init; }
    public bool? CleanupWarmupSkipped { get; init; }
    public int? CleanupIdleTimeoutOverrideSeconds { get; init; }
    public string? SpeechWorkerMode { get; init; }
    public string? SpeechWorkerAssembly { get; init; }
    public string? SpeechWorkerAssemblySha256 { get; init; }
    public string? MemoryObserverProfile { get; init; }
}
[JsonSerializable(typeof(Report))]
[JsonSourceGenerationOptions(WriteIndented = true, DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull)]
internal sealed partial class EvaluationJsonContext : JsonSerializerContext;

internal sealed class MemoryPeak
{
    private long _working, _commit;
    private long _hostPeak, _speechPeak, _cleanupPeak;
    private MemoryBreakdown? _atPeak;
    internal void Observe(long host, long speech, long cleanup, long commit)
    {
        var working = host + speech + cleanup;
        if (working > _working) { _working = working; _atPeak = new(host, speech, cleanup); }
        _commit = Math.Max(_commit, commit);
        _hostPeak = Math.Max(_hostPeak, host); _speechPeak = Math.Max(_speechPeak, speech); _cleanupPeak = Math.Max(_cleanupPeak, cleanup);
    }
    internal void IncludeObserved(MemorySample observed)
    {
        if (observed.PeakSummedWorkingSetBytes > _working)
        {
            _working = observed.PeakSummedWorkingSetBytes;
            _atPeak = observed.AtSummedWorkingSetPeak;
        }
        _commit = Math.Max(_commit, observed.PeakSummedPrivateCommitBytes ?? 0);
        _hostPeak = Math.Max(_hostPeak, observed.PeakHostWorkingSetBytes);
        _speechPeak = Math.Max(_speechPeak, observed.PeakSpeechWorkingSetBytes);
        _cleanupPeak = Math.Max(_cleanupPeak, observed.PeakCleanupWorkingSetBytes);
    }
    internal MemorySample Snapshot() => new(_working, OperatingSystem.IsWindows() ? _commit : null)
    {
        PeakHostWorkingSetBytes = _hostPeak, PeakSpeechWorkingSetBytes = _speechPeak,
        PeakCleanupWorkingSetBytes = _cleanupPeak, AtSummedWorkingSetPeak = _atPeak,
    };
}

internal sealed class ObservedCleanup(ITranscriptPostProcessor inner, Func<int?> speechId, Func<int?> cleanupId) : ITranscriptPostProcessor
{
    internal string? Input { get; private set; }
    internal string? Output { get; private set; }
    internal double? SpeechCpuMilliseconds { get; private set; }
    internal double? CleanupWorkerCpuMilliseconds { get; private set; }
    internal double? HostCpuMilliseconds { get; private set; }
    internal string? FailureCode { get; private set; }
    public async ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)
    {
        Input = text;
        var speech = speechId(); var cleanup = cleanupId();
        var speechBefore = ProcessMetrics.ReadCpuTicks(speech);
        var cleanupBefore = ProcessMetrics.ReadCpuTicks(cleanup);
        var hostBefore = ProcessMetrics.ReadCpuTicks(Environment.ProcessId);
        try { return Output = await inner.ProcessAsync(text, cancellationToken).ConfigureAwait(false); }
        catch (Exception error)
        {
            FailureCode = error.Message switch
            {
                "Cleanup did not produce a complete response." => "IncompleteNativeResponse",
                "The complete transcript and output do not fit the configured cleanup context." => "InputBudgetExceeded",
                "Cleanup returned empty text or model control output." => "EmptyOrControlOutput",
                "Cleanup did not return text." => "MissingNativeContent",
                _ => error.GetType().Name,
            };
            throw;
        }
        finally
        {
            SpeechCpuMilliseconds = ProcessMetrics.CpuDelta(speechBefore, ProcessMetrics.ReadCpuTicks(speech));
            CleanupWorkerCpuMilliseconds = ProcessMetrics.CpuDelta(cleanupBefore, ProcessMetrics.ReadCpuTicks(cleanup));
            HostCpuMilliseconds = ProcessMetrics.CpuDelta(hostBefore, ProcessMetrics.ReadCpuTicks(Environment.ProcessId));
        }
    }
    public ValueTask DisposeAsync() => ValueTask.CompletedTask;
}

internal static class ProcessMetrics
{
    internal static (long Working, long Commit) ReadMemory(int? id)
    {
        if (id is null) return (0, 0);
        try
        {
            using var process = Process.GetProcessById(id.Value);
            return (process.WorkingSet64, OperatingSystem.IsWindows() ? process.PrivateMemorySize64 : 0);
        }
        catch (ArgumentException) { return (0, 0); }
        catch (InvalidOperationException) { return (0, 0); }
        catch (System.ComponentModel.Win32Exception) { return (0, 0); }
    }
    internal static long? ReadCpuTicks(int? id)
    {
        if (id is null) return null;
        try { using var process = Process.GetProcessById(id.Value); return process.TotalProcessorTime.Ticks; }
        catch (ArgumentException) { return null; }
        catch (InvalidOperationException) { return null; }
        catch (System.ComponentModel.Win32Exception) { return null; }
    }
    internal static double? CpuDelta(long? before, long? after) => before is null || after is null || after < before
        ? null : TimeSpan.FromTicks(after.Value - before.Value).TotalMilliseconds;
}

// Each descriptor remains bound to one procfs process instance. A launcher generation
// invalidates it even if the OS reuses a numeric PID between sampling iterations.
internal sealed class LinuxResidentReader : IDisposable
{
    private SafeFileHandle? _handle;
    private int? _pid;
    private int _generation;
    internal long Read(int? pid, int generation)
    {
        if (_pid != pid || _generation != generation)
        {
            _handle?.Dispose(); _handle = null;
            _pid = pid; _generation = generation;
        }
        if (pid is null or <= 0) return 0;
        try
        {
            _handle ??= File.OpenHandle("/proc/" + pid.Value.ToString(CultureInfo.InvariantCulture) + "/statm",
                FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            Span<byte> buffer = stackalloc byte[256];
            var length = RandomAccess.Read(_handle, buffer, 0);
            var contents = buffer[..length];
            var at = 0;
            while (at < contents.Length && contents[at] is not (32 or 9 or 10)) at++;
            while (at < contents.Length && contents[at] is 32 or 9 or 10) at++;
            if (!Utf8Parser.TryParse(contents[at..], out long pages, out var consumed) || consumed == 0 || pages < 0) return 0;
            return checked(pages * Environment.SystemPageSize);
        }
        catch (IOException) { _handle?.Dispose(); _handle = null; return 0; }
        catch (UnauthorizedAccessException) { _handle?.Dispose(); _handle = null; return 0; }
        catch (OverflowException) { return 0; }
    }
    public void Dispose() { _handle?.Dispose(); _handle = null; }
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

internal sealed class ExecutableLauncher(string executable, string dataDirectory, bool portableWorker) : IWorkerLauncher
{
    private int _generation;
    internal int Generation => Volatile.Read(ref _generation);
    public IWorkerProcess Launch(string pipeName, string secret)
    {
        using var parent = Process.GetCurrentProcess();
        var startExecutable = portableWorker ? Environment.ProcessPath ?? throw new IOException("Research evaluator host path is unavailable.") : executable;
        var start = new ProcessStartInfo(startExecutable) { UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden };
        if (portableWorker && Path.GetFileNameWithoutExtension(startExecutable).Equals("dotnet", StringComparison.OrdinalIgnoreCase))
            start.ArgumentList.Add(Program.ResearchWorkerAssemblyPath);
        start.Environment["FREEHAND_DATA_DIRECTORY"] = dataDirectory;
        foreach (var argument in new[] { portableWorker ? "--portable-speech-worker" : "--speech-worker", pipeName, secret, Environment.ProcessId.ToString(CultureInfo.InvariantCulture), parent.StartTime.ToUniversalTime().Ticks.ToString(CultureInfo.InvariantCulture) }) start.ArgumentList.Add(argument);
        var process = Process.Start(start) ?? throw new IOException("Worker did not start.");
        Interlocked.Increment(ref _generation);
        return new EvaluationWorker(process);
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

// This portable research launcher never arms the Windows capture or injection boundary.
internal sealed class EvaluationCleanupLauncher : ICleanupWorkerLauncher
{
    private int _workerId;
    private int _generation;
    internal int? WorkerId => Volatile.Read(ref _workerId) is var id && id != 0 ? id : null;
    internal int Generation => Volatile.Read(ref _generation);
    public IWorkerProcess Launch(CleanupWorkerStartInfo startInfo)
    {
        var start = new ProcessStartInfo(startInfo.ExecutablePath)
        {
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardOutput = true, RedirectStandardError = true,
            WorkingDirectory = Path.GetDirectoryName(startInfo.ExecutablePath)!,
        };
        foreach (var argument in startInfo.Arguments) start.ArgumentList.Add(argument);
        foreach (var pair in startInfo.EnvironmentVariables) start.Environment[pair.Key] = pair.Value;
        var process = Process.Start(start) ?? throw new IOException("Cleanup worker did not start.");
        Interlocked.Increment(ref _generation);
        Volatile.Write(ref _workerId, process.Id);
        return new EvaluationCleanupWorker(process, this);
    }

    private sealed class EvaluationCleanupWorker : IWorkerProcess
    {
        private readonly Process _process;
        private readonly EvaluationCleanupLauncher _owner;
        private readonly Task _stdout, _stderr;
        private int _disposed;
        internal EvaluationCleanupWorker(Process process, EvaluationCleanupLauncher owner)
        {
            _process = process; _owner = owner;
            _stdout = process.StandardOutput.BaseStream.CopyToAsync(Stream.Null);
            _stderr = process.StandardError.BaseStream.CopyToAsync(Stream.Null);
        }
        public int Id => _process.Id;
        public bool HasExited => _process.HasExited;
        public Task WaitForExitAsync(CancellationToken cancellationToken) => _process.WaitForExitAsync(cancellationToken);
        public void Terminate()
        {
            try { if (!_process.HasExited) _process.Kill(entireProcessTree: true); }
            catch (InvalidOperationException) when (_process.HasExited) { }
        }
        public async ValueTask DisposeAsync()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0) return;
            try
            {
                Terminate();
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
                await _process.WaitForExitAsync(deadline.Token).ConfigureAwait(false);
                await Task.WhenAll(_stdout, _stderr).WaitAsync(deadline.Token).ConfigureAwait(false);
            }
            finally
            {
                Interlocked.CompareExchange(ref _owner._workerId, 0, _process.Id);
                _process.Dispose();
            }
        }
    }
}

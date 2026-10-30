using System.Diagnostics;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Freehand.Abstractions;
using Freehand.Core;
using Freehand.Dictionary;
using Freehand.Testing;

namespace Freehand.Cleanup.Probe;

internal static class Program
{
    private const string Limitations = "Text-fixture probe through the real DictationEngine, dictionary, number normalizer, optional cleanup provider and delivery orchestration. "
        + "A generated tone and canned transcriber feed the selected transcript; RecordingTextInjector counts calls without typing. "
        + "This does not test recognition accuracy, a microphone, a physical hotkey, foreground application insertion, Windows worker ownership or whole-desktop performance. "
        + "Candidate text precedes Core validation; output is the accepted result or original-text fallback. Automatic checks do not establish semantic fidelity.";

    private static async Task<int> Main(string[] args)
    {
        try
        {
            if (args is ["--selftest"]) return await SelfTestAsync().ConfigureAwait(false);
            var options = ParseArguments(args);
            using var cancelled = new CancellationTokenSource();
            void Cancel(object? sender, ConsoleCancelEventArgs eventArgs) { eventArgs.Cancel = true; cancelled.Cancel(); }
            Console.CancelKeyPress += Cancel;
            try { return await RunAsync(options, cancelled.Token).ConfigureAwait(false); }
            finally { Console.CancelKeyPress -= Cancel; }
        }
        catch (Exception exception) when (exception is ArgumentException or IOException or JsonException or InvalidDataException or UnauthorizedAccessException)
        {
            Console.Error.WriteLine(exception.GetType().Name + ": " + exception.Message);
            Console.Error.WriteLine("Usage: Freehand.Cleanup.Probe --input corpus.json --output results.json [--manifest cleanup-manifest.json] [--split development|heldout|all] [--cleanup-timeout-seconds 120]");
            return 2;
        }
    }

    private static Arguments ParseArguments(string[] args)
    {
        string? input = null, output = null, manifest = null;
        var split = "all";
        var timeoutSeconds = 120;
        for (var index = 0; index < args.Length; index++)
        {
            if (index + 1 >= args.Length) throw new ArgumentException("Each option needs a value.");
            var value = args[++index];
            switch (args[index - 1])
            {
                case "--input": input = Path.GetFullPath(value); break;
                case "--output": output = Path.GetFullPath(value); break;
                case "--manifest": manifest = Path.GetFullPath(value); break;
                case "--split": split = value; break;
                case "--cleanup-timeout-seconds":
                    if (!int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out timeoutSeconds))
                        throw new ArgumentException("Cleanup timeout must be an integer.");
                    break;
                default: throw new ArgumentException("Unknown probe option: " + args[index - 1]);
            }
        }
        if (input is null || output is null) throw new ArgumentException("--input and --output are required.");
        if (split is not ("all" or "development" or "heldout")) throw new ArgumentException("Unsupported split.");
        if (timeoutSeconds is < 1 or > 1800) throw new ArgumentException("Cleanup timeout must be 1-1800 seconds.");
        if (input == output || manifest == output) throw new ArgumentException("Output must not overwrite input or the model manifest.");
        return new Arguments(input, output, manifest, split, TimeSpan.FromSeconds(timeoutSeconds));
    }

    private static async Task<int> RunAsync(Arguments arguments, CancellationToken cancellationToken)
    {
        var inputBytes = await File.ReadAllBytesAsync(arguments.Input, cancellationToken).ConfigureAwait(false);
        using var document = JsonDocument.Parse(inputBytes, new JsonDocumentOptions { MaxDepth = 32 });
        var cases = ReadCases(document.RootElement, arguments.Split);
        var cleanupOptions = arguments.Manifest is null ? null : LlamaCleanupOptions.LoadManifest(arguments.Manifest);
        var metadata = new ProbeMetadata(
            DateTimeOffset.UtcNow, arguments.Input, Convert.ToHexString(SHA256.HashData(inputBytes)),
            arguments.Manifest, arguments.Manifest is null ? null : await HashFileAsync(arguments.Manifest, cancellationToken).ConfigureAwait(false),
            cleanupOptions?.ModelId, cleanupOptions?.PromptStyle.ToString(),
            cleanupOptions is null ? null : new Artifact(cleanupOptions.RuntimePath, cleanupOptions.RuntimeSha256, null),
            cleanupOptions is null ? null : new Artifact(cleanupOptions.ModelPath, cleanupOptions.ModelSha256, null),
            cleanupOptions?.Threads, cleanupOptions?.ContextSize, cleanupOptions?.MaxOutputTokens, cleanupOptions?.GpuLayers,
            arguments.CleanupTimeout.TotalSeconds, arguments.Split,
            RuntimeInformation.OSDescription, RuntimeInformation.ProcessArchitecture.ToString(),
            RuntimeInformation.FrameworkDescription, Environment.ProcessorCount, GC.GetGCMemoryInfo().TotalAvailableMemoryBytes,
            typeof(Program).Assembly.GetName().Version?.ToString(),
            await ManagedHashesAsync(cancellationToken).ConfigureAwait(false), Limitations);
        var results = new List<ProbeCaseResult>();
        var report = new ProbeReport(1, metadata, true, results);
        await WriteReportAsync(arguments.Output, report).ConfigureAwait(false);
        var interrupted = false;
        await using (var processor = cleanupOptions is null ? null : new LlamaTranscriptPostProcessor(cleanupOptions, new ProbeCleanupWorkerLauncher()))
        {
            foreach (var fixture in cases)
            {
                if (cancellationToken.IsCancellationRequested) { interrupted = true; break; }
                try
                {
                    var references = await NormalizeReferencesAsync(fixture, cancellationToken).ConfigureAwait(false);
                    var result = await RunCaseAsync(fixture, processor, arguments.CleanupTimeout, cancellationToken).ConfigureAwait(false);
                    result = result with { NormalizedTargets = references.Targets, NormalizedChecks = references.Checks };
                    results.Add(result);
                    await WriteReportAsync(arguments.Output, report).ConfigureAwait(false);
                    Console.WriteLine(fixture.Id + ": " + result.CleanupStatus + ", insertions="
                        + result.InsertionCount.ToString(CultureInfo.InvariantCulture));
                }
                catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { interrupted = true; break; }
            }
        }
        if (cleanupOptions is not null)
        {
            // Hash after trials so independent report verification does not warm
            // model pages before the provider's first measured startup.
            metadata = metadata with
            {
                Runtime = new Artifact(cleanupOptions.RuntimePath, cleanupOptions.RuntimeSha256,
                    await HashFileAsync(cleanupOptions.RuntimePath, CancellationToken.None).ConfigureAwait(false)),
                Model = new Artifact(cleanupOptions.ModelPath, cleanupOptions.ModelSha256,
                    await HashFileAsync(cleanupOptions.ModelPath, CancellationToken.None).ConfigureAwait(false)),
            };
        }
        await WriteReportAsync(arguments.Output, report with { Metadata = metadata, Incomplete = interrupted }).ConfigureAwait(false);
        Console.WriteLine("Report: " + arguments.Output);
        if (interrupted) return 130;
        return results.All(result => result.Error is null && result.InsertionCount == 1
            && result.CleanupStatus is not ("Rejected" or "Failed" or "TimedOut")) ? 0 : 1;
    }

    private static List<Fixture> ReadCases(JsonElement root, string split)
    {
        if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("cases", out var cases) || cases.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException("Corpus must contain a cases array.");
        var result = new List<Fixture>();
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in cases.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Each case must be an object.");
            var id = RequiredString(item, "id");
            if (!ids.Add(id)) throw new InvalidDataException("Duplicate case id: " + id);
            var input = RequiredString(item, "input", allowEmpty: true);
            var caseSplit = OptionalString(item, "split") ?? "development";
            var dictionary = new List<DictionaryEntry>();
            if (item.TryGetProperty("dictionary", out var entries))
            {
                if (entries.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Case dictionary must be an array.");
                foreach (var entry in entries.EnumerateArray())
                {
                    if (entry.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Each dictionary entry must be an object.");
                    var kindText = OptionalString(entry, "kind") ?? "Correction";
                    if (!Enum.TryParse<EntryKind>(kindText, ignoreCase: true, out var kind) || !Enum.IsDefined(kind))
                        throw new InvalidDataException("Dictionary kind must be Term or Correction.");
                    var enabled = true;
                    if (entry.TryGetProperty("is_enabled", out var enabledValue))
                    {
                        if (enabledValue.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                            throw new InvalidDataException("Dictionary is_enabled must be a Boolean.");
                        enabled = enabledValue.GetBoolean();
                    }
                    dictionary.Add(new DictionaryEntry
                    {
                        Kind = kind, Hear = OptionalString(entry, "hear") ?? string.Empty,
                        Write = RequiredString(entry, "write", allowEmpty: true), IsEnabled = enabled,
                    });
                }
            }
            var targets = ReadStrings(item, "targets");
            FixtureChecks? checks = null;
            if (item.TryGetProperty("checks", out var checksElement))
            {
                if (checksElement.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Case checks must be an object.");
                checks = new FixtureChecks(ReadStrings(checksElement, "include"), ReadStrings(checksElement, "exclude"),
                    ReadStrings(checksElement, "literals"), ReadStringGroups(checksElement, "any_of"), ReadStringGroups(checksElement, "ordered"));
            }
            if (split == "all" || split == caseSplit) result.Add(new Fixture(id, input, caseSplit, dictionary, targets, checks));
        }
        if (result.Count == 0) throw new InvalidDataException("No cases match the requested split.");
        return result;
    }

    private static string RequiredString(JsonElement element, string name, bool allowEmpty = false)
    {
        var value = OptionalString(element, name);
        if (value is null || (!allowEmpty && string.IsNullOrWhiteSpace(value)))
            throw new InvalidDataException("Missing corpus string: " + name);
        return value;
    }

    private static string? OptionalString(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var value)) return null;
        if (value.ValueKind != JsonValueKind.String) throw new InvalidDataException("Corpus field must be a string: " + name);
        return value.GetString();
    }

    private static string[] ReadStrings(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var values)) return [];
        if (values.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Corpus field must be an array: " + name);
        return values.EnumerateArray().Select(value => value.ValueKind == JsonValueKind.String
            ? value.GetString()! : throw new InvalidDataException("Corpus array needs strings: " + name)).ToArray();
    }

    private static IReadOnlyList<string>[] ReadStringGroups(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out var groups)) return [];
        if (groups.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Corpus field must be an array: " + name);
        return groups.EnumerateArray().Select(group =>
        {
            if (group.ValueKind != JsonValueKind.Array) throw new InvalidDataException("Corpus check needs string groups: " + name);
            return (IReadOnlyList<string>)group.EnumerateArray().Select(value => value.ValueKind == JsonValueKind.String
                ? value.GetString()! : throw new InvalidDataException("Corpus check needs strings: " + name)).ToArray();
        }).ToArray();
    }

    private static async Task<ReferenceNormalization> NormalizeReferencesAsync(Fixture fixture, CancellationToken cancellationToken)
    {
        var cache = new Dictionary<string, string>(StringComparer.Ordinal);
        async Task<string> NormalizeAsync(string text)
        {
            if (cache.TryGetValue(text, out var cached)) return cached;
            if (string.IsNullOrWhiteSpace(text)) return text;
            var reference = new Fixture(fixture.Id + "/reference", text, fixture.Split, fixture.Dictionary);
            var result = await RunCaseAsync(reference, null, TimeSpan.FromSeconds(5), cancellationToken).ConfigureAwait(false);
            if (result.Error is not null || result.Output is null || result.InsertionCount != 1)
                throw new InvalidDataException("Reference normalization failed for case: " + fixture.Id);
            cache.Add(text, result.Output);
            return result.Output;
        }
        async Task<IReadOnlyList<string>> NormalizeStringsAsync(IReadOnlyList<string> texts)
        {
            var normalized = new List<string>(texts.Count);
            foreach (var text in texts) normalized.Add(await NormalizeAsync(text).ConfigureAwait(false));
            return normalized;
        }
        async Task<IReadOnlyList<IReadOnlyList<string>>> NormalizeGroupsAsync(IReadOnlyList<IReadOnlyList<string>> groups)
        {
            var normalized = new List<IReadOnlyList<string>>(groups.Count);
            foreach (var group in groups) normalized.Add(await NormalizeStringsAsync(group).ConfigureAwait(false));
            return normalized;
        }
        var targets = await NormalizeStringsAsync(fixture.Targets ?? []).ConfigureAwait(false);
        var checks = fixture.Checks;
        var normalizedChecks = checks is null ? null : new FixtureChecks(
            await NormalizeStringsAsync(checks.Include).ConfigureAwait(false),
            await NormalizeStringsAsync(checks.Exclude).ConfigureAwait(false), checks.Literals,
            await NormalizeGroupsAsync(checks.AnyOf).ConfigureAwait(false),
            await NormalizeGroupsAsync(checks.Ordered).ConfigureAwait(false));
        return new ReferenceNormalization(targets, normalizedChecks);
    }

    private static async Task<ProbeCaseResult> RunCaseAsync(Fixture fixture, ITranscriptPostProcessor? processor,
        TimeSpan cleanupTimeout, CancellationToken cancellationToken)
    {
        var key = new FakeHotkeySource();
        var capture = FakeAudioCapture.Tone(0.1);
        var injector = new RecordingTextInjector();
        var observer = processor is null ? null : new ObservedProcessor(processor);
        var completed = new TaskCompletionSource<DictationResult>(TaskCreationOptions.RunContinuationsAsynchronously);
        var captured = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var started = Stopwatch.GetTimestamp();
        await using var engine = new DictationEngine(capture, key, new FakeTranscriber(fixture.Input), injector,
            () => fixture.Dictionary, transcriptPostProcessor: observer, cleanupTimeout: cleanupTimeout);
        engine.Completed += (_, result) => completed.TrySetResult(result);
        engine.Changed += (_, _) => { if (engine.Level > 0) captured.TrySetResult(); };
        if (!engine.Start()) throw new InvalidOperationException("The fake hotkey could not start.");
        key.Press();
        await captured.Task.WaitAsync(TimeSpan.FromSeconds(5), cancellationToken).ConfigureAwait(false);
        while (capture.IsCapturing) await Task.Delay(1, cancellationToken).ConfigureAwait(false);
        key.Release();
        var (result, error) = await WaitForCompletionAsync(engine, completed.Task,
            cleanupTimeout + TimeSpan.FromSeconds(10), cancellationToken).ConfigureAwait(false);
        if (result?.CleanupOutcome == TranscriptCleanupOutcome.Rejected) error = "CoreRejectedOutput";
        else if (result?.CleanupOutcome == TranscriptCleanupOutcome.TimedOut) error = "CleanupDeadline";
        else if (result?.CleanupOutcome == TranscriptCleanupOutcome.Failed) error = observer?.Error ?? "CleanupFailed";
        return new ProbeCaseResult(fixture.Id, fixture.Split, fixture.Input,
            result?.OriginalText ?? result?.Text, result?.Text, observer?.Output, observer?.Input,
            result?.CleanupOutcome.ToString() ?? "NoResult", result?.CleanupTime.TotalMilliseconds,
            result?.ProcessingTime.TotalMilliseconds, Stopwatch.GetElapsedTime(started).TotalMilliseconds,
            injector.Injected.Count, injector.Injected.Count, result?.Delivery.ToString(),
            engine.Feedback?.Outcome.ToString(), error, result?.Corrections.Count ?? 0);
    }

    private static async Task<(DictationResult? Result, string? Error)> WaitForCompletionAsync(
        DictationEngine engine, Task<DictationResult> completed, TimeSpan timeout, CancellationToken cancellationToken)
    {
        var started = Stopwatch.GetTimestamp();
        while (!completed.IsCompleted)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (engine.State == DictationState.AwaitingRetry
                || (engine.State == DictationState.Idle && engine.Feedback is not null))
                return (null, engine.Feedback?.Outcome.ToString() ?? "NoCompletedResult");
            if (Stopwatch.GetElapsedTime(started) >= timeout) return (null, "CompletionDeadline");
            await Task.Delay(10, cancellationToken).ConfigureAwait(false);
        }
        return (await completed.ConfigureAwait(false), null);
    }

    private static async Task<string> HashFileAsync(string path, CancellationToken cancellationToken)
    {
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 65536,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        return Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken).ConfigureAwait(false));
    }

    private static async Task<Dictionary<string, string>> ManagedHashesAsync(CancellationToken cancellationToken)
    {
        var hashes = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var name in new[] { "Freehand.Cleanup.Probe.dll", "Freehand.Core.dll", "Freehand.Cleanup.dll",
            "Freehand.Dictionary.dll", "Freehand.Testing.dll", "Freehand.Abstractions.dll" })
        {
            var path = Path.Combine(AppContext.BaseDirectory, name);
            if (File.Exists(path)) hashes.Add(name, await HashFileAsync(path, cancellationToken).ConfigureAwait(false));
        }
        return hashes;
    }

    private static async Task WriteReportAsync(string path, ProbeReport report)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(report, ProbeJsonContext.Default.ProbeReport)).ConfigureAwait(false);
            File.Move(temporary, path, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private static async Task<int> SelfTestAsync()
    {
        var fixtures = new[]
        {
            new Fixture("dictionary-number", "send fifty dollars to acme", "development", [DictionaryEntry.Correction("acme", "ACME")]),
            new Fixture("literal-path", "the path is src/one/two.cs", "development", []),
            new Fixture("literal-whitespace", "replace phrase", "development", [DictionaryEntry.Correction("phrase", "\n Exact  ")]),
        };
        string[] expected = ["send $50 to ACME", "the path is src/one/two.cs", "replace \n Exact  "];
        for (var index = 0; index < fixtures.Length; index++)
        {
            var result = await RunCaseAsync(fixtures[index], null, TimeSpan.FromSeconds(5), CancellationToken.None).ConfigureAwait(false);
            if (result.Error is not null || result.Output != expected[index] || result.NormalizedInput != expected[index]
                || result.InsertionCount != 1 || result.CleanupStatus != "Disabled")
                throw new InvalidDataException("Managed pipeline self-test failed: " + fixtures[index].Id);
        }
        Console.WriteLine("Managed pipeline self-test passed: dictionary correction, number formatting, path and literal whitespace preservation, single recorded insertion.");
        return 0;
    }

    private sealed class ObservedProcessor(ITranscriptPostProcessor inner) : ITranscriptPostProcessor
    {
        internal string? Input { get; private set; }
        internal string? Output { get; private set; }
        internal string? Error { get; private set; }

        public async ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)
        {
            Input = text;
            try { Output = await inner.ProcessAsync(text, cancellationToken).ConfigureAwait(false); return Output; }
            catch (Exception exception) { Error = "Processor:" + exception.GetType().Name; throw; }
        }

        // Each engine owns its observer; the outer probe owns the shared provider.
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    private sealed record Arguments(string Input, string Output, string? Manifest, string Split, TimeSpan CleanupTimeout);
    private sealed record Fixture(string Id, string Input, string Split, IReadOnlyList<DictionaryEntry> Dictionary,
        IReadOnlyList<string>? Targets = null, FixtureChecks? Checks = null);
    private sealed record ReferenceNormalization(IReadOnlyList<string> Targets, FixtureChecks? Checks);
}

internal sealed record Artifact(string Path, string ExpectedSha256, string? ActualSha256);
internal sealed record ProbeMetadata(DateTimeOffset StartedAtUtc, string CorpusPath, string CorpusSha256,
    string? ManifestPath, string? ManifestSha256, string? ModelId, string? PromptStyle,
    Artifact? Runtime, Artifact? Model, int? Threads, int? ContextSize, int? MaxOutputTokens, int? GpuLayers,
    double CleanupTimeoutSeconds, string Split, string OperatingSystem, string Architecture,
    string Framework, int LogicalProcessorCount, long GcTotalAvailableMemoryBytes, string? ProbeVersion,
    IReadOnlyDictionary<string, string> ManagedAssemblySha256, string Limitations);
internal sealed record ProbeCaseResult(string Id, string Split, string Input, string? NormalizedInput,
    string? Output, string? CandidateText, string? CleanupInput, string CleanupStatus,
    double? CleanupTimeMs, double? ProcessingTimeMs, double ElapsedMs, int InsertionCount, int DeliveredCount,
    string? DeliveryOutcome, string? DictationOutcome, string? Error, int AppliedCorrectionCount)
{
    public IReadOnlyList<string> NormalizedTargets { get; init; } = [];
    public FixtureChecks? NormalizedChecks { get; init; }
}
internal sealed record FixtureChecks(IReadOnlyList<string> Include, IReadOnlyList<string> Exclude,
    IReadOnlyList<string> Literals, IReadOnlyList<IReadOnlyList<string>> AnyOf, IReadOnlyList<IReadOnlyList<string>> Ordered);
internal sealed record ProbeReport(int SchemaVersion, ProbeMetadata Metadata, bool Incomplete, IReadOnlyList<ProbeCaseResult> Cases);

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower, WriteIndented = true)]
[JsonSerializable(typeof(ProbeReport))]
internal sealed partial class ProbeJsonContext : JsonSerializerContext;

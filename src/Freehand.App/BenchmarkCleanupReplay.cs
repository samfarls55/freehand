using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Freehand.Cleanup;
using Freehand.Abstractions;

namespace Freehand.App;

// Benchmark-only instrumentation. The platform launcher retains process-tree
// ownership; these independent handles identify the exact processes for sampling.
internal sealed class BenchmarkCleanupWorkerLauncher(ICleanupWorkerLauncher inner) : ICleanupWorkerLauncher, IDisposable
{
    private readonly object _sync = new();
    private readonly List<(Process Process, int Id, DateTime StartedUtc)> _workers = [];

    public IWorkerProcess Launch(CleanupWorkerStartInfo startInfo)
    {
        var worker = inner.Launch(startInfo);
        try
        {
            var process = Process.GetProcessById(worker.Id);
            _ = process.Handle;
            lock (_sync) _workers.Add((process, worker.Id, process.StartTime.ToUniversalTime()));
            return worker;
        }
        catch
        {
            worker.Terminate();
            worker.DisposeAsync().AsTask().GetAwaiter().GetResult();
            throw;
        }
    }

    internal IReadOnlyList<BenchmarkWorkerIdentity> Snapshot()
    {
        lock (_sync) return _workers.Select(worker =>
            new BenchmarkWorkerIdentity(worker.Id, worker.StartedUtc, worker.Process.HasExited) { Role = "cleanup" }).ToArray();
    }

    internal IReadOnlyList<int> LiveWorkerIds()
    {
        lock (_sync) return _workers.Where(worker => !worker.Process.HasExited).Select(worker => worker.Id).ToArray();
    }

    public void Dispose()
    {
        lock (_sync)
        {
            foreach (var worker in _workers) worker.Process.Dispose();
            _workers.Clear();
        }
    }
}

internal sealed record ConfiguredCleanupSnapshot(long Epoch, string? Selection, string DirectoryPath,
    LlamaCleanupOptions? Options, string? ManifestSha256, string? OptionsFingerprint, bool Available);

internal static class BenchmarkCleanupIdentity
{
    internal static byte[] OptionsBytes(LlamaCleanupOptions options) =>
        JsonSerializer.SerializeToUtf8Bytes(options, BenchmarkCleanupJsonContext.Default.LlamaCleanupOptions);
    internal static string Fingerprint(LlamaCleanupOptions options) => Convert.ToHexString(SHA256.HashData(OptionsBytes(options)));
    internal static byte[] ReadManifest(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
        if (stream.Length > 2 * 1024 * 1024) throw new InvalidDataException("Cleanup qualification manifest is too large.");
        using var bytes = new MemoryStream();
        var buffer = new byte[8192];
        int read;
        while ((read = stream.Read(buffer)) != 0)
        {
            if (bytes.Length + read > 2 * 1024 * 1024) throw new InvalidDataException("Cleanup qualification manifest is too large.");
            bytes.Write(buffer, 0, read);
        }
        return bytes.ToArray();
    }
}

internal sealed class BenchmarkCleanupReplayContext
{
    private readonly string? _selection;
    private readonly string _directory, _manifestPath, _manifestSha256, _fingerprint;
    private long _expectedEpoch;
    private string? _identityFailure;
    internal ConfiguredTranscriptPostProcessor Processor { get; }
    internal Func<bool> Enabled { get; }
    internal BenchmarkCleanupWorkerLauncher Workers { get; }
    internal TimeSpan IdleTimeout { get; }
    internal LlamaCleanupOptions Options { get; }
    internal long InitialEpoch { get; }
    internal string ManifestPath => _manifestPath;
    internal string ManifestSha256 => _manifestSha256;
    internal string OptionsFingerprint => _fingerprint;

    internal BenchmarkCleanupReplayContext(ConfiguredTranscriptPostProcessor processor, Func<bool> enabled,
        BenchmarkCleanupWorkerLauncher workers)
    {
        Processor = processor; Enabled = enabled; Workers = workers;
        var actual = processor.BenchmarkSnapshot();
        Options = actual.Options ?? throw new InvalidDataException("Cleanup has no cached configuration.");
        IdleTimeout = Options.IdleTimeout;
        _selection = actual.Selection; _directory = actual.DirectoryPath;
        _expectedEpoch = InitialEpoch = actual.Epoch;
        _manifestPath = Path.Combine(_directory, "cleanup-manifest.json");
        var bytes = BenchmarkCleanupIdentity.ReadManifest(_manifestPath);
        var parsed = LlamaCleanupOptions.LoadManifest(_manifestPath, bytes);
        _manifestSha256 = Convert.ToHexString(SHA256.HashData(bytes));
        _fingerprint = BenchmarkCleanupIdentity.Fingerprint(parsed);
        ValidateConfiguration();
    }

    internal void ValidateCachedIdentity()
    {
        if (_identityFailure is not null) throw new InvalidDataException(_identityFailure);
        var actual = Processor.BenchmarkSnapshot();
        if (!Enabled() || !actual.Available || actual.Epoch != _expectedEpoch
            || !string.Equals(actual.Selection, _selection, StringComparison.Ordinal)
            || !string.Equals(actual.DirectoryPath, _directory, StringComparison.Ordinal)
            || !string.Equals(actual.ManifestSha256, _manifestSha256, StringComparison.Ordinal)
            || !string.Equals(actual.OptionsFingerprint, _fingerprint, StringComparison.Ordinal))
            FailIdentity("The actual configured cleanup selection or epoch changed during qualification.");
    }

    internal void ValidateConfiguration()
    {
        ValidateCachedIdentity();
        var current = Convert.ToHexString(SHA256.HashData(BenchmarkCleanupIdentity.ReadManifest(_manifestPath)));
        if (!string.Equals(current, _manifestSha256, StringComparison.Ordinal))
            FailIdentity("The cleanup manifest changed during qualification.");
        ValidateCachedIdentity();
    }

    internal async ValueTask ResetAsync()
    {
        ValidateConfiguration();
        var before = _expectedEpoch;
        await Processor.ConfigureAsync(_selection, enabled: true, reload: true).ConfigureAwait(false);
        var actual = Processor.BenchmarkSnapshot();
        if (actual.Epoch != before + 1) FailIdentity("An unexpected cleanup configuration transition occurred during benchmark reset.");
        _expectedEpoch = actual.Epoch;
        ValidateConfiguration();
    }

    internal async ValueTask StopAsync()
    {
        Exception? identityError = null;
        try { ValidateConfiguration(); }
        catch (Exception error) when (error is IOException or InvalidDataException or UnauthorizedAccessException) { identityError = error; }
        // Always release the actual current worker, even if source identity drifted.
        var current = Processor.BenchmarkSnapshot();
        await Processor.ConfigureAsync(current.Selection, enabled: false).ConfigureAwait(false);
        if (identityError is not null) System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(identityError).Throw();
        var after = Processor.BenchmarkSnapshot();
        if (after.Epoch != _expectedEpoch + 1) FailIdentity("An unexpected cleanup transition occurred during teardown.");
        _expectedEpoch = after.Epoch;
        ValidateConfiguration();
    }

    private void FailIdentity(string message)
    {
        _identityFailure ??= message;
        throw new InvalidDataException(_identityFailure);
    }
}

// DictationEngine owns and disposes its processor argument. Replay therefore
// borrows the application's configured processor through this non-owning wrapper.
internal sealed class BenchmarkCleanupProcessor(ITranscriptPostProcessor inner, BenchmarkCleanupReplayContext? context = null) : ITranscriptPostProcessor
{
    private long _calls;
    internal long Calls => Interlocked.Read(ref _calls);
    internal string? LastInput { get; private set; }
    internal string? LastCandidate { get; private set; }

    public async ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)
    {
        LastInput = text;
        LastCandidate = null;
        context?.ValidateCachedIdentity();
        Interlocked.Increment(ref _calls);
        var result = await inner.ProcessAsync(text, cancellationToken).ConfigureAwait(false);
        context?.ValidateCachedIdentity();
        return LastCandidate = result;
    }

    public ValueTask DisposeAsync() => ValueTask.CompletedTask;
}

internal sealed record BenchmarkCleanupTrial(string Phase, int RecordingSeconds, string Outcome, double CleanupMilliseconds,
    long ProviderCalls, string? ProviderInput, string? ProviderCandidate, string SelectedText, string? NormalizedOriginal);
internal sealed record BenchmarkCleanupWarmup(string Phase, double Milliseconds, long ProviderCalls);
internal sealed record BenchmarkCleanupConfiguration(string ModelId, string ManifestPath, string ManifestSha256,
    string ModelSha256, string RuntimeSha256, string PromptStyle, int Threads, int ContextSize, int MaxOutputTokens,
    int BatchSize, int MicroBatchSize, bool MaskSpecialistLiterals, bool Repack, double IdleTimeoutMilliseconds,
    long ConfigurationEpoch = 0, string? OptionsFingerprint = null, JsonElement? ActualOptions = null);

internal sealed record BenchmarkLatencySummary(int Count, double? P50Milliseconds, double? P95Milliseconds, double? MaximumMilliseconds)
{
    internal static BenchmarkLatencySummary From(IReadOnlyList<double> values)
    {
        if (values.Count == 0) return new(0, null, null, null);
        var ordered = values.Order().ToArray();
        return new(ordered.Length, ordered[(ordered.Length - 1) / 2],
            ordered[Math.Max(0, (int)Math.Ceiling(ordered.Length * .95) - 1)], ordered[^1]);
    }
}

internal sealed record BenchmarkApplicationIdentity(string ProcessPath, string ProcessSha256,
    string ManagedModuleVersionId, string? ManagedAssemblySha256)
{
    internal static async Task<BenchmarkApplicationIdentity> CaptureAsync()
    {
        var path = Environment.ProcessPath ?? throw new IOException("The benchmark process identity is unavailable.");
        static async Task<string> HashAsync(string file)
        {
            await using var stream = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read, 65536,
                FileOptions.Asynchronous | FileOptions.SequentialScan);
            return Convert.ToHexString(await SHA256.HashDataAsync(stream).ConfigureAwait(false));
        }
        var assembly = Path.Combine(AppContext.BaseDirectory, "Freehand.App.dll");
        return new(path, await HashAsync(path).ConfigureAwait(false), typeof(Composition).Module.ModuleVersionId.ToString("D"),
            File.Exists(assembly) ? await HashAsync(assembly).ConfigureAwait(false) : null);
    }
}

[JsonSerializable(typeof(LlamaCleanupOptions))]
internal sealed partial class BenchmarkCleanupJsonContext : JsonSerializerContext;

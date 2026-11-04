using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;

namespace Freehand.Cleanup;

/// <summary>Progress of an explicit cleanup-model installation; no transcript data is involved.</summary>
/// <param name="Stage">A user-facing description of the current operation.</param>
/// <param name="BytesReceived">Total verified/downloaded bytes received during this operation.</param>
/// <param name="TotalBytes">Pinned total byte size of the required downloads.</param>
public sealed record CleanupAssetProgress(string Stage, long BytesReceived, long TotalBytes);

/// <summary>A complete, pinned local bundle ready to select in the application.</summary>
/// <param name="DirectoryPath">Absolute immutable bundle directory.</param>
/// <param name="ManifestPath">Absolute prepared cleanup-manifest.json path.</param>
/// <param name="ModelId">The selected model identifier.</param>
public sealed record CleanupAssetInstallation(string DirectoryPath, string ManifestPath, string ModelId);

/// <summary>Verified acquisition metadata, without downloading or selecting a model.</summary>
/// <param name="ModelId">The model available for explicit installation.</param>
/// <param name="ModelBytes">Pinned model file size.</param>
/// <param name="DownloadBytes">Pinned combined download size, including the runtime and notices.</param>
public sealed record CleanupAssetMetadata(string ModelId, long ModelBytes, long DownloadBytes);

/// <summary>Acquires pinned cleanup assets only when explicitly requested by the user.</summary>
/// <remarks>
/// The caller owns the HTTP client and selects a dedicated profile directory. Downloads
/// are staged, authenticated before extraction, and promoted by one directory rename.
/// Existing model directories are retained, including when repair or cancellation fails.
/// This service never runs during dictation and never downloads transcript content.
/// </remarks>
public sealed class CleanupAssetInstaller
{
    private const long MaximumLicenseBytes = 2 * 1024 * 1024;
    private const long MaximumExtractedBytes = 1024L * 1024 * 1024;
    private static readonly string[] RuntimeNoticePrefixes = ["LICENSE", "LICENCE", "NOTICE", "COPYING", "THIRD"];
    private readonly HttpClient _http;
    private readonly string _root;
    private readonly object _sync = new();
    private bool _installing;

    /// <summary>Creates an installer with a caller-owned transport and dedicated model-cache root.</summary>
    public CleanupAssetInstaller(HttpClient httpClient, string rootDirectory)
    {
        ArgumentNullException.ThrowIfNull(httpClient);
        ArgumentException.ThrowIfNullOrWhiteSpace(rootDirectory);
        _http = httpClient;
        _root = Path.GetFullPath(rootDirectory);
        if (Path.TrimEndingDirectorySeparator(_root) == Path.GetPathRoot(_root))
            throw new ArgumentException("Cleanup installation requires a dedicated directory.", nameof(rootDirectory));
    }

    /// <summary>Validates packaged acquisition metadata without network access or filesystem writes.</summary>
    public static CleanupAssetMetadata ValidateAcquisitionMetadata(string modelManifestPath, string runtimeManifestPath)
    {
        CheckManifestLength(modelManifestPath);
        CheckManifestLength(runtimeManifestPath);
        var plan = ReadPlan(File.ReadAllBytes(modelManifestPath), File.ReadAllBytes(runtimeManifestPath));
        return new(plan.ModelId, plan.Model.Size, plan.TotalBytes);
    }

    /// <summary>Installs the pinned Windows CPU or Vulkan model/runtime selected by the packaged acquisition manifests.</summary>
    public async Task<CleanupAssetInstallation> InstallAsync(string modelManifestPath, string runtimeManifestPath,
        IProgress<CleanupAssetProgress>? progress = null, CancellationToken cancellationToken = default)
    {
        lock (_sync)
        {
            if (_installing) throw new InvalidOperationException("A cleanup installation is already running.");
            _installing = true;
        }
        string? stage = null;
        try
        {
            var modelBytes = await ReadManifestAsync(modelManifestPath, cancellationToken).ConfigureAwait(false);
            var runtimeBytes = await ReadManifestAsync(runtimeManifestPath, cancellationToken).ConfigureAwait(false);
            var plan = ReadPlan(modelBytes, runtimeBytes);
            var version = Convert.ToHexString(SHA256.HashData(modelBytes.Concat(runtimeBytes).ToArray())).ToLowerInvariant();
            Directory.CreateDirectory(_root);
            RejectLink(_root);
            var destination = Path.Combine(_root, version);
            progress?.Report(new("Verifying cleanup assets", 0, plan.TotalBytes));
            var completed = Directory.EnumerateDirectories(_root, version + "-*")
                .Where(path => Path.GetFileName(path).Length == version.Length + 33
                    && Guid.TryParseExact(Path.GetFileName(path).AsSpan(version.Length + 1), "N", out _))
                .Order(StringComparer.Ordinal).Prepend(destination);
            foreach (var candidate in completed)
                if (Directory.Exists(candidate) && await IsCompleteAsync(candidate, plan, cancellationToken).ConfigureAwait(false))
                    return Installed(candidate, plan, progress);

            stage = Path.Combine(_root, ".cleanup-install-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(stage);
            Directory.CreateDirectory(Path.Combine(stage, "licenses", "model"));
            var downloads = new List<(Artifact Artifact, string Path, string Label)>
            {
                (plan.Model, "model.gguf", "Downloading cleanup model"),
                (plan.ModelLicense, "licenses/model-LICENSE.txt", "Downloading model license"),
                (plan.RuntimeLicense, "licenses/runtime-LICENSE.txt", "Downloading runtime license"),
                (plan.Archive, "runtime.zip", "Downloading cleanup runtime"),
            };
            downloads.AddRange(plan.Notices.Select(notice => (notice, "licenses/model/" + notice.Name, "Downloading model notices")));
            long received = 0;
            foreach (var download in downloads)
            {
                await DownloadAsync(download.Artifact, Path.Combine(stage, download.Path), download.Label,
                    received, plan.TotalBytes, progress, cancellationToken).ConfigureAwait(false);
                received += download.Artifact.Size;
            }

            progress?.Report(new("Preparing cleanup runtime", received, plan.TotalBytes));
            await PrepareRuntimeAsync(stage, plan, cancellationToken).ConfigureAwait(false);
            File.Delete(Path.Combine(stage, "runtime.zip"));
            await WriteBundleManifestAsync(stage, plan, cancellationToken).ConfigureAwait(false);
            cancellationToken.ThrowIfCancellationRequested();
            // A second installer may have finished, or the previous version may need
            // repair. Keep either directory intact and publish a fresh complete version.
            if (Directory.Exists(destination)) destination += "-" + Guid.NewGuid().ToString("N");
            Directory.Move(stage, destination);
            stage = null;
            return Installed(destination, plan, progress);
        }
        finally
        {
            if (stage is not null)
            {
                try { Directory.Delete(stage, recursive: true); }
                catch (Exception error) when (error is IOException or UnauthorizedAccessException) { /* A later explicit retry uses a new owned staging directory. */ }
            }
            lock (_sync) _installing = false;
        }
    }

    private static CleanupAssetInstallation Installed(string directory, Plan plan, IProgress<CleanupAssetProgress>? progress)
    {
        progress?.Report(new("Cleanup model installed", plan.TotalBytes, plan.TotalBytes));
        return new(directory, Path.Combine(directory, "cleanup-manifest.json"), plan.ModelId);
    }

    private static async Task<byte[]> ReadManifestAsync(string path, CancellationToken token)
    {
        CheckManifestLength(path);
        return await File.ReadAllBytesAsync(path, token).ConfigureAwait(false);
    }

    private static void CheckManifestLength(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        if (new FileInfo(path).Length > 1024 * 1024) throw new InvalidDataException("Cleanup acquisition manifest is too large.");
    }

    private async Task DownloadAsync(Artifact artifact, string path, string label, long previous, long total,
        IProgress<CleanupAssetProgress>? progress, CancellationToken token)
    {
        progress?.Report(new(label, previous, total));
        using var request = new HttpRequestMessage(HttpMethod.Get, artifact.Source);
        using var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token).ConfigureAwait(false);
        if (!response.IsSuccessStatusCode) throw new HttpRequestException("A cleanup artifact download failed.", null, response.StatusCode);
        if (response.RequestMessage?.RequestUri?.Scheme is { } scheme && scheme != Uri.UriSchemeHttps)
            throw new InvalidDataException("Cleanup downloads require HTTPS.");
        if (response.Content.Headers.ContentLength is { } length && length != artifact.Size)
            throw new InvalidDataException("A cleanup artifact does not match its pinned size.");
        await using var input = await response.Content.ReadAsStreamAsync(token).ConfigureAwait(false);
        await using var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None,
            131072, FileOptions.Asynchronous | FileOptions.SequentialScan);
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        var buffer = new byte[131072];
        long received = 0;
        while (true)
        {
            var count = await input.ReadAsync(buffer, token).ConfigureAwait(false);
            if (count == 0) break;
            received += count;
            if (received > artifact.Size) throw new InvalidDataException("A cleanup download exceeds its pinned size.");
            hash.AppendData(buffer, 0, count);
            await output.WriteAsync(buffer.AsMemory(0, count), token).ConfigureAwait(false);
            progress?.Report(new(label, previous + received, total));
        }
        if (received != artifact.Size || !Convert.ToHexString(hash.GetHashAndReset()).Equals(artifact.Sha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("A cleanup download does not match its pinned SHA-256 or size.");
    }

    private static async Task PrepareRuntimeAsync(string stage, Plan plan, CancellationToken token)
    {
        var extracted = Path.Combine(stage, ".runtime-extract");
        Directory.CreateDirectory(extracted);
        using (var archive = ZipFile.OpenRead(Path.Combine(stage, "runtime.zip")))
        {
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            long expanded = 0;
            if (archive.Entries.Count > 4096) throw new InvalidDataException("The cleanup runtime archive has too many entries.");
            foreach (var entry in archive.Entries)
            {
                token.ThrowIfCancellationRequested();
                var relative = SafeArchivePath(entry.FullName);
                if (!names.Add(relative.TrimEnd('/'))) throw new InvalidDataException("The cleanup runtime archive contains duplicate paths.");
                var type = (entry.ExternalAttributes >> 16) & 0xF000;
                if (type is not (0 or 0x4000 or 0x8000) || (entry.ExternalAttributes & (int)FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException("The cleanup runtime archive contains a link or unsupported file type.");
                expanded = checked(expanded + entry.Length);
                if (expanded > MaximumExtractedBytes) throw new InvalidDataException("The cleanup runtime archive is too large after extraction.");
                var path = Path.Combine(extracted, relative.TrimEnd('/'));
                if (relative.EndsWith('/')) { Directory.CreateDirectory(path); continue; }
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                await using var source = entry.Open();
                await using var target = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                    131072, FileOptions.Asynchronous | FileOptions.SequentialScan);
                var buffer = new byte[131072];
                long copied = 0;
                while (true)
                {
                    var count = await source.ReadAsync(buffer, token).ConfigureAwait(false);
                    if (count == 0) break;
                    copied += count;
                    if (copied > entry.Length) throw new InvalidDataException("A cleanup runtime archive entry exceeds its declared size.");
                    await target.WriteAsync(buffer.AsMemory(0, count), token).ConfigureAwait(false);
                }
                if (copied != entry.Length) throw new InvalidDataException("A cleanup runtime archive entry is incomplete.");
            }
        }
        var servers = Directory.GetFiles(extracted, "llama-server.exe", SearchOption.AllDirectories);
        if (servers.Length != 1 || !await MatchesAsync(servers[0], plan.ExecutableSha256, null, token).ConfigureAwait(false))
            throw new InvalidDataException("The cleanup runtime executable does not match its pinned SHA-256.");
        var runtime = Path.Combine(stage, "runtime");
        Directory.CreateDirectory(runtime);
        Directory.CreateDirectory(Path.Combine(stage, "licenses", "runtime"));
        var sourceDirectory = Path.GetDirectoryName(servers[0])!;
        foreach (var file in Directory.EnumerateFiles(sourceDirectory))
        {
            token.ThrowIfCancellationRequested();
            var name = Path.GetFileName(file);
            if (name.Equals("llama-server.exe", StringComparison.OrdinalIgnoreCase) || name.EndsWith(".dll", StringComparison.OrdinalIgnoreCase))
                File.Move(file, Path.Combine(runtime, name));
            else if (IsRuntimeNotice(name)) File.Move(file, Path.Combine(stage, "licenses", "runtime", name));
        }
        Directory.Delete(extracted, recursive: true);
    }

    private static string SafeArchivePath(string value)
    {
        var path = value.Replace('\\', '/');
        var parts = path.TrimEnd('/').Split('/');
        if (parts.Any(part => part.Length == 0 || part is "." or ".." || part.EndsWith('.') || part.EndsWith(' ')
            || part.Any(character => char.IsControl(character) || "<>:\"|?*".Contains(character))
            || IsReservedName(part))) throw new InvalidDataException("The cleanup runtime archive contains an unsafe path.");
        return path;
    }

    private static bool IsReservedName(string name)
    {
        var stem = name.Split('.')[0];
        return stem.Equals("CON", StringComparison.OrdinalIgnoreCase) || stem.Equals("PRN", StringComparison.OrdinalIgnoreCase)
            || stem.Equals("AUX", StringComparison.OrdinalIgnoreCase) || stem.Equals("NUL", StringComparison.OrdinalIgnoreCase)
            || stem.Length == 4 && (stem.StartsWith("COM", StringComparison.OrdinalIgnoreCase) || stem.StartsWith("LPT", StringComparison.OrdinalIgnoreCase))
                && stem[3] is >= '1' and <= '9';
    }

    private static bool IsRuntimeNotice(string name) => RuntimeNoticePrefixes
        .Any(prefix => name.StartsWith(prefix, StringComparison.OrdinalIgnoreCase));

    private static async Task WriteBundleManifestAsync(string directory, Plan plan, CancellationToken token)
    {
        var files = new List<(string Path, long Size, string Hash)>();
        foreach (var file in Directory.GetFiles(directory, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal))
        {
            token.ThrowIfCancellationRequested();
            await using var input = new FileStream(file, FileMode.Open, FileAccess.Read, FileShare.Read,
                131072, FileOptions.Asynchronous | FileOptions.SequentialScan);
            files.Add((Path.GetRelativePath(directory, file).Replace('\\', '/'), input.Length,
                Convert.ToHexString(await SHA256.HashDataAsync(input, token).ConfigureAwait(false)).ToLowerInvariant()));
        }
        using var output = new MemoryStream();
        using (var writer = new Utf8JsonWriter(output, new JsonWriterOptions { Indented = true }))
        {
            writer.WriteStartObject();
            writer.WriteNumber("schemaVersion", 1);
            writer.WriteString("platform", plan.RuntimePlatform);
            writer.WriteString("runtimePath", "runtime/llama-server.exe");
            writer.WriteString("runtimeSha256", plan.ExecutableSha256);
            writer.WriteString("modelPath", "model.gguf");
            writer.WriteString("modelSha256", plan.Model.Sha256);
            writer.WriteString("modelId", plan.ModelId);
            writer.WriteString("promptStyle", plan.PromptStyle);
            writer.WriteString("modelSourceUrl", plan.Model.Source.AbsoluteUri);
            writer.WriteString("modelRevision", plan.ModelRevision);
            writer.WriteString("runtimeSourceUrl", plan.Archive.Source.AbsoluteUri);
            writer.WriteString("runtimeRevision", plan.RuntimeRevision);
            foreach (var setting in plan.Inference) writer.WriteNumber(char.ToLowerInvariant(setting.Key[0]) + setting.Key[1..], setting.Value);
            writer.WriteBoolean("maskSpecialistLiterals", plan.MaskSpecialistLiterals);
            writer.WriteBoolean("repack", plan.Repack);
            writer.WriteString("cacheTypeK", plan.CacheTypeK);
            writer.WriteString("cacheTypeV", plan.CacheTypeV);
            writer.WriteStartArray("files");
            foreach (var file in files)
            {
                writer.WriteStartObject(); writer.WriteString("path", file.Path);
                writer.WriteNumber("size", file.Size); writer.WriteString("sha256", file.Hash); writer.WriteEndObject();
            }
            writer.WriteEndArray(); writer.WriteEndObject();
        }
        await File.WriteAllBytesAsync(Path.Combine(directory, "cleanup-manifest.json"), output.ToArray(), token).ConfigureAwait(false);
    }

    private static async Task<bool> IsCompleteAsync(string directory, Plan plan, CancellationToken token)
    {
        try
        {
            RejectLink(directory);
            foreach (var child in Directory.EnumerateDirectories(directory, "*", SearchOption.AllDirectories)) RejectLink(child);
            var options = LlamaCleanupOptions.LoadManifest(Path.Combine(directory, "cleanup-manifest.json"));
            using var manifest = JsonDocument.Parse(await File.ReadAllBytesAsync(Path.Combine(directory, "cleanup-manifest.json"), token).ConfigureAwait(false));
            var platform = manifest.RootElement.TryGetProperty("platform", out var configuredPlatform)
                ? configuredPlatform.ValueKind == JsonValueKind.String ? configuredPlatform.GetString() : null : "win-x64-cpu";
            if (platform != plan.RuntimePlatform) return false;
            if (options.ModelId != plan.ModelId || options.ModelSha256 != plan.Model.Sha256 || options.RuntimeSha256 != plan.ExecutableSha256
                || options.AdapterPath is not null
                || options.PromptStyle.ToString() != plan.PromptStyle
                || options.Threads != plan.Inference["Threads"] || options.ContextSize != plan.Inference["ContextSize"]
                || options.MaxOutputTokens != plan.Inference["MaxOutputTokens"] || options.GpuLayers != plan.Inference["GpuLayers"]
                || options.BatchSize != plan.Inference["BatchSize"] || options.MicroBatchSize != plan.Inference["MicroBatchSize"]
                || options.PromptCacheMiB != plan.Inference["PromptCacheMiB"] || options.ContextCheckpoints != plan.Inference["ContextCheckpoints"]
                || options.PromptLookupTokens != plan.Inference["PromptLookupTokens"] || options.PromptLookupMatchTokens != plan.Inference["PromptLookupMatchTokens"]
                || options.MaskSpecialistLiterals != plan.MaskSpecialistLiterals || options.Repack != plan.Repack
                || options.CacheTypeK != plan.CacheTypeK || options.CacheTypeV != plan.CacheTypeV
                || options.StartupTimeout != TimeSpan.FromSeconds(plan.Inference["StartupTimeoutSeconds"])
                || options.IdleTimeout != TimeSpan.FromSeconds(plan.Inference["IdleTimeoutSeconds"])
                || !options.ModelPath.Equals(Path.Combine(directory, "model.gguf"), StringComparison.OrdinalIgnoreCase)
                || !options.RuntimePath.Equals(Path.Combine(directory, "runtime", "llama-server.exe"), StringComparison.OrdinalIgnoreCase)) return false;
            var required = new List<(string Path, string Hash, long? Size)>
            {
                ("model.gguf", plan.Model.Sha256, plan.Model.Size),
                ("runtime/llama-server.exe", plan.ExecutableSha256, null),
                ("licenses/model-LICENSE.txt", plan.ModelLicense.Sha256, plan.ModelLicense.Size),
                ("licenses/runtime-LICENSE.txt", plan.RuntimeLicense.Sha256, plan.RuntimeLicense.Size),
            };
            required.AddRange(plan.Notices.Select(notice => ("licenses/model/" + notice.Name, notice.Sha256, (long?)notice.Size)));
            if (required.Any(expected => !options.Artifacts.Any(actual =>
                actual.Path.Equals(Path.GetFullPath(expected.Path, directory), StringComparison.OrdinalIgnoreCase)
                && actual.Sha256.Equals(expected.Hash, StringComparison.OrdinalIgnoreCase)
                && (expected.Size is null || actual.Size == expected.Size)))) return false;
            foreach (var artifact in options.Artifacts)
            {
                RejectLink(artifact.Path);
                if (!await MatchesAsync(artifact.Path, artifact.Sha256, artifact.Size, token).ConfigureAwait(false)) return false;
            }
            var owned = options.Artifacts.Select(file => file.Path).Append(Path.Combine(directory, "cleanup-manifest.json"))
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            return Directory.EnumerateFiles(directory, "*", SearchOption.AllDirectories).All(owned.Contains);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException or ArgumentException or InvalidOperationException)
        { return false; }
    }

    private static void RejectLink(string path)
    {
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            throw new InvalidDataException("Cleanup installation directories and assets must not be symbolic links.");
    }

    private static async Task<bool> MatchesAsync(string path, string hash, long? size, CancellationToken token)
    {
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
            131072, FileOptions.Asynchronous | FileOptions.SequentialScan);
        return (size is null || stream.Length == size) && Convert.ToHexString(await SHA256.HashDataAsync(stream, token).ConfigureAwait(false))
            .Equals(hash, StringComparison.OrdinalIgnoreCase);
    }

    private sealed record Artifact(Uri Source, string Sha256, long Size, string? Name = null);
    private sealed record Plan(string ModelId, string PromptStyle, string ModelRevision, string RuntimeRevision, string RuntimePlatform,
        Artifact Model, Artifact ModelLicense, Artifact RuntimeLicense, Artifact Archive, Artifact[] Notices,
        string ExecutableSha256, IReadOnlyDictionary<string, int> Inference,
        bool MaskSpecialistLiterals, bool Repack, string CacheTypeK, string CacheTypeV)
    {
        internal long TotalBytes => checked(Model.Size + ModelLicense.Size + RuntimeLicense.Size + Archive.Size + Notices.Sum(notice => notice.Size));
    }

    private static Plan ReadPlan(byte[] modelBytes, byte[] runtimeBytes)
    {
        using var model = JsonDocument.Parse(modelBytes, new JsonDocumentOptions { MaxDepth = 16 });
        using var runtime = JsonDocument.Parse(runtimeBytes, new JsonDocumentOptions { MaxDepth = 16 });
        var selected = model.RootElement;
        var native = runtime.RootElement;
        if (Number(selected, "SchemaVersion") != 1 || Number(native, "SchemaVersion") != 1)
            throw new InvalidDataException("Cleanup acquisition manifest version is unsupported.");
        var id = Text(selected, "ModelId");
        var style = Text(selected, "PromptStyle");
        if (id.Length > 256 || id.Any(char.IsControl) || !Enum.TryParse<CleanupPromptStyle>(style, out var parsed) || !Enum.IsDefined(parsed))
            throw new InvalidDataException("Cleanup acquisition model configuration is invalid.");
        var modelInfo = selected.GetProperty("Model");
        var revision = Text(modelInfo, "Revision");
        var runtimeRevision = Text(native, "SourceCommit");
        if (!IsHex(revision, 40) || !IsHex(runtimeRevision, 40)) throw new InvalidDataException("Cleanup sources require immutable revisions.");
        var weights = ReadArtifact(modelInfo);
        if (weights.Source.Host.Equals("huggingface.co", StringComparison.OrdinalIgnoreCase)
            && !weights.Source.AbsolutePath.Contains("/resolve/" + revision + "/", StringComparison.Ordinal))
            throw new InvalidDataException("Hugging Face cleanup downloads must resolve the pinned revision.");
        var runtimePlatform = selected.TryGetProperty("RuntimePlatform", out _) ? Text(selected, "RuntimePlatform") : "win-x64-cpu";
        if (runtimePlatform is not ("win-x64-cpu" or "win-x64-vulkan"))
            throw new InvalidDataException("Cleanup setup requires a supported pinned Windows runtime platform.");
        var artifacts = native.GetProperty("Artifacts").EnumerateArray()
            .Where(value => Text(value, "Platform") == runtimePlatform).ToArray();
        if (artifacts.Length != 1 || Text(artifacts[0], "Executable") != "llama-server.exe")
            throw new InvalidDataException("The Windows cleanup runtime must be pinned exactly once.");
        var executableHash = Text(artifacts[0], "ExecutableSha256");
        if (!IsHex(executableHash, 64)) throw new InvalidDataException("The cleanup runtime executable requires a SHA-256 pin.");
        var archive = ReadArtifact(artifacts[0], "ArchiveSha256", "ArchiveSize");
        if (archive.Size > 512L * 1024 * 1024) throw new InvalidDataException("The cleanup runtime download is too large.");
        var notices = selected.TryGetProperty("ModelNotices", out var entries)
            ? entries.EnumerateArray().Select(value => ReadArtifact(value) with { Name = Text(value, "Name") }).ToArray() : [];
        var noticeNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var notice in notices)
            if (notice.Name is null || notice.Name.Contains('/') || notice.Name.Contains('\\') || SafeArchivePath(notice.Name) != notice.Name
                || !(notice.Name.EndsWith(".txt", StringComparison.OrdinalIgnoreCase) || notice.Name.EndsWith(".md", StringComparison.OrdinalIgnoreCase))
                || !noticeNames.Add(notice.Name) || notice.Size > MaximumLicenseBytes)
                throw new InvalidDataException("Cleanup notice filenames or sizes are invalid.");
        var license = ReadArtifact(selected.GetProperty("ModelLicense"));
        var runtimeLicense = ReadArtifact(selected.GetProperty("RuntimeLicense"));
        if (license.Size > MaximumLicenseBytes || runtimeLicense.Size > MaximumLicenseBytes)
            throw new InvalidDataException("Cleanup licenses are too large.");
        var inference = selected.GetProperty("Inference");
        var settings = new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["Threads"] = Limit(inference, "Threads", 1, 256), ["ContextSize"] = Limit(inference, "ContextSize", 256, 1048576),
            ["MaxOutputTokens"] = Limit(inference, "MaxOutputTokens", 1, 1048575), ["GpuLayers"] = Limit(inference, "GpuLayers", 0, 1000),
            ["StartupTimeoutSeconds"] = Limit(inference, "StartupTimeoutSeconds", 1, 1800), ["IdleTimeoutSeconds"] = Limit(inference, "IdleTimeoutSeconds", 0, 86400),
            ["BatchSize"] = OptionalLimit(inference, "BatchSize", 1, 8192, 128),
            ["MicroBatchSize"] = OptionalLimit(inference, "MicroBatchSize", 1, 8192, 128),
            ["PromptCacheMiB"] = OptionalLimit(inference, "PromptCacheMiB", 0, 8192, 0),
            ["ContextCheckpoints"] = OptionalLimit(inference, "ContextCheckpoints", 0, 32, 0),
            ["PromptLookupTokens"] = OptionalLimit(inference, "PromptLookupTokens", 0, 64, 0),
            ["PromptLookupMatchTokens"] = OptionalLimit(inference, "PromptLookupMatchTokens", 1, 12, 3),
        };
        if (settings["MaxOutputTokens"] >= settings["ContextSize"]) throw new InvalidDataException("Cleanup output must fit inside its context budget.");
        if (settings["MicroBatchSize"] > settings["BatchSize"]) throw new InvalidDataException("Cleanup micro-batch must not exceed its logical batch.");
        if (settings["PromptLookupTokens"] >= settings["BatchSize"]) throw new InvalidDataException("Cleanup prompt lookup plus its sampled token must fit the logical batch.");
        return new(id, style, revision, runtimeRevision, runtimePlatform, weights, license, runtimeLicense, archive, notices, executableHash, settings,
            OptionalBoolean(inference, "MaskSpecialistLiterals", false), OptionalBoolean(inference, "Repack", true),
            CacheType(inference, "CacheTypeK"), CacheType(inference, "CacheTypeV"));
    }

    private static Artifact ReadArtifact(JsonElement value, string hashName = "Sha256", string sizeName = "Size")
    {
        if (!Uri.TryCreate(Text(value, "Source"), UriKind.Absolute, out var source) || source.Scheme != Uri.UriSchemeHttps
            || source.UserInfo.Length != 0 || source.Query.Length != 0 || source.Fragment.Length != 0)
            throw new InvalidDataException("Cleanup artifact sources must use HTTPS without credentials or query strings.");
        var hash = Text(value, hashName);
        var size = Number(value, sizeName);
        if (!IsHex(hash, 64) || size < 1) throw new InvalidDataException("Cleanup artifacts require exact sizes and SHA-256 pins.");
        return new(source, hash.ToLowerInvariant(), size);
    }

    private static string Text(JsonElement value, string name) => value.TryGetProperty(name, out var property)
        && property.ValueKind == JsonValueKind.String && !string.IsNullOrWhiteSpace(property.GetString())
            ? property.GetString()! : throw new InvalidDataException("A required cleanup manifest string is missing.");
    private static long Number(JsonElement value, string name) => value.TryGetProperty(name, out var property)
        && property.ValueKind == JsonValueKind.Number && property.TryGetInt64(out var result)
            ? result : throw new InvalidDataException("A required cleanup manifest integer is missing.");
    private static bool IsHex(string value, int length) => value.Length == length && value.All(char.IsAsciiHexDigit);
    private static int Limit(JsonElement value, string name, int minimum, int maximum)
    {
        var number = Number(value, name);
        return number >= minimum && number <= maximum ? (int)number : throw new InvalidDataException("A cleanup inference limit is invalid.");
    }
    private static int OptionalLimit(JsonElement value, string name, int minimum, int maximum, int fallback) =>
        value.TryGetProperty(name, out _) ? Limit(value, name, minimum, maximum) : fallback;
    private static bool OptionalBoolean(JsonElement value, string name, bool fallback)
    {
        if (!value.TryGetProperty(name, out var property)) return fallback;
        if (property.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new InvalidDataException("A cleanup inference boolean is invalid.");
        return property.GetBoolean();
    }
    private static string CacheType(JsonElement value, string name)
    {
        if (!value.TryGetProperty(name, out _)) return "f16";
        var type = Text(value, name);
        return type is "f16" or "q8_0" or "q4_0" ? type : throw new InvalidDataException("A cleanup cache type is invalid.");
    }
}

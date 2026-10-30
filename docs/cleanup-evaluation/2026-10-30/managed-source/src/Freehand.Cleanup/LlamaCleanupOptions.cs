using System.Text.Json;

namespace Freehand.Cleanup;

/// <summary>The input contract used by an explicitly selected cleanup model.</summary>
public enum CleanupPromptStyle
{
    /// <summary>Quill's prescribed raw ChatML prompt with an empty thinking block.</summary>
    QuillChatMl,
    /// <summary>Qwen3.5 instruction model using the model's embedded chat template.</summary>
    Qwen35,
    /// <summary>Ministral 3 instruction model using its embedded chat template.</summary>
    Ministral3,
    /// <summary>Gemma 4 instruction model using its embedded chat template.</summary>
    Gemma4,
}

/// <summary>A pinned runtime dependency, model or accompanying asset in the cleanup bundle.</summary>
/// <param name="Path">Absolute path resolved from a safe manifest-relative path.</param>
/// <param name="Sha256">SHA-256 of the complete file.</param>
/// <param name="Size">Optional exact file size, in bytes.</param>
public sealed record CleanupArtifactHash(string Path, string Sha256, long? Size = null);

/// <summary>Pinned local artifacts and bounded inference settings. Loading never downloads artifacts.</summary>
public sealed record LlamaCleanupOptions
{
    /// <summary>Absolute path to the local llama-server executable.</summary>
    public required string RuntimePath { get; init; }
    /// <summary>SHA-256 of the selected runtime executable.</summary>
    public required string RuntimeSha256 { get; init; }
    /// <summary>Absolute path to the selected GGUF model.</summary>
    public required string ModelPath { get; init; }
    /// <summary>SHA-256 of the selected GGUF model.</summary>
    public required string ModelSha256 { get; init; }
    /// <summary>The pinned model identifier, also used as the local server alias.</summary>
    public required string ModelId { get; init; }
    /// <summary>The selected model's trained input contract.</summary>
    public required CleanupPromptStyle PromptStyle { get; init; }
    /// <summary>Absolute manifest directory for a complete bundle inventory, when supplied.</summary>
    public string? BundleDirectory { get; init; }
    /// <summary>Optional complete inventory, including runtime dependencies, the model and accompanying assets.</summary>
    public IReadOnlyList<CleanupArtifactHash> Artifacts { get; init; } = [];
    /// <summary>CPU generation and prompt-processing thread count.</summary>
    public int Threads { get; init; } = 4;
    /// <summary>Total input and output token budget for one inference slot.</summary>
    public int ContextSize { get; init; } = 8192;
    /// <summary>Maximum complete response length; reaching the limit is rejected.</summary>
    public int MaxOutputTokens { get; init; } = 2048;
    /// <summary>Number of layers to offload to the configured local GPU; zero uses CPU.</summary>
    public int GpuLayers { get; init; }
    /// <summary>Maximum artifact verification and worker readiness duration.</summary>
    public TimeSpan StartupTimeout { get; init; } = TimeSpan.FromSeconds(60);
    /// <summary>Idle time before terminating the model worker and releasing its memory.</summary>
    public TimeSpan IdleTimeout { get; init; } = TimeSpan.FromSeconds(60);

    /// <summary>Reads an explicit manifest. Relative artifact paths are resolved beside that manifest.</summary>
    /// <remarks>Hashes are verified asynchronously on first use, rather than while loading settings.</remarks>
    public static LlamaCleanupOptions LoadManifest(string manifestPath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(manifestPath);
        var fullPath = Path.GetFullPath(manifestPath);
        if (!File.Exists(fullPath)) throw new FileNotFoundException("Cleanup manifest is missing.", fullPath);
        using var document = JsonDocument.Parse(File.ReadAllBytes(fullPath), new JsonDocumentOptions { MaxDepth = 8 });
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Cleanup manifest must be a JSON object.");
        var directory = Path.GetDirectoryName(fullPath)!;
        var artifacts = ReadArtifacts(root, directory);
        if (!Enum.TryParse<CleanupPromptStyle>(Required(root, "promptStyle"), true, out var style) || !Enum.IsDefined(style))
            throw new InvalidDataException("Cleanup manifest promptStyle is unsupported.");
        var options = new LlamaCleanupOptions
        {
            RuntimePath = Path.GetFullPath(Required(root, "runtimePath"), directory),
            RuntimeSha256 = Required(root, "runtimeSha256"),
            ModelPath = Path.GetFullPath(Required(root, "modelPath"), directory),
            ModelSha256 = Required(root, "modelSha256"),
            ModelId = Required(root, "modelId"),
            PromptStyle = style,
            BundleDirectory = artifacts.Length > 0 ? directory : null,
            Artifacts = artifacts,
            Threads = Integer(root, "threads", 4),
            ContextSize = Integer(root, "contextSize", 8192),
            MaxOutputTokens = Integer(root, "maxOutputTokens", 2048),
            GpuLayers = Integer(root, "gpuLayers", 0),
            StartupTimeout = TimeSpan.FromSeconds(Integer(root, "startupTimeoutSeconds", 60)),
            IdleTimeout = TimeSpan.FromSeconds(Integer(root, "idleTimeoutSeconds", 60)),
        };
        options.Validate();
        if (!File.Exists(options.RuntimePath)) throw new FileNotFoundException("Cleanup runtime is missing.", options.RuntimePath);
        if (!File.Exists(options.ModelPath)) throw new FileNotFoundException("Cleanup model is missing.", options.ModelPath);
        foreach (var artifact in artifacts)
            if (!File.Exists(artifact.Path)) throw new FileNotFoundException("A cleanup bundle artifact is missing.", artifact.Path);
        return options;
    }

    internal void Validate()
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(RuntimePath);
        ArgumentException.ThrowIfNullOrWhiteSpace(ModelPath);
        ArgumentException.ThrowIfNullOrWhiteSpace(ModelId);
        if (!Path.IsPathFullyQualified(RuntimePath) || !Path.IsPathFullyQualified(ModelPath))
            throw new ArgumentException("Cleanup artifact paths must be absolute.");
        if (!IsHash(RuntimeSha256) || !IsHash(ModelSha256)) throw new ArgumentException("Cleanup artifacts require SHA-256 hashes.");
        if (!Enum.IsDefined(PromptStyle)) throw new ArgumentOutOfRangeException(nameof(PromptStyle));
        if (Threads is < 1 or > 256) throw new ArgumentOutOfRangeException(nameof(Threads));
        if (ContextSize < 256) throw new ArgumentOutOfRangeException(nameof(ContextSize));
        if (MaxOutputTokens < 1 || MaxOutputTokens >= ContextSize) throw new ArgumentOutOfRangeException(nameof(MaxOutputTokens));
        if (GpuLayers < 0) throw new ArgumentOutOfRangeException(nameof(GpuLayers));
        if (StartupTimeout <= TimeSpan.Zero || StartupTimeout > TimeSpan.FromMinutes(30)) throw new ArgumentOutOfRangeException(nameof(StartupTimeout));
        if (IdleTimeout < TimeSpan.Zero || IdleTimeout > TimeSpan.FromDays(1)) throw new ArgumentOutOfRangeException(nameof(IdleTimeout));
        if (ModelId.Length > 256 || ModelId.Any(char.IsControl)) throw new ArgumentException("Cleanup model identifier is invalid.");
        ValidateArtifacts();
    }

    private void ValidateArtifacts()
    {
        ArgumentNullException.ThrowIfNull(Artifacts);
        if (Artifacts.Count == 0) return;
        if (string.IsNullOrWhiteSpace(BundleDirectory) || !Path.IsPathFullyQualified(BundleDirectory))
            throw new ArgumentException("A cleanup bundle inventory requires its absolute manifest directory.");
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var artifact in Artifacts)
        {
            if (!Path.IsPathFullyQualified(artifact.Path) || !IsWithinDirectory(BundleDirectory, artifact.Path))
                throw new ArgumentException("A cleanup artifact is outside its bundle directory.");
            if (!IsHash(artifact.Sha256) || artifact.Size < 0) throw new ArgumentException("A cleanup artifact hash or size is invalid.");
            if (!paths.Add(artifact.Path)) throw new ArgumentException("The cleanup bundle contains duplicate artifact paths.");
        }
        if (!Artifacts.Any(file => file.Path.Equals(RuntimePath, StringComparison.OrdinalIgnoreCase)
                && file.Sha256.Equals(RuntimeSha256, StringComparison.OrdinalIgnoreCase))
            || !Artifacts.Any(file => file.Path.Equals(ModelPath, StringComparison.OrdinalIgnoreCase)
                && file.Sha256.Equals(ModelSha256, StringComparison.OrdinalIgnoreCase)))
            throw new ArgumentException("The cleanup inventory must include the configured runtime and model with matching hashes.");
    }

    private static CleanupArtifactHash[] ReadArtifacts(JsonElement root, string directory)
    {
        var inventory = Property(root, "files");
        if (inventory.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null) return [];
        if (inventory.ValueKind != JsonValueKind.Array || inventory.GetArrayLength() == 0)
            throw new InvalidDataException("Cleanup manifest files must be a nonempty array.");
        var files = new List<CleanupArtifactHash>();
        foreach (var entry in inventory.EnumerateArray())
        {
            if (entry.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Cleanup manifest file entries must be objects.");
            var relative = Required(entry, "path").Replace('\\', '/');
            var parts = relative.Split('/');
            if (relative.Contains(':') || Path.IsPathRooted(relative) || parts.Any(part => part is "" or "." or ".."))
                throw new InvalidDataException("Cleanup bundle files require safe relative paths.");
            var absolute = Path.GetFullPath(relative, directory);
            if (!IsWithinDirectory(directory, absolute)) throw new InvalidDataException("A cleanup bundle file is outside its manifest directory.");
            var sizeValue = Property(entry, "size");
            long? size = null;
            if (sizeValue.ValueKind is not (JsonValueKind.Undefined or JsonValueKind.Null))
            {
                if (sizeValue.ValueKind != JsonValueKind.Number || !sizeValue.TryGetInt64(out var parsed) || parsed < 0)
                    throw new InvalidDataException("Cleanup manifest file size must be a nonnegative integer.");
                size = parsed;
            }
            files.Add(new CleanupArtifactHash(absolute, Required(entry, "sha256"), size));
        }
        return files.ToArray();
    }

    private static bool IsWithinDirectory(string directory, string path)
    {
        var relative = Path.GetRelativePath(Path.GetFullPath(directory), Path.GetFullPath(path));
        return !Path.IsPathRooted(relative) && relative != "." && relative != ".."
            && !relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            && !relative.StartsWith(".." + Path.AltDirectorySeparatorChar, StringComparison.Ordinal);
    }

    private static bool IsHash(string? value) => value is { Length: 64 } && value.All(char.IsAsciiHexDigit);
    private static string Required(JsonElement root, string name)
    {
        var value = Property(root, name);
        if (value.ValueKind != JsonValueKind.String || string.IsNullOrWhiteSpace(value.GetString()))
            throw new InvalidDataException("Cleanup manifest is missing a required field: " + name + ".");
        return value.GetString()!;
    }
    private static int Integer(JsonElement root, string name, int fallback)
    {
        var value = Property(root, name);
        if (value.ValueKind == JsonValueKind.Undefined) return fallback;
        if (!value.TryGetInt32(out var number)) throw new InvalidDataException("Cleanup manifest contains an invalid integer: " + name + ".");
        return number;
    }
    private static JsonElement Property(JsonElement root, string name)
    {
        foreach (var property in root.EnumerateObject())
            if (property.Name.Equals(name, StringComparison.OrdinalIgnoreCase)) return property.Value;
        return default;
    }
}

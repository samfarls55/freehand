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
    /// <summary>S1-mini by Superwhisper, with the prescribed system, controls and empty thinking prefix.</summary>
    S1Mini,
    /// <summary>Handy Editor's documented empty-system ChatML condition.</summary>
    HandyEditor,
    /// <summary>Handy Editor's user-only template condition, for a separately labeled comparison.</summary>
    HandyEditorUserOnly,
    /// <summary>Emberon-2's short fixed instruction and raw transcript.</summary>
    Emberon2,
    /// <summary>BitVoice's SmolLM2 fine-tune, with its trained cleanup instruction.</summary>
    BitVoiceSmol,
    /// <summary>Kudu Writer Tiny's v2 prose prompt with its optional polished-text note.</summary>
    KuduTinyPolished,
    /// <summary>localflow-clean's fixed instruction and dictation tags, without optional context.</summary>
    LocalflowClean,
    /// <summary>Spokenly Cleanup 1's plain key-value completion, without optional context.</summary>
    SpokenlyCleanup,
    /// <summary>ScribeKey Fast's semi-casual/prose/general task completion.</summary>
    ScribeKeyFast,
    /// <summary>Original Sotto's BOS and input/output task completion.</summary>
    Sotto,
    /// <summary>A general instruction-model control using the embedded chat template.</summary>
    GenericChat,
    /// <summary>SmolLM2 Post-ASR Engine's clean-punctuate formatting task.</summary>
    SmolPostAsr,
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
    /// <summary>Optional absolute path to one explicitly selected native GGUF LoRA adapter.</summary>
    public string? AdapterPath { get; init; }
    /// <summary>SHA-256 of the complete selected adapter; required together with its path.</summary>
    public string? AdapterSha256 { get; init; }
    /// <summary>Native adapter multiplier, independent of the alpha/rank scaling embedded in its GGUF.</summary>
    /// <remarks>The pinned runtime cannot parse a nonunit adapter path containing a colon; Windows drive paths require scale 1.</remarks>
    public double AdapterScale { get; init; } = 1;
    /// <summary>The pinned model identifier, also used as the local server alias.</summary>
    public required string ModelId { get; init; }
    /// <summary>The selected model's trained input contract.</summary>
    public required CleanupPromptStyle PromptStyle { get; init; }
    /// <summary>Whether to protect dictionary blocks and paired quoted wording with verified compact specialist identifiers.</summary>
    /// <remarks>Disabled by default so trained specialist contracts can be evaluated independently of this adapter.</remarks>
    public bool MaskSpecialistLiterals { get; init; }
    /// <summary>Absolute manifest directory for a complete bundle inventory, when supplied.</summary>
    public string? BundleDirectory { get; init; }
    /// <summary>Optional complete inventory, including runtime dependencies, the model and accompanying assets.</summary>
    public IReadOnlyList<CleanupArtifactHash> Artifacts { get; init; } = [];
    /// <summary>CPU generation and prompt-processing thread count.</summary>
    public int Threads { get; init; } = 4;
    /// <summary>Logical prompt batch bound; independent of the complete input context limit.</summary>
    public int BatchSize { get; init; } = 128;
    /// <summary>Physical compute batch bound; must not exceed the logical batch.</summary>
    public int MicroBatchSize { get; init; } = 128;
    /// <summary>Maximum retained host prompt-cache size in MiB; zero disables it.</summary>
    public int PromptCacheMiB { get; init; }
    /// <summary>Maximum recurrent/sliding-window state checkpoints per inference slot; zero disables them.</summary>
    public int ContextCheckpoints { get; init; }
    /// <summary>KV key-cache type. Quantized types require exact model/backend validation.</summary>
    public string CacheTypeK { get; init; } = "f16";
    /// <summary>KV value-cache type. Quantized types require exact model/backend validation.</summary>
    public string CacheTypeV { get; init; } = "f16";
    /// <summary>Whether the CPU runtime may repack weights for its selected kernels.</summary>
    public bool Repack { get; init; } = true;
    /// <summary>Maximum prompt-lookup draft tokens for fixed ngram-map-k speculation; zero disables it.</summary>
    public int PromptLookupTokens { get; init; }
    /// <summary>Prompt-lookup match length in tokens; only used when prompt lookup is enabled.</summary>
    public int PromptLookupMatchTokens { get; init; } = 3;
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
        return LoadManifest(fullPath, File.ReadAllBytes(fullPath));
    }

    /// <summary>Parses one already-read manifest snapshot, resolving its artifacts beside the supplied manifest path.</summary>
    /// <remarks>This overload lets qualification bind the exact parsed bytes to a source hash without a second file read.</remarks>
    public static LlamaCleanupOptions LoadManifest(string manifestPath, ReadOnlyMemory<byte> contents)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(manifestPath);
        var fullPath = Path.GetFullPath(manifestPath);
        using var document = JsonDocument.Parse(contents, new JsonDocumentOptions { MaxDepth = 8 });
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object) throw new InvalidDataException("Cleanup manifest must be a JSON object.");
        var directory = Path.GetDirectoryName(fullPath)!;
        var artifacts = ReadArtifacts(root, directory);
        if (!Enum.TryParse<CleanupPromptStyle>(Required(root, "promptStyle"), true, out var style) || !Enum.IsDefined(style))
            throw new InvalidDataException("Cleanup manifest promptStyle is unsupported.");
        var adapterPath = OptionalArtifactPath(root, "adapterPath", directory);
        if (adapterPath is null && Property(root, "adapterScale").ValueKind != JsonValueKind.Undefined)
            throw new InvalidDataException("Cleanup manifest adapterScale requires an adapter.");
        var options = new LlamaCleanupOptions
        {
            RuntimePath = Path.GetFullPath(Required(root, "runtimePath"), directory),
            RuntimeSha256 = Required(root, "runtimeSha256"),
            ModelPath = Path.GetFullPath(Required(root, "modelPath"), directory),
            ModelSha256 = Required(root, "modelSha256"),
            AdapterPath = adapterPath,
            AdapterSha256 = Property(root, "adapterSha256").ValueKind == JsonValueKind.Undefined ? null : Required(root, "adapterSha256"),
            AdapterScale = Number(root, "adapterScale", 1),
            ModelId = Required(root, "modelId"),
            PromptStyle = style,
            MaskSpecialistLiterals = Boolean(root, "maskSpecialistLiterals", false),
            BundleDirectory = artifacts.Length > 0 ? directory : null,
            Artifacts = artifacts,
            Threads = Integer(root, "threads", 4),
            BatchSize = Integer(root, "batchSize", 128),
            MicroBatchSize = Integer(root, "microBatchSize", 128),
            PromptCacheMiB = Integer(root, "promptCacheMiB", 0),
            ContextCheckpoints = Integer(root, "contextCheckpoints", 0),
            CacheTypeK = OptionalString(root, "cacheTypeK", "f16"),
            CacheTypeV = OptionalString(root, "cacheTypeV", "f16"),
            Repack = Boolean(root, "repack", true),
            PromptLookupTokens = Integer(root, "promptLookupTokens", 0),
            PromptLookupMatchTokens = Integer(root, "promptLookupMatchTokens", 3),
            ContextSize = Integer(root, "contextSize", 8192),
            MaxOutputTokens = Integer(root, "maxOutputTokens", 2048),
            GpuLayers = Integer(root, "gpuLayers", 0),
            StartupTimeout = TimeSpan.FromSeconds(Integer(root, "startupTimeoutSeconds", 60)),
            IdleTimeout = TimeSpan.FromSeconds(Integer(root, "idleTimeoutSeconds", 60)),
        };
        options.Validate();
        if (!File.Exists(options.RuntimePath)) throw new FileNotFoundException("Cleanup runtime is missing.", options.RuntimePath);
        if (!File.Exists(options.ModelPath)) throw new FileNotFoundException("Cleanup model is missing.", options.ModelPath);
        if (options.AdapterPath is not null && !File.Exists(options.AdapterPath))
            throw new FileNotFoundException("Cleanup adapter is missing.", options.AdapterPath);
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
        if (!double.IsFinite(AdapterScale) || AdapterScale is <= 0 or > 16)
            throw new ArgumentOutOfRangeException(nameof(AdapterScale));
        if (AdapterPath is null)
        {
            if (AdapterSha256 is not null || AdapterScale != 1)
                throw new ArgumentException("A cleanup adapter hash or scale requires its path.");
        }
        else if (string.IsNullOrWhiteSpace(AdapterPath) || !Path.IsPathFullyQualified(AdapterPath) || !IsHash(AdapterSha256))
            throw new ArgumentException("A cleanup adapter requires its absolute path and SHA-256 hash.");
        if (AdapterPath?.Contains(',') == true || (AdapterScale != 1 && AdapterPath?.Contains(':') == true))
            throw new ArgumentException("The cleanup adapter path contains a separator unsupported by its native adapter option.", nameof(AdapterPath));
        if (!Enum.IsDefined(PromptStyle)) throw new ArgumentOutOfRangeException(nameof(PromptStyle));
        if (Threads is < 1 or > 256) throw new ArgumentOutOfRangeException(nameof(Threads));
        if (BatchSize is < 1 or > 8192) throw new ArgumentOutOfRangeException(nameof(BatchSize));
        if (MicroBatchSize < 1 || MicroBatchSize > BatchSize) throw new ArgumentOutOfRangeException(nameof(MicroBatchSize));
        if (PromptCacheMiB is < 0 or > 8192) throw new ArgumentOutOfRangeException(nameof(PromptCacheMiB));
        if (ContextCheckpoints is < 0 or > 32) throw new ArgumentOutOfRangeException(nameof(ContextCheckpoints));
        if (CacheTypeK is not ("f16" or "f32" or "q8_0" or "q4_0")) throw new ArgumentException("Unsupported cleanup key-cache type.", nameof(CacheTypeK));
        if (CacheTypeV is not ("f16" or "f32" or "q8_0" or "q4_0")) throw new ArgumentException("Unsupported cleanup value-cache type.", nameof(CacheTypeV));
        if (PromptLookupTokens is < 0 or > 64) throw new ArgumentOutOfRangeException(nameof(PromptLookupTokens));
        if (PromptLookupMatchTokens is < 1 or > 12) throw new ArgumentOutOfRangeException(nameof(PromptLookupMatchTokens));
        if (PromptLookupTokens >= BatchSize) throw new ArgumentException("Prompt lookup plus its sampled token must fit the logical batch.", nameof(PromptLookupTokens));
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
        if (AdapterPath is not null && !Artifacts.Any(file => file.Path.Equals(AdapterPath,
                OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal)
                && file.Sha256.Equals(AdapterSha256, StringComparison.OrdinalIgnoreCase)))
            throw new ArgumentException("The cleanup inventory must include the configured adapter with its matching hash.");
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
    private static string? OptionalArtifactPath(JsonElement root, string name, string directory)
    {
        if (Property(root, name).ValueKind == JsonValueKind.Undefined) return null;
        var path = Required(root, name);
        if (Path.IsPathFullyQualified(path)) return Path.GetFullPath(path);
        var relative = path.Replace('\\', '/');
        if (relative.Contains(':') || Path.IsPathRooted(relative) || relative.Split('/').Any(part => part is "" or "." or ".."))
            throw new InvalidDataException("Cleanup manifest adapter paths must be absolute or safe relative paths.");
        return Path.GetFullPath(relative, directory);
    }
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
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt32(out var number))
            throw new InvalidDataException("Cleanup manifest contains an invalid integer: " + name + ".");
        return number;
    }
    private static double Number(JsonElement root, string name, double fallback)
    {
        var value = Property(root, name);
        if (value.ValueKind == JsonValueKind.Undefined) return fallback;
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetDouble(out var number))
            throw new InvalidDataException("Cleanup manifest contains an invalid number: " + name + ".");
        return number;
    }
    private static string OptionalString(JsonElement root, string name, string fallback)
    {
        var value = Property(root, name);
        if (value.ValueKind == JsonValueKind.Undefined) return fallback;
        if (value.ValueKind != JsonValueKind.String) throw new InvalidDataException("Cleanup manifest contains an invalid string: " + name + ".");
        return value.GetString()!;
    }
    private static bool Boolean(JsonElement root, string name, bool fallback)
    {
        var value = Property(root, name);
        if (value.ValueKind == JsonValueKind.Undefined) return fallback;
        if (value.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new InvalidDataException("Cleanup manifest contains an invalid boolean: " + name + ".");
        return value.GetBoolean();
    }
    private static JsonElement Property(JsonElement root, string name)
    {
        foreach (var property in root.EnumerateObject())
            if (property.Name.Equals(name, StringComparison.OrdinalIgnoreCase)) return property.Value;
        return default;
    }
}

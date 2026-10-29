using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Freehand.Abstractions;

namespace Freehand.Speech;

/// <summary>Verified Parakeet assets shared by desktop, worker and installer checks.</summary>
public sealed class ModelResolver : IModelAssets, IDisposable
{
    /// <summary>Whether this isolated development process selects the GPU accuracy candidate.</summary>
    public static bool UsesAcceleratedModel { get; } = ReadProfile();
    private static bool ReadProfile()
    {
        var profile = Environment.GetEnvironmentVariable("FREEHAND_MODEL_PROFILE");
        if (string.IsNullOrEmpty(profile)) return false;
        if (profile != "accuracy-vulkan" || string.IsNullOrEmpty(Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY")))
            throw new InvalidDataException("The GPU accuracy profile requires an isolated development data directory.");
        return true;
    }
    /// <summary>Pinned upstream revision.</summary>
    public static string Version => Manifest.Version;
    /// <summary>Folder for the single bundled model.</summary>
    public static string DirectoryName => Manifest.DirectoryName;
    /// <summary>Mel feature count required by the pinned encoder.</summary>
    public static int FeatureDimension => Manifest.FeatureDimension;
    /// <summary>The selected model's name for settings and measurements.</summary>
    public static string DisplayName => Manifest.DisplayName ?? "Parakeet TDT 110M";
    internal static int DecoderContext => Manifest.DecoderContext;
    internal static string? VoiceActivityModel => Manifest.VoiceActivityModel;
    private static readonly ModelManifest Manifest = LoadManifest();
    /// <summary>Assets required by the selected pinned model.</summary>
    public static IReadOnlyList<string> RequiredFiles { get; } = Manifest.Files.Select(asset => asset.Name).ToArray();
    private static ModelManifest LoadManifest()
    {
        using var stream = typeof(ModelResolver).Assembly.GetManifestResourceStream(UsesAcceleratedModel
            ? "Freehand.AccuracyModelManifest.json" : "Freehand.ModelManifest.json") ?? throw new InvalidDataException("Missing manifest");
        return JsonSerializer.Deserialize(stream, ModelJsonContext.Default.ModelManifest) ?? throw new InvalidDataException("Invalid manifest");
    }
    private readonly string _cacheDirectory;
    private readonly SemaphoreSlim _gate = new(1);
    /// <summary>Installed files are kept beside the app, without per-launch extraction.</summary>
    public string BundledDirectory { get; }
    /// <summary>Actual selected path, including a configured custom path.</summary>
    public string ResolvedDirectory { get; private set; }
    /// <summary>Latest verification result.</summary>
    public bool IsVerified { get; private set; }
    /// <summary>Actionable installation failure.</summary>
    public string? Error { get; private set; }
    /// <summary>Creates the shared resolver.</summary>
    public ModelResolver(string? customPath = null, string? baseDirectory = null, string? cacheDirectory = null)
    {
        BundledDirectory = Path.Combine(baseDirectory ?? AppContext.BaseDirectory, "models", DirectoryName);
        ResolvedDirectory = ResolvePath(customPath);
        var developmentData = Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY");
        _cacheDirectory = cacheDirectory ?? Path.Combine(string.IsNullOrWhiteSpace(developmentData)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Freehand")
            : Path.GetFullPath(developmentData), "verification");
    }
    /// <summary>Changes selection without loading the model.</summary>
    public void Select(string? customPath)
    {
        ResolvedDirectory = ResolvePath(customPath);
        IsVerified = false; Error = null;
    }
    private string ResolvePath(string? customPath)
    {
        if (string.IsNullOrWhiteSpace(customPath)) return BundledDirectory;
        try { return Path.GetFullPath(customPath); }
        catch (Exception e) when (e is ArgumentException or NotSupportedException) { return customPath; }
    }
    /// <summary>Hashes only after detected changes, or for explicit installation/repair validation.</summary>
    public async Task<bool> VerifyAsync(CancellationToken cancellationToken, bool force = false)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var directory = ResolvedDirectory;
            var key = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(directory)));
            var cachePath = Path.Combine(_cacheDirectory, key + ".json");
            var stamps = Manifest.Files.Select(a =>
            {
                var info = new FileInfo(Path.Combine(directory, a.Name));
                if (!info.Exists || info.Length != a.Size) throw new InvalidDataException("Missing or damaged " + a.Name);
                return new AssetStamp(a.Name, info.Length, info.LastWriteTimeUtc.Ticks);
            }).ToArray();
            if (!force && File.Exists(cachePath))
            {
                try
                {
                    var cached = JsonSerializer.Deserialize(await File.ReadAllTextAsync(cachePath, cancellationToken).ConfigureAwait(false), ModelJsonContext.Default.VerificationCache);
                    if (cached is { Stamps: { } cachedStamps } && cached.Version == Version && cachedStamps.SequenceEqual(stamps)) { IsVerified = true; Error = null; return true; }
                }
                catch (Exception e) when (e is JsonException or IOException or UnauthorizedAccessException) { }
            }
            foreach (var asset in Manifest.Files)
            {
                await using var file = File.OpenRead(Path.Combine(directory, asset.Name));
                var hash = await SHA256.HashDataAsync(file, cancellationToken).ConfigureAwait(false);
                if (!Convert.ToHexString(hash).Equals(asset.Sha256, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Damaged " + asset.Name);
            }
            IsVerified = true; Error = null;
            try
            {
                Directory.CreateDirectory(_cacheDirectory);
                var temporary = cachePath + "." + Guid.NewGuid().ToString("N") + ".tmp";
                await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(new VerificationCache(Version, stamps), ModelJsonContext.Default.VerificationCache), cancellationToken).ConfigureAwait(false);
                File.Move(temporary, cachePath, true);
            }
            catch (Exception e) when (e is IOException or UnauthorizedAccessException) { /* Verification still succeeded. */ }
            return true;
        }
        catch (Exception e) when (e is IOException or InvalidDataException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            IsVerified = false;
            Error = "The selected model is missing or damaged. Use the bundled model, or run the Freehand installer again to repair it.";
            return false;
        }
        finally { _gate.Release(); }
    }
    /// <inheritdoc />
    public void Dispose() => _gate.Dispose();
}
internal sealed record ModelAsset(string Name, long Size, string Sha256, string? Source = null);
internal sealed record ModelManifest(string Version, string DirectoryName, int FeatureDimension, ModelAsset[] Files,
    int DecoderContext = 0, string? DisplayName = null, string? VoiceActivityModel = null);
internal sealed record AssetStamp(string Name, long Size, long Modified);
internal sealed record VerificationCache(string Version, AssetStamp[] Stamps);
[JsonSerializable(typeof(VerificationCache))]
[JsonSerializable(typeof(ModelManifest))]
internal sealed partial class ModelJsonContext : JsonSerializerContext;

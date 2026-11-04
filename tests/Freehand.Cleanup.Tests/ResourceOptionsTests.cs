using System.Text.Json;
using Shouldly;
using Xunit;

namespace Freehand.Cleanup.Tests;

public sealed class ResourceOptionsTests
{
    [Fact]
    public void Manifest_can_explicitly_select_f32_caches_without_changing_default_precision()
    {
        using var fixture = new Fixture();
        fixture.Write([]);
        var defaults = LlamaCleanupOptions.LoadManifest(fixture.ManifestPath);
        defaults.CacheTypeK.ShouldBe("f16"); defaults.CacheTypeV.ShouldBe("f16");

        fixture.Write(new Dictionary<string, object> { ["cacheTypeK"] = "f32", ["cacheTypeV"] = "f32" });
        var selected = LlamaCleanupOptions.LoadManifest(fixture.ManifestPath);

        selected.CacheTypeK.ShouldBe("f32"); selected.CacheTypeV.ShouldBe("f32");
        selected.ContextSize.ShouldBe(defaults.ContextSize);
        selected.MaxOutputTokens.ShouldBe(defaults.MaxOutputTokens);
    }

    [Fact]
    public void Manifest_preserves_the_explicit_bounded_resource_profile()
    {
        using var fixture = new Fixture();
        fixture.Write(new Dictionary<string, object>
        {
            ["batchSize"] = 256, ["microBatchSize"] = 64, ["promptCacheMiB"] = 16,
            ["contextCheckpoints"] = 1, ["cacheTypeK"] = "q8_0", ["cacheTypeV"] = "q4_0", ["repack"] = false,
            ["promptLookupTokens"] = 16, ["promptLookupMatchTokens"] = 3,
        });

        var options = LlamaCleanupOptions.LoadManifest(fixture.ManifestPath);

        options.BatchSize.ShouldBe(256); options.MicroBatchSize.ShouldBe(64);
        options.PromptCacheMiB.ShouldBe(16); options.ContextCheckpoints.ShouldBe(1);
        options.CacheTypeK.ShouldBe("q8_0"); options.CacheTypeV.ShouldBe("q4_0"); options.Repack.ShouldBeFalse();
        options.PromptLookupTokens.ShouldBe(16); options.PromptLookupMatchTokens.ShouldBe(3);
    }

    [Theory]
    [InlineData("batchSize", 0)]
    [InlineData("batchSize", 8193)]
    [InlineData("microBatchSize", 0)]
    [InlineData("microBatchSize", 129)]
    [InlineData("promptCacheMiB", -1)]
    [InlineData("promptCacheMiB", 8193)]
    [InlineData("contextCheckpoints", -1)]
    [InlineData("contextCheckpoints", 33)]
    [InlineData("promptLookupTokens", -1)]
    [InlineData("promptLookupTokens", 65)]
    [InlineData("promptLookupMatchTokens", 0)]
    [InlineData("promptLookupMatchTokens", 13)]
    [InlineData("cacheTypeK", "unexpected")]
    [InlineData("cacheTypeV", "q8_0 --model another.gguf")]
    public void Manifest_rejects_invalid_or_unbounded_resource_settings(string name, object value)
    {
        using var fixture = new Fixture();
        fixture.Write(new Dictionary<string, object> { [name] = value });

        Should.Throw<ArgumentException>(() => LlamaCleanupOptions.LoadManifest(fixture.ManifestPath));
    }

    [Theory]
    [InlineData("cacheTypeK", 8)]
    [InlineData("cacheTypeV", true)]
    [InlineData("repack", "false")]
    [InlineData("repack", 0)]
    [InlineData("promptLookupTokens", "16")]
    [InlineData("promptLookupMatchTokens", true)]
    public void Manifest_rejects_wrong_resource_value_types(string name, object value)
    {
        using var fixture = new Fixture();
        fixture.Write(new Dictionary<string, object> { [name] = value });

        Should.Throw<InvalidDataException>(() => LlamaCleanupOptions.LoadManifest(fixture.ManifestPath));
    }

    [Fact]
    public void Prompt_lookup_requires_room_for_the_sampled_token_in_the_logical_batch()
    {
        using var fixture = new Fixture();
        fixture.Write(new Dictionary<string, object> { ["batchSize"] = 16, ["microBatchSize"] = 16, ["promptLookupTokens"] = 16 });

        Should.Throw<ArgumentException>(() => LlamaCleanupOptions.LoadManifest(fixture.ManifestPath));
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = Path.Combine(Path.GetTempPath(), "freehand-cleanup-resource-" + Guid.NewGuid().ToString("N"));
        public string ManifestPath => Path.Combine(_directory, "cleanup-manifest.json");
        public Fixture()
        {
            Directory.CreateDirectory(_directory);
            File.WriteAllText(Path.Combine(_directory, "runtime.exe"), "runtime");
            File.WriteAllText(Path.Combine(_directory, "model.gguf"), "model");
        }

        public void Write(Dictionary<string, object> values)
        {
            values["runtimePath"] = "runtime.exe"; values["modelPath"] = "model.gguf";
            values["runtimeSha256"] = new string('0', 64); values["modelSha256"] = new string('0', 64);
            values["modelId"] = "pinned-model"; values["promptStyle"] = "QuillChatMl";
            File.WriteAllText(ManifestPath, JsonSerializer.Serialize(values));
        }

        public void Dispose() => Directory.Delete(_directory, true);
    }
}

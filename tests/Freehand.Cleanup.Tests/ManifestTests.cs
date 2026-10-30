using System.Text.Json;
using Shouldly;
using Xunit;

namespace Freehand.Cleanup.Tests;

public sealed class ManifestTests
{
    [Theory]
    [InlineData("../outside.dll")]
    [InlineData("runtime/../../outside.dll")]
    [InlineData("/outside.dll")]
    [InlineData("C:\\outside.dll")]
    [InlineData("runtime\\..\\outside.dll")]
    [InlineData("runtime//outside.dll")]
    public void Bundle_inventory_rejects_absolute_or_traversing_paths(string relativePath)
    {
        using var fixture = new ManifestFixture();
        fixture.Write(new[] { new { path = relativePath, sha256 = fixture.Hash } });
        Should.Throw<InvalidDataException>(() => LlamaCleanupOptions.LoadManifest(fixture.ManifestPath));
    }

    [Fact]
    public void Bundle_inventory_requires_primary_runtime_and_model_with_matching_hashes()
    {
        using var fixture = new ManifestFixture();
        fixture.Write(new[] { new { path = "runtime.exe", sha256 = fixture.Hash } });
        Should.Throw<ArgumentException>(() => LlamaCleanupOptions.LoadManifest(fixture.ManifestPath))
            .Message.ShouldContain("configured runtime and model");
    }

    [Fact]
    public void Bundle_inventory_rejects_duplicate_paths_on_windows_case_rules()
    {
        using var fixture = new ManifestFixture();
        fixture.Write(new[] { new { path = "runtime.exe", sha256 = fixture.Hash }, new { path = "RUNTIME.EXE", sha256 = fixture.Hash } });
        Should.Throw<ArgumentException>(() => LlamaCleanupOptions.LoadManifest(fixture.ManifestPath))
            .Message.ShouldContain("duplicate");
    }

    [Fact]
    public void Bundle_inventory_loads_safe_paths_and_optional_size_metadata()
    {
        using var fixture = new ManifestFixture();
        fixture.Write(new[]
        {
            new { path = "runtime.exe", sha256 = fixture.Hash, size = 7 },
            new { path = "model.gguf", sha256 = fixture.Hash, size = 5 },
        });
        var options = LlamaCleanupOptions.LoadManifest(fixture.ManifestPath);
        options.BundleDirectory.ShouldBe(fixture.DirectoryPath);
        options.Artifacts.Count.ShouldBe(2);
        options.Artifacts[0].Path.ShouldBe(Path.Combine(fixture.DirectoryPath, "runtime.exe"));
        options.Artifacts[0].Size.ShouldBe(7);
    }

    [Fact]
    public void Manifest_resolves_relative_paths_and_does_not_hash_model_on_settings_load()
    {
        var directory = Path.Combine(Path.GetTempPath(), "freehand-cleanup-manifest-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try
        {
            File.WriteAllText(Path.Combine(directory, "runtime.exe"), "runtime");
            File.WriteAllText(Path.Combine(directory, "model.gguf"), "model");
            var path = Path.Combine(directory, "cleanup-manifest.json");
            var hash = new string('0', 64);
            File.WriteAllText(path, JsonSerializer.Serialize(new
            {
                runtimePath = "runtime.exe", runtimeSha256 = hash, modelPath = "model.gguf", modelSha256 = hash,
                modelId = "pinned-model", promptStyle = "QuillChatMl", contextSize = 4096, maxOutputTokens = 1024,
            }));
            var options = LlamaCleanupOptions.LoadManifest(path);
            options.ModelPath.ShouldBe(Path.Combine(directory, "model.gguf"));
            options.RuntimePath.ShouldBe(Path.Combine(directory, "runtime.exe"));
            options.ModelSha256.ShouldBe(hash);
            options.ContextSize.ShouldBe(4096);
            options.PromptStyle.ShouldBe(CleanupPromptStyle.QuillChatMl);
        }
        finally { Directory.Delete(directory, true); }
    }

    private sealed class ManifestFixture : IDisposable
    {
        public string DirectoryPath { get; } = Path.Combine(Path.GetTempPath(), "freehand-cleanup-manifest-" + Guid.NewGuid().ToString("N"));
        public string ManifestPath => Path.Combine(DirectoryPath, "cleanup-manifest.json");
        public string Hash { get; } = new('0', 64);
        public ManifestFixture()
        {
            Directory.CreateDirectory(DirectoryPath);
            File.WriteAllText(Path.Combine(DirectoryPath, "runtime.exe"), "runtime");
            File.WriteAllText(Path.Combine(DirectoryPath, "model.gguf"), "model");
        }
        public void Write<T>(T files) => File.WriteAllText(ManifestPath, JsonSerializer.Serialize(new
        {
            runtimePath = "runtime.exe", runtimeSha256 = Hash, modelPath = "model.gguf", modelSha256 = Hash,
            modelId = "pinned-model", promptStyle = "QuillChatMl", files,
        }));
        public void Dispose() => Directory.Delete(DirectoryPath, true);
    }
}

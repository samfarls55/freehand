using System.Text.Json;
using Freehand.Abstractions;
using Freehand.App;
using Freehand.Cleanup;
using Shouldly;
using Xunit;

namespace Freehand.AppTests;

public sealed class CleanupSelfTestTests
{
    [Fact]
    public void Metadata_only_package_validates_pins_without_native_inference_or_downloads()
    {
        using var metadata = new ProvisioningMetadata();
        SelfTest.CheckProvisioningMetadata(metadata.DirectoryPath).ShouldBe(0);
        Directory.GetFiles(metadata.DirectoryPath).Length.ShouldBe(2);
    }

    [Theory]
    [InlineData("model-missing")]
    [InlineData("runtime-missing")]
    [InlineData("malformed")]
    [InlineData("runtime-pin")]
    [InlineData("model-pin")]
    public void Metadata_only_package_selftest_rejects_incomplete_or_invalid_acquisition_data(string failure)
    {
        using var metadata = new ProvisioningMetadata();
        switch (failure)
        {
            case "model-missing": File.Delete(metadata.ModelManifest); break;
            case "runtime-missing": File.Delete(metadata.RuntimeManifest); break;
            case "malformed": File.WriteAllText(metadata.ModelManifest, "{"); break;
            case "runtime-pin":
                File.WriteAllText(metadata.RuntimeManifest, File.ReadAllText(metadata.RuntimeManifest).Replace(new string('b', 40), "unversioned", StringComparison.Ordinal));
                break;
            case "model-pin":
                File.WriteAllText(metadata.ModelManifest, File.ReadAllText(metadata.ModelManifest).Replace(new string('0', 64), "invalid-hash", StringComparison.Ordinal));
                break;
        }
        SelfTest.CheckProvisioningMetadata(metadata.DirectoryPath).ShouldBe(1);
    }

    [Fact]
    public void Absent_optional_acquisition_metadata_does_not_change_the_clean_runner_contract()
    {
        SelfTest.CheckProvisioningMetadata(Path.Combine(Path.GetTempPath(), "freehand-metadata-absent-" + Guid.NewGuid().ToString("N"))).ShouldBe(0);
    }

    [Fact]
    public async Task Missing_optional_bundle_does_not_require_a_platform_worker()
    {
        var absent = Path.Combine(Path.GetTempPath(), "freehand-selftest-absent-" + Guid.NewGuid().ToString("N"));
        (await SelfTest.CheckCleanupAsync(absent, null)).ShouldBe(0);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("{invalid")]
    [InlineData("{}")]
    public async Task Present_but_incomplete_bundle_fails_published_selftest(string? manifest)
    {
        using var assets = new Assets();
        if (manifest is null) File.Delete(assets.Manifest);
        else File.WriteAllText(assets.Manifest, manifest);
        (await SelfTest.CheckCleanupAsync(assets.DirectoryPath, new Launcher(), (_, _) =>
            throw new InvalidOperationException("Invalid assets must not launch inference."))).ShouldBe(1);
    }

    [Fact]
    public async Task Bundled_cleanup_runs_complete_inference_and_disposes_the_owned_processor()
    {
        using var assets = new Assets();
        var processor = new Processor();
        var launcher = new Launcher();
        (await SelfTest.CheckCleanupAsync(assets.DirectoryPath, launcher, (options, workerLauncher) =>
        {
            options.ModelId.ShouldBe("test-cleanup");
            workerLauncher.ShouldBeSameAs(launcher);
            return processor;
        })).ShouldBe(0);
        processor.Input.ShouldBe("Freehand is ready.");
        processor.Disposed.ShouldBeTrue();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Worker_failure_or_empty_completion_fails_selftest_and_disposes_processor(bool fail)
    {
        using var assets = new Assets();
        var processor = new Processor { Fail = fail, Output = "" };
        (await SelfTest.CheckCleanupAsync(assets.DirectoryPath, new Launcher(), (_, _) => processor)).ShouldBe(1);
        processor.Disposed.ShouldBeTrue();
    }

    [Fact]
    public async Task Bundled_model_requires_the_packaged_platform_launcher()
    {
        using var assets = new Assets();
        (await SelfTest.CheckCleanupAsync(assets.DirectoryPath, null)).ShouldBe(1);
    }

    private sealed class Assets : IDisposable
    {
        internal string DirectoryPath { get; } = Path.Combine(Path.GetTempPath(), "freehand-cleanup-selftest-" + Guid.NewGuid().ToString("N"));
        internal string Manifest => Path.Combine(DirectoryPath, "cleanup-manifest.json");
        internal Assets()
        {
            Directory.CreateDirectory(DirectoryPath);
            File.WriteAllText(Path.Combine(DirectoryPath, "runtime.exe"), "fixture-runtime");
            File.WriteAllText(Path.Combine(DirectoryPath, "model.gguf"), "fixture-model");
            File.WriteAllText(Manifest, JsonSerializer.Serialize(new
            {
                runtimePath = "runtime.exe", runtimeSha256 = new string('0', 64),
                modelPath = "model.gguf", modelSha256 = new string('0', 64),
                modelId = "test-cleanup", promptStyle = "QuillChatMl",
            }));
        }
        public void Dispose() => Directory.Delete(DirectoryPath, true);
    }

    private sealed class ProvisioningMetadata : IDisposable
    {
        internal string DirectoryPath { get; } = Path.Combine(Path.GetTempPath(), "freehand-cleanup-metadata-" + Guid.NewGuid().ToString("N"));
        internal string ModelManifest => Path.Combine(DirectoryPath, "cleanup-model-manifest.json");
        internal string RuntimeManifest => Path.Combine(DirectoryPath, "cleanup-runtime-manifest.json");
        internal ProvisioningMetadata()
        {
            Directory.CreateDirectory(DirectoryPath);
            var hash = new string('0', 64);
            var license = new { Source = "https://assets.example/LICENSE.txt", Sha256 = hash, Size = 100 };
            File.WriteAllText(ModelManifest, JsonSerializer.Serialize(new
            {
                SchemaVersion = 1, ModelId = "packaged-test-model", PromptStyle = "QuillChatMl",
                Model = new { Source = "https://assets.example/model.gguf", Sha256 = hash, Size = 2000, Revision = new string('a', 40) },
                ModelLicense = license, RuntimeLicense = license,
                Inference = new { Threads = 4, ContextSize = 8192, MaxOutputTokens = 2048, GpuLayers = 0, StartupTimeoutSeconds = 60, IdleTimeoutSeconds = 60 },
            }));
            File.WriteAllText(RuntimeManifest, JsonSerializer.Serialize(new
            {
                SchemaVersion = 1, SourceCommit = new string('b', 40), Artifacts = new[]
                {
                    new { Platform = "win-x64-cpu", Source = "https://assets.example/runtime.zip", ArchiveSize = 3000,
                        ArchiveSha256 = hash, Executable = "llama-server.exe", ExecutableSha256 = hash },
                },
            }));
        }
        public void Dispose() => Directory.Delete(DirectoryPath, recursive: true);
    }

    private sealed class Processor : ITranscriptPostProcessor
    {
        internal string? Input { get; private set; }
        internal string Output { get; init; } = "Freehand is ready.";
        internal bool Fail { get; init; }
        internal bool Disposed { get; private set; }
        public ValueTask<string> ProcessAsync(string text, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Input = text;
            if (Fail) throw new IOException("Fixture native startup failure.");
            return ValueTask.FromResult(Output);
        }
        public ValueTask DisposeAsync() { Disposed = true; return ValueTask.CompletedTask; }
    }

    private sealed class Launcher : ICleanupWorkerLauncher
    {
        public IWorkerProcess Launch(CleanupWorkerStartInfo startInfo) =>
            throw new InvalidOperationException("The unit-test processor owns simulated inference.");
    }
}

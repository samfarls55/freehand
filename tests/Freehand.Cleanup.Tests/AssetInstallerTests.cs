using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Shouldly;
using Xunit;

namespace Freehand.Cleanup.Tests;

public sealed class AssetInstallerTests
{
    [Fact]
    public void Acquisition_metadata_validation_is_read_only_and_does_not_download()
    {
        using var fixture = new Fixture();
        var metadata = CleanupAssetInstaller.ValidateAcquisitionMetadata(fixture.ModelManifest, fixture.RuntimeManifest);
        metadata.ModelId.ShouldBe("fixture-cleanup");
        metadata.ModelBytes.ShouldBe(fixture.ModelBytes.Length);
        metadata.DownloadBytes.ShouldBeGreaterThan(metadata.ModelBytes);
        fixture.Transport.RequestCount.ShouldBe(0);
        Directory.Exists(fixture.Root).ShouldBeFalse();
    }

    [Fact]
    public async Task Explicit_setup_pins_complete_bundle_and_reuses_verified_install_without_network()
    {
        using var fixture = new Fixture();
        var progress = new RecordedProgress();
        var installer = fixture.Installer();
        var installed = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest, progress);

        installed.ModelId.ShouldBe("fixture-cleanup");
        var options = LlamaCleanupOptions.LoadManifest(installed.ManifestPath);
        options.ModelId.ShouldBe(installed.ModelId);
        options.ModelSha256.ShouldBe(Hash(fixture.ModelBytes));
        options.BatchSize.ShouldBe(128); options.MicroBatchSize.ShouldBe(128);
        options.MaskSpecialistLiterals.ShouldBeFalse(); options.Repack.ShouldBeTrue();
        options.SpecialistLiteralProtocol.ShouldBe(SpecialistLiteralProtocol.CompactV3);
        File.ReadAllText(installed.ManifestPath).ShouldNotContain("specialistLiteralProtocol");
        options.PromptCacheMiB.ShouldBe(0); options.ContextCheckpoints.ShouldBe(0);
        options.PromptLookupTokens.ShouldBe(0); options.PromptLookupMatchTokens.ShouldBe(3);
        options.Artifacts.Count.ShouldBe(7);
        File.ReadAllText(Path.Combine(installed.DirectoryPath, "runtime", "dependency.dll")).ShouldBe("fixture DLL");
        File.ReadAllText(Path.Combine(installed.DirectoryPath, "licenses", "model", "base-LICENSE.txt")).ShouldBe("base model license");
        foreach (var artifact in options.Artifacts)
            Hash(await File.ReadAllBytesAsync(artifact.Path)).ShouldBe(artifact.Sha256);
        progress.Values.Last().Stage.ShouldBe("Cleanup model installed");
        progress.Values.Last().BytesReceived.ShouldBe(progress.Values.Last().TotalBytes);
        var requests = fixture.Transport.RequestCount;
        (await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest)).DirectoryPath.ShouldBe(installed.DirectoryPath);
        fixture.Transport.RequestCount.ShouldBe(requests);
        fixture.StagingDirectories.ShouldBeEmpty();
    }

    [Fact]
    public async Task Specialist_setup_preserves_the_complete_explicit_profile_and_reuses_it()
    {
        using var fixture = new Fixture();
        fixture.SetInference(new Dictionary<string, object>
        {
            ["BatchSize"] = 256, ["MicroBatchSize"] = 64, ["PromptCacheMiB"] = 16, ["ContextCheckpoints"] = 2,
            ["CacheTypeK"] = "q8_0", ["CacheTypeV"] = "q4_0", ["Repack"] = false, ["MaskSpecialistLiterals"] = true,
            ["PromptLookupTokens"] = 16, ["PromptLookupMatchTokens"] = 3,
        });
        var installer = fixture.Installer();

        var installed = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        var options = LlamaCleanupOptions.LoadManifest(installed.ManifestPath);

        options.PromptStyle.ShouldBe(CleanupPromptStyle.S1Mini);
        options.BatchSize.ShouldBe(256); options.MicroBatchSize.ShouldBe(64);
        options.PromptCacheMiB.ShouldBe(16); options.ContextCheckpoints.ShouldBe(2);
        options.CacheTypeK.ShouldBe("q8_0"); options.CacheTypeV.ShouldBe("q4_0");
        options.Repack.ShouldBeFalse(); options.MaskSpecialistLiterals.ShouldBeTrue();
        options.PromptLookupTokens.ShouldBe(16); options.PromptLookupMatchTokens.ShouldBe(3);
        var requests = fixture.Transport.RequestCount;
        (await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest)).DirectoryPath.ShouldBe(installed.DirectoryPath);
        fixture.Transport.RequestCount.ShouldBe(requests);
    }

    [Fact]
    public async Task Explicit_quote_v4_setup_preserves_version_and_repairs_a_changed_cached_protocol()
    {
        using var fixture = new Fixture();
        fixture.SetInference(new Dictionary<string, object>
        {
            ["MaskSpecialistLiterals"] = true, ["SpecialistLiteralProtocol"] = "CompactV4",
        });
        var installer = fixture.Installer();
        var installed = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        LlamaCleanupOptions.LoadManifest(installed.ManifestPath).SpecialistLiteralProtocol.ShouldBe(SpecialistLiteralProtocol.CompactV4);
        var requests = fixture.Transport.RequestCount;
        (await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest)).DirectoryPath.ShouldBe(installed.DirectoryPath);
        fixture.Transport.RequestCount.ShouldBe(requests);
        var manifest = System.Text.Json.Nodes.JsonNode.Parse(await File.ReadAllTextAsync(installed.ManifestPath))!;
        manifest["specialistLiteralProtocol"] = "CompactV3";
        await File.WriteAllTextAsync(installed.ManifestPath, manifest.ToJsonString());
        var repaired = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        repaired.DirectoryPath.ShouldNotBe(installed.DirectoryPath);
        LlamaCleanupOptions.LoadManifest(repaired.ManifestPath).SpecialistLiteralProtocol.ShouldBe(SpecialistLiteralProtocol.CompactV4);
        File.Exists(installed.ManifestPath).ShouldBeTrue();
    }

    [Fact]
    public async Task Vulkan_setup_selects_the_pinned_windows_artifact_and_preserves_existing_cpu_assets()
    {
        using var fixture = new Fixture();
        var installer = fixture.Installer();
        var cpu = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        fixture.SetInference(new Dictionary<string, object> { ["GpuLayers"] = 999, ["PromptLookupTokens"] = 16 });
        fixture.SetRuntimePlatform("win-x64-vulkan");

        var vulkan = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);

        vulkan.DirectoryPath.ShouldNotBe(cpu.DirectoryPath);
        File.Exists(cpu.ManifestPath).ShouldBeTrue();
        using var manifest = JsonDocument.Parse(await File.ReadAllBytesAsync(vulkan.ManifestPath));
        manifest.RootElement.GetProperty("platform").GetString().ShouldBe("win-x64-vulkan");
        var options = LlamaCleanupOptions.LoadManifest(vulkan.ManifestPath);
        options.GpuLayers.ShouldBe(999); options.PromptLookupTokens.ShouldBe(16);
        var requests = fixture.Transport.RequestCount;
        (await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest)).DirectoryPath.ShouldBe(vulkan.DirectoryPath);
        fixture.Transport.RequestCount.ShouldBe(requests);
    }

    [Theory]
    [InlineData("linux-x64-cpu")]
    [InlineData("win-x64-cuda")]
    [InlineData("arbitrary")]
    public void Setup_rejects_platforms_outside_the_windows_cpu_vulkan_allowlist(string platform)
    {
        using var fixture = new Fixture();
        fixture.SetRuntimePlatform(platform, includeArtifact: false);

        Should.Throw<InvalidDataException>(() => CleanupAssetInstaller.ValidateAcquisitionMetadata(fixture.ModelManifest, fixture.RuntimeManifest));

        fixture.Transport.RequestCount.ShouldBe(0);
    }

    [Fact]
    public void Vulkan_setup_cannot_substitute_the_cpu_artifact_when_its_pin_is_missing()
    {
        using var fixture = new Fixture();
        fixture.SetRuntimePlatform("win-x64-vulkan", includeArtifact: false);

        Should.Throw<InvalidDataException>(() => CleanupAssetInstaller.ValidateAcquisitionMetadata(fixture.ModelManifest, fixture.RuntimeManifest));

        fixture.Transport.RequestCount.ShouldBe(0);
    }

    [Fact]
    public async Task Legacy_cached_bundle_without_optional_profile_fields_uses_compatible_defaults()
    {
        using var fixture = new Fixture();
        var installer = fixture.Installer();
        var installed = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        var manifest = System.Text.Json.Nodes.JsonNode.Parse(await File.ReadAllTextAsync(installed.ManifestPath))!.AsObject();
        foreach (var field in new[] { "platform", "batchSize", "microBatchSize", "promptCacheMiB", "contextCheckpoints", "cacheTypeK", "cacheTypeV", "repack", "maskSpecialistLiterals", "promptLookupTokens", "promptLookupMatchTokens" })
            manifest.Remove(field);
        await File.WriteAllTextAsync(installed.ManifestPath, manifest.ToJsonString());
        var requests = fixture.Transport.RequestCount;

        (await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest)).DirectoryPath.ShouldBe(installed.DirectoryPath);

        fixture.Transport.RequestCount.ShouldBe(requests);
    }

    [Fact]
    public async Task Cached_setup_cannot_activate_an_adapter_absent_from_the_selected_acquisition_plan()
    {
        using var fixture = new Fixture();
        var installer = fixture.Installer();
        var installed = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        var manifest = System.Text.Json.Nodes.JsonNode.Parse(await File.ReadAllTextAsync(installed.ManifestPath))!.AsObject();
        manifest["adapterPath"] = "model.gguf";
        manifest["adapterSha256"] = Hash(fixture.ModelBytes);
        await File.WriteAllTextAsync(installed.ManifestPath, manifest.ToJsonString());
        LlamaCleanupOptions.LoadManifest(installed.ManifestPath).AdapterPath.ShouldNotBeNull();

        var repaired = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);

        repaired.DirectoryPath.ShouldNotBe(installed.DirectoryPath);
        LlamaCleanupOptions.LoadManifest(repaired.ManifestPath).AdapterPath.ShouldBeNull();
        File.Exists(installed.ManifestPath).ShouldBeTrue();
    }

    [Theory]
    [InlineData("BatchSize", 0)]
    [InlineData("BatchSize", 8193)]
    [InlineData("MicroBatchSize", 129)]
    [InlineData("PromptCacheMiB", -1)]
    [InlineData("ContextCheckpoints", 33)]
    [InlineData("BatchSize", "128")]
    [InlineData("BatchSize", true)]
    [InlineData("MaskSpecialistLiterals", "true")]
    [InlineData("SpecialistLiteralProtocol", "CompactV4")]
    [InlineData("SpecialistLiteralProtocol", "CompactV5")]
    [InlineData("SpecialistLiteralProtocol", true)]
    [InlineData("Repack", 0)]
    [InlineData("CacheTypeK", "q2_bad")]
    [InlineData("CacheTypeV", 8)]
    [InlineData("PromptLookupTokens", -1)]
    [InlineData("PromptLookupTokens", 65)]
    [InlineData("PromptLookupMatchTokens", 0)]
    [InlineData("PromptLookupMatchTokens", 13)]
    [InlineData("PromptLookupTokens", "16")]
    [InlineData("PromptLookupMatchTokens", true)]
    public void Acquisition_rejects_invalid_profile_values_before_downloading(string name, object value)
    {
        using var fixture = new Fixture();
        fixture.SetInference(new Dictionary<string, object> { [name] = value });

        Should.Throw<InvalidDataException>(() => CleanupAssetInstaller.ValidateAcquisitionMetadata(fixture.ModelManifest, fixture.RuntimeManifest));

        fixture.Transport.RequestCount.ShouldBe(0);
        Directory.Exists(fixture.Root).ShouldBeFalse();
    }

    [Fact]
    public void Acquisition_rejects_a_lookup_draft_that_leaves_no_sampled_token_batch_space()
    {
        using var fixture = new Fixture();
        fixture.SetInference(new Dictionary<string, object> { ["BatchSize"] = 16, ["MicroBatchSize"] = 16, ["PromptLookupTokens"] = 16 });

        Should.Throw<InvalidDataException>(() => CleanupAssetInstaller.ValidateAcquisitionMetadata(fixture.ModelManifest, fixture.RuntimeManifest));

        fixture.Transport.RequestCount.ShouldBe(0);
    }

    [Fact]
    public async Task Failed_hash_and_cancelled_download_preserve_the_previous_complete_model()
    {
        using var fixture = new Fixture();
        var installer = fixture.Installer();
        var original = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        fixture.SetModel(Encoding.UTF8.GetBytes("replacement model"));
        fixture.Transport.Payloads["/model"] = Encoding.UTF8.GetBytes("corrupted content");
        await Should.ThrowAsync<InvalidDataException>(async () =>
            await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest));
        File.Exists(original.ManifestPath).ShouldBeTrue();
        File.ReadAllBytes(Path.Combine(original.DirectoryPath, "model.gguf")).ShouldBe(Encoding.UTF8.GetBytes("fixture model"));
        fixture.StagingDirectories.ShouldBeEmpty();

        fixture.SetModel(new byte[512 * 1024]);
        using var cancellation = new CancellationTokenSource();
        var progress = new RecordedProgress(value => { if (value.BytesReceived > 0) cancellation.Cancel(); });
        await Should.ThrowAsync<OperationCanceledException>(async () =>
            await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest, progress, cancellation.Token));
        File.Exists(original.ManifestPath).ShouldBeTrue();
        fixture.StagingDirectories.ShouldBeEmpty();
    }

    [Fact]
    public async Task Repair_publishes_a_new_complete_directory_without_overwriting_old_files()
    {
        using var fixture = new Fixture();
        var installer = fixture.Installer();
        var original = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        await File.WriteAllTextAsync(Path.Combine(original.DirectoryPath, "runtime", "dependency.dll"), "damaged existing DLL");

        var repaired = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);

        repaired.DirectoryPath.ShouldNotBe(original.DirectoryPath);
        File.ReadAllText(Path.Combine(original.DirectoryPath, "runtime", "dependency.dll")).ShouldBe("damaged existing DLL");
        File.ReadAllText(Path.Combine(repaired.DirectoryPath, "runtime", "dependency.dll")).ShouldBe("fixture DLL");
        var requests = fixture.Transport.RequestCount;
        var checkedAgain = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        checkedAgain.DirectoryPath.ShouldBe(repaired.DirectoryPath);
        fixture.Transport.RequestCount.ShouldBe(requests, "the verified repair should be reused instead of downloading another complete model");
        File.ReadAllText(Path.Combine(original.DirectoryPath, "runtime", "dependency.dll")).ShouldBe("damaged existing DLL");
        fixture.StagingDirectories.ShouldBeEmpty();
    }

    [Theory]
    [InlineData("promptStyle", "Qwen35")]
    [InlineData("platform", "win-x64-vulkan")]
    [InlineData("threads", "8")]
    [InlineData("contextSize", "4096")]
    [InlineData("maxOutputTokens", "1024")]
    [InlineData("gpuLayers", "1")]
    [InlineData("startupTimeoutSeconds", "90")]
    [InlineData("idleTimeoutSeconds", "0")]
    [InlineData("batchSize", "256")]
    [InlineData("microBatchSize", "64")]
    [InlineData("promptCacheMiB", "16")]
    [InlineData("contextCheckpoints", "1")]
    [InlineData("maskSpecialistLiterals", "true")]
    [InlineData("repack", "false")]
    [InlineData("cacheTypeK", "q8_0")]
    [InlineData("cacheTypeV", "q4_0")]
    [InlineData("promptLookupTokens", "16")]
    [InlineData("promptLookupMatchTokens", "12")]
    [InlineData("license", "changed license")]
    [InlineData("notice", "changed base notice")]
    public async Task Cache_reuse_requires_the_selected_inference_and_license_pins(string property, string value)
    {
        using var fixture = new Fixture();
        var installer = fixture.Installer();
        var original = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);
        var manifest = System.Text.Json.Nodes.JsonNode.Parse(await File.ReadAllTextAsync(original.ManifestPath))!;
        if (property is "license" or "notice")
        {
            var relative = property == "license" ? "licenses/model-LICENSE.txt" : "licenses/model/base-LICENSE.txt";
            var altered = Encoding.UTF8.GetBytes(value);
            await File.WriteAllBytesAsync(Path.Combine(original.DirectoryPath, relative), altered);
            var entry = manifest["files"]!.AsArray().Single(file => file!["path"]!.GetValue<string>() == relative)!;
            entry["sha256"] = Hash(altered); entry["size"] = altered.Length;
        }
        else if (property is "promptStyle" or "platform" or "cacheTypeK" or "cacheTypeV") manifest[property] = value;
        else if (property is "maskSpecialistLiterals" or "repack") manifest[property] = bool.Parse(value);
        else manifest[property] = int.Parse(value, System.Globalization.CultureInfo.InvariantCulture);
        await File.WriteAllTextAsync(original.ManifestPath, manifest.ToJsonString());
        var before = fixture.Transport.RequestCount;

        var repaired = await installer.InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest);

        repaired.DirectoryPath.ShouldNotBe(original.DirectoryPath);
        fixture.Transport.RequestCount.ShouldBeGreaterThan(before);
        var options = LlamaCleanupOptions.LoadManifest(repaired.ManifestPath);
        options.PromptStyle.ShouldBe(CleanupPromptStyle.QuillChatMl);
        options.Threads.ShouldBe(4); options.ContextSize.ShouldBe(8192); options.MaxOutputTokens.ShouldBe(2048);
        options.GpuLayers.ShouldBe(0); options.StartupTimeout.ShouldBe(TimeSpan.FromSeconds(60)); options.IdleTimeout.ShouldBe(TimeSpan.FromSeconds(60));
        File.ReadAllText(Path.Combine(repaired.DirectoryPath, "licenses", "model-LICENSE.txt")).ShouldBe("model license");
        File.ReadAllText(Path.Combine(repaired.DirectoryPath, "licenses", "model", "base-LICENSE.txt")).ShouldBe("base model license");
    }

    [Theory]
    [InlineData("../outside.dll", false)]
    [InlineData("/absolute.dll", false)]
    [InlineData("folder/../../outside.dll", false)]
    [InlineData("folder/file.dll:stream", false)]
    [InlineData("folder/CON.txt", false)]
    [InlineData("folder/link.dll", true)]
    public async Task Verified_archives_still_reject_unsafe_paths_and_links(string path, bool link)
    {
        using var fixture = new Fixture(path, link);
        await Should.ThrowAsync<InvalidDataException>(async () =>
            await fixture.Installer().InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest));
        fixture.StagingDirectories.ShouldBeEmpty();
        Directory.GetFiles(fixture.Root, "*", SearchOption.AllDirectories).ShouldBeEmpty();
    }

    [Fact]
    public async Task Runtime_archive_and_executable_are_verified_independently()
    {
        using var fixture = new Fixture(wrongExecutableHash: true);
        var error = await Should.ThrowAsync<InvalidDataException>(async () =>
            await fixture.Installer().InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest));
        error.Message.ShouldContain("executable");
        fixture.StagingDirectories.ShouldBeEmpty();
    }

    [Fact]
    public async Task Invalid_sources_fail_before_any_network_request()
    {
        using var fixture = new Fixture();
        var manifest = await File.ReadAllTextAsync(fixture.ModelManifest);
        await File.WriteAllTextAsync(fixture.ModelManifest, manifest.Replace("https://assets.example/model", "http://assets.example/model", StringComparison.Ordinal));
        await Should.ThrowAsync<InvalidDataException>(async () =>
            await fixture.Installer().InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest));
        fixture.Transport.RequestCount.ShouldBe(0);
    }

    [Fact]
    public async Task Duplicate_archive_paths_are_rejected_case_insensitively()
    {
        using var fixture = new Fixture("runtime/DEPENDENCY.dll");
        await Should.ThrowAsync<InvalidDataException>(async () =>
            await fixture.Installer().InstallAsync(fixture.ModelManifest, fixture.RuntimeManifest));
        fixture.StagingDirectories.ShouldBeEmpty();
    }

    private static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    private sealed class RecordedProgress(Action<CleanupAssetProgress>? callback = null) : IProgress<CleanupAssetProgress>
    {
        internal List<CleanupAssetProgress> Values { get; } = [];
        public void Report(CleanupAssetProgress value) { Values.Add(value); callback?.Invoke(value); }
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = Path.Combine(Path.GetTempPath(), "freehand-cleanup-download-" + Guid.NewGuid().ToString("N"));
        private readonly HttpClient _http;
        private readonly Dictionary<string, object> _model;
        internal Transport Transport { get; } = new();
        internal string Root => Path.Combine(_directory, "owned-models");
        internal string ModelManifest => Path.Combine(_directory, "selected.json");
        internal string RuntimeManifest => Path.Combine(_directory, "runtime.json");
        internal byte[] ModelBytes { get; private set; } = Encoding.UTF8.GetBytes("fixture model");
        internal string[] StagingDirectories => Directory.Exists(Root) ? Directory.GetDirectories(Root, ".cleanup-install-*") : [];

        internal Fixture(string? unsafeEntry = null, bool link = false, bool wrongExecutableHash = false)
        {
            Directory.CreateDirectory(_directory);
            var server = Encoding.UTF8.GetBytes("fixture server");
            var archive = Archive(server, unsafeEntry, link);
            var modelLicense = Encoding.UTF8.GetBytes("model license");
            var runtimeLicense = Encoding.UTF8.GetBytes("runtime license");
            var notice = Encoding.UTF8.GetBytes("base model license");
            Transport.Payloads["/model"] = ModelBytes;
            Transport.Payloads["/model-license"] = modelLicense;
            Transport.Payloads["/runtime-license"] = runtimeLicense;
            Transport.Payloads["/notice"] = notice;
            Transport.Payloads["/runtime.zip"] = archive;
            _model = new Dictionary<string, object>(StringComparer.Ordinal)
            {
                ["SchemaVersion"] = 1, ["ModelId"] = "fixture-cleanup", ["PromptStyle"] = "QuillChatMl",
                ["Model"] = ModelArtifact(), ["ModelLicense"] = Artifact("model-license", modelLicense),
                ["RuntimeLicense"] = Artifact("runtime-license", runtimeLicense),
                ["ModelNotices"] = new[] { new { Name = "base-LICENSE.txt", Source = "https://assets.example/notice", Size = notice.Length, Sha256 = Hash(notice) } },
                ["Inference"] = new { Threads = 4, ContextSize = 8192, MaxOutputTokens = 2048, GpuLayers = 0, StartupTimeoutSeconds = 60, IdleTimeoutSeconds = 60 },
            };
            File.WriteAllText(ModelManifest, JsonSerializer.Serialize(_model));
            File.WriteAllText(RuntimeManifest, JsonSerializer.Serialize(new
            {
                SchemaVersion = 1, SourceCommit = new string('b', 40), Artifacts = new[]
                {
                    new { Platform = "win-x64-cpu", Source = "https://assets.example/runtime.zip", ArchiveSha256 = Hash(archive),
                        ArchiveSize = archive.Length, Executable = "llama-server.exe", ExecutableSha256 = wrongExecutableHash ? new string('0', 64) : Hash(server) },
                },
            }));
            _http = new HttpClient(Transport);
        }

        internal CleanupAssetInstaller Installer() => new(_http, Root);
        internal void SetRuntimePlatform(string platform, bool includeArtifact = true)
        {
            _model["RuntimePlatform"] = platform;
            File.WriteAllText(ModelManifest, JsonSerializer.Serialize(_model));
            if (!includeArtifact) return;
            var runtime = System.Text.Json.Nodes.JsonNode.Parse(File.ReadAllText(RuntimeManifest))!;
            var original = runtime["Artifacts"]![0]!;
            var selected = original.DeepClone();
            selected["Platform"] = platform;
            runtime["Artifacts"]!.AsArray().Add(selected);
            // Only the explicitly selected row has the correct executable pin.
            original["ExecutableSha256"] = new string('0', 64);
            File.WriteAllText(RuntimeManifest, runtime.ToJsonString());
        }
        internal void SetInference(Dictionary<string, object> overrides)
        {
            var settings = new Dictionary<string, object>(StringComparer.Ordinal)
            {
                ["Threads"] = 4, ["ContextSize"] = 8192, ["MaxOutputTokens"] = 2048, ["GpuLayers"] = 0,
                ["StartupTimeoutSeconds"] = 60, ["IdleTimeoutSeconds"] = 60,
            };
            foreach (var setting in overrides) settings[setting.Key] = setting.Value;
            _model["Inference"] = settings;
            _model["PromptStyle"] = "S1Mini";
            File.WriteAllText(ModelManifest, JsonSerializer.Serialize(_model));
        }
        internal void SetModel(byte[] bytes)
        {
            ModelBytes = bytes; Transport.Payloads["/model"] = bytes;
            _model["Model"] = ModelArtifact(); File.WriteAllText(ModelManifest, JsonSerializer.Serialize(_model));
        }
        private object ModelArtifact() => new { Source = "https://assets.example/model", Revision = new string('a', 40), Sha256 = Hash(ModelBytes), Size = ModelBytes.Length };
        private static object Artifact(string path, byte[] bytes) => new { Source = "https://assets.example/" + path, Sha256 = Hash(bytes), Size = bytes.Length };
        private static byte[] Archive(byte[] server, string? unsafeEntry, bool link)
        {
            using var bytes = new MemoryStream();
            using (var archive = new ZipArchive(bytes, ZipArchiveMode.Create, leaveOpen: true))
            {
                Write("runtime/llama-server.exe", server);
                Write("runtime/dependency.dll", Encoding.UTF8.GetBytes("fixture DLL"));
                Write("runtime/LICENSE.txt", Encoding.UTF8.GetBytes("bundled runtime notice"));
                if (unsafeEntry is not null)
                {
                    var entry = Write(unsafeEntry, Encoding.UTF8.GetBytes("unsafe"));
                    if (link) entry.ExternalAttributes = 0xA1FF << 16;
                }
                ZipArchiveEntry Write(string name, byte[] content)
                {
                    var entry = archive.CreateEntry(name);
                    using var output = entry.Open(); output.Write(content); return entry;
                }
            }
            return bytes.ToArray();
        }
        public void Dispose() { _http.Dispose(); Directory.Delete(_directory, recursive: true); }
    }

    private sealed class Transport : HttpMessageHandler
    {
        internal Dictionary<string, byte[]> Payloads { get; } = new(StringComparer.Ordinal);
        internal int RequestCount { get; private set; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested(); RequestCount++;
            request.RequestUri!.Scheme.ShouldBe("https");
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
                { Content = new ByteArrayContent(Payloads[request.RequestUri.AbsolutePath]), RequestMessage = request });
        }
    }
}

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
    [InlineData("threads", "8")]
    [InlineData("contextSize", "4096")]
    [InlineData("maxOutputTokens", "1024")]
    [InlineData("gpuLayers", "1")]
    [InlineData("startupTimeoutSeconds", "90")]
    [InlineData("idleTimeoutSeconds", "0")]
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
        else if (property == "promptStyle") manifest[property] = value;
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

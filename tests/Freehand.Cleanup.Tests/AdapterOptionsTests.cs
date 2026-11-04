using System.Text.Json;
using Freehand.Abstractions;
using Shouldly;
using Xunit;

namespace Freehand.Cleanup.Tests;

public sealed class AdapterOptionsTests
{
    [Fact]
    public async Task Existing_options_and_manifests_leave_adapters_disabled()
    {
        using var fixture = new Fixture();
        var options = fixture.Options();
        await using var provider = new LlamaTranscriptPostProcessor(options, new UnusedLauncher());

        options.AdapterPath.ShouldBeNull();
        options.AdapterSha256.ShouldBeNull();
        options.AdapterScale.ShouldBe(1d);
        var manifest = fixture.Load();
        manifest.AdapterPath.ShouldBeNull();
        manifest.AdapterSha256.ShouldBeNull();
        manifest.AdapterScale.ShouldBe(1d);
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Direct_options_require_adapter_path_and_hash_together(bool hasPath)
    {
        using var fixture = new Fixture();
        var options = fixture.Options() with
        {
            AdapterPath = hasPath ? fixture.AdapterPath : null,
            AdapterSha256 = hasPath ? null : fixture.AdapterHash,
        };

        Should.Throw<ArgumentException>(() => new LlamaTranscriptPostProcessor(options, new UnusedLauncher()));
    }

    [Theory]
    [InlineData("")]
    [InlineData(" ")]
    [InlineData("adapter.gguf")]
    [InlineData("adapters/cleanup.gguf")]
    public void Direct_options_require_an_absolute_nonempty_adapter_path(string path)
    {
        using var fixture = new Fixture();
        var options = fixture.Options() with { AdapterPath = path, AdapterSha256 = fixture.AdapterHash };

        Should.Throw<ArgumentException>(() => new LlamaTranscriptPostProcessor(options, new UnusedLauncher()));
    }

    [Theory]
    [InlineData(63, 'a')]
    [InlineData(65, 'a')]
    [InlineData(64, 'g')]
    public void Adapter_hash_must_be_a_complete_sha256_pin(int length, char character)
    {
        using var fixture = new Fixture();
        var invalidHash = new string(character, length);
        var options = fixture.Options() with { AdapterPath = fixture.AdapterPath, AdapterSha256 = invalidHash };

        Should.Throw<ArgumentException>(() => new LlamaTranscriptPostProcessor(options, new UnusedLauncher()));
        Should.Throw<ArgumentException>(() => fixture.Load(new()
        {
            ["adapterPath"] = "adapters/cleanup.gguf", ["adapterSha256"] = invalidHash,
        }));
    }

    [Theory]
    [InlineData(0d)]
    [InlineData(-1d)]
    [InlineData(16.001d)]
    [InlineData(double.NaN)]
    [InlineData(double.NegativeInfinity)]
    [InlineData(double.PositiveInfinity)]
    public void Direct_options_reject_nonfinite_or_out_of_range_adapter_scale(double scale)
    {
        using var fixture = new Fixture();
        var options = fixture.Options() with
        {
            AdapterPath = fixture.AdapterPath, AdapterSha256 = fixture.AdapterHash, AdapterScale = scale,
        };

        Should.Throw<ArgumentException>(() => new LlamaTranscriptPostProcessor(options, new UnusedLauncher()));
    }

    [Theory]
    [InlineData(.5d)]
    [InlineData(2d)]
    public void Direct_options_cannot_set_a_nondefault_scale_without_an_adapter(double scale)
    {
        using var fixture = new Fixture();
        var options = fixture.Options() with { AdapterScale = scale };

        Should.Throw<ArgumentException>(() => new LlamaTranscriptPostProcessor(options, new UnusedLauncher()));
    }

    [Theory]
    [InlineData(1d)]
    [InlineData(.5d)]
    [InlineData(16d)]
    public void All_adapter_paths_reject_the_native_csv_separator(double scale)
    {
        using var fixture = new Fixture();
        var options = fixture.Options() with
        {
            AdapterPath = Path.Combine(fixture.BundleDirectory, "adapter,other.gguf"),
            AdapterSha256 = fixture.AdapterHash, AdapterScale = scale,
        };

        Should.Throw<ArgumentException>(() => new LlamaTranscriptPostProcessor(options, new UnusedLauncher()));
        Should.Throw<ArgumentException>(() => fixture.Load(new()
        {
            ["adapterPath"] = "adapter,other.gguf", ["adapterSha256"] = fixture.AdapterHash, ["adapterScale"] = scale,
        }));
    }

    [Theory]
    [InlineData(.5d)]
    [InlineData(16d)]
    public void Nonunit_adapter_paths_reject_windows_drive_colons_for_the_pinned_parser(double scale)
    {
        using var fixture = new Fixture();
        var path = Path.GetFullPath(@"C:\models\adapter.gguf", fixture.BundleDirectory);
        var options = fixture.Options() with
        {
            AdapterPath = path, AdapterSha256 = fixture.AdapterHash, AdapterScale = scale,
        };

        Should.Throw<ArgumentException>(() => new LlamaTranscriptPostProcessor(options, new UnusedLauncher()))
            .ParamName.ShouldBe(nameof(LlamaCleanupOptions.AdapterPath));
        Should.Throw<ArgumentException>(() => fixture.Load(new()
        {
            ["adapterPath"] = path, ["adapterSha256"] = fixture.AdapterHash, ["adapterScale"] = scale,
        })).ParamName.ShouldBe(nameof(LlamaCleanupOptions.AdapterPath));
    }

    [Fact]
    public async Task Unit_adapter_scale_preserves_windows_drive_colons()
    {
        using var fixture = new Fixture();
        var path = Path.GetFullPath(@"C:\models\adapter.gguf", fixture.BundleDirectory);
        var options = fixture.Options() with { AdapterPath = path, AdapterSha256 = fixture.AdapterHash };

        await using var provider = new LlamaTranscriptPostProcessor(options, new UnusedLauncher());

        options.AdapterPath.ShouldBe(path);
        options.AdapterScale.ShouldBe(1d);
    }

    [Theory]
    [InlineData(.125d)]
    [InlineData(1d)]
    [InlineData(16d)]
    public async Task Direct_options_allow_a_pinned_absolute_adapter_without_a_bundle_inventory(double scale)
    {
        using var fixture = new Fixture();
        var options = fixture.Options() with
        {
            AdapterPath = fixture.AdapterPath, AdapterSha256 = fixture.AdapterHash, AdapterScale = scale,
        };

        if (scale != 1 && fixture.AdapterPath.Contains(':'))
        {
            Should.Throw<ArgumentException>(() => new LlamaTranscriptPostProcessor(options, new UnusedLauncher()))
                .ParamName.ShouldBe(nameof(LlamaCleanupOptions.AdapterPath));
            return;
        }

        await using var provider = new LlamaTranscriptPostProcessor(options, new UnusedLauncher());

        options.Artifacts.ShouldBeEmpty();
    }

    [Theory]
    [InlineData("adapters/cleanup.gguf")]
    [InlineData("adapters\\cleanup.gguf")]
    public void Manifest_resolves_safe_relative_adapter_paths_and_defaults_the_scale(string relative)
    {
        using var fixture = new Fixture();
        var options = fixture.Load(new()
        {
            ["adapterPath"] = relative, ["adapterSha256"] = fixture.AdapterHash,
        });

        options.AdapterPath.ShouldBe(fixture.AdapterPath);
        options.AdapterSha256.ShouldBe(fixture.AdapterHash);
        options.AdapterScale.ShouldBe(1d);
    }

    [Fact]
    public void Unbundled_manifest_allows_an_absolute_adapter_path_and_explicit_unit_scale()
    {
        using var fixture = new Fixture();
        var options = fixture.Load(new()
        {
            ["adapterPath"] = fixture.OutsideAdapterPath, ["adapterSha256"] = fixture.AdapterHash,
            ["adapterScale"] = 1d,
        });

        options.AdapterPath.ShouldBe(fixture.OutsideAdapterPath);
        options.AdapterScale.ShouldBe(1d);
        options.Artifacts.ShouldBeEmpty();
    }

    [Theory]
    [InlineData("../outside.gguf")]
    [InlineData("adapters/../../outside.gguf")]
    [InlineData("adapters\\..\\cleanup.gguf")]
    [InlineData("./adapters/cleanup.gguf")]
    [InlineData("adapters//cleanup.gguf")]
    [InlineData("adapters/cleanup.gguf/")]
    [InlineData("adapters/cleanup.gguf:stream")]
    [InlineData("C:cleanup.gguf")]
    public void Manifest_rejects_traversing_or_ambiguous_relative_adapter_paths(string path)
    {
        using var fixture = new Fixture();

        Should.Throw<InvalidDataException>(() => fixture.Load(new()
        {
            ["adapterPath"] = path, ["adapterSha256"] = fixture.AdapterHash,
        }));
    }

    [Theory]
    [InlineData(true)]
    [InlineData(false)]
    public void Manifest_requires_adapter_path_and_hash_together(bool hasPath)
    {
        using var fixture = new Fixture();
        var values = new Dictionary<string, object?>
        {
            [hasPath ? "adapterPath" : "adapterSha256"] = hasPath ? "adapters/cleanup.gguf" : fixture.AdapterHash,
        };

        Should.Throw<ArgumentException>(() => fixture.Load(values));
    }

    [Theory]
    [InlineData("adapterPath", null)]
    [InlineData("adapterPath", "")]
    [InlineData("adapterPath", " ")]
    [InlineData("adapterPath", 7)]
    [InlineData("adapterPath", true)]
    [InlineData("adapterSha256", null)]
    [InlineData("adapterSha256", "")]
    [InlineData("adapterSha256", " ")]
    [InlineData("adapterSha256", 7)]
    [InlineData("adapterSha256", false)]
    [InlineData("adapterScale", null)]
    [InlineData("adapterScale", "1")]
    [InlineData("adapterScale", true)]
    public void Manifest_rejects_wrong_or_empty_adapter_field_values(string name, object? value)
    {
        using var fixture = new Fixture();

        Should.Throw<InvalidDataException>(() => fixture.Load(new()
        {
            ["adapterPath"] = "adapters/cleanup.gguf", ["adapterSha256"] = fixture.AdapterHash,
            [name] = value,
        }));
    }

    [Theory]
    [InlineData(0d)]
    [InlineData(-.5d)]
    [InlineData(16.001d)]
    public void Manifest_rejects_out_of_range_adapter_scales(double scale)
    {
        using var fixture = new Fixture();

        Should.Throw<ArgumentException>(() => fixture.Load(new()
        {
            ["adapterPath"] = "adapters/cleanup.gguf", ["adapterSha256"] = fixture.AdapterHash,
            ["adapterScale"] = scale,
        }));
    }

    [Theory]
    [InlineData("1e400")]
    [InlineData("-1e400")]
    public void Manifest_rejects_numeric_adapter_scales_that_overflow_a_finite_double(string number)
    {
        using var fixture = new Fixture();
        using var document = JsonDocument.Parse(number);

        Should.Throw<ArgumentException>(() => fixture.Load(new()
        {
            ["adapterPath"] = "adapters/cleanup.gguf", ["adapterSha256"] = fixture.AdapterHash,
            ["adapterScale"] = document.RootElement,
        }));
    }

    [Theory]
    [InlineData(.5d)]
    [InlineData(1d)]
    public void Manifest_rejects_even_a_default_explicit_scale_without_an_adapter(double scale)
    {
        using var fixture = new Fixture();

        Should.Throw<InvalidDataException>(() => fixture.Load(new() { ["adapterScale"] = scale }));
    }

    [Fact]
    public void Manifest_requires_the_configured_adapter_file_to_exist()
    {
        using var fixture = new Fixture();
        File.Delete(fixture.AdapterPath);

        Should.Throw<FileNotFoundException>(() => fixture.Load(new()
        {
            ["adapterPath"] = "adapters/cleanup.gguf", ["adapterSha256"] = fixture.AdapterHash,
        })).FileName.ShouldBe(fixture.AdapterPath);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Bundle_inventory_requires_the_adapter_with_its_configured_hash(bool includeWrongHash)
    {
        using var fixture = new Fixture();
        var files = fixture.Inventory();
        if (includeWrongHash)
            files.Add(new { path = "adapters/cleanup.gguf", sha256 = new string('d', 64) });

        Should.Throw<ArgumentException>(() => fixture.Load(new()
        {
            ["adapterPath"] = "adapters/cleanup.gguf", ["adapterSha256"] = fixture.AdapterHash,
            ["files"] = files,
        }));
    }

    [Fact]
    public void Bundle_inventory_accepts_a_pinned_adapter_and_preserves_its_scale()
    {
        using var fixture = new Fixture();
        var files = fixture.Inventory();
        files.Add(new { path = "adapters/cleanup.gguf", sha256 = fixture.AdapterHash });
        var scale = fixture.AdapterPath.Contains(':') ? 1d : 16d;

        var options = fixture.Load(new()
        {
            ["adapterPath"] = "adapters/cleanup.gguf", ["adapterSha256"] = fixture.AdapterHash,
            ["adapterScale"] = scale, ["files"] = files,
        });

        options.BundleDirectory.ShouldBe(fixture.BundleDirectory);
        options.Artifacts.Single(file => file.Path == fixture.AdapterPath).Sha256.ShouldBe(fixture.AdapterHash);
        options.AdapterScale.ShouldBe(scale);
    }

    [Fact]
    public void Bundle_inventory_rejects_an_absolute_adapter_outside_its_directory()
    {
        using var fixture = new Fixture();

        Should.Throw<ArgumentException>(() => fixture.Load(new()
        {
            ["adapterPath"] = fixture.OutsideAdapterPath, ["adapterSha256"] = fixture.AdapterHash,
            ["files"] = fixture.Inventory(),
        }));
    }

    [Fact]
    public void Case_sensitive_hosts_cannot_substitute_an_unverified_adapter_through_windows_path_matching()
    {
        if (OperatingSystem.IsWindows()) return;
        using var fixture = new Fixture();
        var alternate = Path.Combine(Path.GetDirectoryName(fixture.AdapterPath)!, "CLEANUP.gguf");
        File.WriteAllText(alternate, "distinct adapter outside the verified inventory");
        var files = fixture.Inventory();
        files.Add(new { path = "adapters/cleanup.gguf", sha256 = fixture.AdapterHash });

        Should.Throw<ArgumentException>(() => fixture.Load(new()
        {
            ["adapterPath"] = alternate, ["adapterSha256"] = fixture.AdapterHash, ["files"] = files,
        }));
    }

    private sealed class UnusedLauncher : ICleanupWorkerLauncher
    {
        public IWorkerProcess Launch(CleanupWorkerStartInfo startInfo) =>
            throw new InvalidOperationException("Options validation must not launch a worker.");
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = Path.Combine(Path.GetTempPath(), "freehand-cleanup-adapter-" + Guid.NewGuid().ToString("N"));
        public string BundleDirectory => Path.Combine(_directory, "bundle");
        public string ManifestPath => Path.Combine(BundleDirectory, "cleanup-manifest.json");
        public string RuntimePath => Path.Combine(BundleDirectory, "runtime.exe");
        public string ModelPath => Path.Combine(BundleDirectory, "model.gguf");
        public string AdapterPath => Path.Combine(BundleDirectory, "adapters", "cleanup.gguf");
        public string OutsideAdapterPath => Path.Combine(_directory, "outside.gguf");
        public string RuntimeHash { get; } = new('a', 64);
        public string ModelHash { get; } = new('b', 64);
        public string AdapterHash { get; } = new('c', 64);

        public Fixture()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(AdapterPath)!);
            File.WriteAllText(RuntimePath, "fixture runtime");
            File.WriteAllText(ModelPath, "fixture model");
            File.WriteAllText(AdapterPath, "fixture adapter");
            File.WriteAllText(OutsideAdapterPath, "fixture adapter");
        }

        public LlamaCleanupOptions Options() => new()
        {
            RuntimePath = RuntimePath, RuntimeSha256 = RuntimeHash,
            ModelPath = ModelPath, ModelSha256 = ModelHash,
            ModelId = "pinned-model", PromptStyle = CleanupPromptStyle.QuillChatMl,
        };

        public List<object> Inventory() =>
        [
            new { path = "runtime.exe", sha256 = RuntimeHash },
            new { path = "model.gguf", sha256 = ModelHash },
        ];

        public LlamaCleanupOptions Load(Dictionary<string, object?>? values = null)
        {
            values ??= [];
            values["runtimePath"] = "runtime.exe"; values["runtimeSha256"] = RuntimeHash;
            values["modelPath"] = "model.gguf"; values["modelSha256"] = ModelHash;
            values["modelId"] = "pinned-model"; values["promptStyle"] = "QuillChatMl";
            File.WriteAllText(ManifestPath, JsonSerializer.Serialize(values));
            return LlamaCleanupOptions.LoadManifest(ManifestPath);
        }

        public void Dispose() => Directory.Delete(_directory, true);
    }
}

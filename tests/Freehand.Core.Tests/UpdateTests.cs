using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Freehand.Abstractions;
using Freehand.Core.Updates;
using Xunit;

namespace Freehand.CoreTests;

public sealed class UpdateTests
{
    [Theory]
    [InlineData("1.0.0", false, false, false)]
    [InlineData("0.9.0", false, false, false)]
    [InlineData("1.0.1", true, false, false)]
    [InlineData("1.0.1", false, true, false)]
    [InlineData("1.0.1", false, false, true)]
    [InlineData("1.0.1-preview.1", false, false, false)]
    [InlineData("01.0.1", false, false, false)]
    public async Task Discovery_offers_only_newer_complete_stable_releases(string version, bool draft, bool prerelease, bool expected)
    {
        using var http = Client(_ => Json(Release(version, draft, prerelease)));
        var package = await new GitHubUpdateSource(http).FindAsync(new Version(1, 0, 0), CancellationToken.None);
        Assert.Equal(expected, package is not null);
    }

    [Fact]
    public async Task Missing_or_foreign_release_assets_are_rejected()
    {
        foreach (var url in new[] { "https://example.com/installer.exe", "https://github.com/another/repo/releases/download/v1.0.1/installer.exe", "http://github.com/samfarls55/freehand/installer.exe" })
        {
            using var http = Client(_ => Json(Release("1.0.1", installerUrl: url)));
            await Assert.ThrowsAsync<InvalidDataException>(() => new GitHubUpdateSource(http).FindAsync(new Version(1, 0, 0), CancellationToken.None));
        }
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(true, false)]
    [InlineData(false, true)]
    public async Task Download_is_executable_only_after_size_and_hash_match(bool badHash, bool truncated)
    {
        using var directory = new TestDirectory();
        var bytes = Encoding.UTF8.GetBytes("installer fixture");
        var package = Package(bytes.Length);
        var hash = Convert.ToHexString(SHA256.HashData(badHash ? [1, 2, 3] : bytes));
        using var http = Client(request => request.RequestUri!.AbsolutePath.EndsWith(".sha256", StringComparison.Ordinal)
            ? new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(hash + "  " + package.FileName) }
            : new HttpResponseMessage(HttpStatusCode.OK) { Content = new ByteArrayContent(truncated ? bytes[..^1] : bytes) });
        var source = new GitHubUpdateSource(http);
        if (badHash || truncated)
        {
            await Assert.ThrowsAsync<InvalidDataException>(() => source.DownloadAsync(package, directory.Path, CancellationToken.None));
            Assert.Empty(Directory.EnumerateFiles(directory.Path));
        }
        else
        {
            var path = await source.DownloadAsync(package, directory.Path, CancellationToken.None);
            Assert.Equal(bytes, await File.ReadAllBytesAsync(path));
            Assert.Single(Directory.EnumerateFiles(directory.Path));
        }
    }

    [Fact]
    public async Task Failed_checks_recover_and_a_check_never_downloads_or_installs()
    {
        var source = new FakeSource { Failure = new HttpRequestException("offline") };
        var installer = new FakeInstaller();
        await using var service = Service(source, installer);
        await service.CheckAsync(); Assert.Equal(UpdatePhase.Failed, service.Snapshot.Phase);
        source.Failure = null;
        await service.CheckAsync(); Assert.Equal(UpdatePhase.Available, service.Snapshot.Phase);
        Assert.Equal(0, source.Downloads); Assert.Equal(0, installer.Calls);
        await service.InstallAsync(); Assert.Equal(0, installer.Calls);
        await service.DownloadAsync(); Assert.Equal(UpdatePhase.Ready, service.Snapshot.Phase);
        await service.CheckAsync(); Assert.Equal(UpdatePhase.Ready, service.Snapshot.Phase);
        installer.Result = 1;
        await service.InstallAsync(); Assert.Equal(UpdatePhase.Failed, service.Snapshot.Phase);
        Assert.Equal(1, installer.Calls);
    }

    [Fact]
    public async Task A_failed_download_never_reaches_the_installer()
    {
        var source = new FakeSource(); var installer = new FakeInstaller();
        await using var service = Service(source, installer);
        await service.CheckAsync(); source.Failure = new InvalidDataException("checksum");
        await service.DownloadAsync(); await service.InstallAsync();
        Assert.Equal(UpdatePhase.Failed, service.Snapshot.Phase); Assert.Equal(0, installer.Calls);
    }

    [Fact]
    public async Task Concurrent_checks_do_not_start_duplicate_requests()
    {
        var source = new BlockingSource();
        await using var service = new UpdateService(source, new FakeInstaller(), new Version(1, 0, 0), "unused", "unused", () => false);
        var first = service.CheckAsync();
        await service.CheckAsync(); await service.DownloadAsync();
        Assert.Equal(1, source.Calls);
        source.Complete.SetResult(null); await first;
        Assert.Equal(UpdatePhase.Current, service.Snapshot.Phase);
    }

    [Fact]
    public async Task Cancelled_download_removes_partial_files()
    {
        using var directory = new TestDirectory(); using var cancellation = new CancellationTokenSource();
        var package = Package(10);
        using var http = Client(request => request.RequestUri!.AbsolutePath.EndsWith(".sha256", StringComparison.Ordinal)
            ? new(HttpStatusCode.OK) { Content = new StringContent(new string('a', 64) + "  " + package.FileName) }
            : new(HttpStatusCode.OK) { Content = new StreamContent(new CancelledStream(cancellation)) });
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => new GitHubUpdateSource(http).DownloadAsync(package, directory.Path, cancellation.Token));
        Assert.Empty(Directory.EnumerateFiles(directory.Path));
    }

    [Fact]
    public async Task Shutdown_cancels_installer_wait_without_waiting_for_setup_to_finish()
    {
        var installer = new FakeInstaller { Wait = true };
        var service = Service(new FakeSource(), installer);
        await service.CheckAsync(); await service.DownloadAsync();
        var installing = service.InstallAsync();
        Assert.Equal(UpdatePhase.Installing, service.Snapshot.Phase);
        await service.DisposeAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(2));
        await installing;
        Assert.True(installer.WaitCancelled);
    }

    [Theory]
    [InlineData("1.2.3", true)]
    [InlineData("1.2", false)]
    [InlineData("1.2.3.4", false)]
    [InlineData("1.02.3", false)]
    [InlineData("1.2.65535", false)]
    [InlineData("1.2.3-preview", false)]
    public void Versions_are_canonical_and_orderable(string text, bool expected) => Assert.Equal(expected, UpdatePackage.TryParseVersion(text, out _));

    private static UpdateService Service(FakeSource source, FakeInstaller installer) => new(source, installer, new Version(1, 0, 0), "unused-installation", "unused-download", () => false);
    private static UpdatePackage Package(long size = 10) => new(new Version(1, 0, 1),
        new Uri("https://github.com/samfarls55/freehand/releases/download/v1.0.1/Freehand-1.0.1-win-x64-Setup.exe"),
        new Uri("https://github.com/samfarls55/freehand/releases/download/v1.0.1/Freehand-1.0.1-win-x64-Setup.exe.sha256"), size);
    private static string Release(string version, bool draft = false, bool prerelease = false, string? installerUrl = null)
    {
        var name = $"Freehand-{version}-win-x64-Setup.exe";
        var url = $"https://github.com/samfarls55/freehand/releases/download/v{version}/{name}";
        return JsonSerializer.Serialize(new { tag_name = "v" + version, draft, prerelease,
            assets = new[] { new { name, browser_download_url = installerUrl ?? url, size = 10 },
                new { name = name + ".sha256", browser_download_url = url + ".sha256", size = 100 } } });
    }
    private static HttpResponseMessage Json(string text) => new(HttpStatusCode.OK) { Content = new StringContent(text) };
    private static HttpClient Client(Func<HttpRequestMessage, HttpResponseMessage> respond) => new(new Handler(respond));
    private sealed class Handler(Func<HttpRequestMessage, HttpResponseMessage> respond) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => Task.FromResult(respond(request));
    }
    private sealed class FakeSource : IUpdateSource
    {
        public Exception? Failure { get; set; }
        public int Downloads { get; private set; }
        public Task<UpdatePackage?> FindAsync(Version currentVersion, CancellationToken cancellationToken) => Failure is { } error
            ? Task.FromException<UpdatePackage?>(error) : Task.FromResult<UpdatePackage?>(Package());
        public Task<string> DownloadAsync(UpdatePackage package, string directory, CancellationToken cancellationToken)
        { Downloads++; return Failure is { } error ? Task.FromException<string>(error) : Task.FromResult("verified.exe"); }
    }
    private sealed class BlockingSource : IUpdateSource
    {
        public int Calls { get; private set; }
        public TaskCompletionSource<UpdatePackage?> Complete { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Task<UpdatePackage?> FindAsync(Version currentVersion, CancellationToken cancellationToken) { Calls++; return Complete.Task.WaitAsync(cancellationToken); }
        public Task<string> DownloadAsync(UpdatePackage package, string directory, CancellationToken cancellationToken) => throw new InvalidOperationException();
    }
    private sealed class CancelledStream(CancellationTokenSource cancellation) : MemoryStream(new byte[10])
    {
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        { cancellation.Cancel(); return ValueTask.FromCanceled<int>(cancellation.Token); }
    }
    private sealed class FakeInstaller : IUpdateInstaller
    {
        public bool IsInstallationInProgress(string installationDirectory) => false;
        public int Calls { get; private set; }
        public int Result { get; set; }
        public bool Wait { get; init; }
        public bool WaitCancelled { get; private set; }
        public async Task<int> RunAsync(string installer, string installationDirectory, CancellationToken cancellationToken)
        {
            Calls++;
            if (Wait)
            {
                try { await Task.Delay(Timeout.Infinite, cancellationToken); }
                catch (OperationCanceledException) { WaitCancelled = true; throw; }
            }
            return Result;
        }
    }
    private sealed class TestDirectory : IDisposable
    {
        public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "freehand-update-" + Guid.NewGuid().ToString("N"));
        public TestDirectory() => Directory.CreateDirectory(Path);
        public void Dispose() => Directory.Delete(Path, recursive: true);
    }
}

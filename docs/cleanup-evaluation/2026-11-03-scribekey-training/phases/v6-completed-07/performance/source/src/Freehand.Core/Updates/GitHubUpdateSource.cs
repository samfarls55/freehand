using System.Net;
using System.Security.Cryptography;
using System.Text.Json;

namespace Freehand.Core.Updates;

/// <summary>Public GitHub Releases feed. No credentials or personal data are sent.</summary>
public sealed class GitHubUpdateSource(HttpClient client) : IUpdateSource
{
    private const string Repository = "samfarls55/freehand";
    private const long MaximumInstallerSize = 2L * 1024 * 1024 * 1024;

    /// <inheritdoc />
    public async Task<UpdatePackage?> FindAsync(Version currentVersion, CancellationToken cancellationToken)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, $"https://api.github.com/repos/{Repository}/releases/latest");
        request.Headers.UserAgent.ParseAdd("Freehand/" + currentVersion);
        request.Headers.Accept.ParseAdd("application/vnd.github+json");
        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        if (response.StatusCode == HttpStatusCode.NotFound) return null;
        response.EnsureSuccessStatusCode();
        using var document = JsonDocument.Parse(await ReadBoundedAsync(response.Content, 1024 * 1024, cancellationToken).ConfigureAwait(false));
        var release = document.RootElement;
        if (release.GetProperty("draft").GetBoolean() || release.GetProperty("prerelease").GetBoolean()) return null;
        var tag = release.GetProperty("tag_name").GetString() ?? "";
        if (!tag.StartsWith('v') || !UpdatePackage.TryParseVersion(tag[1..], out var version) || version <= currentVersion) return null;
        var name = $"Freehand-{version}-win-x64-Setup.exe";
        var installer = FindAsset(release, tag, name);
        var checksum = FindAsset(release, tag, name + ".sha256");
        var size = installer.GetProperty("size").GetInt64();
        if (size is <= 0 or > MaximumInstallerSize) throw new InvalidDataException("Invalid installer size.");
        return new UpdatePackage(version, new Uri(installer.GetProperty("browser_download_url").GetString()!),
            new Uri(checksum.GetProperty("browser_download_url").GetString()!), size);
    }

    private static JsonElement FindAsset(JsonElement release, string tag, string name)
    {
        var assets = release.GetProperty("assets").EnumerateArray().Where(a => a.GetProperty("name").GetString() == name).ToArray();
        var expected = $"https://github.com/{Repository}/releases/download/{tag}/{name}";
        if (assets.Length != 1 || assets[0].GetProperty("browser_download_url").GetString() != expected)
            throw new InvalidDataException("Release asset missing or outside the Freehand repository.");
        return assets[0];
    }

    /// <inheritdoc />
    public async Task<string> DownloadAsync(UpdatePackage package, string directory, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(package);
        // Validate again at the download boundary, including callers outside FindAsync.
        var expectedUrl = $"https://github.com/{Repository}/releases/download/v{package.Version}/{package.FileName}";
        if (!UpdatePackage.TryParseVersion(package.Version.ToString(), out _) || package.Installer.AbsoluteUri != expectedUrl
            || package.Checksum.AbsoluteUri != expectedUrl + ".sha256" || package.Size is <= 0 or > MaximumInstallerSize)
            throw new InvalidDataException("Invalid update package.");
        using var checksumResponse = await client.GetAsync(package.Checksum, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
        checksumResponse.EnsureSuccessStatusCode();
        var checksum = await ReadBoundedAsync(checksumResponse.Content, 1024, cancellationToken).ConfigureAwait(false);
        var fields = checksum.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        if (fields.Length != 2 || fields[0].Length != 64 || fields[1] != package.FileName || !fields[0].All(char.IsAsciiHexDigit))
            throw new InvalidDataException("Invalid installer checksum.");
        var expected = Convert.FromHexString(fields[0]);
        Directory.CreateDirectory(directory);
        var destination = Path.Combine(directory, package.FileName);
        var partial = destination + "." + Guid.NewGuid().ToString("N") + ".partial";
        try
        {
            using var response = await client.GetAsync(package.Installer, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            if (response.Content.Headers.ContentLength is { } length && length != package.Size)
                throw new InvalidDataException("Installer size changed.");
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            await using (var input = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false))
            await using (var output = new FileStream(partial, FileMode.CreateNew, FileAccess.Write, FileShare.None, 65536, useAsync: true))
            {
                var buffer = new byte[65536]; long total = 0;
                int read;
                while ((read = await input.ReadAsync(buffer, cancellationToken).ConfigureAwait(false)) > 0)
                {
                    total += read;
                    if (total > package.Size) throw new InvalidDataException("Installer exceeds its published size.");
                    hash.AppendData(buffer, 0, read);
                    await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
                }
                if (total != package.Size || !CryptographicOperations.FixedTimeEquals(hash.GetHashAndReset(), expected))
                    throw new InvalidDataException("Installer checksum failed.");
            }
            cancellationToken.ThrowIfCancellationRequested();
            File.Move(partial, destination, overwrite: true);
            // This directory belongs only to update downloads. Keep one verified installer.
            foreach (var old in Directory.EnumerateFiles(directory, "Freehand-*-win-x64-Setup.exe"))
                if (!old.Equals(destination, StringComparison.OrdinalIgnoreCase)) TryDelete(old);
            return destination;
        }
        finally { TryDelete(partial); }
    }

    private static async Task<string> ReadBoundedAsync(HttpContent content, int limit, CancellationToken cancellationToken)
    {
        await using var input = await content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
        using var output = new MemoryStream();
        var buffer = new byte[8192]; int read;
        while ((read = await input.ReadAsync(buffer, cancellationToken).ConfigureAwait(false)) > 0)
        {
            if (output.Length + read > limit) throw new InvalidDataException("Update metadata is too large.");
            await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
        }
        return System.Text.Encoding.UTF8.GetString(output.GetBuffer(), 0, checked((int)output.Length)).TrimStart('\uFEFF');
    }
    private static void TryDelete(string path)
    {
        try { File.Delete(path); } catch (Exception e) when (e is IOException or UnauthorizedAccessException) { }
    }
}

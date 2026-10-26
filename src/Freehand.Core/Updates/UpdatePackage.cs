namespace Freehand.Core.Updates;

/// <summary>A complete Windows installer from a published release.</summary>
public sealed record UpdatePackage(Version Version, Uri Installer, Uri Checksum, long Size)
{
    /// <summary>The expected local filename.</summary>
    public string FileName => $"Freehand-{Version}-win-x64-Setup.exe";

    /// <summary>Accepts only canonical three-part release versions supported by Windows.</summary>
    public static bool TryParseVersion(string text, out Version version)
    {
        if (Version.TryParse(text, out var parsed) && parsed.Revision == -1 && parsed.Build >= 0
            && parsed.Major <= 65534 && parsed.Minor <= 65534 && parsed.Build <= 65534
            && parsed.ToString(3).Equals(text, StringComparison.Ordinal))
        { version = parsed; return true; }
        version = new Version(0, 0, 0); return false;
    }
}

/// <summary>Discovers and verifies releases without involving the speech worker.</summary>
public interface IUpdateSource
{
    /// <summary>Returns a newer published release, or null.</summary>
    Task<UpdatePackage?> FindAsync(Version currentVersion, CancellationToken cancellationToken);
    /// <summary>Returns an installer path only after size and SHA-256 verification.</summary>
    Task<string> DownloadAsync(UpdatePackage package, string directory, CancellationToken cancellationToken);
}

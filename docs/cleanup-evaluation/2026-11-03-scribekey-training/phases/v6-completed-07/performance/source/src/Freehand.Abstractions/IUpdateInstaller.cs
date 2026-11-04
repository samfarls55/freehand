namespace Freehand.Abstractions;

/// <summary>Runs a separate installer, which survives the app shutting down.</summary>
public interface IUpdateInstaller
{
    /// <summary>Prevents an interactive launch from locking files while setup verifies or restores them.</summary>
    bool IsInstallationInProgress(string installationDirectory);
    /// <summary>Waits for setup without terminating it when the caller exits.</summary>
    Task<int> RunAsync(string installer, string installationDirectory, CancellationToken cancellationToken);
}

using System.Diagnostics;
using Freehand.Abstractions;

namespace Freehand.Platform.Windows;

/// <summary>Starts setup outside the app's process lifetime.</summary>
public sealed class WindowsUpdateInstaller : IUpdateInstaller
{
    /// <inheritdoc />
    public bool IsInstallationInProgress(string installationDirectory)
    {
        var root = Path.TrimEndingDirectorySeparator(Path.GetFullPath(installationDirectory));
        var name = "Local\\FreehandSetup-" + Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(root.ToUpperInvariant())));
        using var mutex = new Mutex(false, name);
        var acquired = false;
        try { acquired = mutex.WaitOne(0); }
        catch (AbandonedMutexException) { acquired = true; }
        if (acquired) mutex.ReleaseMutex();
        return !acquired;
    }
    /// <inheritdoc />
    public async Task<int> RunAsync(string installer, string installationDirectory, CancellationToken cancellationToken)
    {
        var start = new ProcessStartInfo(installer)
        {
            UseShellExecute = false, CreateNoWindow = true, WindowStyle = ProcessWindowStyle.Hidden,
            WorkingDirectory = Path.GetTempPath(),
        };
        start.ArgumentList.Add("--update"); start.ArgumentList.Add("--directory"); start.ArgumentList.Add(installationDirectory);
        start.Environment.Remove("FREEHAND_DATA_DIRECTORY");
        using var process = Process.Start(start) ?? throw new IOException("Could not start Freehand setup.");
        // Cancelling the wait on app shutdown must never kill the installer.
        await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
        return process.ExitCode;
    }
}

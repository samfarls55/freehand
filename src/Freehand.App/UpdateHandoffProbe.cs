using System.Globalization;
using Freehand.Abstractions;

namespace Freehand.App;

/// <summary>Headless packaging verification using the real desktop shutdown signal and startup guard.</summary>
internal static class UpdateHandoffProbe
{
    internal static async Task<int> RunAsync(IDesktopIntegration? desktop)
    {
        var profile = Environment.GetEnvironmentVariable("FREEHAND_DATA_DIRECTORY");
        var installed = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Freehand");
        if (desktop is null || string.IsNullOrWhiteSpace(profile)
            || Path.TrimEndingDirectorySeparator(AppContext.BaseDirectory).Equals(installed, StringComparison.OrdinalIgnoreCase)) return 2;
        var stopped = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        desktop.ShutdownRequested += (_, _) => stopped.TrySetResult();
        desktop.StartNotifications();
        Directory.CreateDirectory(profile);
        await File.WriteAllTextAsync(Path.Combine(profile, "update-handoff.pid"),
            Environment.ProcessId.ToString(CultureInfo.InvariantCulture)).ConfigureAwait(false);
        // No capture, hooks, injection, UI, or login registration runs in this mode.
        using var deadline = new CancellationTokenSource(TimeSpan.FromMinutes(5));
        try { await stopped.Task.WaitAsync(deadline.Token).ConfigureAwait(false); return 0; }
        catch (OperationCanceledException) { return 1; }
    }
}

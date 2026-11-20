namespace Freehand.Abstractions;

/// <summary>A local cleanup worker executable with literal arguments and environment overrides.</summary>
/// <param name="ExecutablePath">The verified executable to start without a command shell.</param>
/// <param name="Arguments">Arguments added individually, without shell expansion.</param>
/// <param name="EnvironmentVariables">Per-process environment values; these can contain private authentication data.</param>
public sealed record CleanupWorkerStartInfo(string ExecutablePath, IReadOnlyList<string> Arguments,
    IReadOnlyDictionary<string, string> EnvironmentVariables);

/// <summary>Starts a hidden, app-owned local cleanup worker through the platform boundary.</summary>
public interface ICleanupWorkerLauncher
{
    /// <summary>Starts the worker and owns its process tree until disposal.</summary>
    IWorkerProcess Launch(CleanupWorkerStartInfo startInfo);
}

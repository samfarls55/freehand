namespace Freehand.Abstractions;

/// <summary>Records a keyboard combination while suspending dictation shortcuts.</summary>
public interface IHotkeyRecorder
{
    /// <summary>Reports held keys and completes when the user releases the combination.</summary>
    /// <returns>The recorded virtual keys, or null when recording is unavailable.</returns>
    Task<IReadOnlyList<int>?> RecordAsync(IProgress<IReadOnlyList<int>> progress, CancellationToken cancellationToken);
}
